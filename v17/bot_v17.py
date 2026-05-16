"""
HYDRA Trading Bot v17.3 - LONG-TERM ARCHITECTURE (STATE MACHINE)
Engineered with finite state machine: IDLE -> SCANNING -> BUYING -> IN_POSITION -> EXITING
"""
import time
import signal
import sys
import os
from enum import Enum, auto
from datetime import datetime
from typing import Optional, Dict

# Подключаем пути к общей папке shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'shared')))

from logger_setup import logger
from config import config
from exchange_utils import ExchangeManager
from database import TradeDatabase
from indicators_v17 import analyzer
from scanner_integration import ScannerIntegration, DynamicSymbolManager
from utils import safe_float, format_currency, format_percentage

class BotState(Enum):
    """Строгие архитектурные состояния конечного автомата бота"""
    IDLE = auto()
    SCANNING = auto()
    BUYING = auto()
    IN_POSITION = auto()
    EXITING = auto()

class TradingBot:
    def __init__(self):
        logger.info("Инициализация долгосрочной архитектуры HYDRA-NET v17.3...")
        self.config = config
        self.exchange = ExchangeManager()
        self.trade_db = TradeDatabase()
        
        root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.hot_symbols_file = os.path.join(root_path, "hot_symbols.txt")
        
        self.scanner_integration = ScannerIntegration(self.hot_symbols_file)
        self.symbol_manager = DynamicSymbolManager(
            base_symbols=self.config.get_symbols(),
            scanner_integration=self.scanner_integration
        )
 
        self.session_profit = 0.0
        self.price_history = {symbol: [0.0, time.time()] for symbol in self.config.get_symbols()}
 
        self.should_stop = False
        self.loop_counter = 0
        self.trading_config = self.config.get_trading_config()
        self.indicators_enabled = self.config.are_indicators_enabled()
        self.last_loss_time = 0.0
        
        # [Инженерия]: Инициализация State Machine
        self.state = BotState.IDLE
        self.state_data = {} # Сюда сохраняются параметры текущего состояния (ордера, цены, объемы)
 
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
 
    def _signal_handler(self, signum, frame):
        logger.info("Сигнал остановки получен, закрываемся...")
        self.should_stop = True
 
    def run(self) -> None:
        try:
            logger.info("HYDRA v17.3 STARTED | Конечный автомат (State Machine) активен.")
            self.exchange.load_markets()
 
            while not self.should_stop:
                try:
                    self.loop_counter += 1
                    
                    # === ДИСПЕТЧЕР КОНЕЧНОГО АВТОМАТА (STATE MACHINE) ===
                    if self.state == BotState.IDLE:
                        self._handle_idle_state()
                        
                    elif self.state == BotState.SCANNING:
                        self._handle_scanning_state()
                        
                    elif self.state == BotState.BUYING:
                        # Состояние обработки и подстраховки входа
                        pass # Управляется внутренней логикой _enter_trade
                        
                    elif self.state == BotState.IN_POSITION:
                        self._handle_in_position_state()
                        
                    elif self.state == BotState.EXITING:
                        # Состояние экстренной очистки ордеров
                        pass
 
                    # Сводные периодические задачи (раз в 5 минут)
                    if self.loop_counter % 300 == 0:
                        self.exchange.clear_caches()
                        stats = self.trade_db.get_session_stats()
                        logger.info(f"📊 Статистика сессии - Сделок: {stats.get('total_trades', 0)}, Профит: ${stats.get('total_profit', 0.0):.2f}")
 
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Ошибка в диспетчере автомата состояний: {e}", exc_info=True)
                    time.sleep(10)
        finally:
            logger.info("Бот остановлен.")
            
    def _handle_idle_state(self):
        """Состояние IDLE: Проверка рисков, времени суток и баланса перед сканированием"""
        if not self._check_risk_limits():
            time.sleep(10)
            return
            
        if not self._check_time_session():
            time.sleep(60)
            return
            
        if not self._check_balance():
            time.sleep(5)
            return
            
        # Если все проверки пройдены — переключаем автомат в режим активного сканирования рынка
        self.state = BotState.SCANNING

    def _handle_scanning_state(self):
        """Состояние SCANNING: Изолированный поиск сигналов по индикаторам"""
        self._scan_for_entries()
        # После успешного скана возвращаемся в IDLE для повторного круга проверок безопасности
        if self.state == BotState.SCANNING:
            self.state = BotState.IDLE

    def _handle_in_position_state(self):
        """Состояние IN_POSITION: Изолированный мониторинг открытого Тейк-Профита и Стоп-Лосса"""
        try:
            symbol = self.state_data['symbol']
            order_id = self.state_data['order_id']
            
            try:
                order = self.exchange.fetch_order(order_id, symbol)
            except Exception as order_err:
                if "last 500 orders" in str(order_err):
                    time.sleep(1.5)
                    balance = self.exchange.fetch_balance()
                    coin_name = symbol.split('/')
                    actual_qty = safe_float(balance['free'].get(coin_name, 0))
                    if actual_qty <= 0:
                        logger.info(f"💰 Тейк-Профит по {symbol} успешно исполнился на Bybit!")
                        self.state_data = {}
                        self.state = BotState.IDLE # Позиция закрыта, возвращаемся в начало
                    return
                raise order_err

            if order['status'] == 'closed':
                close_price = safe_float(order.get('price') or order.get('average', self.state_data['buy_price']))
                trade_profit = (close_price - self.state_data['buy_price']) * self.state_data['amount']
                self.session_profit += trade_profit
                self.trade_db.log_trade(symbol, "sell", self.state_data['amount'], close_price, confidence=0.0)
                logger.info(f" PROFIT TAKEN! {symbol} +${trade_profit:.2f}")
                self.state_data = {}
                self.state = BotState.IDLE
                return
 
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = safe_float(ticker['last'])
            change_percent = ((current_price - self.state_data['buy_price']) / self.state_data['buy_price']) * 100
            elapsed = time.time() - self.state_data['buy_time']
 
            print(f"📈 Мониторинг {symbol}: {change_percent:.2f}% | Время: {int(elapsed)}с [STATE: IN_POSITION]", end='\r')
 
            if change_percent <= -self.trading_config['panic_stop']:
                logger.warning(f"🚨 СРАБОТАЛ СТОП-ЛОСС для {symbol} ({change_percent:.2f}%)")
                self.last_loss_time = time.time()
                self._panic_sell()
                return
                
            if elapsed > self.trading_config['timeout_breakeven'] and not self.state_data['is_breakeven']:
                self._set_breakeven()
        except Exception as e:
            logger.error(f"Ошибка в обработчике состояния IN_POSITION: {e}")

    def _panic_sell(self) -> None:
        """Переключение в состояние EXITING и экстренная очистка ордеров"""
        self.state = BotState.EXITING
        try:
            symbol = self.state_data['symbol']
            try: self.exchange.cancel_order(self.state_data['order_id'], symbol)
            except: pass
            time.sleep(0.5)
            amount = float(self.exchange.exchange.amount_to_precision(symbol, self.state_data['amount']))
            market_order = self.exchange.create_market_sell_order(symbol, amount)
            time.sleep(1.0)
            executed_order = self.exchange.fetch_order(market_order['id'], symbol)
            real_close_price = safe_float(executed_order.get('average') or executed_order.get('price') or self.state_data['buy_price'] * 0.98)
            self.trade_db.log_trade(symbol, "sell_panic", amount, real_close_price, confidence=0.0)
            logger.warning(f"⚠️ Паник-селл завершен. Цена: {real_close_price}")
        except Exception as e:
            logger.error(f"Ошибка выполнения паник-селла в состоянии EXITING: {e}")
        finally:
            self.state_data = {}
            self.state = BotState.IDLE
 
    def _set_breakeven(self) -> None:
        try:
            symbol = self.state_data['symbol']
            self.exchange.cancel_order(self.state_data['order_id'], symbol)
            time.sleep(0.5)
            breakeven_price = float(self.exchange.exchange.price_to_precision(symbol, self.state_data['buy_price'] * 1.0022))
            amount = float(self.exchange.exchange.amount_to_precision(symbol, self.state_data['amount']))
            new_order = self.exchange.create_limit_sell_order(symbol, amount, breakeven_price)
            self.state_data['order_id'] = new_order['id']
            self.state_data['is_breakeven'] = True
        except Exception as e:
            logger.error(f"Ошибка перевода в безубыток: {e}")
            
    def _check_time_session(self) -> bool:
        if not self.trading_config.get('block_night_trading', False):
            return True
        current_hour = datetime.now().hour
        if 0 <= current_hour < 5:
            print(f"💤 Ночной защитный режим активен (Текущий час: {current_hour}). Ждем утра... ", end='\r')
            return False
        return True
            
    def _check_risk_limits(self) -> bool:
        try:
            cooldown_min = self.trading_config.get('cooldown_after_loss_minutes', 30)
            if time.time() - self.last_loss_time < (cooldown_min * 60):
                remaining = int((cooldown_min * 60) - (time.time() - self.last_loss_time))
                print(f"⏳ Режим Cooldown после убытка. До конца паузы: {remaining}с ", end='\r')
                return False
                
            stats = self.trade_db.get_session_stats()
            max_day_trades = self.trading_config.get('max_trades_per_day', 5)
            if stats.get('total_trades', 0) >= max_day_trades:
                print(f"🛑 Достигнут суточный лимит сделок ({max_day_trades}/{max_day_trades}). ", end='\r')
                return False
            return True
        except Exception:
            return True
            
    def _calculate_real_rvol(self, ohlcv) -> float:
        try:
            if len(ohlcv) < 20: return 1.0
            volumes = [safe_float(candle[5]) for candle in ohlcv]
            current_volume = volumes[-1]
            avg_volume = sum(volumes[-16:-1]) / 15
            if avg_volume <= 0: return 1.0
            return current_volume / avg_volume
        except:
            return 1.0
 
    def _check_balance(self) -> bool:
        try:
            balance = self.exchange.fetch_balance()
            usdt_free = safe_float(balance['free'].get('USDT', 0))
            total_equity = safe_float(balance['total'].get('USDT', usdt_free))
            if total_equity > 0 and total_equity < self.trading_config['stop_loss_total']:
                self.should_stop = True
                return False
            if usdt_free < self.trading_config['min_exchange_limit']:
                print(f"⌛ Доступно: {usdt_free:.2f}$ | Ожидание лимита... ", end='\r')
                return False
            return True
        except Exception as e:
            logger.error(f"Ошибка проверки баланса: {e}")
            return False
 
    def _scan_for_entries(self) -> None:
        try:
            symbols = self.symbol_manager.get_symbols(refresh_scanner=True)
            try: tickers = self.exchange.fetch_tickers(symbols)
            except Exception: return
 
            btc_trend = "neutral"
            try:
                btc_ohlcv_1h = self.exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
                if len(btc_ohlcv_1h) >= 2:
                    btc_open = safe_float(btc_ohlcv_1h[-2][1])
                    btc_close = safe_float(btc_ohlcv_1h[-1][4])
                    btc_change_1h = ((btc_close - btc_open) / btc_open) * 100
                    if btc_change_1h < -0.8: btc_trend = "bearish"
                    elif btc_change_1h > 0.8: btc_trend = "bullish"
            except: pass
            
            try:
                btc_ohlcv_15m = self.exchange.fetch_ohlcv('BTC/USDT', timeframe='5m', limit=4)
                if len(btc_ohlcv_15m) >= 3:
                    btc_high_15m = max([safe_float(c[2]) for c in btc_ohlcv_15m])
                    btc_current = safe_float(tickers.get('BTC/USDT', {}).get('ask') or btc_ohlcv_15m[-1][4])
                    btc_drop_15m = ((btc_current - btc_high_15m) / btc_high_15m) * 100
                    
                    crash_limit = self.trading_config.get('btc_crash_15m_limit', -2.0)
                    if btc_drop_15m <= crash_limit:
                        print(f"🛑 БЛОКИРОВКА: Биткоин падает на {btc_drop_15m:.2f}% за 15 мин! ", end='\r')
                        return
            except: pass
 
            print(f"Поиск сигналов... BTC 1h: [{btc_trend.upper()}] {time.strftime('%H:%M:%S')} ", end='\r')
 
            for symbol in symbols:
                if symbol not in tickers:
                    continue
                try:
                    price_now = safe_float(tickers[symbol]['ask'])
                    if symbol not in self.price_history or self.price_history[symbol] == 0.0:
                        self.price_history[symbol] = [price_now, time.time()]
                        continue
                    if price_now > self.price_history[symbol][0]:
                        self.price_history[symbol] = [price_now, time.time()]
                        continue
                    if time.time() - self.price_history[symbol][1] > 900:
                        self.price_history[symbol] = [price_now, time.time()]
                        continue
 
                    drop = ((self.price_history[symbol][0] - price_now) / self.price_history[symbol][0]) * 100
 
                    if drop >= self.trading_config['drop_threshold']:
                        try: ohlcv = self.exchange.fetch_ohlcv(symbol, '1m', limit=60)
                        except Exception: continue
                        
                        real_rvol = self._calculate_real_rvol(ohlcv)
                        min_rvol = self.trading_config.get('min_rvol_threshold', 1.5)
                        if real_rvol < min_rvol: continue
 
                        if self.indicators_enabled:
                            analysis = analyzer.complete_analysis(
                                ohlcv_data=ohlcv,
                                current_price=price_now,
                                market_volatility=1.0,
                                btc_trend=btc_trend
                            )
                            if analysis['status'] != 'ok': continue
                            
                            base_threshold = self.trading_config.get('min_confidence_threshold', 60.0)
                            if btc_trend == "bearish": base_threshold += 15.0
                                
                            if analysis['recommendation'] in ['STRONG_BUY', 'BUY'] and analysis.get('confidence_score', 0) >= base_threshold:
                                logger.info(f"🔥 СИГНАЛ ОДОБРЕН ПО {symbol} (RVOL: {real_rvol:.1f}x)")
                                logger.info(analysis['signal_analysis'])
                                self._enter_trade(symbol, price_now, tickers)
                                break
                        else:
                            self._enter_trade(symbol, price_now, tickers)
                            break
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Ошибка сканирования: {e}")
 
    def _enter_trade(self, symbol: str, price: float, tickers: Dict) -> None:
        """Вход в позицию со строгой сменой состояния автомата в BUYING -> IN_POSITION"""
        self.state = BotState.BUYING
        try:
            buy_price = safe_float(tickers[symbol]['ask'])
            slot_size = self.trading_config['slot_size']
            amount_target = float(self.exchange.exchange.amount_to_precision(symbol, slot_size / buy_price))
            
            logger.info(f"🛒 Лимитный ордер: {symbol} на {slot_size}$ по цене {buy_price}")
            order = self.exchange.create_limit_buy_order(symbol, amount_target, buy_price)
            
            filled = 0
            for _ in range(7):
                time.sleep(1)
                try:
                    check = self.exchange.fetch_order(order['id'], symbol)
                    filled = safe_float(check.get('filled', 0))
                    if check['status'] in ['closed', 'canceled']: break
                except: pass
            
            filled_usd = filled * buy_price
            if filled_usd >= 5.0:
                if filled < (amount_target * 0.95):
                    logger.warning(f"⚠️ ЧАСТИЧНЫЙ ФИЛЛ по {symbol}: {filled}/{amount_target} монет (${filled_usd:.2f})")
                
                time.sleep(2.5)
                balance = self.exchange.fetch_balance()
                actual_qty = safe_float(balance['free'].get(symbol.split('/')[0], 0))
                safe_amount = float(self.exchange.exchange.amount_to_precision(symbol, actual_qty if actual_qty > 0 else filled))
                
                take_profit_pct = self.trading_config.get('take_profit', 1.5)
                sell_price = float(self.exchange.exchange.price_to_precision(symbol, buy_price * (1 + (take_profit_pct / 100))))
                
                if sell_price <= buy_price: 
                    sell_price += self.exchange.exchange.markets[symbol]['precision']['price']

                logger.info(f" Выставление ордера продажи: {safe_amount} {symbol} по ${sell_price}")
                sell_order = self.exchange.create_limit_sell_order(symbol, safe_amount, sell_price)
                
                # Намертво фиксируем состояние сделки внутри стейт-машины
                self.state_data = {
                    'symbol': symbol,
                    'buy_price': buy_price,
                    'buy_time': time.time(),
                    'order_id': sell_order['id'],
                    'amount': safe_amount,
                    'is_breakeven': False
                }
                self.trade_db.log_trade(symbol, "buy", safe_amount, buy_price, confidence=100.0)
                logger.info(f"✅ State Machine -> IN_POSITION для {symbol}")
                self.state = BotState.IN_POSITION
            else:
                logger.warning(f"❌ Ордер не исполнился. Отмена и возврат в IDLE.")
                try: self.exchange.cancel_order(order['id'], symbol)
                except: pass
                self.state = BotState.IDLE
        except Exception as e:
            logger.error(f"❌ Ошибка входа: {e}")
            self.state = BotState.IDLE

def main():
    bot = TradingBot()
    bot.run()

if __name__ == "__main__":
    main()
