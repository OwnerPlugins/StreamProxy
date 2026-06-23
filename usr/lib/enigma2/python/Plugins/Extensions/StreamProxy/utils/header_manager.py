# -*- coding: utf-8 -*-
# utils/header_manager.py - Header manager for correct propagation between
# M3U8 and TS segments

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class HeaderManager:
    """Manages correct header propagation between M3U8 and TS segments."""

    def __init__(self):
        self.stream_headers = {}  # stream_id -> headers

    def save_stream_headers(self, stream_id: str, headers: Dict[str, str]):
        """Save headers for a specific stream."""
        if not stream_id or not headers:
            return

        # Essential headers for authentication
        essential_headers = [
            'Authorization', 'X-Channel-Key', 'X-Client-Token',
            'Heartbeat-Url', 'User-Agent', 'Referer', 'Origin', 'Cookie'
        ]

        # Filter only essential headers
        filtered_headers = {}
        for key, value in headers.items():
            if key in essential_headers:
                filtered_headers[key] = value

        if filtered_headers:
            self.stream_headers[stream_id] = filtered_headers
            logger.info(
                "[HEADER_MANAGER] Saved %d headers for stream %s" % (
                    len(filtered_headers), stream_id))
            logger.debug(
                "[HEADER_MANAGER] Headers: %s" % list(
                    filtered_headers.keys()))

    def get_stream_headers(self, stream_id: str) -> Dict[str, str]:
        """Get saved headers for a stream."""
        return self.stream_headers.get(stream_id, {})

    def combine_headers(self,
                        stream_id: str,
                        query_headers: Dict[str,
                                            str]) -> Dict[str,
                                                          str]:
        """Combine headers from query string with saved stream headers."""
        saved_headers = self.get_stream_headers(stream_id)

        # Headers from query string take priority
        combined = saved_headers.copy()
        combined.update(query_headers)

        # Check for missing critical headers
        critical_headers = ['Authorization', 'X-Channel-Key', 'X-Client-Token']
        missing_critical = [h for h in critical_headers if h not in combined]

        if missing_critical:
            logger.warning(
                "[HEADER_MANAGER] Missing critical headers for %s: %s" % (
                    stream_id, missing_critical))

        return combined

    def clear_stream(self, stream_id: str):
        """Remove headers for a specific stream."""
        if stream_id in self.stream_headers:
            del self.stream_headers[stream_id]
            logger.debug(
                "[HEADER_MANAGER] Removed headers for stream %s" % stream_id)

    def clear_all(self):
        """Remove all saved headers."""
        count = len(self.stream_headers)
        self.stream_headers.clear()
        if count > 0:
            logger.info(
                "[HEADER_MANAGER] Removed headers for %d streams" % count)


# Global instance
header_manager = HeaderManager()
