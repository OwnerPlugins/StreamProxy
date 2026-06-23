# cache_manager.py - Centralized cache management for StreamProxy
import time
import threading
from .StreamProxyLog import enhanced_log


class SimpleTTLCache(dict):
    """Time-To-Live cache for M3U8 files"""

    def __init__(
            self,
            maxsize=100,
            ttl=5,
            cleanup_interval=30,
            max_memory_mb=50):
        super().__init__()
        self.maxsize = maxsize
        self.ttl = ttl
        self._timestamps = {}
        self._sizes = {}  # Tracks the size of each item
        self._total_size = 0  # Total size in bytes
        self._max_memory = max_memory_mb * 1024 * 1024  # Memory limit in bytes
        self._lock = threading.RLock()
        self._cleanup_interval = cleanup_interval
        self._cleanup_thread = threading.Thread(
            target=self._periodic_cleanup, daemon=True)
        self._cleanup_thread.start()

    def __setitem__(self, key, value):
        with self._lock:
            # Estimate the size of the value
            value_size = len(value) if isinstance(value, (bytes, str)) else 512

            # If the item already exists, subtract its current size
            if dict.__contains__(self, key):
                self._total_size -= self._sizes.get(key, 0)

            # Check if adding would exceed the memory limit
            if self._total_size + value_size > self._max_memory:
                self._evict_by_memory(value_size)

            # Check if adding would exceed the maximum number of items
            if len(self) >= self.maxsize and not dict.__contains__(self, key):
                self._evict_oldest()

            # Update cache, timestamp and size
            super().__setitem__(key, value)
            self._timestamps[key] = time.time()
            self._sizes[key] = value_size
            self._total_size += value_size

    def _evict_by_memory(self, needed_space):
        # Remove items until enough space is freed
        while self._total_size + needed_space > self._max_memory * \
                0.9 and self:  # Keep 10% margin
            oldest = min(
                self._timestamps,
                key=self._timestamps.get) if self._timestamps else None
            if not oldest:
                break
            self._safe_remove(oldest)

    def __getitem__(self, key):
        with self._lock:
            # Check if the key exists and is not expired
            if dict.__contains__(
                self,
                key) and (
                time.time() -
                self._timestamps.get(
                    key,
                    0)) < self.ttl:
                return dict.__getitem__(self, key)
            # If the key is expired or does not exist, remove it and raise
            # KeyError
            self._safe_remove(key)
            raise KeyError(key)

    def __contains__(self, key):
        with self._lock:
            # Check if the key exists and is not expired
            if dict.__contains__(
                self,
                key) and (
                time.time() -
                self._timestamps.get(
                    key,
                    0)) < self.ttl:
                return True
            # If the key is expired, remove it
            self._safe_remove(key)
            return False

    def _evict_oldest(self):
        # Remove the oldest or expired items
        expired = [
            k for k,
            t in self._timestamps.items() if (
                time.time() -
                t) >= self.ttl]
        for k in expired:
            self._safe_remove(k)
        # If still needed, remove the oldest one
        if len(self) >= self.maxsize and self._timestamps:
            oldest = min(self._timestamps, key=self._timestamps.get)
            self._safe_remove(oldest)

    def _safe_remove(self, key):
        # Safely remove a key and update the total size
        if dict.__contains__(self, key):
            self._total_size -= self._sizes.pop(key, 0)
            dict.pop(self, key, None)
            self._timestamps.pop(key, None)

    def _periodic_cleanup(self):
        """Run periodic cache cleanup in a separate thread."""
        while True:
            try:
                time.sleep(self._cleanup_interval)
                with self._lock:
                    # Remove expired items
                    now = time.time()
                    expired = [
                        k for k, t in self._timestamps.items() if (
                            now - t) >= self.ttl]
                    for k in expired:
                        self._safe_remove(k)

                    # Check if memory usage is above 90% of the limit
                    if self._total_size > self._max_memory * 0.9:
                        # Remove items until usage drops below 80%
                        while self._total_size > self._max_memory * 0.8 and self._timestamps:
                            oldest = min(
                                self._timestamps, key=self._timestamps.get)
                            self._safe_remove(oldest)

                    # Check if the number of items exceeds the limit
                    while len(self) > self.maxsize and self._timestamps:
                        oldest = min(
                            self._timestamps, key=self._timestamps.get)
                        self._safe_remove(oldest)
            except Exception as e:
                # Catch any exceptions to prevent the cleanup thread from
                # stopping
                enhanced_log(
                    "Error during TTL cache cleanup: %s" % str(e),
                    "ERROR",
                    "CACHE")
                # Short pause before retrying
                time.sleep(5)


class SimpleLRUCache(dict):
    """LRU (Least Recently Used) cache for TS segments and keys"""

    def __init__(self, maxsize=1000, cleanup_interval=120):
        super().__init__()
        self.maxsize = maxsize
        self._order = []
        self._lock = threading.RLock()
        self._cleanup_interval = cleanup_interval
        self._cleanup_thread = threading.Thread(
            target=self._periodic_cleanup, daemon=True)
        self._cleanup_thread.start()

    def __setitem__(self, key, value):
        with self._lock:
            if dict.__contains__(self, key):
                self._order.remove(key)
            elif len(self) >= self.maxsize:
                # Remove items no longer in the cache for consistency before
                # eviction
                self._order = [k for k in self._order if k in self]
                if self._order:  # Only if there are correctly removed items
                    oldest = self._order.pop(0)
                    self.pop(oldest, None)
                else:  # If the cache is empty and we try to evict, avoid KeyError
                    pass
            dict.__setitem__(self, key, value)
            self._order.append(key)

    def __getitem__(self, key):
        with self._lock:
            if dict.__contains__(self, key):
                self._order.remove(key)
                self._order.append(key)
                return dict.__getitem__(self, key)
            raise KeyError(key)

    def __contains__(self, key):
        with self._lock:
            return dict.__contains__(self, key)

    def _periodic_cleanup(self):
        while True:
            time.sleep(self._cleanup_interval)
            with self._lock:
                # Remove any orphaned keys from the order
                self._order = [k for k in self._order if k in self]
                # If the cache is too large, evict
                while len(self) > self.maxsize:
                    if not self._order:  # Avoid error if order is empty
                        break
                    oldest = self._order.pop(0)
                    self.pop(oldest, None)


# Global cache instances
M3U8_CACHE = SimpleTTLCache(maxsize=200, ttl=5)
TS_CACHE = SimpleLRUCache(maxsize=1000)
KEY_CACHE = SimpleLRUCache(maxsize=200)
CACHE_ENABLED = True
