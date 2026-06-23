# -*- coding: utf-8 -*-
# utils/drm_handler.py - Simplified DRM handler for Enigma2
# Based on EasyProxy/utils/drm_decrypter.py but simplified

from typing import Dict, Any

try:
    from Crypto.Cipher import AES
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class DRMHandler:
    """Simplified DRM handler for Enigma2."""

    def __init__(self):
        self.keys = {}

    def add_key(self, key_id: str, key: str):
        """Add a decryption key."""
        try:
            self.keys[key_id] = bytes.fromhex(key)
        except ValueError:
            pass

    def decrypt_aes128(self, data: bytes, key: bytes, iv: bytes) -> bytes:
        """AES-128 CTR decryption."""
        if not CRYPTO_AVAILABLE:
            return data

        try:
            # Pad IV to 16 bytes
            if len(iv) < 16:
                iv = iv + b'\x00' * (16 - len(iv))

            cipher = AES.new(key, AES.MODE_CTR, initial_value=iv, nonce=b'')
            return cipher.decrypt(data)
        except Exception:
            return data

    def process_clearkey(self, key_data: Dict[str, Any]) -> Dict[str, str]:
        """Process ClearKey data."""
        keys = {}

        if 'keys' in key_data:
            for key_info in key_data['keys']:
                if 'kid' in key_info and 'k' in key_info:
                    keys[key_info['kid']] = key_info['k']

        return keys

    def has_crypto(self) -> bool:
        """Check if crypto support is available."""
        return CRYPTO_AVAILABLE
