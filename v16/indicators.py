"""Base RSI / EMA / MACD analyzer for HYDRA v16."""
from typing import Dict, List, Tuple

import numpy as np

from config import config
from logger_setup import logger


class IndicatorAnalyzer:
    def get_signal_analysis(self, ohlcv_data: List[List]) -> Dict:
        cfg = config.get_indicator_config()
        rsi_period = cfg.get("rsi_period", 14)
        ema_fast = cfg.get("ema_fast", 9)
        ema_slow = cfg.get("ema_slow", 21)

        rsi = self._calculate_rsi(ohlcv_data, rsi_period)
        ema9 = self._calculate_ema(ohlcv_data, ema_fast)
        ema21 = self._calculate_ema(ohlcv_data, ema_slow)
        macd_line, macd_signal, macd_hist = self._calculate_macd(ohlcv_data)

        signals: List[str] = []
        score = 0

        if rsi < cfg.get("rsi_oversold", 30):
            signals.append("RSI oversold")
            score += 1
        elif rsi > cfg.get("rsi_overbought", 70):
            signals.append("RSI overbought")
            score -= 1

        if ema9 > ema21:
            signals.append("EMA bullish")
            score += 1
        elif ema9 < ema21:
            signals.append("EMA bearish")
            score -= 1

        if macd_line > macd_signal and macd_hist > 0:
            signals.append("MACD bullish")
            score += 1
        elif macd_line < macd_signal and macd_hist < 0:
            signals.append("MACD bearish")
            score -= 1

        return {
            "rsi": rsi,
            "ema9": ema9,
            "ema21": ema21,
            "macd": macd_line,
            "macd_signal": macd_signal,
            "macd_histogram": macd_hist,
            "score": score,
            "signals": signals,
        }

    def should_enter_trade(self, signal_analysis: Dict) -> Tuple[bool, str]:
        min_score = config.get_indicator_config().get("min_signal_score", 2)
        score = signal_analysis.get("score", 0)
        if score >= min_score:
            return True, f"Entry approved (score {score} >= {min_score})"
        return False, f"Entry rejected (score {score} < {min_score})"

    @staticmethod
    def _calculate_rsi(ohlcv_data: List[List], period: int = 14) -> float:
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
            return float(np.clip(100 - (100 / (1 + rs)), 0, 100))
        except Exception as e:
            logger.error(f"RSI calculation error: {e}")
            return 50.0

    @staticmethod
    def _calculate_ema(ohlcv_data: List[List], period: int = 9) -> float:
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

    @staticmethod
    def _calculate_macd(
        ohlcv_data: List[List],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> Tuple[float, float, float]:
        try:
            ema_fast = IndicatorAnalyzer._calculate_ema(ohlcv_data, fast)
            ema_slow = IndicatorAnalyzer._calculate_ema(ohlcv_data, slow)
            macd_line = ema_fast - ema_slow
            closes = [float(c[4]) for c in ohlcv_data]
            if len(closes) >= slow + signal:
                macd_values = []
                for i in range(slow - 1, len(closes)):
                    ema_f = IndicatorAnalyzer._calculate_ema(ohlcv_data[:i + 1], fast)
                    ema_s = IndicatorAnalyzer._calculate_ema(ohlcv_data[:i + 1], slow)
                    macd_values.append(ema_f - ema_s)
                signal_line = float(np.mean(macd_values[-signal:])) if macd_values else macd_line
            else:
                signal_line = macd_line
            return float(macd_line), float(signal_line), float(macd_line - signal_line)
        except Exception as e:
            logger.error(f"MACD calculation error: {e}")
            return 0.0, 0.0, 0.0
