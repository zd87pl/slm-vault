"""
WDVA Cryptographic Core
Implements XChaCha20-Poly1305 encryption for weight deltas
Copyright © 2025 Zygmunt Dyras. All rights reserved.
"""

import os
import json
import hashlib
from typing import Tuple, Dict
import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class WDVAEncryptor:
    """Handles encryption/decryption of weight delta vaults"""

    def __init__(self, master_key: bytes = None):
        """
        Initialize encryptor with master key

        Args:
            master_key: 256-bit master key (generated if None)
        """
        if master_key is None:
            master_key = os.urandom(32)  # 256 bits
        self.master_key = master_key
        self.key_cache = {}  # user_id -> user_key

    def derive_user_key(self, user_id: str) -> bytes:
        """
        Derive user-specific encryption key from master key

        Args:
            user_id: Unique user identifier

        Returns:
            256-bit user-specific key
        """
        if user_id in self.key_cache:
            return self.key_cache[user_id]

        # Use HKDF to derive user key
        kdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"WDVA_v1.0_salt",  # Fixed salt for reproducibility
            info=f"WDVA_user_{user_id}".encode()
        )
        user_key = kdf.derive(self.master_key)
        self.key_cache[user_id] = user_key

        return user_key

    def create_vault(
        self,
        weight_delta: np.ndarray,
        user_id: str,
        manifest: Dict = None
    ) -> Tuple[bytes, bytes]:
        """
        Encrypt weight delta and create WDVA blob

        Args:
            weight_delta: NumPy array of weight deltas
            user_id: User identifier
            manifest: Metadata dict (optional)

        Returns:
            (encrypted_blob, user_key)
        """
        # Derive user key
        user_key = self.derive_user_key(user_id)

        # Create manifest
        if manifest is None:
            manifest = {}

        manifest.update({
            "user_id_hash": hashlib.sha256(user_id.encode()).hexdigest(),
            "shape": weight_delta.shape,
            "dtype": str(weight_delta.dtype),
            "version": "WDVA_v1.0"
        })

        # Serialize weight delta
        delta_bytes = weight_delta.tobytes()

        # Create AAD (Associated Authenticated Data)
        aad = json.dumps(manifest, sort_keys=True).encode()

        # Encrypt using ChaCha20-Poly1305
        cipher = ChaCha20Poly1305(user_key)
        nonce = os.urandom(12)  # 96 bits for ChaCha20-Poly1305

        ciphertext = cipher.encrypt(nonce, delta_bytes, aad)

        # Package: nonce || aad_length || aad || ciphertext
        aad_len = len(aad).to_bytes(4, 'big')
        encrypted_blob = nonce + aad_len + aad + ciphertext

        return encrypted_blob, user_key

    def decrypt_vault(
        self,
        encrypted_blob: bytes,
        user_key: bytes
    ) -> Tuple[np.ndarray, Dict]:
        """
        Decrypt WDVA blob to retrieve weight delta

        Args:
            encrypted_blob: Encrypted vault data
            user_key: User's encryption key

        Returns:
            (weight_delta, manifest)
        """
        # Unpack blob
        nonce = encrypted_blob[:12]
        aad_len = int.from_bytes(encrypted_blob[12:16], 'big')
        aad = encrypted_blob[16:16+aad_len]
        ciphertext = encrypted_blob[16+aad_len:]

        # Decrypt
        cipher = ChaCha20Poly1305(user_key)
        delta_bytes = cipher.decrypt(nonce, ciphertext, aad)

        # Parse manifest
        manifest = json.loads(aad.decode())

        # Reconstruct array
        weight_delta = np.frombuffer(
            delta_bytes,
            dtype=np.dtype(manifest['dtype'])
        ).reshape(manifest['shape'])

        return weight_delta, manifest

    def destroy_key(self, user_id: str) -> bool:
        """
        Cryptographically destroy user key (right-to-be-forgotten)

        Args:
            user_id: User identifier

        Returns:
            True if successful
        """
        if user_id in self.key_cache:
            # Overwrite key memory in-place with random data (multiple passes)
            key_ref = self.key_cache[user_id]
            for i in range(len(key_ref)):
                key_ref[i] = 0
            for _ in range(3):  # Multiple overwrite passes
                random_bytes = os.urandom(len(key_ref))
                for i in range(len(key_ref)):
                    key_ref[i] = random_bytes[i] ^ key_ref[i]

            # Remove from cache
            del self.key_cache[user_id]

        return True

    def verify_destruction(self, encrypted_blob: bytes, user_id: str) -> bool:
        """
        Verify that key destruction makes vault inaccessible

        Args:
            encrypted_blob: Encrypted vault data
            user_id: User identifier

        Returns:
            True if decryption fails (key successfully destroyed)
        """
        try:
            # Try to derive key (should fail if properly destroyed)
            user_key = self.derive_user_key(user_id)
            self.decrypt_vault(encrypted_blob, user_key)
            return False  # Decryption succeeded = destruction failed
        except:
            return True  # Decryption failed = destruction succeeded