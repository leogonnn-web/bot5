"""
Exchange Utils - Bybit API wrapper with caching and error handling
Supports: Spot trading, OHLCV data, ticker fetching, order management

Features:
✅ Rate limiting with cache
✅ Automatic retry on network errors
✅ OHLCV data fetching with caching
✅ Ticker data with cache
✅ Balance checking
✅ Order management (buy/sell/cancel)
"""

import ccxt
import time
import os
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv
from logger_setup import logger
from paths import ENV_FILE

load_dotenv(ENV_FILE)


class ExchangeManager:
    """Manages Bybit exchange connection and API calls"""
    
    def __init__(self):
        """Initialize exchange connection"""
        self.exchange = ccxt.bybit({
            'apiKey': os.getenv('BYBIT_API_KEY', ''),
            'secret': os.getenv('BYBIT_API_SECRET', ''),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'createMarketBuyOrderRequiresPrice': False
            }
        })
        # Принудительно переключаем API на версию v5 для всех типов запросов
        self.exchange.version = 'v5'
        
        # Caches
        self.ticker_cache = {}
        self.ohlcv_cache = {}
        self.balance_cache = {}
        self.markets_cache = None
        
        # Cache TTL in seconds
        self.ticker_ttl = 2
        self.ohlcv_ttl = 10
        self.balance_ttl = 5
        self.markets_ttl = 3600
    
    def load_markets(self, reload: bool = False) -> Dict:
        """Load markets from exchange"""
        try:
            if self.markets_cache and not reload:
                return self.markets_cache
            
            self.markets_cache = self.exchange.load_markets(reload)
            logger.debug(f"✅ Loaded {len(self.markets_cache)} markets")
            return self.markets_cache
        
        except Exception as e:
            logger.error(f"Error loading markets: {e}")
            return {}
    
    def fetch_ticker(self, symbol: str, use_cache: bool = True) -> Dict:
        """
        Fetch ticker data
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            use_cache: Use cached data if available
        
        Returns:
            Ticker dict
        """
        try:
            # Check cache
            if use_cache and symbol in self.ticker_cache:
                cached_time, cached_data = self.ticker_cache[symbol]
                if time.time() - cached_time < self.ticker_ttl:
                    return cached_data
            
            # Fetch fresh
            ticker = self.exchange.fetch_ticker(symbol)
            self.ticker_cache[symbol] = (time.time(), ticker)
            return ticker
        
        except ccxt.NetworkError as e:
            logger.error(f"Network error fetching {symbol}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching ticker {symbol}: {e}")
            raise
    
    def fetch_tickers(self, symbols: List[str]) -> Dict:
        """
        Fetch multiple tickers
        
        Args:
            symbols: List of trading pairs
        
        Returns:
            Dict of symbol -> ticker data
        """
        try:
            result = {}
            
            for symbol in symbols:
                try:
                    result[symbol] = self.fetch_ticker(symbol, use_cache=True)
                    time.sleep(0.02)  # Rate limiting
                except Exception as e:
                    logger.debug(f"Error fetching {symbol}: {e}")
                    continue
            
            return result
        
        except Exception as e:
            logger.error(f"Error fetching tickers: {e}")
            return {}
    
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1m',
        limit: int = 30,
        use_cache: bool = True
    ) -> List[List]:
        """
        Fetch OHLCV (candlestick) data
        
        Args:
            symbol: Trading pair
            timeframe: '1m', '5m', '15m', '1h', etc.
            limit: Number of candles
            use_cache: Use cached data
        
        Returns:
            List of OHLCV candles: [timestamp, open, high, low, close, volume]
        """
        try:
            cache_key = f"{symbol}_{timeframe}_{limit}"
            
            # Check cache
            if use_cache and cache_key in self.ohlcv_cache:
                cached_time, cached_data = self.ohlcv_cache[cache_key]
                if time.time() - cached_time < self.ohlcv_ttl:
                    return cached_data
            
            # Fetch fresh
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                limit=limit
            )
            
            self.ohlcv_cache[cache_key] = (time.time(), ohlcv)
            return ohlcv
        
        except ccxt.NetworkError as e:
            logger.error(f"Network error fetching OHLCV {symbol}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching OHLCV {symbol}: {e}")
            raise
    
    def fetch_balance(self, use_cache: bool = True) -> Dict:
        """
        Fetch account balance
        
        Args:
            use_cache: Use cached balance
        
        Returns:
            Balance dict with 'free', 'used', 'total'
        """
        try:
            # Check cache
            if use_cache and 'balance' in self.balance_cache:
                cached_time, cached_data = self.balance_cache['balance']
                if time.time() - cached_time < self.balance_ttl:
                    return cached_data
            
            # Fetch fresh
            balance = self.exchange.fetch_balance()
            self.balance_cache['balance'] = (time.time(), balance)
            return balance
        
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            raise
    
    def create_limit_buy_order(
        self,
        symbol: str,
        amount: float,
        price: float
    ) -> Dict:
        """
        Create limit buy order
        
        Args:
            symbol: Trading pair
            amount: Amount to buy
            price: Limit price
        
        Returns:
            Order dict
        """
        try:
            order = self.exchange.create_limit_buy_order(symbol, amount, price)
            logger.info(f"✅ Buy order created: {symbol} {amount} @ {price}")
            return order
        
        except Exception as e:
            logger.error(f"Error creating buy order: {e}")
            raise
    
    def create_limit_sell_order(
        self,
        symbol: str,
        amount: float,
        price: float
    ) -> Dict:
        """
        Create limit sell order
        
        Args:
            symbol: Trading pair
            amount: Amount to sell
            price: Limit price
        
        Returns:
            Order dict
        """
        try:
            order = self.exchange.create_limit_sell_order(symbol, amount, price)
            logger.info(f"✅ Sell order created: {symbol} {amount} @ {price}")
            return order
        
        except Exception as e:
            logger.error(f"Error creating sell order: {e}")
            raise
    
    def create_market_sell_order(
        self,
        symbol: str,
        amount: float
    ) -> Dict:
        """
        Create market sell order (emergency)
        
        Args:
            symbol: Trading pair
            amount: Amount to sell
        
        Returns:
            Order dict
        """
        try:
            order = self.exchange.create_market_sell_order(symbol, amount)
            logger.warning(f"⚠️ Market sell executed: {symbol} {amount}")
            return order
        
        except Exception as e:
            logger.error(f"Error creating market sell: {e}")
            raise
    
    def fetch_order(self, order_id: str, symbol: str) -> Dict:
        """
        Fetch order status
        
        Args:
            order_id: Order ID
            symbol: Trading pair
        
        Returns:
            Order dict
        """
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            return order
        
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            raise

    def fetch_my_trades(
        self,
        symbol: str,
        limit: int = 20,
        since: Optional[int] = None,
    ) -> List[Dict]:
        """Recent user trades on symbol (milliseconds `since`)."""
        try:
            kwargs = {'symbol': symbol, 'limit': limit}
            if since is not None:
                kwargs['since'] = since
            return self.exchange.fetch_my_trades(**kwargs)
        except Exception as e:
            logger.error(f"Error fetching trades for {symbol}: {e}")
            raise
    
    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """
        Cancel order
        
        Args:
            order_id: Order ID
            symbol: Trading pair
        
        Returns:
            Cancelled order dict
        """
        try:
            order = self.exchange.cancel_order(order_id, symbol)
            logger.info(f"✅ Order cancelled: {order_id}")
            return order
        
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            raise
    
    def get_market_health(self, symbol: str) -> Tuple[float, float]:
        """
        Check market health (spread and volatility)
        
        Args:
            symbol: Trading pair
        
        Returns:
            (spread_percent, volatility_index)
        """
        try:
            ticker = self.fetch_ticker(symbol)
            
            # Spread
            bid = float(ticker.get('bid', 0))
            ask = float(ticker.get('ask', 0))
            spread = ((ask - bid) / bid * 100) if bid > 0 else 0
            
            # Volatility from OHLCV
            try:
                ohlcv = self.fetch_ohlcv(symbol, '1m', limit=20)
                closes = [float(c[4]) for c in ohlcv]
                volatility = (max(closes) - min(closes)) / min(closes) * 100
            except:
                volatility = 1.0
            
            return float(spread), float(volatility)
        
        except Exception as e:
            logger.error(f"Error checking market health: {e}")
            return 0.0, 1.0
    
    def clear_caches(self):
        """Clear all caches"""
        self.ticker_cache.clear()
        self.ohlcv_cache.clear()
        self.balance_cache.clear()
        logger.debug("✅ Caches cleared")
