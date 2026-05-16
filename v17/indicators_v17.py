"""
Enhanced Indicators v17.0
Complete indicator suite with Ichimoku, Volume Profile, and Signal Optimization

New in v17.0:
✅ Ichimoku Cloud integration
✅ Volume Profile & POC analysis
✅ Signal Optimizer with conflict resolution
✅ Unified signal aggregation
✅ Market condition adjustment
✅ Divergence detection

Usage:
from indicators_v17 import EnhancedIndicatorAnalyzer

# All indicators in one call
analysis = EnhancedIndicatorAnalyzer.complete_analysis(
    ohlcv_data=ohlcv,
    current_price=price,
    market_volatility=1.0
)
"""

from typing import List, Dict, Tuple, Optional
import numpy as np
from logger_setup import logger
from ichimoku_analyzer import IchimokuAnalyzer
from volume_profile import VolumeProfileAnalyzer
from signal_optimizer import SignalOptimizer


class EnhancedIndicatorAnalyzer:
    """Complete v17.0 indicator analysis with full integration"""
    
    def __init__(self, optimizer: Optional[SignalOptimizer] = None):
        self.optimizer = optimizer if optimizer is not None else SignalOptimizer()
    
    # ===== RSI (from v16.0) =====
    @staticmethod
    def calculate_rsi(ohlcv_data: List[List], period: int = 14) -> float:
        """Calculate RSI (Relative Strength Index)"""
        try:
            if len(ohlcv_data) < period + 1:
                return 50.0
            
            closes = np.array([float(c[4]) for c in ohlcv_data[-period - 1:]])
            deltas = np.diff(closes)
            
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            
            if avg_loss == 0:
                return 100.0 if avg_gain > 0 else 50.0
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return float(np.clip(rsi, 0, 100))
        
        except Exception as e:
            logger.error(f"RSI calculation error: {e}")
            return 50.0
    
    # ===== EMA (from v16.0) =====
    @staticmethod
    def calculate_ema(ohlcv_data: List[List], period: int = 9) -> float:
        """Calculate Exponential Moving Average"""
        try:
            closes = [float(c[4]) for c in ohlcv_data]
            
            if len(closes) < period:
                return closes[-1] if closes else 0.0
            
            multiplier = 2 / (period + 1)
            ema = np.mean(closes[:period])
            
            for close in closes[period:]:
                ema = close * multiplier + ema * (1 - multiplier)
            
            return float(ema)
        
        except Exception as e:
            logger.error(f"EMA calculation error: {e}")
            return 0.0
    
    # ===== MACD (from v16.0) =====
    @staticmethod
    def calculate_macd(
        ohlcv_data: List[List],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[float, float, float]:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        try:
            ema_fast = EnhancedIndicatorAnalyzer.calculate_ema(ohlcv_data, fast)
            ema_slow = EnhancedIndicatorAnalyzer.calculate_ema(ohlcv_data, slow)
            macd_line = ema_fast - ema_slow
            
            # Signal line (EMA of MACD)
            closes = [float(c[4]) for c in ohlcv_data]
            if len(closes) >= slow + signal:
                macd_values = []
                for i in range(slow - 1, len(closes)):
                    ema_f = EnhancedIndicatorAnalyzer.calculate_ema(ohlcv_data[:i + 1], fast)
                    ema_s = EnhancedIndicatorAnalyzer.calculate_ema(ohlcv_data[:i + 1], slow)
                    macd_values.append(ema_f - ema_s)
                
                signal_line = np.mean(macd_values[-signal:]) if macd_values else 0.0
            else:
                signal_line = macd_line
            
            histogram = macd_line - signal_line
            
            return float(macd_line), float(signal_line), float(histogram)
        
        except Exception as e:
            logger.error(f"MACD calculation error: {e}")
            return 0.0, 0.0, 0.0
    
    # ===== Stochastic (from v16.0) =====
    @staticmethod
    def calculate_stochastic(
        ohlcv_data: List[List],
        period: int = 14,
        k_smooth: int = 3,
        d_smooth: int = 3
    ) -> Tuple[float, float]:
        """Calculate Stochastic Oscillator"""
        try:
            if len(ohlcv_data) < period:
                return 50.0, 50.0
            
            lows = np.array([float(c[3]) for c in ohlcv_data[-period:]])
            highs = np.array([float(c[2]) for c in ohlcv_data[-period:]])
            closes = np.array([float(c[4]) for c in ohlcv_data[-period:]])
            
            lowest_low = np.min(lows)
            highest_high = np.max(highs)
            
            if highest_high == lowest_low:
                return 50.0, 50.0
            
            k_values = []
            for i in range(len(closes)):
                lo = np.min(lows[max(0, i - period + 1):i + 1])
                hi = np.max(highs[max(0, i - period + 1):i + 1])
                if hi == lo:
                    k_values.append(50.0)
                else:
                    k = ((closes[i] - lo) / (hi - lo)) * 100
                    k_values.append(k)
            
            if len(k_values) >= k_smooth:
                k = np.mean(k_values[-k_smooth:])
            else:
                k = k_values[-1] if k_values else 50.0
            
            if len(k_values) >= d_smooth:
                d = np.mean(k_values[-d_smooth:])
            else:
                d = k
            
            return float(np.clip(k, 0, 100)), float(np.clip(d, 0, 100))
        
        except Exception as e:
            logger.error(f"Stochastic calculation error: {e}")
            return 50.0, 50.0
    
    # ===== ATR (from v16.0) =====
    @staticmethod
    def calculate_atr(ohlcv_data: List[List], period: int = 14) -> float:
        """Calculate Average True Range"""
        try:
            if len(ohlcv_data) < period:
                return 0.0
            
            tr_values = []
            
            for i in range(len(ohlcv_data)):
                high = float(ohlcv_data[i][2])
                low = float(ohlcv_data[i][3])
                close_prev = float(ohlcv_data[i - 1][4]) if i > 0 else high
                
                tr = max(
                    high - low,
                    abs(high - close_prev),
                    abs(low - close_prev)
                )
                tr_values.append(tr)
            
            if len(tr_values) < period:
                return np.mean(tr_values)
            
            multiplier = 2 / (period + 1)
            ema = np.mean(tr_values[:period])
            
            for tr in tr_values[period:]:
                ema = tr * multiplier + ema * (1 - multiplier)
            
            return float(ema)
        
        except Exception as e:
            logger.error(f"ATR calculation error: {e}")
            return 0.0
    
    # ===== Dynamic Stops (from v16.0) =====
    @staticmethod
    def calculate_dynamic_stops(
        entry_price: float,
        ohlcv_data: List[List],
        atr_multiplier: float = 1.5,
        min_stop_pct: float = 1.0,
        max_stop_pct: float = 5.0
    ) -> Tuple[float, float]:
        """Calculate dynamic stop losses based on ATR"""
        try:
            atr = EnhancedIndicatorAnalyzer.calculate_atr(ohlcv_data, 14)
            stop_distance = atr * atr_multiplier
            stop_loss_pct = (stop_distance / entry_price) * 100
            stop_loss_pct = np.clip(stop_loss_pct, min_stop_pct, max_stop_pct)
            stop_price = entry_price * (1 - stop_loss_pct / 100)
            
            return float(stop_price), float(stop_loss_pct)
        
        except Exception as e:
            logger.error(f"Dynamic stop calculation error: {e}")
            return entry_price * 0.985, 1.5
    
    # ===== COMPLETE ANALYSIS (NEW v17.0) =====
    def complete_analysis(
        self,
        ohlcv_data: List[List],
        current_price: float,
        market_volatility: float = 1.0,
        btc_trend: str = "neutral"
    ) -> Dict:
        """
        Complete multi-indicator analysis with signal optimization
        
        Args:
            ohlcv_data: OHLCV candle data (minimum 60 candles recommended)
            current_price: Current market price
            market_volatility: Volatility multiplier (0.5-2.0)
            btc_trend: BTC market trend ("bullish", "neutral", "bearish")
        
        Returns:
            Dict with complete analysis and recommendation
        """
        try:
            if len(ohlcv_data) < 52:
                return {
                    'status': 'insufficient_data',
                    'recommendation': 'WAIT',
                    'confidence': 0.0,
                    'message': f'Need 52+ candles, have {len(ohlcv_data)}'
                }
            
            # === Calculate all indicators ===
            
            # RSI
            rsi = self.calculate_rsi(ohlcv_data)
            rsi_oversold = rsi < 30
            rsi_overbought = rsi > 70
            
            # EMA
            ema_9 = self.calculate_ema(ohlcv_data, 9)
            ema_21 = self.calculate_ema(ohlcv_data, 21)
            ema_alignment = 0
            if current_price > ema_9 > ema_21:
                ema_alignment = 2
            elif current_price > ema_9 or ema_9 > ema_21:
                ema_alignment = 1
            elif current_price < ema_9 < ema_21:
                ema_alignment = -2
            
            # MACD
            macd, macd_signal, macd_hist = self.calculate_macd(ohlcv_data)
            macd_bullish = macd > macd_signal and macd_hist > 0
            macd_bearish = macd < macd_signal and macd_hist < 0
            
            # Stochastic
            k, d = self.calculate_stochastic(ohlcv_data)
            stoch_oversold = k < 20
            stoch_overbought = k > 80
            stoch_bullish_cross = k > d and (k - 5) <= d  # Recent crossover
            
            # Ichimoku (NEW v17.0)
            ichimoku_analysis = IchimokuAnalyzer.get_ichimoku_signals(ohlcv_data, current_price)
            
            # Volume Profile (NEW v17.0)
            volume_analysis = VolumeProfileAnalyzer.get_volume_signals(ohlcv_data, current_price)
            
            # === Prepare signal data for optimizer ===
            
            rsi_signal = {
                'oversold': rsi_oversold,
                'overbought': rsi_overbought,
                'value': rsi,
                'ema_alignment': ema_alignment
            }
            
            ema_signal = {
                'bullish': ema_alignment >= 1,
                'alignment': ema_alignment,
                'ema_9': ema_9,
                'ema_21': ema_21
            }
            
            macd_signal = {
                'bullish': macd_bullish,
                'bearish': macd_bearish,
                'histogram_positive': macd_hist > 0,
                'value': macd
            }
            
            stochastic_signal = {
                'oversold': stoch_oversold,
                'overbought': stoch_overbought,
                'bullish_crossover': stoch_bullish_cross,
                'value': k,
                'signal': d
            }
            
            volume_signal = {
                'at_poc': volume_analysis.get('at_poc', False),
                'support_level': volume_analysis.get('support_level', False),
                'poc_bullish': volume_analysis.get('volume_trend', {}).get('trend') == 'INCREASING',
                'strength': volume_analysis.get('volume_strength', 0)
            }
            
            # === Optimize and aggregate signals ===
            
            signal_result = self.optimizer.aggregate_signals(
                rsi_signal=rsi_signal,
                ema_signal=ema_signal,
                macd_signal=macd_signal,
                stochastic_signal=stochastic_signal,
                ichimoku_signal=ichimoku_analysis,
                volume_signal=volume_signal,
                volatility_level=market_volatility
            )
            
            # === Adjust for market conditions ===
            
            adjusted_threshold = self.optimizer.adjust_threshold_for_market_conditions(
                btc_trend=btc_trend,
                market_volatility=market_volatility,
                trading_session="american"  # Can be parameterized
            )
            
            # Final recommendation based on threshold
            if signal_result['confidence'] >= self.optimizer.strong_buy_threshold:
                final_recommendation = "STRONG_BUY"
            elif signal_result['confidence'] >= adjusted_threshold:
                final_recommendation = "BUY"
            else:
                final_recommendation = "SKIP"
            
            # === Compile comprehensive result ===
            
            result = {
                'status': 'ok',
                'recommendation': final_recommendation,
                'confidence': signal_result['confidence'],
                'adjusted_threshold': adjusted_threshold,
                'signal_analysis': self.optimizer.format_signal_report(signal_result),
                
                # Component values
                'components': {
                    'rsi': float(rsi),
                    'ema_9': float(ema_9),
                    'ema_21': float(ema_21),
                    'macd': float(macd.get('macd', 0.0) if isinstance(macd, dict) else macd),
                    'macd_signal': float(macd_signal.get('signal', 0.0) if isinstance(macd_signal, dict) else macd_signal),
                    'macd_histogram': float(macd_hist.get('histogram', 0.0) if isinstance(macd_hist, dict) else macd_hist),
                    'stochastic_k': float(k.get('k', 0.0) if isinstance(k, dict) else k),
                    'stochastic_d': float(d.get('d', 0.0) if isinstance(d, dict) else d),
                    'atr': float(self.calculate_atr(ohlcv_data))
                },
                
                # Signal details
                'signals': {
                    'rsi': rsi_signal,
                    'ema': ema_signal,
                    'macd': macd_signal,
                    'stochastic': stochastic_signal,
                    'ichimoku': ichimoku_analysis,
                    'volume': volume_analysis
                },
                
                # Trade setup
                'trade_setup': {
                    'entry_price': float(current_price),
                    'support_level': float(ichimoku_analysis['components'].get('tenkan', current_price * 0.99)),
                    'resistance_level': float(ichimoku_analysis['components'].get('kijun', current_price * 1.01)),
                    'atr_value': float(self.calculate_atr(ohlcv_data))
                }
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Complete analysis error: {e}", exc_info=True)
            return {
                'status': 'error',
                'recommendation': 'SKIP',
                'confidence': 0.0,
                'message': f'Analysis error: {str(e)}'
            }


try:
    from hydra_v17_config import config as _v17_config
    _default_optimizer = SignalOptimizer.from_config(
        _v17_config.get_signal_optimizer_config(),
        _v17_config.get_market_conditions_config(),
    )
except ImportError:
    _default_optimizer = SignalOptimizer()


analyzer = EnhancedIndicatorAnalyzer(optimizer=_default_optimizer)


# Example usage:
"""
In bot.py:

from indicators_v17 import analyzer

# In _scan_for_entries():
ohlcv = self.exchange.fetch_ohlcv(symbol, '1m', limit=60)
analysis = analyzer.complete_analysis(
    ohlcv_data=ohlcv,
    current_price=current_price,
    market_volatility=1.0,
    btc_trend="bullish"
)

# Log analysis
logger.info(analysis['signal_analysis'])

# Make decision
if analysis['recommendation'] in ['STRONG_BUY', 'BUY']:
    self._enter_trade(symbol, current_price, tickers)
"""
