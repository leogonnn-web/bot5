"""
HYDRA Trading Bot v17.0 - IRON GUARD HYBRID EDITION
Advanced Indicator System (Ichimoku + Volume Profile) with v14.7 Execution
"""
import time
import signal
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from logger_setup import logger
from hydra_v17_config import config
from paths import HOT_SYMBOLS_FILE
from exchange_utils import ExchangeManager
from database import TradeDatabase
from indicators_v17 import analyzer, EnhancedIndicatorAnalyzer
from scanner_integration import ScannerIntegration, DynamicSymbolManager
from utils import (
 ProfitManager, HealthChecker, SoundNotifier,
 safe_float, format_currency, format_percentage
)
@dataclass
class ActiveDeal:
    symbol: Optional[str] = None
    buy_price: float = 0.0
    buy_time: float = 0.0
    order_id: Optional[str] = None
    amount: float = 0.0
    is_breakeven: bool = False
class TradingBot:
    """Main trading bot v17.0 with v14.7 execution reliability"""
 
    def __init__(self):
        self.config = config
        self.exchange = ExchangeManager()
        self.trade_db = TradeDatabase()
        self.profit_manager = ProfitManager()
        self.health_checker = HealthChecker()
        self.sound = SoundNotifier()
 
        self.scanner_integration = ScannerIntegration(HOT_SYMBOLS_FILE)
        self.symbol_manager = DynamicSymbolManager(
            base_symbols=self.config.get_symbols(),
            scanner_integration=self.scanner_integration
        )
        self._btc_trend_cache = "neutral"
        self._btc_market_vol_cache = 1.0
 
        self.session_profit = self.profit_manager.load()
        self.active_deal = ActiveDeal()
        self.price_history = {symbol: [0.0, time.time()] for symbol in self.config.get_symbols()}
 
        self.should_stop = False
        self.loop_counter = 0
        self.trading_config = self.config.get_trading_config()
        self.indicators_enabled = self.config.are_indicators_enabled()
        self.dynamic_stops_enabled = self.config.use_dynamic_stops()
        self.take_profit_pct = self.config.get_take_profit_pct()
 
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
 
    def _signal_handler(self, signum, frame):
        logger.info("Shutdown signal received, closing gracefully...")
        self.should_stop = True

    def _apply_session_profit(self, trade_profit: float) -> None:
        self.session_profit += trade_profit
        self.profit_manager.session_profit = self.session_profit
        self.profit_manager.total_trades += 1
        if trade_profit > 0:
            self.profit_manager.winning_trades += 1
        self.profit_manager.save()

    def _base_coin_dust_threshold(self, symbol: str) -> float:
        """Minimum 'meaningful' free amount for base coin (exchange limits + dust)."""
        try:
            market = self.exchange.exchange.market(symbol)
            min_amt = (market.get('limits') or {}).get('amount', {}).get('min')
            if min_amt is not None and float(min_amt) > 0:
                return float(min_amt) * 1.5
            prec = (market.get('precision') or {}).get('amount')
            if isinstance(prec, int) and prec >= 0:
                return max(10 ** (-prec) * 5, 1e-10)
        except Exception:
            pass
        return 1e-8

    def _refresh_btc_context_if_needed(self) -> None:
        """BTC trend + volatility multiplier for complete_analysis (not per-symbol)."""
        mc = self.config.get_market_conditions_config()
        if not mc.get('btc_trend_detection', True):
            self._btc_trend_cache = "neutral"
            self._btc_market_vol_cache = 1.0
            return
        if self.loop_counter % 45 != 0:
            return
        btc_sym = "BTC/USDT"
        try:
            _spread, vol_pct = self.exchange.get_market_health(btc_sym)
            ref = max(float(self.trading_config.get("volatility_min", 0.85)), 0.35)
            self._btc_market_vol_cache = max(0.5, min(2.5, float(vol_pct) / ref))
        except Exception as e:
            logger.debug(f"BTC volatility context: {e}")
            self._btc_market_vol_cache = 1.0
        try:
            ohlcv = self.exchange.fetch_ohlcv(btc_sym, "15m", limit=40)
            if len(ohlcv) < 16:
                self._btc_trend_cache = "neutral"
                return
            ema = EnhancedIndicatorAnalyzer.calculate_ema(ohlcv, 14)
            last = float(ohlcv[-1][4])
            band = 0.0025
            if last > ema * (1.0 + band):
                self._btc_trend_cache = "bullish"
            elif last < ema * (1.0 - band):
                self._btc_trend_cache = "bearish"
            else:
                self._btc_trend_cache = "neutral"
        except Exception as e:
            logger.debug(f"BTC trend detection: {e}")
            self._btc_trend_cache = "neutral"

    def _resolve_market_sell_execution(
        self,
        symbol: str,
        order_id: Optional[str],
        expected_amount: float,
        t0: float,
    ) -> Tuple[float, float, bool]:
        """Return (filled, avg_price, used_trades_fallback)."""
        terminal = {"closed", "canceled", "cancelled", "expired", "rejected"}
        last: Dict = {}
        oid = order_id or ""
        if oid:
            deadline = time.time() + 18.0
            while time.time() < deadline:
                try:
                    o = self.exchange.fetch_order(oid, symbol)
                    last = o
                    st = str(o.get("status", "")).lower()
                    filled = safe_float(o.get("filled", 0))
                    if st in terminal or filled >= expected_amount * 0.995:
                        break
                except Exception:
                    pass
                time.sleep(0.45)

        avg_px = safe_float(last.get("average") or last.get("price") or 0)
        filled_amt = safe_float(last.get("filled") or 0)
        if avg_px > 0 and filled_amt > 0:
            return filled_amt, avg_px, False

        try:
            since_ms = max(0, int((t0 - 5.0) * 1000))
            trades = self.exchange.fetch_my_trades(symbol, limit=25, since=since_ms)
            now_ms = time.time() * 1000
            for tr in reversed(trades):
                if str(tr.get("side", "")).lower() != "sell":
                    continue
                ts = float(tr.get("timestamp") or now_ms)
                if now_ms - ts > 65000:
                    continue
                amt = safe_float(tr.get("amount", expected_amount))
                cost = safe_float(tr.get("cost") or 0)
                px = safe_float(tr.get("price") or ((cost / amt) if amt else 0))
                if px > 0 and amt > 0:
                    return amt, px, True
        except Exception as e:
            logger.warning(f"Selling: trade-history fallback failed: {e}")

        return 0.0, 0.0, False

    def _recent_sell_on_symbol(self, symbol: str, min_ts: float) -> bool:
        """Detect a sell shortly after entry (recovery path when balance is dust)."""
        try:
            since_ms = max(0, int((min_ts - 15.0) * 1000))
            trades = self.exchange.fetch_my_trades(symbol, limit=20, since=since_ms)
            now_ms = time.time() * 1000
            for tr in trades:
                if str(tr.get("side", "")).lower() != "sell":
                    continue
                ts = float(tr.get("timestamp") or now_ms)
                if now_ms - ts <= 125000:
                    return True
        except Exception as e:
            logger.debug(f"recent sell probe: {e}")
        return False

    def _is_falling_knife(self, symbol: str, price_now: float) -> bool:
        """Детектор 'падающего ножа' из v14.7"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='5m', limit=3)
            if len(ohlcv) < 3: return False
            high_15m = max([c[2] for c in ohlcv])
            drop_15m = ((high_15m - price_now) / high_15m) * 100

            threshold = self.config.get_falling_knife_threshold_pct()
            if drop_15m > threshold:
                return True
            return False
        except Exception:
            return False
    def run(self) -> None:
        """Main bot trading loop"""
        try:
            logger.info(f"HYDRA v17.0 STARTED | Previous profit: {format_currency(self.session_profit)}")
            self.exchange.load_markets()
 
            while not self.should_stop:
                try:
                    self.loop_counter += 1
                    self._refresh_btc_context_if_needed()

                    if self.active_deal.symbol:
                        self._monitor_active_deal()
                        continue
 
                    if not self._check_balance():
                        time.sleep(5)
                        continue
 
                    self._scan_for_entries()
 
                    if self.loop_counter % 300 == 0:
                        self.health_checker.check()
                        self.exchange.clear_caches()
                        stats = self.trade_db.get_session_stats()
                        logger.info(f" Session stats - Trades: {stats.get('total_trades', 0)}, Profit: {format_currency(stats.get('total_profit', 0.0))}")
 
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    time.sleep(10)
        finally:
            self._shutdown()
 
    def _monitor_active_deal(self) -> None:
        """Мониторинг сделки с умным дожимом ордеров из v14.7"""
        try:
            # Логика дожима: если ордер на продажу потерялся, восстанавливаем по балансу биржи
            if not self.active_deal.order_id:
                balance = self.exchange.fetch_balance()
                coin_name = self.active_deal.symbol.split('/')[0]
                actual_qty = safe_float(balance['free'].get(coin_name, 0))
                dust = self._base_coin_dust_threshold(self.active_deal.symbol)

                if actual_qty <= dust:
                    logger.warning(
                        f"Recovery sell: lost order_id and free {coin_name}={actual_qty} "
                        f"(dust_floor={dust}); rechecking balance"
                    )
                    time.sleep(0.6)
                    balance = self.exchange.fetch_balance()
                    actual_qty = safe_float(balance['free'].get(coin_name, 0))
                    if actual_qty <= dust:
                        if self._recent_sell_on_symbol(self.active_deal.symbol, self.active_deal.buy_time):
                            logger.info(
                                f"Recent sell activity on {self.active_deal.symbol}; "
                                "assuming position flat, clearing active_deal"
                            )
                        else:
                            logger.warning(
                                "STUCK active_deal cleared: no base coin after recovery — "
                                "limit sell may have filled or only dust remains"
                            )
                        self.active_deal = ActiveDeal()
                        return

                safe_amount = float(self.exchange.exchange.amount_to_precision(self.active_deal.symbol, actual_qty))
                self.active_deal.amount = safe_amount

                sell_raw = self.active_deal.buy_price * (1 + (self.take_profit_pct / 100))
                sell_p = float(self.exchange.exchange.price_to_precision(self.active_deal.symbol, sell_raw))

                new_o = self.exchange.create_limit_sell_order(self.active_deal.symbol, safe_amount, sell_p)
                self.active_deal.order_id = new_o['id']
                logger.info(f"✅ УСПЕХ: Ордер продажи восстановлен дожимом: {new_o['id']}")
                return
            try:
                order = self.exchange.fetch_order(self.active_deal.order_id, self.active_deal.symbol)
            except Exception as order_err:
                if "last 500 orders" in str(order_err):
                    self.active_deal.order_id = None # Сбрасываем ID для активации дожима
                    return
                raise order_err
            if order['status'] == 'closed':
                self._close_deal(order)
                return
 
            ticker = self.exchange.fetch_ticker(self.active_deal.symbol)
            current_price = safe_float(ticker['last'])
            change_percent = ((current_price - self.active_deal.buy_price) / self.active_deal.buy_price) * 100
            elapsed = time.time() - self.active_deal.buy_time
 
            print(f" {self.active_deal.symbol}: {format_percentage(change_percent)} | {int(elapsed)}s", end='\r')

            if self.dynamic_stops_enabled:
                try:
                    ohlcv = self.exchange.fetch_ohlcv(self.active_deal.symbol, '1m', limit=30)
                    stop_price, stop_loss_pct = analyzer.calculate_dynamic_stops(
                        entry_price=self.active_deal.buy_price,
                        ohlcv_data=ohlcv,
                        atr_multiplier=self.trading_config.get('atr_multiplier', 1.5),
                        min_stop_pct=self.trading_config.get('min_stop_pct', 1.0),
                        max_stop_pct=self.trading_config.get('max_stop_pct', 5.0),
                    )
                    if current_price <= stop_price or change_percent <= -stop_loss_pct:
                        logger.warning(
                            f"DYNAMIC STOP {self.active_deal.symbol}: "
                            f"price={current_price:.8f} stop={stop_price:.8f} "
                            f"change={change_percent:.2f}% limit=-{stop_loss_pct:.2f}%"
                        )
                        self._panic_sell(current_price)
                        return
                except Exception as stop_err:
                    logger.error(f"Dynamic stop check failed: {stop_err}")
                    if change_percent <= -self.trading_config['panic_stop']:
                        self._panic_sell(current_price)
                        return
            elif change_percent <= -self.trading_config['panic_stop']:
                self._panic_sell(current_price)
                return

            if elapsed > self.trading_config['timeout_breakeven'] and not self.active_deal.is_breakeven:
                self._set_breakeven()
                return
 
        except Exception as e:
            logger.error(f"Error monitoring deal: {e}")
 
    def _close_deal(self, order: Dict) -> None:
        """Close completed deal and log profit"""
        try:
            close_price = safe_float(order.get('price') or order.get('average', self.active_deal.buy_price))
            trade_profit = (close_price - self.active_deal.buy_price) * self.active_deal.amount
 
            self._apply_session_profit(trade_profit)

            self.trade_db.log_trade(self.active_deal.symbol, "sell", self.active_deal.amount, close_price, confidence=0.0)
            logger.info(f" PROFIT TAKEN! {self.active_deal.symbol} +{format_currency(trade_profit)}")
            self.active_deal = ActiveDeal()
        except Exception as e:
            logger.error(f"Error closing deal: {e}")
 
    def _panic_sell(self, exit_price_hint: Optional[float] = None) -> None:
        """Execute panic sell; PnL/trade log use actual fill when API allows."""
        symbol = self.active_deal.symbol
        buy_price = self.active_deal.buy_price
        qty_hint = self.active_deal.amount
        _ = exit_price_hint  # optional future use; stop loss passes last mark
            if prev_oid:
                try:
                    self.exchange.cancel_order(prev_oid, symbol)
                except Exception:
                    pass
            time.sleep(0.5)

            balance = self.exchange.fetch_balance()
            coin_name = symbol.split('/')[0]
            actual_qty = safe_float(balance['free'].get(coin_name, 0))
            amount = float(self.exchange.exchange.amount_to_precision(
                symbol, actual_qty if actual_qty > 0 else qty_hint
            ))
            if amount <= 0:
                logger.warning(f"Panic sell skipped: no balance for {coin_name}")
                self.active_deal = ActiveDeal()
                return

            t_place = time.time()
            sell_order = self.exchange.create_market_sell_order(symbol, amount)
            sell_oid = sell_order.get('id')

            filled_amt, avg_px, trades_fb = self._resolve_market_sell_execution(
                symbol, str(sell_oid) if sell_oid else "", amount, t_place
            )

            used_estimate = False
            if avg_px <= 0 or filled_amt <= 0:
                ticker = self.exchange.fetch_ticker(symbol)
                avg_px = safe_float(ticker.get('bid') or ticker.get('last', buy_price))
                filled_amt = amount
                used_estimate = True
                logger.warning(
                    "PANIC SELL: could not resolve fill from API — "
                    f"PnL logged with ticker estimate px={avg_px:.8f}"
                )
            trade_profit = (avg_px - buy_price) * filled_amt
            self._apply_session_profit(trade_profit)
            self.trade_db.log_trade(symbol, "sell", filled_amt, avg_px, confidence=0.0)
            fb = " (fills from trades API)" if trades_fb else ""
            est = " [ESTIMATED PX]" if used_estimate else ""
            logger.warning(
                f"PANIC SELL {symbol}{fb}{est} Δ={format_currency(trade_profit)} | "
                f"Session={format_currency(self.session_profit)}"
            )
            self.active_deal = ActiveDeal()
        except Exception as e:
            logger.error(f"Error in panic sell: {e}")
 
    def _set_breakeven(self) -> None:
        """Set breakeven sell order after timeout"""
        try:
            try:
                self.exchange.cancel_order(self.active_deal.order_id, self.active_deal.symbol)
            except:
                pass
            time.sleep(0.5)
            breakeven_price = float(self.exchange.exchange.price_to_precision(self.active_deal.symbol, self.active_deal.buy_price * 1.0005))
            amount = float(self.exchange.exchange.amount_to_precision(self.active_deal.symbol, self.active_deal.amount))
            new_order = self.exchange.create_limit_sell_order(self.active_deal.symbol, amount, breakeven_price)
            self.active_deal.order_id = new_order['id']
            self.active_deal.is_breakeven = True
            logger.info(f"{self.active_deal.symbol} set to breakeven")
        except Exception as e:
            logger.error(f"Error setting breakeven: {e}")
 
    def _check_balance(self) -> bool:
        """Check balance and stop loss conditions"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_free = safe_float(balance['free'].get('USDT', 0))
            total_equity = safe_float(balance['total'].get('USDT', usdt_free))
 
            min_equity = self.config.get_min_equity_usd()
            if total_equity > 0 and total_equity < min_equity:
                logger.critical(
                    f" EQUITY FLOOR! {format_currency(total_equity)} < min {format_currency(min_equity)}"
                )
                self.should_stop = True
                return False
 
            if usdt_free < self.trading_config['min_exchange_limit']:
                print(f" Insufficient balance ({format_currency(usdt_free)}), waiting... ", end='\r')
                return False
            return True
        except Exception as e:
            logger.error(f"Error checking balance: {e}")
            return False
 
    def _scan_for_entries(self) -> None:
        """Scan market with advanced v17.0 indicators"""
        try:
            symbols = self.symbol_manager.get_symbols(refresh_scanner=True)
            try:
                tickers = self.exchange.fetch_tickers(symbols)
            except Exception as e:
                logger.warning(f"Ошибка получения тикеров с биржи: {e}")
                return
 
            print(f"Scanning market... {time.strftime('%H:%M:%S')} ", end='\r')
 
            for symbol in symbols:
                if symbol not in tickers:
                    continue
                try:
                    price_now = safe_float(tickers[symbol]['ask'])
                    if symbol not in self.price_history:
                        self.price_history[symbol] = [price_now, time.time()]
                        continue
                    if (time.time() - self.price_history[symbol][1] > 900 or price_now > self.price_history[symbol][0]):
                        self.price_history[symbol] = [price_now, time.time()]
                        continue
 
                    drop = ((self.price_history[symbol][0] - price_now) / self.price_history[symbol][0]) * 100
 
                    if drop >= self.trading_config['drop_threshold']:
                        if self._is_falling_knife(symbol, price_now):
                            continue

                        spread, vol = self.exchange.get_market_health(symbol)
                        if spread > self.trading_config['spread_max']:
                            continue
                        if vol < self.trading_config['volatility_min']:
                            continue

                        try:
                            ohlcv = self.exchange.fetch_ohlcv(symbol, '1m', limit=60)
                        except Exception as ohlcv_err:
                            logger.warning(f" Пропуск {symbol} | Не удалось получить графики: {ohlcv_err}")
                            continue
 
                        if self.indicators_enabled:
                            mc = self.config.get_market_conditions_config()
                            if mc.get('btc_trend_detection', True):
                                btc_trend = self._btc_trend_cache
                                mvol = self._btc_market_vol_cache
                            else:
                                btc_trend = "neutral"
                                mvol = 1.0
                            analysis = analyzer.complete_analysis(
                                ohlcv_data=ohlcv,
                                current_price=price_now,
                                market_volatility=mvol,
                                btc_trend=btc_trend,
                            )
                            if analysis['status'] != 'ok':
                                continue
                            if analysis['recommendation'] in ['STRONG_BUY', 'BUY']:
                                self._enter_trade(symbol, price_now, tickers)
                                break
                        else:
                            self._enter_trade(symbol, price_now, tickers)
                            break
                except Exception as entry_err:
                    logger.warning(f" Ошибка при анализе пары {symbol}: {entry_err}")
                    continue
        except Exception as e:
            logger.error(f"Error scanning: {e}")
 
    def _enter_trade(self, symbol: str, price: float, tickers: Dict) -> None:
        """Вход в сделку из v14.7 с адаптацией под v17.0"""
        try:
            buy_price = safe_float(tickers[symbol]['ask'])
            amount_target = float(self.exchange.exchange.amount_to_precision(symbol, self.trading_config['slot_size'] / buy_price))
            
            logger.info(f"🛒 Покупка: {symbol} x{amount_target} @ ${buy_price:.6f}")
            order = self.exchange.create_limit_buy_order(symbol, amount_target, buy_price)
            
            filled = 0
            for _ in range(7):
                time.sleep(1)
                try:
                    check = self.exchange.fetch_order(order['id'], symbol)
                    filled = safe_float(check.get('filled', 0))
                    if check['status'] in ['closed', 'canceled']: break
                except:
                    pass
            
            filled_usd = filled * buy_price
            if filled_usd < 5.0:
                try:
                    self.exchange.cancel_order(order['id'], symbol)
                except Exception:
                    pass
                logger.warning(f"Buy fill below $5 ({filled_usd:.2f}), order cancelled")
                return

            self.active_deal = ActiveDeal(symbol=symbol, buy_price=buy_price, buy_time=time.time(), amount=filled)

            time.sleep(2.5)  # UTA Bybit balance sync
            balance = self.exchange.fetch_balance()
            actual_qty = safe_float(balance['free'].get(symbol.split('/')[0], 0))
            safe_amount = float(self.exchange.exchange.amount_to_precision(symbol, actual_qty if actual_qty > 0 else filled))

            sell_p = float(self.exchange.exchange.price_to_precision(
                symbol, buy_price * (1 + self.take_profit_pct / 100)
            ))
            if sell_p <= buy_price:
                tick = self.exchange.exchange.markets[symbol]['precision']['price']
                sell_p += tick if isinstance(tick, (int, float)) else float(tick or 0)
            sell_order = self.exchange.create_limit_sell_order(symbol, safe_amount, sell_p)
            self.active_deal.order_id = sell_order['id']
            self.active_deal.amount = safe_amount
            self.trade_db.log_trade(symbol, "buy", safe_amount, buy_price, confidence=100.0)
            logger.info(f"СДЕЛКА: {symbol} | sell @ ${sell_p} (+{self.take_profit_pct}%)")
        except Exception as e:
            logger.error(f"❌ Ошибка входа: {e}")
            self.price_history[symbol] = [price, time.time()]
 
    def _shutdown(self) -> None:
        logger.info("Bot shutting down...")
        self.profit_manager.session_profit = self.session_profit
        self.profit_manager.save()
        logger.info(f" Bot stopped. Session profit: {format_currency(self.session_profit)}")
def main():
    bot = TradingBot()
    bot.run()
if __name__ == "__main__":
    main()