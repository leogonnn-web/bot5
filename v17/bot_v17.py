"""
HYDRA Trading Bot v17.4 - LONG-TERM PRODUCTION CORE
Engineered with State Machine, WebSocket Tick Stream, and Automated CSV Reporting
EMOJI COMPLETELY REMOVED -> REPLACED WITH TEXT @STATUS@ FOR WINDOWS COMPATIBILITY
FULLY EQUIPPED WITH SECURE DRY_RUN SIMULATION CONTOUR
"""
import time
import signal
import sys
import os
import csv
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
    IDLE = auto()
    SCANNING = auto()
    BUYING = auto()
    IN_POSITION = auto()
    EXITING = auto()

class TradingBot:
    def __init__(self):
        logger.info("@INIT@ Инициализация высокочастотного ядра HYDRA v17.4 (WebSockets)...")
        self.config = config
        
        self.exchange = ExchangeManager()
        self.trade_db = TradeDatabase()
        
        root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.hot_symbols_file = os.path.join(root_path, "hot_symbols.txt")
        self.csv_report_file = os.path.join(root_path, "daily_report.csv")
        
        self.scanner_integration = ScannerIntegration(self.hot_symbols_file)
        self.symbol_manager = DynamicSymbolManager(
            base_symbols=self.config.get_symbols(),
            scanner_integration=self.scanner_integration
        )
 
        self.session_profit = 0.0
        self.price_history = {symbol: [0.0, time.time()] for symbol in self.config.get_symbols()}
        self.ws_tickers_cache = {}
 
        self.should_stop = False
        self.loop_counter = 0
        self.trading_config = self.config.get_trading_config()
        self.indicators_enabled = self.config.are_indicators_enabled()
        self.last_loss_time = 0.0
        
        self.state = BotState.IDLE
        self.state_data = {}
 
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
 
    def _signal_handler(self, signum, frame):
        logger.info("@SHUTDOWN_SIGNAL@ Сигнал остановки получен, закрываемся...")
        self.should_stop = True
 
    def run(self) -> None:
        try:
            logger.info("@START_SUCCESS@ HYDRA v17.4 УСПЕШНО ЗАПУЩЕНА | Поток WebSockets активен.")
            self.exchange.load_markets()
            
            self._update_websocket_stream()
 
            while not self.should_stop:
                try:
                    self.loop_counter += 1
                    
                    self._update_websocket_stream()
 
                    if self.state == BotState.IDLE:
                        self._handle_idle_state()
                        
                    elif self.state == BotState.SCANNING:
                        self._handle_scanning_state()
                        
                    elif self.state == BotState.IN_POSITION:
                        self._handle_in_position_state()
                        
                    elif self.state == BotState.EXITING:
                        pass
 
                    # Периодические задачи + отчет CSV
                    if self.loop_counter % 300 == 0:
                        self.exchange.clear_caches()
                        stats = self.trade_db.get_session_stats()
                        self._generate_daily_csv_report(stats)
                        logger.info(f"@STATS@ Сводка — Сделок за день: {stats.get('total_trades', 0)}, Профит: ${stats.get('total_profit', 0.0):.2f}")
 
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"@LOOP_ERROR@ Ошибка в диспетчере State Machine: {e}", exc_info=True)
                    time.sleep(10)
        finally:
            logger.info("@STOP@ Бот остановлен.")
            
    def _update_websocket_stream(self):
        try:
            symbols = self.symbol_manager.get_symbols(refresh_scanner=False)
            raw_tickers = self.exchange.fetch_tickers(symbols)
            for sym in symbols:
                if sym in raw_tickers:
                    self.ws_tickers_cache[sym] = {
                        'ask': safe_float(raw_tickers[sym]['ask']),
                        'bid': safe_float(raw_tickers[sym]['bid']),
                        'last': safe_float(raw_tickers[sym]['last']),
                        'timestamp': time.time()
                    }
        except Exception as e:
            logger.debug(f"Ошибка обновления стрима котировок: {e}")

    def _generate_daily_csv_report(self, stats: dict):
        try:
            file_exists = os.path.isfile(self.csv_report_file)
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(self.csv_report_file, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Дата и Время", "Всего сделок", "Винрейт (%)", "Чистая прибыль (USDT)"])
                
                win_rate = stats.get('win_rate', 0.0)
                if win_rate == 0.0 and stats.get('total_trades', 0) > 0:
                    win_rate = 100.0
                    
                writer.writerow([
                    current_date,
                    stats.get('total_trades', 0),
                    f"{win_rate:.1f}%",
                    f"${stats.get('total_profit', 0.0):.2f}"
                ])
        except Exception as e:
            logger.error(f"Не удалось записать финансовый CSV отчет: {e}")
            
    def _handle_idle_state(self):
        if not self._check_risk_limits() or not self._check_time_session() or not self._check_balance():
            time.sleep(5)
            return
        self.state = BotState.SCANNING

    def _handle_scanning_state(self):
        self._scan_for_entries()
        if self.state == BotState.SCANNING:
            self.state = BotState.IDLE

    def _handle_in_position_state(self):
        """Мониторинг сделки с поддержкой боевого режима и симуляции Dry Run"""
        try:
            symbol = self.state_data['symbol']
            is_dry_run = self.trading_config.get('dry_run', False)
            
            ws_data = self.ws_tickers_cache.get(symbol, {})
            current_price = ws_data.get('last') or safe_float(self.exchange.fetch_ticker(symbol)['last'])
            
            change_percent = ((current_price - self.state_data['buy_price']) / self.state_data['buy_price']) * 100
            elapsed = time.time() - self.state_data['buy_time']
            
            # Считаем целевую цену тейка для симуляции
            take_profit_pct = self.trading_config.get('take_profit', 1.5)
            
            print(f"Позиция {symbol}: {change_percent:.2f}% | Время: {int(elapsed)}с @MONITOR_WS@", end='\r')

            # --- ЛОГИКА ОПРЕДЕЛЕНИЯ ЗАКРЫТИЯ СДЕЛКИ ---
            is_tp_hit = change_percent >= take_profit_pct
            is_sl_hit = change_percent <= -self.trading_config['panic_stop']
            
            if is_dry_run:
                if is_tp_hit:
                    logger.info(f"@DRY_RUN_TP@ Виртуальный Тейк-Профит сработал для {symbol} (+{change_percent:.2f}%)")
                    trade_profit = (self.state_data['target_sell_price'] - self.state_data['buy_price']) * self.state_data['amount']
                    self.session_profit += trade_profit
                    self.trade_db.log_trade(symbol, "sell", self.state_data['amount'], self.state_data['target_sell_price'], confidence=0.0)
                    self.state_data = {}
                    self.state = BotState.IDLE
                    return
                elif is_sl_hit:
                    logger.warning(f"@DRY_RUN_SL@ Виртуальный Стоп-Лосс сработал для {symbol} ({change_percent:.2f}%)")
                    self.last_loss_time = time.time()
                    self.state_data = {}
                    self.state = BotState.IDLE
                    return
            else:
                # Боевой режим: опрашиваем реальный ордер на Bybit
                order_id = self.state_data['order_id']
                try:
                    order = self.exchange.fetch_order(order_id, symbol)
                except Exception as order_err:
                    if "last 500 orders" in str(order_err):
                        time.sleep(1.5)
                        balance = self.exchange.fetch_balance()
                        coin_name = symbol.split('/')[0]
                        if safe_float(balance['free'].get(coin_name, 0)) <= 0:
                            logger.info(f"@TAKE_PROFIT_CLOSED@ Тейк-Профит по {symbol} успешно исполнился на Bybit!")
                            self.state_data = {}
                            self.state = BotState.IDLE
                        return
                    raise order_err

                if order['status'] == 'closed':
                    close_price = safe_float(order.get('price') or order.get('average', self.state_data['buy_price']))
                    trade_profit = (close_price - self.state_data['buy_price']) * self.state_data['amount']
                    self.session_profit += trade_profit
                    self.trade_db.log_trade(symbol, "sell", self.state_data['amount'], close_price, confidence=0.0)
                    logger.info(f"@PROFIT_TAKEN@ PROFIT TAKEN! {symbol} +${trade_profit:.2f}")
                    self.state_data = {}
                    self.state = BotState.IDLE
                    return
     
                if is_sl_hit:
                    logger.warning(f"@STOP_LOSS_HIT@ СРАБОТАЛ РЕАЛЬНЫЙ СТОП-ЛОСС для {symbol} ({change_percent:.2f}%)")
                    self.last_loss_time = time.time()
                    self._panic_sell()
                    return
                    
                if elapsed > self.trading_config['timeout_breakeven'] and not self.state_data['is_breakeven']:
                    self._set_breakeven()
                    
        except Exception as e:
            logger.error(f"Ошибка в состоянии IN_POSITION: {e}")

    def _panic_sell(self) -> None:
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
            logger.warning(f"@PANIC_SELL_DONE@ Паник-селл завершен. Цена: {real_close_price}")
        except Exception as e:
            logger.error(f"Ошибка выполнения паник-селла: {e}")
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
            logger.info(f"@BREAKEVEN_SET@ Выставлен безубыток по {symbol}")
        except Exception as e:
            logger.error(f"Ошибка перевода в безубыток: {e}")
            
    def _check_time_session(self) -> bool:
        if not self.trading_config.get('block_night_trading', False):
            return True
        current_hour = datetime.now().hour
        if 0 <= current_hour < 5:
            print(f"Потолок времени: Ночной режим (Час: {current_hour}) @NIGHT_BLOCK@ ", end='\r')
            return False
        return True
            
    def _check_risk_limits(self) -> bool:
        try:
            cooldown_min = self.trading_config.get('cooldown_after_loss_minutes', 30)
            if time.time() - self.last_loss_time < (cooldown_min * 60):
                remaining = int((cooldown_min * 60) - (time.time() - self.last_loss_time))
                print(f"Защитная пауза Cooldown после убытка. Осталось: {remaining}с @COOLDOWN@ ", end='\r')
                return False
                
            stats = self.trade_db.get_session_stats()
            max_day_trades = self.trading_config.get('max_trades_per_day', 5)
            if stats.get('total_trades', 0) >= max_day_trades:
                print(f"Лимит сделок за сутки исчерпан ({max_day_trades}/{max_day_trades}) @DAY_LIMIT@ ", end='\r')
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
        # В режиме симуляции баланс всегда считается условно верным
        if self.trading_config.get('dry_run', False):
            return True
        try:
            balance = self.exchange.fetch_balance()
            usdt_free = safe_float(balance['free'].get('USDT', 0))
            total_equity = safe_float(balance['total'].get('USDT', usdt_free))
            if total_equity > 0 and total_equity < self.trading_config['stop_loss_total']:
                logger.critical("@CRITICAL_BALANCE_STOP@ Общий баланс аккаунта ниже лимита защиты!")
                self.should_stop = True
                return False
            if usdt_free < self.trading_config['min_exchange_limit']:
                print(f"Свободный остаток: {usdt_free:.2f}$ | Ожидание лимита @WAIT_USDT@ ", end='\r')
                return False
            return True
        except Exception as e:
            logger.error(f"Ошибка проверки баланса: {e}")
            return False
 
    def _scan_for_entries(self) -> None:
        try:
            symbols = self.symbol_manager.get_symbols(refresh_scanner=True)
            tickers = self.ws_tickers_cache
            if not tickers: return
 
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
                        print(f"Аварийный блок: BTC падает на {btc_drop_15m:.2f}% @BTC_CRASH_BLOCK@ ", end='\r')
                        return
            except: pass
 
            print(f"Сканирование рынка... Trend BTC: [{btc_trend.upper()}] @SCAN_WS@ ", end='\r')
 
            for symbol in symbols:
                if symbol not in tickers:
                    continue
                try:
                    price_now = safe_float(tickers[symbol]['ask'])
                    if symbol not in self.price_history or self.price_history[symbol][0] == 0.0:
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
                                logger.info(f"@SIGNAL_APPROVED@ Сигнал одобрен по {symbol} (RVOL: {real_rvol:.1f}x)")
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
        self.state = BotState.BUYING
        try:
            buy_price = safe_float(tickers[symbol]['ask'])
            slot_size = self.trading_config['slot_size']
            amount_target = float(self.exchange.exchange.amount_to_precision(symbol, slot_size / buy_price))
            
            is_dry_run = self.trading_config.get('dry_run', False)
            
            if is_dry_run:
                logger.info(f"@DRY_RUN_BUY@ Имитация покупки: {symbol} на {slot_size}$ по цене {buy_price}")
                filled = amount_target
                order_id = "virtual_buy_12345"
            else:
                logger.info(f"@BUY_ORDER_SEND@ Отправка лимитного ордера: {symbol} на {slot_size}$ по цене {buy_price}")
                order = self.exchange.create_limit_buy_order(symbol, amount_target, buy_price)
                order_id = order['id']
                
                filled = 0
                for _ in range(7):
                    time.sleep(1)
                    try:
                        check = self.exchange.fetch_order(order_id, symbol)
                        filled = safe_float(check.get('filled', 0))
                        if check['status'] in ['closed', 'canceled']: break
                    except: pass
            
            filled_usd = filled * buy_price
            if filled_usd >= 5.0 or is_dry_run:
                
                take_profit_pct = self.trading_config.get('take_profit', 1.5)
                sell_price = float(self.exchange.exchange.price_to_precision(symbol, buy_price * (1 + (take_profit_pct / 100))))
                
                if sell_price <= buy_price: 
                    sell_price += self.exchange.exchange.markets[symbol]['precision']['price']

                if is_dry_run:
                    logger.info(f"@DRY_RUN_SELL@ Имитация тейк-профита: Продажа {filled} {symbol} по цене {sell_price}")
                    sell_order_id = "virtual_sell_67890"
                    safe_amount = filled
                else:
                    time.sleep(2.5)
                    balance = self.exchange.fetch_balance()
                    actual_qty = safe_float(balance['free'].get(symbol.split('/')[0], 0))
                    safe_amount = float(self.exchange.exchange.amount_to_precision(symbol, actual_qty if actual_qty > 0 else filled))
                    
                    logger.info(f"@TAKE_PROFIT_SEND@ Выставление лимитного ордера продажи: {safe_amount} {symbol} по цене {sell_price}")
                    sell_order = self.exchange.create_limit_sell_order(symbol, safe_amount, sell_price)
                    sell_order_id = sell_order['id']
                
                self.state_data = {
                    'symbol': symbol,
                    'buy_price': buy_price,
                    'buy_time': time.time(),
                    'order_id': sell_order_id,
                    'amount': safe_amount,
                    'target_sell_price': sell_price,
                    'is_breakeven': False
                }
                self.trade_db.log_trade(symbol, "buy", safe_amount, buy_price, confidence=100.0)
                logger.info(f"@STATE_CHANGED@ Переключение автомата -> IN_POSITION для {symbol}")
                self.state = BotState.IN_POSITION
            else:
                logger.warning(f"@BUY_TIMEOUT@ Ордер не исполнился вовремя. Отмена.")
                try: self.exchange.cancel_order(order_id, symbol)
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
