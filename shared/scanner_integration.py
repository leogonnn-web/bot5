"""
Scanner Integration Module
Provides integration between scanner_v3.py and bot.py

Classes:
✅ ScannerIntegration - Reads hot_symbols.txt from scanner
✅ DynamicSymbolManager - Combines scanner signals with base config symbols

Usage in bot.py:
    from scanner_integration import ScannerIntegration, DynamicSymbolManager
    
    # In __init__:
    self.scanner_integration = ScannerIntegration("hot_symbols.txt")
    self.symbol_manager = DynamicSymbolManager(
        base_symbols=self.config.get_symbols(),
        scanner_integration=self.scanner_integration
    )
    
    # In _scan_for_entries():
    symbols = self.symbol_manager.get_symbols(refresh_scanner=True)
"""

import os
import re
import time
from typing import List, Dict, Set
from logger_setup import logger


class ScannerIntegration:
    """Reads and parses hot_symbols.txt from scanner_v3.py"""
    
    def __init__(self, filename: str = "hot_symbols.txt"):
        """
        Initialize scanner integration
        
        Args:
            filename: Path to scanner output file (default: hot_symbols.txt)
        """
        self.filename = filename
        self.last_symbols = set()
        self.last_update = 0
        self.cache_ttl = 300  # 5 minutes
    
    def read_symbols(self, force_refresh: bool = False) -> Set[str]:
        """
        Read symbols from scanner file
        
        Args:
            force_refresh: Ignore cache and read fresh from file
        
        Returns:
            Set of symbols like {'NOT/USDT', 'TON/USDT'}
        """
        try:
            # Check cache
            if not force_refresh and time.time() - self.last_update < self.cache_ttl:
                return self.last_symbols
            
            # File doesn't exist
            if not os.path.exists(self.filename):
                logger.debug(f"Scanner file {self.filename} not found")
                return set()
            
            with open(self.filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse SYMBOLS = ['NOT/USDT', 'TON/USDT', ...] format
            match = re.search(r'SYMBOLS\s*=\s*\[(.*?)\]', content)
            if not match:
                return set()
            
            symbols_str = match.group(1)
            # Extract quoted symbols
            symbols = re.findall(r"'([A-Z0-9]+/USDT)'", symbols_str)
            
            result = set(symbols)
            
            # Log changes
            if result != self.last_symbols:
                new_symbols = result - self.last_symbols
                removed_symbols = self.last_symbols - result
                
                if new_symbols:
                    logger.debug(f"Scanner: New symbols: {', '.join(new_symbols)}")
                if removed_symbols:
                    logger.debug(f"Scanner: Removed symbols: {', '.join(removed_symbols)}")
            
            self.last_symbols = result
            self.last_update = time.time()
            
            return result
        
        except Exception as e:
            logger.error(f"Error reading scanner file: {e}")
            return set()
    
    def get_scanner_symbols(self) -> Set[str]:
        """Get current scanner symbols (cached)"""
        return self.read_symbols(force_refresh=False)
    
    def refresh(self) -> Set[str]:
        """Force refresh from file"""
        return self.read_symbols(force_refresh=True)


class DynamicSymbolManager:
    """Manages symbol list combining scanner signals and base config"""
    
    def __init__(
        self,
        base_symbols: List[str],
        scanner_integration: ScannerIntegration
    ):
        """
        Initialize dynamic symbol manager
        
        Args:
            base_symbols: Base symbol list from config.json
            scanner_integration: ScannerIntegration instance
        """
        self.base_symbols = set(base_symbols)
        self.scanner = scanner_integration
        self.stats = {
            'total': 0,
            'from_scanner': 0,
            'from_base': 0,
            'last_update': 0
        }
    
    def get_symbols(self, refresh_scanner: bool = True) -> List[str]:
        """
        Get combined symbol list
        
        Args:
            refresh_scanner: Refresh scanner data from file
        
        Returns:
            List of symbols, prioritizing scanner signals
            
        Priority:
            1. Scanner symbols (if any)
            2. Base config symbols
        """
        try:
            # Get symbols
            scanner_symbols = self.scanner.read_symbols(force_refresh=refresh_scanner)
            
            # Combine: scanner first (higher priority), then base
            if scanner_symbols:
                combined = list(scanner_symbols) + [
                    s for s in self.base_symbols if s not in scanner_symbols
                ]
            else:
                combined = list(self.base_symbols)
            
            # Update stats
            self.stats['total'] = len(combined)
            self.stats['from_scanner'] = len(scanner_symbols)
            self.stats['from_base'] = len([s for s in combined if s not in scanner_symbols])
            self.stats['last_update'] = time.time()
            
            return combined
        
        except Exception as e:
            logger.error(f"Error getting symbols: {e}")
            return list(self.base_symbols)
    
    def get_scanner_only(self) -> List[str]:
        """Get only scanner symbols (for debugging)"""
        return list(self.scanner.get_scanner_symbols())
    
    def get_base_only(self) -> List[str]:
        """Get only base symbols (for debugging)"""
        return list(self.base_symbols)
    
    def get_stats(self) -> Dict:
        """Get statistics about symbol sources"""
        return self.stats.copy()
    
    def has_scanner_signals(self) -> bool:
        """Check if scanner has found any signals"""
        return len(self.scanner.get_scanner_symbols()) > 0
