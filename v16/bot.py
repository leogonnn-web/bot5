"""
HYDRA Trading Bot v16.0 - Main Application with Technical Indicators + Scanner Integration
Professional cryptocurrency trading bot for Bybit with RSI, EMA, MACD, Stochastic, and Dynamic Stops

Features:
✅ Scanner v3.0 integration for hot symbols
✅ Stochastic Oscillator for entry confirmation
✅ Dynamic ATR-based stop losses
✅ RSI, EMA, MACD technical indicators
✅ Automatic retry for lost orders
✅ Windows-optimized
"""

import time
import signal
from typing import Optional, Dict
from dataclasses import dataclass
from datetime import datetime

from logger_setup import logger
from config import config
from exchange_utils import ExchangeManager
from trade_logger import TradeDatabase
from indicators import IndicatorAnalyzer
from indicators_v16 import EnhancedIndicatorAnalyzer
from scanner_integration import ScannerIntegration, DynamicSymbolManager
from utils import (
    ProfitManager, HealthChecker, SoundNotifier,
    safe_float, format_currency, format_percentage
)


@dataclass
class ActiveDeal:
    """Represents an active trading deal"""
    symbol: Optional[str] = None
    buy_price: float = 0.0
    buy_time: float = 0.0
    order_id: Optional[str] = None
    amount: float = 0.0
    is_breakeven: bool = False


class TradingBot:
    """Main trading bot implementation with technical indicators + scanner integration"""
    
    def __init__(self):
        self.config = config
        self.exchange = ExchangeManager()
        self.trade_db = TradeDatabase()
        self.profit_manager = ProfitManager()
        self.health_checker = HealthChecker()
        self.sound = SoundNotifier()
        self.indicator = IndicatorAnalyzer()
        
        # Scanner integration (NEW in v16.0)
        self.scanner_integration = ScannerIntegration("hot_symbols.txt")
        self.symbol_manager = DynamicSymbolManager(
            base_symbols=self.config.get_symbols(),
            scanner_integration=self.scanner_integration
        )
        
        self.session_profit = self.profit_manager.load()
        self.active_deal = ActiveDeal()
        self.price_history = {symbol: [0.0, time.time()] for symbol in self.config.get_symbols()}
        
        self.should_stop = False
        self.loop_counter = 0
        self.trading_config = self.config.get_trading_config()
        self.indicator_config = self.config.get_indicator_config()
        self.scanner_config = self.config.get_scanner_config()
        self.indicators_enabled = self.config.are_indicators_enabled()
        self.stochastic_enabled = self.config.is_stochastic_enabled()
        self.dynamic_stops_enabled = self.config.use_dynamic_stops()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle graceful shutdown on signals"""
        logger.info("Shutdown signal received, closing gracefully...")
        self.should_stop = True
    
    def run(self) -> None:
        """Main bot trading loop"""
        try:
            logger.info(f"🚀 HYDRA v16.0 STARTED | Previous profit: {format_currency(self.session_profit)}")
            
            # Log enabled features
            features = []
            if self.indicators_enabled:
                features.append("RSI, EMA, MACD")
            if self.stochastic_enabled:
                features.append("Stochastic")
            if self.dynamic_stops_enabled:
                features.append("Dynamic ATR Stops")
            if self.scanner_config.get('enabled', False):
                features.append("Scanner v3.0")
            
            if features:
                logger.info(f"✅ Enabled features: {' | '.join(features)}")
            else:
                logger.warning("⚠️ No advanced features enabled - using legacy mode")
            
            self.exchange.load_markets()
            
            while not self.should_stop:
                try:
                    self.loop_counter += 1
                    
                    # Priority 1: Monitor active deal
                    if self.active_deal.symbol:
                        self._monitor_active_deal()
                        continue
                    
                    # Priority 2: Check balance and limits
                    if not self._check_balance():
                        time.sleep(5)
                        continue
                    
                    # Priority 3: Scan for entries
                    self._scan_for_entries()
                    
                    # Periodic tasks (every 5 minutes)
                    if self.loop_counter % 300 == 0:
                        self.health_checker.check()
                        self.exchange.clear_caches()
                        stats = self.trade_db.get_session_stats()
                        symbol_stats = self.symbol_manager.get_stats()
                        logger.info(
                            f"📊 Session stats - Trades: {stats['total_trades']}, "
                            f"Profit: {format_currency(stats['total_profit'])} | "
                            f"Symbols: {symbol_stats['total']} "
                            f"({symbol_stats['from_scanner']} scanner, {symbol_stats['from_base']} base)"
                        )
                    
                    time.sleep(1)
                
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    time.sleep(10)
        
        except KeyboardInterrupt:
            logger.info("Bot interrupted by user")
        except Exception as e:
            logger.critical(f"Critical error in bot: {e}", exc_info=True)
        finally:
            self._shutdown()
    
    def _monitor_active_deal(self) -> None:
        """Monitor and manage active trading deal"""
        try:
            # Retry logic for missing sell order
            if not self.active_deal.order_id:
                try:
                    logger.warning(f"🔄 RETRY SELL: {self.active_deal.symbol}")
                    balance = self.exchange.fetch_balance()
                    coin_name = self.active_deal.symbol.split('/')[0]
                    actual_qty = safe_float(balance['free'].get(coin_name, 0))
                    
                    if actual_qty <= 0:
                        logger.warning(f"No balance for {coin_name}")
                        self.active_deal = ActiveDeal()
                        return
                    
                    safe_amount = float(self.exchange.exchange.amount_to_precision(
                        self.active_deal.symbol, actual_qty
                    ))
                    sell_raw = self.active_deal.buy_price * (1 + (self.trading_config['entry_threshold'] / 100))
                    sell_price = float(self.exchange.exchange.price_to_precision(
                        self.active_deal.symbol, sell_raw
                    ))
                    
                    new_order = self.exchange.create_limit_sell_order(
                        self.active_deal.symbol, safe_amount, sell_price
                    )
                    self.active_deal.order_id = new_order['id']
                    logger.info(f"✅ Sell order recreated: {new_order['id']}")
                    return
                except Exception as e:
                    logger.error(f"Retry sell failed: {e}")
                    return
            
            # Check order status
            order = self.exchange.fetch_order(self.active_deal.order_id, self.active_deal.symbol)
            
            if order['status'] == 'closed':
                self._close_deal(order)
                return
            
            # Check current price
            ticker = self.exchange.fetch_ticker(self.active_deal.symbol)
            current_price = safe_float(ticker['last'])
            change_percent = ((current_price - self.active_deal.buy_price) / self.active_deal.buy_price) * 100
            elapsed = time.time() - self.active_deal.buy_time
            
            print(
                f"📈 {self.active_deal.symbol}: {format_percentage(change_percent)} | "
                f"Elapsed: {int(elapsed)}s        ",
                end='\r'
            )
            
            # Check dynamic or static stop loss
            try:
                if self.dynamic_stops_enabled:
                    ohlcv = self.exchange.fetch_ohlcv(self.active_deal.symbol, '1m', limit=30)
                    _, dynamic_stop = EnhancedIndicatorAnalyzer.calculate_dynamic_stops(
                        entry_price=self.active_deal.buy_price,
                        ohlcv_data=ohlcv,
                        atr_multiplier=self.trading_config.get('atr_multiplier', 1.5),
                        min_stop_pct=self.trading_config.get('min_stop_pct', 1.0)
                    )
                    stop_loss_pct = abs((current_price - dynamic_stop) / self.active_deal.buy_price * 100)
                else:
                    stop_loss_pct = self.trading_config['panic_stop']
                
                if change_percent <= -stop_loss_pct:
                    stop_type = "DYNAMIC" if self.dynamic_stops_enabled else "STATIC"
                    logger.warning(f"💀 {stop_type} STOP HIT: {self.active_deal.symbol} ({stop_loss_pct:.2f}%)")
                    self._panic_sell()
                    return
            except Exception as e:
                logger.error(f"Stop check error: {e}, using static fallback")
                if change_percent <= -self.trading_config['panic_stop']:
                    logger.warning(f"💀 FALLBACK STOP: {self.active_deal.symbol}")
                    self._panic_sell()
                    return
            
            # Check breakeven timeout
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
            
            self.session_profit += trade_profit
            self.profit_manager.save(self.session_profit)
            
            # Log trade
            elapsed = int(time.time() - self.active_deal.buy_time)
            self.trade_db.log_trade(
                self.active_deal.symbol,
                self.active_deal.buy_price,
                close_price,
                self.active_deal.amount,
                elapsed
            )
            
            logger.info(
                f"💰 PROFIT TAKEN! {self.active_deal.symbol} "
                f"+{format_currency(trade_profit)} | Session: {format_currency(self.session_profit)}"
            )
            
            self.sound.beep_success()
            self.active_deal = ActiveDeal()
        
        except Exception as e:
            logger.error(f"Error closing deal: {e}")
    
    def _panic_sell(self) -> None:
        """Execute panic sell"""
        try:
            self.exchange.cancel_order(self.active_deal.order_id, self.active_deal.symbol)
            time.sleep(0.5)
            
            amount = float(self.exchange.exchange.amount_to_precision(
                self.active_deal.symbol,
                self.active_deal.amount
            ))
            
            self.exchange.create_market_sell_order(self.active_deal.symbol, amount)
            self.active_deal = ActiveDeal()
        
        except Exception as e:
            logger.error(f"Error in panic sell: {e}")
    
    def _set_breakeven(self) -> None:
        """Set breakeven sell order after timeout"""
        try:
            self.exchange.cancel_order(self.active_deal.order_id, self.active_deal.symbol)
            time.sleep(0.5)
            
            # Calculate breakeven price
            breakeven_raw = self.active_deal.buy_price * 1.0005
            breakeven_price = float(self.exchange.exchange.price_to_precision(
                self.active_deal.symbol,
                breakeven_raw
            ))
            
            # Ensure price is above buy price
            if breakeven_price <= self.active_deal.buy_price:
                market_precision = self.exchange.exchange.markets[self.active_deal.symbol]['precision']['price']
                breakeven_price += market_precision
            
            amount = float(self.exchange.exchange.amount_to_precision(
                self.active_deal.symbol,
                self.active_deal.amount
            ))
            
            new_order = self.exchange.create_limit_sell_order(
                self.active_deal.symbol,
                amount,
                breakeven_price
            )
            
            self.active_deal.order_id = new_order['id']
            self.active_deal.is_breakeven = True
            
            logger.info(f"⏰ {self.active_deal.symbol} set to breakeven")
        
        except Exception as e:
            logger.error(f"Error setting breakeven: {e}")
    
    def _check_balance(self) -> bool:
        """Check balance and stop loss conditions"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_free = safe_float(balance['free'].get('USDT', 0))
            total_equity = safe_float(balance['info'].get('totalEquity', 0))
            
            # Calculate total equity if not provided
            if total_equity <= 0:
                total_equity = safe_float(balance['total'].get('USDT', 0))
                for currency, amount in balance['total'].items():
                    if currency != 'USDT' and safe_float(amount) > 0.001:
                        try:
                            ticker = self.exchange.fetch_ticker(f"{currency}/USDT")
                            total_equity += safe_float(amount) * safe_float(ticker['last'])
                        except:
                            continue
            
            # Check stop loss
            stop_loss = self.trading_config['stop_loss_total']
            if total_equity > 0 and total_equity < stop_loss:
                logger.critical(f"🚨 STOP LOSS! Equity {format_currency(total_equity)} below limit")
                self.should_stop = True
                return False
            
            # Check minimum limit
            min_limit = self.trading_config['min_exchange_limit']
            if usdt_free < min_limit:
                print(f"⏳ Insufficient balance ({format_currency(usdt_free)}), waiting...        ", end='\r')
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Error checking balance: {e}")
            return False
    
    def _scan_for_entries(self) -> None:
        """Scan market for trading opportunities with technical indicators"""
        try:
            # Get symbols - now includes scanner signals (NEW in v16.0)
            symbols = self.symbol_manager.get_symbols(refresh_scanner=True)
            tickers = self.exchange.fetch_tickers(symbols)
            
            print(f"📡 Scanning market... {time.strftime('%H:%M:%S')}        ", end='\r')
            
            for symbol in symbols:
                if symbol not in tickers:
                    continue
                
                price_now = safe_float(tickers[symbol]['ask'])
                
                # Update price history if first time or new high
                if (time.time() - self.price_history[symbol][1] > 900 or
                    price_now > self.price_history[symbol][0]):
                    self.price_history[symbol] = [price_now, time.time()]
                    continue
                
                # Calculate drop
                drop = ((self.price_history[symbol][0] - price_now) / self.price_history[symbol][0]) * 100
                
                if drop >= self.trading_config['drop_threshold']:
                    # Check market health
                    spread, vol = self.exchange.get_market_health(symbol)
                    
                    if spread > self.trading_config['spread_max']:
                        continue
                    if vol < self.trading_config['volatility_min']:
                        continue
                    
                    logger.info(f"📉 SIGNAL: {symbol} dropped {format_percentage(drop)}")
                    
                    # Technical indicators analysis
                    if self.indicators_enabled:
                        try:
                            ohlcv = self.exchange.fetch_ohlcv(symbol, '1m', limit=30)
                            signal_analysis = self.indicator.get_signal_analysis(ohlcv)
                            
                            # Log indicator values
                            logger.info(
                                f"   RSI: {signal_analysis['rsi']:.1f} | "
                                f"EMA9: ${signal_analysis['ema9']:.8f} | "
                                f"EMA21: ${signal_analysis['ema21']:.8f} | "
                                f"Score: {signal_analysis['score']}"
                            )
                            
                            # Log signals
                            for sig in signal_analysis['signals']:
                                logger.info(f"   {sig}")
                            
                            # NEW in v16.0: Stochastic confirmation
                            if self.stochastic_enabled:
                                k, d = EnhancedIndicatorAnalyzer.calculate_stochastic(ohlcv)
                                stoch_signal = EnhancedIndicatorAnalyzer.get_stochastic_signal(k, d)
                                logger.info(f"   {stoch_signal['description']}")
                                
                                # Block if overbought
                                if k > 80 or d > 80:
                                    logger.warning(f"   ⚠️ Stochastic overbought - SKIPPING")
                                    continue
                            
                            # Check if we should enter
                            should_enter, reason = self.indicator.should_enter_trade(signal_analysis)
                            logger.info(f"   {reason}")
                            
                            if should_enter:
                                self._enter_trade(symbol, price_now, tickers)
                                break
                        except Exception as e:
                            logger.error(f"Indicator analysis error for {symbol}: {e}")
                            continue
                    else:
                        # Legacy mode - no indicators
                        self._enter_trade(symbol, price_now, tickers)
                        break
        
        except Exception as e:
            logger.error(f"Error scanning for entries: {e}")
    
    def _enter_trade(self, symbol: str, price: float, tickers: Dict) -> None:
        """Enter a trade"""
        try:
            buy_price = safe_float(tickers[symbol]['ask'])
            slot_size = self.trading_config['slot_size']
            amount_target = float(self.exchange.exchange.amount_to_precision(
                symbol,
                slot_size / buy_price
            ))
            
            # Create buy order
            order = self.exchange.create_limit_buy_order(symbol, amount_target, buy_price)
            
            # Wait for fill or timeout
            filled = 0
            for attempt in range(7):
                time.sleep(1)
                check = self.exchange.fetch_order(order['id'], symbol)
                filled = safe_float(check.get('filled', 0))
                
                if check['status'] in ['closed', 'canceled']:
                    break
            
            # Cancel if not filled enough
            if filled * buy_price < 5.0:
                try:
                    self.exchange.cancel_order(order['id'], symbol)
                except:
                    pass
                
                time.sleep(1)
                final_check = self.exchange.fetch_order(order['id'], symbol)
                filled = safe_float(final_check.get('filled', 0))
            
            # Check if trade is worth continuing
            if filled * buy_price >= 5.0:
                self.sound.beep_alert()
                
                # Calculate sell price
                entry_threshold = self.trading_config['entry_threshold']
                sell_raw = buy_price * (1 + (entry_threshold / 100))
                sell_price = float(self.exchange.exchange.price_to_precision(symbol, sell_raw))
                
                # Ensure sell price is above buy price
                if sell_price <= buy_price:
                    market_precision = self.exchange.exchange.markets[symbol]['precision']['price']
                    sell_price += market_precision
                
                safe_amount = float(self.exchange.exchange.amount_to_precision(symbol, filled))
                sell_order = self.exchange.create_limit_sell_order(symbol, safe_amount, sell_price)
                
                # Update active deal
                self.active_deal = ActiveDeal(
                    symbol=symbol,
                    buy_price=buy_price,
                    buy_time=time.time(),
                    order_id=sell_order['id'],
                    amount=safe_amount,
                    is_breakeven=False
                )
                
                self.price_history[symbol] = [0.0, time.time()]
                
                logger.info(
                    f"✅ ENTERED TRADE: {symbol} | Buy: {format_currency(buy_price)} | "
                    f"Sell: {format_currency(sell_price)} | Amount: {safe_amount}"
                )
        
        except Exception as e:
            logger.error(f"Error entering trade: {e}")
            self.price_history[symbol] = [price, time.time()]
    
    def _shutdown(self) -> None:
        """Clean shutdown and save state"""
        logger.info("Bot shutting down...")
        self.profit_manager.save(self.session_profit)
        
        stats = self.trade_db.get_session_stats()
        logger.info(
            f"📊 Final stats - Trades: {stats['total_trades']}, "
            f"Total profit: {format_currency(stats['total_profit'])}"
        )
        
        logger.info(f"👋 Bot stopped. Session profit: {format_currency(self.session_profit)}")


def main():
    """Entry point"""
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()
