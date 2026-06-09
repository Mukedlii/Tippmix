"""
bot/api_limiter.py

Rate limiting for API calls and database operations.
Prevents exceeding free-tier limits and timeout issues.
"""

import os
import time
from typing import Dict, Any, Optional
from functools import wraps


class APILimiter:
    """
    Track and enforce API rate limits.
    
    Supports per-run budgets for:
    - TheOddsAPI
    - Poisson calculations
    - Database writes
    """
    
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.limits: Dict[str, int] = {}
        self._load_limits()
    
    def _load_limits(self):
        """Load limits from environment."""
        
        # TheOddsAPI limit
        self.limits["odds_api"] = int(os.getenv("ODDS_MAX_REQUESTS_PER_RUN", "10"))
        
        # Poisson calculations (unlimited, just for tracking)
        self.limits["poisson"] = int(os.getenv("TIPPMIX_MAX_POISSON_PER_RUN", "1000"))
        
        # Database writes (atomic operations)
        self.limits["db_writes"] = int(os.getenv("TIPPMIX_MAX_DB_WRITES_PER_RUN", "50"))
        
        # Total matches to process
        self.limits["matches"] = int(os.getenv("TIPPMIX_MAX_MATCHES_PER_RUN", "100"))
        
        # Tips to generate
        self.limits["tips"] = int(os.getenv("TIPPMIX_MAX_TIPS_PER_RUN", "20"))
    
    def increment(self, counter: str, amount: int = 1) -> bool:
        """
        Increment counter. Returns True if under limit.
        
        Args:
            counter: Counter name (e.g., "odds_api")
            amount: Increment amount
        
        Returns:
            True if still under limit, False if exceeded
        """
        
        if counter not in self.counters:
            self.counters[counter] = 0
        
        self.counters[counter] += amount
        limit = self.limits.get(counter, float('inf'))
        
        if self.counters[counter] > limit:
            print(f"[LIMITER] {counter} exceeded: {self.counters[counter]} > {limit}")
            return False
        
        return True
    
    def get_remaining(self, counter: str) -> int:
        """Get remaining budget for counter."""
        limit = self.limits.get(counter, 0)
        used = self.counters.get(counter, 0)
        return max(0, limit - used)
    
    def is_under_limit(self, counter: str) -> bool:
        """Check if counter is under limit."""
        limit = self.limits.get(counter, float('inf'))
        used = self.counters.get(counter, 0)
        return used < limit
    
    def reset(self):
        """Reset counters (for new run)."""
        self.counters = {}
    
    def report(self) -> Dict[str, Dict[str, int]]:
        """Get usage report."""
        return {
            counter: {
                "used": self.counters.get(counter, 0),
                "limit": self.limits.get(counter, 0),
                "remaining": self.get_remaining(counter),
            }
            for counter in self.limits.keys()
        }


# Global instance
_limiter = APILimiter()


def get_limiter() -> APILimiter:
    """Get global API limiter."""
    return _limiter


def limit_api_calls(api_name: str, max_calls: Optional[int] = None):
    """
    Decorator to limit API calls.
    
    Args:
        api_name: Name of API (e.g., "odds_api")
        max_calls: Override limit (uses env if not specified)
    """
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter = get_limiter()
            
            if max_calls is not None:
                limiter.limits[api_name] = max_calls
            
            if not limiter.is_under_limit(api_name):
                print(f"[LIMITER] {api_name} limit reached")
                return None
            
            limiter.increment(api_name)
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


class DatabaseLock:
    """
    Atomic database write lock.
    Prevents concurrent writes to SQLite (common in GitHub Actions).
    """
    
    def __init__(self, lock_file: str = "data/.db.lock", timeout: int = 30):
        self.lock_file = lock_file
        self.timeout = timeout
        self.start_time: Optional[float] = None
    
    def __enter__(self):
        """Acquire lock."""
        import os
        os.makedirs(os.path.dirname(self.lock_file), exist_ok=True)
        
        self.start_time = time.time()
        while os.path.exists(self.lock_file):
            elapsed = time.time() - self.start_time
            if elapsed > self.timeout:
                print(f"[DB_LOCK] Timeout waiting for lock (>{self.timeout}s)")
                break
            
            print(f"[DB_LOCK] Waiting for lock... ({elapsed:.1f}s)")
            time.sleep(0.5)
        
        # Create lock
        open(self.lock_file, 'a').close()
        return self
    
    def __exit__(self, *args):
        """Release lock."""
        try:
            os.remove(self.lock_file)
        except Exception:
            pass


def safe_db_operation(func):
    """Decorator for safe database operations with locking."""
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        lock = DatabaseLock()
        try:
            with lock:
                return func(*args, **kwargs)
        except Exception as e:
            print(f"[DB_LOCK] Operation failed: {repr(e)}")
            raise
    
    return wrapper


# Usage example in bot/main.py:
#
# from bot.api_limiter import get_limiter, DatabaseLock
#
# limiter = get_limiter()
# limiter.reset()
#
# # Track API calls
# if limiter.increment("odds_api"):
#     odds = fetch_odds(...)
#
# # Atomic DB write
# with DatabaseLock():
#     insert_bets(run_id, vip_bets)
#
# # Report
# print(limiter.report())
