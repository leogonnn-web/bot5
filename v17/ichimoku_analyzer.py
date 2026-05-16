"""
Ichimoku Cloud Analyzer v1.0
Complete Ichimoku Kinky Hyo implementation for trend analysis

Components:
✅ Tenkan-sen (Conversion Line) - 9-period
✅ Kijun-sen (Base Line) - 26-period
✅ Senkou Span A (Cloud boundary)
✅ Senkou Span B (Cloud boundary)
✅ Chikou Span (Momentum)

Trading Rules:
1. Price > Cloud → Bullish
2. Price < Cloud → Bearish
3. Tenkan > Kijun → Momentum up
4. Kijun > Senkou Span B → Trend strength

Entry Signals:
- Price above cloud + Tenkan > Kijun + Chikou in uptrend = STRONG BUY
- Price below cloud + Tenkan < Kijun + Chikou in downtrend = STRONG SELL
"""

from typing import List, Dict, Tuple
import numpy as np
from logger_setup import logger


class IchimokuAnalyzer:
    """Ichimoku Kinky Hyo technical analysis"""
    
    # Standard periods
    TENKAN_PERIOD = 9
    KIJUN_PERIOD = 26
    SENKOU_B_PERIOD = 52
    CHIKOU_SHIFT = 26
    
    @staticmethod
    def calculate_high_low(prices: List[float], period: int) -> Tuple[float, float]:
        """Calculate highest high and lowest low over period"""
        if len(prices) < period:
            prices = prices
        else:
            prices = prices[-period:]
        
        return max(prices), min(prices)
    
    @staticmethod
    def calculate_tenkan(ohlcv_data: List[List]) -> float:
        """
        Calculate Tenkan-sen (Conversion Line)
        = (9-period high + 9-period low) / 2
        """
        try:
            if len(ohlcv_data) < IchimokuAnalyzer.TENKAN_PERIOD:
                return 0.0
            
            closes = [float(c[4]) for c in ohlcv_data[-IchimokuAnalyzer.TENKAN_PERIOD:]]
            highs = [float(c[2]) for c in ohlcv_data[-IchimokuAnalyzer.TENKAN_PERIOD:]]
            lows = [float(c[3]) for c in ohlcv_data[-IchimokuAnalyzer.TENKAN_PERIOD:]]
            
            high_9 = max(highs)
            low_9 = min(lows)
            
            return (high_9 + low_9) / 2
        
        except Exception as e:
            logger.error(f"Tenkan calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_kijun(ohlcv_data: List[List]) -> float:
        """
        Calculate Kijun-sen (Base Line)
        = (26-period high + 26-period low) / 2
        """
        try:
            if len(ohlcv_data) < IchimokuAnalyzer.KIJUN_PERIOD:
                return 0.0
            
            closes = [float(c[4]) for c in ohlcv_data[-IchimokuAnalyzer.KIJUN_PERIOD:]]
            highs = [float(c[2]) for c in ohlcv_data[-IchimokuAnalyzer.KIJUN_PERIOD:]]
            lows = [float(c[3]) for c in ohlcv_data[-IchimokuAnalyzer.KIJUN_PERIOD:]]
            
            high_26 = max(highs)
            low_26 = min(lows)
            
            return (high_26 + low_26) / 2
        
        except Exception as e:
            logger.error(f"Kijun calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_senkou_span_a(ohlcv_data: List[List]) -> float:
        """
        Calculate Senkou Span A (Leading Span A)
        = (Tenkan + Kijun) / 2, plotted 26 periods ahead
        """
        try:
            tenkan = IchimokuAnalyzer.calculate_tenkan(ohlcv_data)
            kijun = IchimokuAnalyzer.calculate_kijun(ohlcv_data)
            
            return (tenkan + kijun) / 2
        
        except Exception as e:
            logger.error(f"Senkou Span A calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_senkou_span_b(ohlcv_data: List[List]) -> float:
        """
        Calculate Senkou Span B (Leading Span B)
        = (52-period high + 52-period low) / 2, plotted 26 periods ahead
        """
        try:
            if len(ohlcv_data) < IchimokuAnalyzer.SENKOU_B_PERIOD:
                return 0.0
            
            highs = [float(c[2]) for c in ohlcv_data[-IchimokuAnalyzer.SENKOU_B_PERIOD:]]
            lows = [float(c[3]) for c in ohlcv_data[-IchimokuAnalyzer.SENKOU_B_PERIOD:]]
            
            high_52 = max(highs)
            low_52 = min(lows)
            
            return (high_52 + low_52) / 2
        
        except Exception as e:
            logger.error(f"Senkou Span B calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_chikou_span(ohlcv_data: List[List], lookback: int = 26) -> float:
        """
        Calculate Chikou Span (Lagging Span)
        = Current close, plotted 26 periods in the past
        """
        try:
            if len(ohlcv_data) < lookback:
                if len(ohlcv_data) > 0:
                    return float(ohlcv_data[-1][4])
                return 0.0
            
            # Chikou is current close price
            return float(ohlcv_data[-1][4])
        
        except Exception as e:
            logger.error(f"Chikou calculation error: {e}")
            return 0.0
    
    @staticmethod
    def get_ichimoku_signals(
        ohlcv_data: List[List],
        current_price: float
    ) -> Dict:
        """
        Analyze Ichimoku and generate signals
        
        Returns:
            Dict with comprehensive Ichimoku analysis
        """
        try:
            if len(ohlcv_data) < 52:
                return {
                    'cloud_bullish': None,
                    'price_above_cloud': None,
                    'tenkan_above_kijun': None,
                    'signal_strength': 0,
                    'description': '⏳ Not enough data (need 52+ candles)',
                    'components': {}
                }
            
            # Calculate components
            tenkan = IchimokuAnalyzer.calculate_tenkan(ohlcv_data)
            kijun = IchimokuAnalyzer.calculate_kijun(ohlcv_data)
            senkou_a = IchimokuAnalyzer.calculate_senkou_span_a(ohlcv_data)
            senkou_b = IchimokuAnalyzer.calculate_senkou_span_b(ohlcv_data)
            chikou = IchimokuAnalyzer.calculate_chikou_span(ohlcv_data)
            
            # Cloud boundaries
            cloud_top = max(senkou_a, senkou_b)
            cloud_bottom = min(senkou_a, senkou_b)
            cloud_thickness = cloud_top - cloud_bottom
            
            # === Cloud Analysis ===
            cloud_bullish = senkou_a > senkou_b  # Cloud turning bullish
            price_above_cloud = current_price > cloud_top
            price_in_cloud = cloud_bottom <= current_price <= cloud_top
            price_below_cloud = current_price < cloud_bottom
            
            # === Line Analysis ===
            tenkan_above_kijun = tenkan > kijun
            chikou_above_price = chikou > current_price
            
            # === Signal Generation ===
            signals = []
            signal_strength = 0
            
            # Price position signals
            if price_above_cloud:
                signals.append("🟢 Price above cloud (bullish)")
                signal_strength += 2
            elif price_below_cloud:
                signals.append("🔴 Price below cloud (bearish)")
                signal_strength -= 2
            elif price_in_cloud:
                signals.append("🟡 Price in cloud (transition zone)")
                signal_strength += 0
            
            # Cloud trend
            if cloud_bullish:
                signals.append("🟢 Cloud trending bullish (Senkou A > B)")
                signal_strength += 1
            else:
                signals.append("🔴 Cloud trending bearish (Senkou A < B)")
                signal_strength -= 1
            
            # Line momentum
            if tenkan_above_kijun:
                signals.append("🟢 Tenkan > Kijun (momentum up)")
                signal_strength += 1
            else:
                signals.append("🔴 Tenkan < Kijun (momentum down)")
                signal_strength -= 1
            
            # Chikou confirmation
            if chikou_above_price and tenkan_above_kijun:
                signals.append("🟢🟢 Chikou above price + momentum up (strong)")
                signal_strength += 2
            elif chikou_above_price:
                signals.append("🟡 Chikou above price (confirmation)")
                signal_strength += 1
            
            # Cloud thickness (support/resistance strength)
            price_to_cloud_pct = ((current_price - cloud_bottom) / cloud_bottom) * 100 if cloud_bottom > 0 else 0
            
            if cloud_thickness > 0:
                if cloud_thickness > 0.05 * cloud_top:
                    signals.append("💪 Thick cloud (strong support/resistance)")
                    signal_strength += 0.5
                else:
                    signals.append("⚠️ Thin cloud (weak support/resistance)")
            
            # === Determine Overall Signal ===
            if signal_strength >= 4:
                description = "🟢🟢 STRONG BULLISH (all Ichimoku aligned)"
                recommendation = "STRONG_BUY"
            elif signal_strength >= 2:
                description = "🟢 BULLISH (cloud + momentum positive)"
                recommendation = "BUY"
            elif signal_strength >= 0:
                description = "🟡 NEUTRAL (mixed Ichimoku signals)"
                recommendation = "WAIT"
            elif signal_strength >= -2:
                description = "🔴 BEARISH (cloud + momentum negative)"
                recommendation = "AVOID"
            else:
                description = "🔴🔴 STRONG BEARISH (all Ichimoku against)"
                recommendation = "SELL"
            
            return {
                'cloud_bullish': cloud_bullish,
                'price_above_cloud': price_above_cloud,
                'price_in_cloud': price_in_cloud,
                'price_below_cloud': price_below_cloud,
                'tenkan_above_kijun': tenkan_above_kijun,
                'chikou_above_price': chikou_above_price,
                'signal_strength': signal_strength,
                'recommendation': recommendation,
                'description': description,
                'signals': signals,
                'components': {
                    'tenkan': float(tenkan),
                    'kijun': float(kijun),
                    'senkou_a': float(senkou_a),
                    'senkou_b': float(senkou_b),
                    'chikou': float(chikou),
                    'cloud_top': float(cloud_top),
                    'cloud_bottom': float(cloud_bottom),
                    'cloud_thickness': float(cloud_thickness)
                }
            }
        
        except Exception as e:
            logger.error(f"Ichimoku signal analysis error: {e}")
            return {
                'cloud_bullish': None,
                'price_above_cloud': None,
                'tenkan_above_kijun': None,
                'signal_strength': 0,
                'recommendation': 'ERROR',
                'description': f'Analysis error: {str(e)}',
                'signals': [],
                'components': {}
            }
    
    @staticmethod
    def find_support_resistance(
        ohlcv_data: List[List],
        current_price: float
    ) -> Dict:
        """
        Use Ichimoku levels as support/resistance
        
        Returns:
            Dict with support/resistance levels
        """
        try:
            tenkan = IchimokuAnalyzer.calculate_tenkan(ohlcv_data)
            kijun = IchimokuAnalyzer.calculate_kijun(ohlcv_data)
            senkou_a = IchimokuAnalyzer.calculate_senkou_span_a(ohlcv_data)
            senkou_b = IchimokuAnalyzer.calculate_senkou_span_b(ohlcv_data)
            
            # Identify support and resistance
            levels = sorted([tenkan, kijun, senkou_a, senkou_b])
            
            # Support (below current price)
            support_levels = [l for l in levels if l < current_price]
            # Resistance (above current price)
            resistance_levels = [l for l in levels if l > current_price]
            
            return {
                'nearest_support': support_levels[-1] if support_levels else None,
                'nearest_resistance': resistance_levels[0] if resistance_levels else None,
                'all_supports': support_levels,
                'all_resistances': resistance_levels,
                'support_distance_pct': ((current_price - support_levels[-1]) / support_levels[-1] * 100) if support_levels else 0,
                'resistance_distance_pct': ((resistance_levels[0] - current_price) / current_price * 100) if resistance_levels else 0
            }
        
        except Exception as e:
            logger.error(f"Support/Resistance error: {e}")
            return {
                'nearest_support': None,
                'nearest_resistance': None,
                'all_supports': [],
                'all_resistances': []
            }


# Example usage:
"""
In bot.py, in _scan_for_entries():

from ichimoku_analyzer import IchimokuAnalyzer

ohlcv = self.exchange.fetch_ohlcv(symbol, '1m', limit=60)
ichimoku_signal = IchimokuAnalyzer.get_ichimoku_signals(ohlcv, current_price)

# Log signals
for sig in ichimoku_signal['signals']:
    logger.info(f"   {sig}")

# Get support/resistance
sr = IchimokuAnalyzer.find_support_resistance(ohlcv, current_price)
logger.info(f"   Support: ${sr['nearest_support']:.8f} | Resistance: ${sr['nearest_resistance']:.8f}")

# Use in signal aggregation
if ichimoku_signal['recommendation'] in ['STRONG_BUY', 'BUY']:
    # Entry signal is valid
    pass
"""
