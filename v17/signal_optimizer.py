"""
Signal Optimizer v1.0 - Intelligent Multi-Indicator Signal Aggregation
Solves conflicts between different indicators and provides weighted consensus

Features:
✅ Weighted signal aggregation (RSI + EMA + MACD + Stochastic + Ichimoku + Volume)
✅ Conflict detection and resolution
✅ Confidence scoring (0-100)
✅ Signal strength ranking
✅ Volatility adjustment
✅ Trend alignment checking

Signal Scoring:
- RSI oversold (< 30): +2 points
- EMA bullish alignment: +2 points  
- MACD bullish: +1 point
- Stochastic oversold + crossover: +3 points
- Ichimoku cloud bullish: +2 points
- Volume POC support: +1.5 points

Max Score: 11.5 points → Confidence: 100%
Min Score: -5 points → Reject trade
"""

from typing import Dict, List, Tuple, Optional

import numpy as np
from logger_setup import logger


class SignalOptimizer:
    """Intelligent signal aggregation and conflict resolution"""
    
    @classmethod
    def from_config(
        cls,
        signal_optimizer: Optional[dict] = None,
        market_conditions: Optional[dict] = None,
    ) -> 'SignalOptimizer':
        so = dict(signal_optimizer or {})
        mc = dict(market_conditions or {})
        return cls(
            signal_weights=so.get('signal_weights'),
            min_confidence_threshold=so.get('min_confidence_threshold', 50),
            strong_buy_threshold=so.get('strong_buy_threshold'),
            use_conflict_detection=so.get('use_conflict_detection', True),
            volatility_adjusted=so.get('volatility_adjusted', True),
            apply_volatility_to_threshold=mc.get('volatility_adjustment', True),
            apply_session_to_threshold=mc.get('trading_session_adjustment', True),
        )

    def __init__(
        self,
        signal_weights: Optional[dict] = None,
        min_confidence_threshold: float = 50.0,
        strong_buy_threshold: Optional[float] = None,
        use_conflict_detection: bool = True,
        volatility_adjusted: bool = True,
        apply_volatility_to_threshold: bool = True,
        apply_session_to_threshold: bool = True,
    ):
        default_weights = {
            'rsi': 2.0,
            'ema': 2.0,
            'macd': 1.0,
            'stochastic': 3.0,
            'ichimoku': 2.0,
            'volume_poc': 1.5,
        }
        self.signal_weights = {**default_weights, **(signal_weights or {})}
        self.min_confidence_threshold = float(min_confidence_threshold)
        if strong_buy_threshold is not None:
            self.strong_buy_threshold = float(strong_buy_threshold)
        else:
            self.strong_buy_threshold = max(75.0, self.min_confidence_threshold + 15.0)
        self.use_conflict_detection = use_conflict_detection
        self.volatility_adjusted = volatility_adjusted
        self.apply_volatility_to_threshold = apply_volatility_to_threshold
        self.apply_session_to_threshold = apply_session_to_threshold

        self.max_possible_score = sum(self.signal_weights.values())
    
    def aggregate_signals(
        self,
        rsi_signal: Dict,
        ema_signal: Dict,
        macd_signal: Dict,
        stochastic_signal: Dict = None,
        ichimoku_signal: Dict = None,
        volume_signal: Dict = None,
        volatility_level: float = 1.0
    ) -> Dict:
        """
        Aggregate all signals into single confidence score
        
        Args:
            rsi_signal: {'oversold': bool, 'overbought': bool, 'value': float}
            ema_signal: {'bullish': bool, 'alignment': int}
            macd_signal: {'bullish': bool, 'histogram_positive': bool}
            stochastic_signal: {'oversold': bool, 'bullish_crossover': bool}
            ichimoku_signal: {'cloud_bullish': bool, 'price_above_cloud': bool}
            volume_signal: {'at_poc': bool, 'support_level': bool}
            volatility_level: Adjustment factor (1.0 = normal, 1.5 = high volatility)
        
        Returns:
            Dict with aggregate score, confidence, and recommendation
        """
        try:
            score = 0.0
            signals_fired = []
            conflicts = []
            
            # === RSI Analysis (2 points max) ===
            if rsi_signal['oversold']:
                score += self.signal_weights['rsi']
                signals_fired.append("🟢 RSI oversold (bullish)")
            elif rsi_signal['overbought']:
                score -= 2.5
                conflicts.append("🔴 RSI overbought (avoid)")
            
            # === EMA Analysis (2 points max) ===
            ema_alignment = rsi_signal.get('ema_alignment', 0)
            if ema_alignment >= 2:  # Price > EMA9 > EMA21
                score += self.signal_weights['ema']
                signals_fired.append("🟢 EMA strong uptrend")
            elif ema_alignment == 1:
                score += 1.0
                signals_fired.append("🟡 EMA weak uptrend")
            elif ema_alignment <= -1:
                score -= 1.5
                conflicts.append("🔴 EMA downtrend")
            
            # === MACD Analysis (1 point max) ===
            if macd_signal.get('bullish'):
                score += self.signal_weights['macd']
                signals_fired.append("🟢 MACD bullish")
            elif macd_signal.get('bearish'):
                score -= 1.5
                conflicts.append("🔴 MACD bearish")
            
            # === Stochastic Analysis (3 points max) ===
            if stochastic_signal:
                if stochastic_signal.get('oversold') and stochastic_signal.get('bullish_crossover'):
                    score += self.signal_weights['stochastic']
                    signals_fired.append("🟢🟢 Stochastic oversold + crossover UP")
                elif stochastic_signal.get('oversold'):
                    score += 2.0
                    signals_fired.append("🟢 Stochastic oversold")
                elif stochastic_signal.get('bullish_crossover'):
                    score += 1.5
                    signals_fired.append("🟢 Stochastic bullish crossover")
                elif stochastic_signal.get('overbought'):
                    score -= 2.0
                    conflicts.append("🔴 Stochastic overbought")
                elif stochastic_signal.get('bearish_crossover'):
                    score -= 1.0
                    conflicts.append("🔴 Stochastic bearish crossover")
            
            # === Ichimoku Analysis (2 points max) ===
            if ichimoku_signal:
                if ichimoku_signal.get('cloud_bullish') and ichimoku_signal.get('price_above_cloud'):
                    score += self.signal_weights['ichimoku']
                    signals_fired.append("🟢 Ichimoku cloud bullish (price above)")
                elif ichimoku_signal.get('cloud_bullish'):
                    score += 1.5
                    signals_fired.append("🟡 Ichimoku cloud bullish")
                elif ichimoku_signal.get('price_above_cloud'):
                    score += 1.0
                    signals_fired.append("🟡 Price above Ichimoku cloud")
                
                if ichimoku_signal.get('tenkan_above_kijun'):
                    score += 0.5
                    signals_fired.append("🟢 Tenkan > Kijun (momentum up)")
                
                if ichimoku_signal.get('cloud_bearish'):
                    score -= 2.0
                    conflicts.append("🔴 Ichimoku cloud bearish")
            
            # === Volume Profile Analysis (1.5 points max) ===
            if volume_signal:
                if volume_signal.get('at_poc'):
                    score += self.signal_weights['volume_poc']
                    signals_fired.append("🟢 Price at POC (high liquidity)")
                elif volume_signal.get('support_level'):
                    score += 1.0
                    signals_fired.append("🟡 Price near volume support")
                
                if volume_signal.get('poc_bullish'):
                    score += 0.3
                    signals_fired.append("🟢 POC trending bullish")
            
            # === Conflict Detection ===
            has_major_conflict = False
            if self.use_conflict_detection:
                has_major_conflict = len(conflicts) >= 2
                if has_major_conflict:
                    logger.warning(f"⚠️ Signal conflict detected: {conflicts}")
                    score *= 0.7

            # === Volatility Adjustment (aggregate score) ===
            if self.volatility_adjusted:
                if volatility_level > 1.3:
                    score *= 0.85
                    signals_fired.append("⚠️ High volatility detected (threshold raised)")
                elif volatility_level < 0.7:
                    score *= 1.1
                    signals_fired.append("✅ Low volatility (threshold relaxed)")
            
            # === Calculate Confidence ===
            confidence = (score / self.max_possible_score) * 100
            confidence = max(0, min(100, confidence))  # Clamp 0-100
            
            min_c = self.min_confidence_threshold
            strong_t = self.strong_buy_threshold
            caution_line = max(0.0, min_c - 10.0)

            # === Decision Making ===
            if has_major_conflict and confidence < min_c:
                recommendation = "SKIP"
                reason = "Multiple conflicting signals reduce confidence"
            elif confidence >= strong_t:
                recommendation = "STRONG_BUY"
                reason = "Strong consensus from multiple indicators"
            elif confidence >= min_c:
                recommendation = "BUY"
                reason = "Good signal alignment"
            elif confidence >= caution_line:
                recommendation = "CAUTION"
                reason = "Weak signal - use with manual confirmation"
            else:
                recommendation = "SKIP"
                reason = "Insufficient confidence"
            
            result = {
                'recommendation': recommendation,
                'confidence': float(np.clip(confidence, 0, 100)),
                'score': float(score),
                'max_score': float(self.max_possible_score),
                'signals_fired': signals_fired,
                'conflicts': conflicts,
                'reason': reason,
                'volatility_adjusted': volatility_level != 1.0
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Error aggregating signals: {e}")
            return {
                'recommendation': 'SKIP',
                'confidence': 0.0,
                'score': 0.0,
                'signals_fired': [],
                'conflicts': [f"Error: {str(e)}"],
                'reason': 'Analysis error'
            }
    
    def format_signal_report(self, signal_data: Dict) -> str:
        """Format signal analysis into readable report"""
        try:
            lines = []
            
            # Header
            conf = signal_data['confidence']
            min_c = getattr(self, 'min_confidence_threshold', 50)
            strong_t = getattr(self, 'strong_buy_threshold', 75)
            caution_line = max(0.0, min_c - 10.0)
            if conf >= strong_t:
                header = "🟢🟢 STRONG SIGNAL"
            elif conf >= min_c:
                header = "🟢 GOOD SIGNAL"
            elif conf >= caution_line:
                header = "🟡 WEAK SIGNAL"
            else:
                header = "🔴 SKIP"
            
            lines.append(f"{header} | Confidence: {conf:.1f}% ({signal_data['score']:.1f}/{signal_data['max_score']:.1f})")
            
            # Positive signals
            if signal_data['signals_fired']:
                for sig in signal_data['signals_fired']:
                    lines.append(f"   ✅ {sig}")
            
            # Conflicts
            if signal_data['conflicts']:
                for conf_sig in signal_data['conflicts']:
                    lines.append(f"   ⚠️ {conf_sig}")
            
            # Reason
            lines.append(f"   → {signal_data['reason']}")
            
            return "\n".join(lines)
        
        except Exception as e:
            logger.error(f"Error formatting report: {e}")
            return "Error in signal report"
    
    def adjust_threshold_for_market_conditions(
        self,
        btc_trend: str,  # "bullish", "neutral", "bearish"
        market_volatility: float,  # 0.5 to 2.0
        trading_session: str  # "asian", "european", "american"
    ) -> float:
        """
        Dynamically adjust confidence threshold based on market conditions
        
        Returns:
            Adjusted confidence threshold (40-70%)
        """
        base_threshold = float(self.min_confidence_threshold)

        # BTC trend adjustment
        if btc_trend == "bullish":
            base_threshold -= 5
        elif btc_trend == "bearish":
            base_threshold += 10

        if self.apply_volatility_to_threshold:
            if market_volatility > 1.5:
                base_threshold += 5
            elif market_volatility < 0.7:
                base_threshold -= 3

        if self.apply_session_to_threshold:
            if trading_session == "asian":
                base_threshold += 3
            elif trading_session == "american":
                base_threshold -= 2
        
        return float(np.clip(base_threshold, 40, 70))
    
    def detect_signal_divergence(
        self,
        rsi_trend: str,  # "up", "down", "neutral"
        price_trend: str,
        macd_trend: str,
        volume_trend: str
    ) -> Dict:
        """
        Detect divergences between indicators
        
        Returns:
            Dict with divergence analysis
        """
        divergences = []
        
        # Bullish divergence: Price down, indicators up
        if price_trend == "down" and rsi_trend == "up":
            divergences.append("🟢 Bullish RSI divergence (price down, RSI up)")
        
        if price_trend == "down" and macd_trend == "up":
            divergences.append("🟢 Bullish MACD divergence (price down, MACD up)")
        
        # Bearish divergence: Price up, indicators down
        if price_trend == "up" and rsi_trend == "down":
            divergences.append("🔴 Bearish RSI divergence (price up, RSI down)")
        
        if price_trend == "up" and macd_trend == "down":
            divergences.append("🔴 Bearish MACD divergence (price up, MACD down)")
        
        # Volume divergence
        if price_trend == "up" and volume_trend == "down":
            divergences.append("⚠️ Weak uptrend (volume decreasing)")
        
        if price_trend == "down" and volume_trend == "up":
            divergences.append("⚠️ Strong downtrend (volume increasing)")
        
        return {
            'has_divergence': len(divergences) > 0,
            'divergences': divergences,
            'strength': "strong" if len(divergences) >= 2 else "weak"
        }


# Example usage:
"""
In bot.py, in _scan_for_entries():

from signal_optimizer import SignalOptimizer
from indicators_v17 import EnhancedIndicatorAnalyzer

optimizer = SignalOptimizer()

# Collect all signals
rsi_signal = {'oversold': True, 'overbought': False, 'ema_alignment': 2}
ema_signal = {'bullish': True, 'alignment': 2}
macd_signal = {'bullish': True, 'histogram_positive': True}
stoch_signal = {'oversold': True, 'bullish_crossover': True}
ichimoku_signal = {'cloud_bullish': True, 'price_above_cloud': True}
volume_signal = {'at_poc': True, 'support_level': True}

# Aggregate
result = optimizer.aggregate_signals(
    rsi_signal=rsi_signal,
    ema_signal=ema_signal,
    macd_signal=macd_signal,
    stochastic_signal=stoch_signal,
    ichimoku_signal=ichimoku_signal,
    volume_signal=volume_signal,
    volatility_level=1.0
)

# Format and log
report = optimizer.format_signal_report(result)
logger.info(f"Signal Analysis:\n{report}")

# Make decision
if result['recommendation'] in ['STRONG_BUY', 'BUY']:
    self._enter_trade(symbol, price_now, tickers)
"""
