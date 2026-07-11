# -*- coding: utf-8 -*-
# vidxgo_extractor.py - VidXgo embed -> HLS extractor for Enigma2 e
import base64
import re
from urllib.parse import urlparse

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError:
    requests = None
    HTTPAdapter = None

try:
    import urllib3
    from urllib3.util.retry import Retry
    from urllib3.exceptions import InsecureRequestWarning
    urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    Retry = None

try:
    from ..StreamProxyLog import enhanced_log
except (ImportError, ValueError):
    try:
        from StreamProxyLog import enhanced_log
    except ImportError:
        def enhanced_log(msg, level="INFO", tag="VIDXGO"):
            print("[%s] [%s] %s" % (level, tag, msg))


DEFAULT_PLAYBACK_DOMAIN = "https://v.vidxgo.co"
EMBED_FETCH_REFERER = "https://altadefinizione.you/"

_OBFUSCATED_RE = re.compile(
    r"var\s+\w+\s*=\s*'([^']*)'\s*,\s*d\s*=\s*atob\(\s*'([^']*)'",
    re.S,
)
_CURRENT_SRC_RE = re.compile(
    r'\bcurrentSrc\s*=\s*["\']( ?https?:[^"\']+?\.m3u8[^"\']*)["\']',
    re.S,
)
_SCRIPT_TAG_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.S | re.I)


class VidXgoExtractorError(Exception):
    pass


class VidXgoExtractor:
    """VidXgo embed -> HLS extractor, synchronous version for Enigma2."""

    def __init__(self):
        self.mediaflow_endpoint = "hls_proxy"
        self.session = None

        self.embed_headers = {
            "user-agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:150.0) "
                "Gecko/20100101 Firefox/150.0"),
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "it-IT,it;q=0.9,en;q=0.8",
            "referer": EMBED_FETCH_REFERER,
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "upgrade-insecure-requests": "1",
        }

        self.playback_headers = {
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Safari/537.36"
            ),
            "accept": "*/*",
            "accept-language": "it-IT,it;q=0.9,en;q=0.8",
            "referer": DEFAULT_PLAYBACK_DOMAIN + "/",
            "origin": DEFAULT_PLAYBACK_DOMAIN,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
        }

        if requests:
            self.session = requests.Session()
            self.session.verify = False
            if Retry and HTTPAdapter:
                retry = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET"],
                )
                adapter = HTTPAdapter(
                    max_retries=retry,
                    pool_connections=2,
                    pool_maxsize=4)
                self.session.mount("http://", adapter)
                self.session.mount("https://", adapter)

    def _fetch(self, url, headers, timeout=20):
        if not self.session:
            raise VidXgoExtractorError("requests not available")
        try:
            resp = self.session.get(
                url, headers=headers, timeout=timeout,
                verify=False, allow_redirects=True
            )
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            raise VidXgoExtractorError(
                "VidXgo fetch failed for %s: %s" % (url[:80], exc))

    @staticmethod
    def _decode_embed(html):
        """XOR-decode the obfuscated player script to extract the m3u8 URL."""
        scripts = _SCRIPT_TAG_RE.findall(html or "")
        # historically at index 5, but scan all as fallback
        candidates = []
        if len(scripts) > 5:
            candidates.append(scripts[5])
        candidates.extend(s for i, s in enumerate(scripts) if i != 5)

        for script in candidates:
            m = _OBFUSCATED_RE.search(script)
            if not m:
                continue
            key, b64_payload = m.group(1), m.group(2)
            if not key or not b64_payload:
                continue
            try:
                decoded = base64.b64decode(b64_payload)
            except Exception:
                continue
            key_bytes = key.encode("utf-8")
            klen = len(key_bytes)
            if not klen:
                continue
            xored = bytes(b ^ key_bytes[i % klen]
                          for i, b in enumerate(decoded))
            try:
                decoded_str = xored.decode("utf-8", errors="ignore")
            except Exception:
                continue
            cm = _CURRENT_SRC_RE.search(decoded_str)
            if cm:
                return cm.group(1).replace("\\", "").strip()

        if "player-container" in html and "corrupt" in html:
            raise VidXgoExtractorError(
                "VidXgo: source marked corrupt or unavailable")
        raise VidXgoExtractorError(
            "VidXgo: currentSrc m3u8 not found in any script")

    def extract(self, url):
        """Extract HLS playlist URL from a VidXgo embed page."""
        enhanced_log("START extract: %s..." % url[:80], "INFO", "VIDXGO")
        try:
            parsed = urlparse(url)
            # build playback headers with correct origin/referer
            playback_domain = "%s://%s" % (parsed.scheme or "https",
                                           parsed.netloc or "v.vidxgo.co")
            pb_headers = dict(self.playback_headers)
            pb_headers["referer"] = playback_domain + "/"
            pb_headers["origin"] = playback_domain

            html = self._fetch(url, self.embed_headers)
            if not html:
                raise VidXgoExtractorError("Empty embed page for %s" % url)

            m3u8_url = self._decode_embed(html)
            enhanced_log("Decoded m3u8: %s..." %
                         m3u8_url[:80], "INFO", "VIDXGO")

            # quick validation: check the manifest is reachable and valid
            manifest = self._fetch(m3u8_url, pb_headers, timeout=15)
            if "#EXTM3U" not in manifest:
                raise VidXgoExtractorError(
                    "Extracted URL did not return a valid HLS manifest")

            enhanced_log("SUCCESS: %s..." % m3u8_url[:120], "INFO", "VIDXGO")
            return {
                "resolved_url": m3u8_url,
                "destination_url": m3u8_url,
                "headers": pb_headers,
                "request_headers": pb_headers,
                "mediaflow_endpoint": self.mediaflow_endpoint,
            }

        except VidXgoExtractorError as exc:
            enhanced_log("Extraction error: %s" % exc, "ERROR", "VIDXGO")
            return None
        except Exception as exc:
            enhanced_log(
                "Unexpected error: %s" %
                str(exc)[
                    :200],
                "ERROR",
                "VIDXGO")
            return None

    def close(self):
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
            finally:
                self.session = None


def is_vidxgo_link(url):
    return "vidxgo" in (url or "").lower()


# global instance
vidxgo_extractor = VidXgoExtractor()
