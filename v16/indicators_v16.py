"""
Enhanced Indicators v16.0
Extends indicators.py with Stochastic Oscillator and Dynamic ATR Stops

New features:
✅ Stochastic Oscillator (%K, %D) for reversal confirmation
✅ ATR (Average True Range) for dynamic stop calculation
✅ Dynamic stops adapt to market volatility
"""

from typing import List, Dict, Tuple
import numpy as np
from logger_setup import logger


class EnhancedIndicatorAnalyzer:
    """Extended technical indicator analysis"""
    
    @staticmethod
    def calculate_stochastic(
        ohlcv_data: List[List],
        period: int = 14,
        k_smooth: int = 3,
        d_smooth: int = 3
    ) -> Tuple[float, float]:
        """
        Calculate Stochastic Oscillator
        
        Returns:
            (%K, %D) - values 0-100
            - %K: Fast stochastic line
            - %D: Signal line (EMA of %K)
            
            < 20: Oversold (bullish)
            > 80: Overbought (bearish)
            Crossovers: Entry signals
        """
        try:
            if len(ohlcv_data) < period:
                return 50.0, 50.0
            
            # Get OHLCV data
            lows = np.array([float(c[3]) for c in ohlcv_data[-period:]])
            highs = np.array([float(c[2]) for c in ohlcv_data[-period:]])
            closes = np.array([float(c[4]) for c in ohlcv_data[-period:]])
            
            # Calculate %K
            lowest_low = np.min(lows)
            highest_high = np.max(highs)
            
            if highest_high == lowest_low:
                return 50.0, 50.0
            
            raw_k = ((closes[-1] - lowest_low) / (highest_high - lowest_low)) * 100
            
            # Smooth %K
            k_values = []
            for i in range(len(closes)):
                lo = np.min(lows[max(0, i - period + 1):i + 1])
                hi = np.max(highs[max(0, i - period + 1):i + 1])
                if hi == lo:
                    k_values.append(50.0)
                else:
                    k = ((closes[i] - lo) / (hi - lo)) * 100
                    k_values.append(k)
            
            # Simple Moving Average for K smoothing
            if len(k_values) >= k_smooth:
                k = np.mean(k_values[-k_smooth:])
            else:
                k = k_values[-1] if k_values else 50.0
            
            # Calculate %D (SMA of K)
            if len(k_values) >= d_smooth:
                d = np.mean(k_values[-d_smooth:])
            else:
                d = k
            
            return float(np.clip(k, 0, 100)), float(np.clip(d, 0, 100))
        
        except Exception as e:
            logger.error(f"Stochastic calculation error: {e}")
            return 50.0, 50.0
    
    @staticmethod
    def calculate_atr(ohlcv_data: List[List], period: int = 14) -> float:
        """
        Calculate Average True Range
        
        Returns:
            float: ATR value (in same currency as price)
            
        Use for:
        - Dynamic stop losses
        - Position sizing
        - Volatility assessment
        """
        try:
            if len(ohlcv_data) < period:
                return 0.0
            
            tr_values = []
            
            for i in range(len(ohlcv_data)):
                high = float(ohlcv_data[i][2])
                low = float(ohlcv_data[i][3])
                close_prev = float(ohlcv_data[i - 1][4]) if i > 0 else high
                
                # True Range = max(H-L, |H-Pc|, |L-Pc|)
                tr = max(
                    high - low,
                    abs(high - close_prev),
                    abs(low - close_prev)
                )
                tr_values.append(tr)
            
            # ATR = EMA of TR
            if len(tr_values) < period:
                return np.mean(tr_values)
            
            # Calculate EMA
            multiplier = 2 / (period + 1)
            ema = np.mean(tr_values[:period])
            
            for tr in tr_values[period:]:
                ema = tr * multiplier + ema * (1 - multiplier)
            
            return float(ema)
        
        except Exception as e:
            logger.error(f"ATR calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_dynamic_stops(
        entry_price: float,
        ohlcv_data: List[List],
        atr_multiplier: float = 1.5,
        min_stop_pct: float = 1.0,
        max_stop_pct: float = 5.0
    ) -> Tuple[float, float]:
        """
        Calculate dynamic stop losses based on ATR
        
        Args:
            entry_price: Entry price for the trade
            ohlcv_data: OHLCV candle data
            atr_multiplier: How many ATRs below entry (default 1.5)
            min_stop_pct: Minimum stop loss % (default 1.0%)
            max_stop_pct: Maximum stop loss % (default 5.0%)
        
        Returns:
            (stop_price, stop_loss_pct)
        """
        try:
            atr = EnhancedIndicatorAnalyzer.calculate_atr(ohlcv_data, 14)
            
            # Calculate stop loss in percentage
            stop_distance = atr * atr_multiplier
            stop_loss_pct = (stop_distance / entry_price) * 100
            
            # Apply min/max bounds
            stop_loss_pct = np.clip(stop_loss_pct, min_stop_pct, max_stop_pct)
            
            # Calculate stop price
            stop_price = entry_price * (1 - stop_loss_pct / 100)
            
            return float(stop_price), float(stop_loss_pct)
        
        except Exception as e:
            logger.error(f"Dynamic stop calculation error: {e}")
            # Return default stop (1.5% below entry)
            return entry_price * 0.985, 1.5
    
    @staticmethod
    def get_stochastic_signal(k: float, d: float, prev_k: float = None) -> Dict:
        """
        Analyze Stochastic for entry/exit signals
        
        Args:
            k: Current %K value
            d: Current %D value
            prev_k: Previous %K (for crossover detection)
        
        Returns:
            Dict with signal analysis
        """
        signal = {
            'oversold': k < 20,
            'overbought': k > 80,
            'bullish_crossover': prev_k is not None and prev_k <= d and k > d,
            'bearish_crossover': prev_k is not None and prev_k >= d and k < d,
            'description': ''
        }
        
        if signal['oversold'] and signal['bullish_crossover']:
            signal['description'] = "🟢 Strong bullish (oversold + crossover up)"
            signal['strength'] = 3
        elif signal['oversold']:
            signal['description'] = "🟡 Oversold (potential reversal)"
            signal['strength'] = 2
        elif signal['bullish_crossover']:
            signal['description'] = "🟢 Bullish crossover"
            signal['strength'] = 2
        elif signal['overbought']:
            signal['description'] = "🔴 Overbought (avoid entry)"
            signal['strength'] = -2
        elif signal['bearish_crossover']:
            signal['description'] = "🔴 Bearish crossover"
            signal['strength'] = -1
        else:
            signal['description'] = "⚪ Neutral"
            signal['strength'] = 0
        
        return signal
