"""
Volume Profile Analyzer v1.0
Point of Control (POC) and volume-based price level analysis

Features:
✅ POC (Point of Control) - price level with highest volume
✅ Value Area (VA) - 70% of volume range
✅ Volume Profile visualization data
✅ Support/Resistance from volume clusters
✅ Volume trend analysis (increasing/decreasing)
✅ Volume spike detection

Usage:
- POC = support/resistance level (traders accumulate here)
- Price at POC = optimal entry (high liquidity)
- Price above POC = sellers control
- Price below POC = buyers control
"""

from typing import List, Dict, Tuple
import numpy as np
from logger_setup import logger


class VolumeProfileAnalyzer:
    """Volume profile and Point of Control analysis"""
    
    @staticmethod
    def calculate_poc(
        ohlcv_data: List[List],
        bins: int = 20
    ) -> Tuple[float, Dict]:
        """
        Calculate Point of Control (POC)
        Price level with highest cumulative volume
        
        Args:
            ohlcv_data: OHLCV candle data
            bins: Number of price bins (default 20)
        
        Returns:
            (poc_price, profile_dict)
        """
        try:
            if len(ohlcv_data) < 5:
                return 0.0, {}
            
            # Extract data
            highs = np.array([float(c[2]) for c in ohlcv_data])
            lows = np.array([float(c[3]) for c in ohlcv_data])
            closes = np.array([float(c[4]) for c in ohlcv_data])
            volumes = np.array([float(c[5]) if c[5] else 0 for c in ohlcv_data])
            
            # Use typical price (HLC/3) as price level
            typical_prices = (highs + lows + closes) / 3
            
            # Create price bins
            price_min = np.min(lows)
            price_max = np.max(highs)
            bin_edges = np.linspace(price_min, price_max, bins + 1)
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
            
            # Assign volumes to bins
            bin_volumes = np.zeros(bins)
            for i, price in enumerate(typical_prices):
                bin_idx = np.digitize(price, bin_edges) - 1
                bin_idx = np.clip(bin_idx, 0, bins - 1)
                bin_volumes[bin_idx] += volumes[i]
            
            # Find POC
            poc_idx = np.argmax(bin_volumes)
            poc_price = bin_centers[poc_idx]
            
            # Create profile
            profile = {
                'poc_price': float(poc_price),
                'poc_volume': float(bin_volumes[poc_idx]),
                'price_levels': [float(p) for p in bin_centers],
                'volumes': [float(v) for v in bin_volumes],
                'price_range': (float(price_min), float(price_max)),
                'total_volume': float(np.sum(volumes))
            }
            
            return float(poc_price), profile
        
        except Exception as e:
            logger.error(f"POC calculation error: {e}")
            return 0.0, {}
    
    @staticmethod
    def calculate_value_area(
        ohlcv_data: List[List],
        bins: int = 20,
        va_percent: float = 70.0
    ) -> Dict:
        """
        Calculate Value Area (VA)
        Price range containing specified percentage of volume
        
        Args:
            ohlcv_data: OHLCV data
            bins: Number of price bins
            va_percent: Percentage of volume to include (default 70%)
        
        Returns:
            Dict with VA high, low, and range
        """
        try:
            poc_price, profile = VolumeProfileAnalyzer.calculate_poc(ohlcv_data, bins)
            
            if not profile:
                return {'va_high': 0, 'va_low': 0, 'va_range': 0}
            
            # Sort bins by volume and accumulate
            volumes = np.array(profile['volumes'])
            total_volume = np.sum(volumes)
            target_volume = total_volume * (va_percent / 100)
            
            # Find which bins contain the target volume
            sorted_indices = np.argsort(volumes)[::-1]  # Descending
            accumulated = 0
            va_indices = []
            
            for idx in sorted_indices:
                accumulated += volumes[idx]
                va_indices.append(idx)
                if accumulated >= target_volume:
                    break
            
            va_indices = sorted(va_indices)
            price_levels = profile['price_levels']
            
            va_low = price_levels[va_indices[0]]
            va_high = price_levels[va_indices[-1]]
            
            return {
                'va_high': float(va_high),
                'va_low': float(va_low),
                'va_range': float(va_high - va_low),
                'va_midpoint': float((va_high + va_low) / 2),
                'va_volume': float(accumulated),
                'va_percent': float((accumulated / total_volume) * 100)
            }
        
        except Exception as e:
            logger.error(f"Value Area calculation error: {e}")
            return {'va_high': 0, 'va_low': 0, 'va_range': 0}
    
    @staticmethod
    def detect_volume_clusters(
        ohlcv_data: List[List],
        threshold_percentile: float = 75.0
    ) -> List[Dict]:
        """
        Detect price levels with abnormally high volume
        
        Returns:
            List of volume clusters with prices and volumes
        """
        try:
            volumes = np.array([float(c[5]) if c[5] else 0 for c in ohlcv_data])
            closes = np.array([float(c[4]) for c in ohlcv_data])
            
            # Find threshold
            threshold = np.percentile(volumes, threshold_percentile)
            
            # Find clusters
            clusters = []
            in_cluster = False
            cluster_start = 0
            
            for i, vol in enumerate(volumes):
                if vol > threshold:
                    if not in_cluster:
                        cluster_start = i
                        in_cluster = True
                else:
                    if in_cluster:
                        cluster_volume = np.sum(volumes[cluster_start:i])
                        cluster_price = np.mean(closes[cluster_start:i])
                        clusters.append({
                            'price': float(cluster_price),
                            'volume': float(cluster_volume),
                            'strength': float(cluster_volume / np.sum(volumes) * 100),
                            'candles': i - cluster_start
                        })
                        in_cluster = False
            
            # Don't forget last cluster
            if in_cluster:
                cluster_volume = np.sum(volumes[cluster_start:])
                cluster_price = np.mean(closes[cluster_start:])
                clusters.append({
                    'price': float(cluster_price),
                    'volume': float(cluster_volume),
                    'strength': float(cluster_volume / np.sum(volumes) * 100),
                    'candles': len(volumes) - cluster_start
                })
            
            return sorted(clusters, key=lambda x: x['volume'], reverse=True)
        
        except Exception as e:
            logger.error(f"Volume cluster detection error: {e}")
            return []
    
    @staticmethod
    def analyze_volume_trend(
        ohlcv_data: List[List],
        lookback: int = 10
    ) -> Dict:
        """
        Analyze volume trend (increasing, decreasing, or stable)
        
        Returns:
            Dict with volume trend analysis
        """
        try:
            if len(ohlcv_data) < lookback:
                lookback = len(ohlcv_data)
            
            volumes = np.array([float(c[5]) if c[5] else 0 for c in ohlcv_data[-lookback:]])
            
            # Calculate average volume
            avg_volume = np.mean(volumes)
            recent_volume = np.mean(volumes[-3:])  # Last 3 candles
            
            # Volume trend
            if recent_volume > avg_volume * 1.2:
                trend = "INCREASING"
                strength = "strong"
            elif recent_volume > avg_volume:
                trend = "INCREASING"
                strength = "weak"
            elif recent_volume < avg_volume * 0.8:
                trend = "DECREASING"
                strength = "strong"
            else:
                trend = "DECREASING"
                strength = "weak"
            
            # Volatility based on volume
            volume_std = np.std(volumes)
            volume_cv = volume_std / avg_volume if avg_volume > 0 else 0
            
            return {
                'trend': trend,
                'strength': strength,
                'current_volume': float(recent_volume),
                'average_volume': float(avg_volume),
                'volume_ratio': float(recent_volume / avg_volume) if avg_volume > 0 else 0,
                'volatility': float(volume_cv),
                'description': f"{trend} volume ({strength})" if volume_cv < 0.5 else f"{trend} volume with spikes"
            }
        
        except Exception as e:
            logger.error(f"Volume trend analysis error: {e}")
            return {
                'trend': 'UNKNOWN',
                'description': f'Error: {str(e)}'
            }
    
    @staticmethod
    def get_volume_signals(
        ohlcv_data: List[List],
        current_price: float
    ) -> Dict:
        """
        Generate trading signals based on volume profile
        
        Returns:
            Dict with volume-based trading signals
        """
        try:
            if len(ohlcv_data) < 10:
                return {
                    'at_poc': False,
                    'support_level': False,
                    'resistance_level': False,
                    'volume_strength': 0,
                    'signals': [],
                    'recommendation': 'INSUFFICIENT_DATA'
                }
            
            # Calculate POC
            poc_price, profile = VolumeProfileAnalyzer.calculate_poc(ohlcv_data)
            
            # Calculate Value Area
            va = VolumeProfileAnalyzer.calculate_value_area(ohlcv_data)
            
            # Get volume clusters
            clusters = VolumeProfileAnalyzer.detect_volume_clusters(ohlcv_data)
            
            # Analyze volume trend
            vol_trend = VolumeProfileAnalyzer.analyze_volume_trend(ohlcv_data)
            
            # Price relative to POC
            price_to_poc_distance = abs(current_price - poc_price) / poc_price * 100
            at_poc = price_to_poc_distance < 0.5  # Within 0.5%
            
            # Support/Resistance
            price_above_poc = current_price > poc_price
            
            # Find nearby clusters
            nearby_cluster = None
            if clusters:
                for cluster in clusters[:3]:  # Top 3 clusters
                    cluster_distance = abs(current_price - cluster['price']) / cluster['price'] * 100
                    if cluster_distance < 2.0:  # Within 2%
                        nearby_cluster = cluster
                        break
            
            # Generate signals
            signals = []
            signal_strength = 0
            
            # POC signal
            if at_poc:
                signals.append("🟢 Price at POC (optimal entry)")
                signal_strength += 2
            elif price_above_poc:
                signals.append("⚠️ Price above POC (potential resistance)")
                signal_strength -= 1
            else:
                signals.append("🟡 Price below POC (potential support)")
                signal_strength += 0
            
            # Value Area signal
            if current_price > va['va_high']:
                signals.append("⚠️ Price above Value Area (extension)")
            elif current_price < va['va_low']:
                signals.append("🟡 Price below Value Area (extension)")
            else:
                signals.append("🟢 Price in Value Area (consolidating)")
                signal_strength += 1
            
            # Volume cluster signal
            if nearby_cluster:
                signals.append(f"🟢 Near volume cluster at ${nearby_cluster['price']:.8f} ({nearby_cluster['strength']:.1f}%)")
                signal_strength += 1
            
            # Volume trend signal
            if vol_trend['trend'] == 'INCREASING' and vol_trend['strength'] == 'strong':
                signals.append("🟢🟢 Volume increasing (strong conviction)")
                signal_strength += 2
            elif vol_trend['trend'] == 'INCREASING':
                signals.append("🟢 Volume increasing")
                signal_strength += 1
            elif vol_trend['trend'] == 'DECREASING' and vol_trend['strength'] == 'strong':
                signals.append("🔴 Volume decreasing (weak conviction)")
                signal_strength -= 1
            
            # Recommendation
            if signal_strength >= 3:
                recommendation = "STRONG_BUY"
            elif signal_strength >= 1:
                recommendation = "BUY"
            elif signal_strength >= -1:
                recommendation = "NEUTRAL"
            else:
                recommendation = "SELL"
            
            return {
                'at_poc': at_poc,
                'poc_price': float(poc_price),
                'price_to_poc_pct': float(price_to_poc_distance),
                'support_level': not price_above_poc,
                'resistance_level': price_above_poc,
                'value_area': va,
                'volume_clusters': clusters[:3],
                'volume_trend': vol_trend,
                'volume_strength': signal_strength,
                'signals': signals,
                'recommendation': recommendation
            }
        
        except Exception as e:
            logger.error(f"Volume signal analysis error: {e}")
            return {
                'at_poc': False,
                'signals': [f"Error: {str(e)}"],
                'recommendation': 'ERROR',
                'volume_strength': 0
            }


# Example usage:
"""
In bot.py, in _scan_for_entries():

from volume_profile import VolumeProfileAnalyzer

ohlcv = self.exchange.fetch_ohlcv(symbol, '1m', limit=50)
volume_signal = VolumeProfileAnalyzer.get_volume_signals(ohlcv, current_price)

# Log signals
for sig in volume_signal['signals']:
    logger.info(f"   {sig}")

# Check if at POC
if volume_signal['at_poc']:
    logger.info(f"   ✅ Price at POC - optimal entry point")

# Use in signal aggregation
volume_input = {
    'at_poc': volume_signal['at_poc'],
    'support_level': volume_signal['support_level'],
    'poc_bullish': volume_signal['volume_trend']['trend'] == 'INCREASING'
}
"""
