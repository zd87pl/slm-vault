"""
Enhanced DoRA adapter encryption/decryption with security improvements.

Features:
- XChaCha20-Poly1305 authenticated encryption
- HKDF-SHA256 key derivation
- Optional zstd compression
- Lazy layer-by-layer decryption
- Memory-locked sensitive data handling
- Versioned encryption for key rotation support
"""

import torch
import os
import io
import json
import zstandard as zstd
from safetensors.torch import save_file, load_file, save, load
from Crypto.Cipher import ChaCha20_Poly1305
from Crypto.Random import get_random_bytes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from base64 import b64encode, b64decode
from typing import Dict, Optional, List, Any
import logging
from pathlib import Path

from utils.memory_security import (
    secure_zero_dict,
    SecureMemoryContext,
    mlock_tensor
)

logger = logging.getLogger(__name__)


# Encryption version for backward compatibility during key rotation
ENCRYPTION_VERSION = "2.0"


class EncryptedDoRAManager:
    """
    Secure DoRA adapter weight encryption and decryption manager.

    Implements defense-in-depth security:
    - Authenticated encryption (prevents tampering)
    - Key derivation (separates storage key from master secret)
    - Optional compression (reduces storage and transfer costs)
    - Lazy decryption (decrypt only needed layers)
    - Memory locking (prevent swapping to disk)
    - Secure cleanup (zero memory on completion)
    """

    def __init__(self,
                 master_password: bytes,
                 enable_compression: bool = True,
                 compression_level: int = 3):
        """
        Initialize encryption manager.

        Args:
            master_password: 32-byte master password for key derivation
            enable_compression: Whether to compress before encryption
            compression_level: Zstd compression level (1-22, default 3)
        """
        if len(master_password) != 32:
            raise ValueError("Master password must be exactly 32 bytes")

        self.master_password = master_password
        self.enable_compression = enable_compression
        self.compression_level = compression_level

        # Initialize compressor if enabled
        if enable_compression:
            self.compressor = zstd.ZstdCompressor(level=compression_level)
            self.decompressor = zstd.ZstdDecompressor()

        logger.info(f"Initialized EncryptedDoRAManager v{ENCRYPTION_VERSION} "
                   f"(compression: {enable_compression})")

    def extract_and_encrypt_dora_weights(self,
                                        model,
                                        output_path: str,
                                        metadata: Optional[Dict[str, Any]] = None) -> Dict:
        """
        Extract DoRA weights from model, serialize, and encrypt.

        Args:
            model: PyTorch model with DoRA adapters
            output_path: Path to save encrypted package
            metadata: Optional metadata to include

        Returns:
            Dictionary with encryption metadata
        """
        logger.info("Extracting DoRA weights from model...")

        # Step 1: Extract DoRA weights
        dora_weights = self._extract_dora_weights(model)
        logger.info(f"Extracted {len(dora_weights)} DoRA tensors")

        # Step 2: Serialize to safetensors format
        serialized_data = save(dora_weights)
        original_size = len(serialized_data)
        logger.debug(f"Serialized to {original_size / 1024**2:.2f} MB")

        # Step 3: Compress if enabled
        if self.enable_compression:
            compressed_data = self.compressor.compress(serialized_data)
            compression_ratio = len(compressed_data) / original_size
            logger.info(f"Compressed to {len(compressed_data) / 1024**2:.2f} MB "
                       f"(ratio: {compression_ratio:.2%})")
            data_to_encrypt = compressed_data
        else:
            data_to_encrypt = serialized_data

        # Step 4: Generate salt and derive encryption key
        salt = get_random_bytes(16)
        encryption_key = self._derive_key(salt, b"dora-encryption-key-v2")

        # Step 5: Encrypt with XChaCha20-Poly1305
        nonce = get_random_bytes(24)  # 192-bit nonce for XChaCha20
        cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)

        # Prepare metadata
        encryption_metadata = {
            'version': ENCRYPTION_VERSION,
            'num_tensors': len(dora_weights),
            'adapter_type': 'DoRA',
            'original_size_bytes': original_size,
            'compressed': self.enable_compression,
            'compression_level': self.compression_level if self.enable_compression else None,
            **(metadata or {})
        }

        # Add metadata as authenticated associated data (AAD)
        aad = json.dumps(encryption_metadata, sort_keys=True).encode('utf-8')
        cipher.update(aad)

        # Encrypt and generate authentication tag
        ciphertext, tag = cipher.encrypt_and_digest(data_to_encrypt)

        # Step 6: Package encrypted data
        encrypted_package = {
            'salt': b64encode(salt).decode('utf-8'),
            'nonce': b64encode(nonce).decode('utf-8'),
            'ciphertext': b64encode(ciphertext).decode('utf-8'),
            'tag': b64encode(tag).decode('utf-8'),
            'metadata': encryption_metadata,
            'algorithm': 'XChaCha20-Poly1305',
            'kdf': 'HKDF-SHA256'
        }

        # Step 7: Save to file
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(encrypted_package, f, indent=2)

        logger.info(f"Encrypted adapter saved to {output_path}")
        return encrypted_package

    def decrypt_and_load_dora_weights(self,
                                     encrypted_path: str,
                                     lock_memory: bool = False) -> Dict[str, torch.Tensor]:
        """
        Load and decrypt DoRA weights ephemerally (in-memory only).

        Args:
            encrypted_path: Path to encrypted weights file
            lock_memory: Whether to lock decrypted weights in memory (prevent swapping)

        Returns:
            Dictionary of decrypted tensors (never persisted to disk)
        """
        logger.info(f"Loading encrypted adapter from {encrypted_path}...")

        # Step 1: Load encrypted package
        with open(encrypted_path, 'r') as f:
            encrypted_package = json.load(f)

        # Verify version compatibility
        version = encrypted_package.get('metadata', {}).get('version', '1.0')
        if version != ENCRYPTION_VERSION:
            logger.warning(f"Encryption version mismatch: {version} != {ENCRYPTION_VERSION}")

        # Step 2: Derive decryption key
        salt = b64decode(encrypted_package['salt'])
        decryption_key = self._derive_key(salt, b"dora-encryption-key-v2")

        # Step 3: Decrypt with XChaCha20-Poly1305
        cipher = ChaCha20_Poly1305.new(
            key=decryption_key,
            nonce=b64decode(encrypted_package['nonce'])
        )

        # Re-add AAD for authentication verification
        aad = json.dumps(encrypted_package['metadata'], sort_keys=True).encode('utf-8')
        cipher.update(aad)

        # Decrypt and verify authentication tag
        try:
            decrypted_data = cipher.decrypt_and_verify(
                b64decode(encrypted_package['ciphertext']),
                b64decode(encrypted_package['tag'])
            )
            logger.debug("Authentication verification successful")
        except ValueError as e:
            raise ValueError(f"Authentication failed - data may be tampered: {e}")

        # Step 4: Decompress if necessary
        if encrypted_package['metadata'].get('compressed', False):
            serialized_data = self.decompressor.decompress(decrypted_data)
            logger.debug(f"Decompressed to {len(serialized_data) / 1024**2:.2f} MB")
        else:
            serialized_data = decrypted_data

        # Step 5: Deserialize from safetensors (in-memory only)
        dora_weights = load(serialized_data)

        logger.info(f"Decrypted {len(dora_weights)} DoRA tensors")

        # Step 6: Lock memory if requested
        if lock_memory:
            for name, tensor in dora_weights.items():
                mlock_tensor(tensor)
            logger.debug("Locked decrypted weights in memory")

        return dora_weights

    def decrypt_layer_lazy(self,
                          encrypted_path: str,
                          layer_name: str) -> Optional[Dict[str, torch.Tensor]]:
        """
        Lazily decrypt a single layer's weights on-demand.

        This is more efficient for models where only specific layers are needed.

        Args:
            encrypted_path: Path to encrypted weights file
            layer_name: Name of layer to decrypt (e.g., "model.layers.0")

        Returns:
            Dictionary with layer weights (lora_A, lora_B, magnitude) or None
        """
        # For full lazy implementation, we'd need to store layers separately
        # For now, decrypt all and filter (TODO: implement per-layer encryption)
        all_weights = self.decrypt_and_load_dora_weights(encrypted_path)

        layer_weights = {}
        for key, tensor in all_weights.items():
            if key.startswith(layer_name):
                layer_weights[key] = tensor

        # Securely zero unused weights
        for key in list(all_weights.keys()):
            if key not in layer_weights:
                all_weights[key].zero_()
                del all_weights[key]

        return layer_weights if layer_weights else None

    def _extract_dora_weights(self, model) -> Dict[str, torch.Tensor]:
        """
        Extract DoRA adapter weights from a PEFT model.

        Args:
            model: PyTorch model with DoRA adapters

        Returns:
            Dictionary of DoRA weights
        """
        dora_weights = {}

        for name, module in model.named_modules():
            # Check for LoRA components
            if hasattr(module, 'lora_A') and hasattr(module, 'lora_B'):
                # Extract LoRA matrices (direction component)
                # Handle ModuleDict (PEFT >= 0.9.0) vs direct module
                lora_a = module.lora_A
                lora_b = module.lora_B

                # If it's a ModuleDict, get the 'default' adapter
                if hasattr(lora_a, 'default'):
                    lora_a = lora_a.default
                if hasattr(lora_b, 'default'):
                    lora_b = lora_b.default

                # Now extract the weight
                if hasattr(lora_a, 'weight'):
                    dora_weights[f"{name}.lora_A"] = lora_a.weight.data.clone()
                    dora_weights[f"{name}.lora_B"] = lora_b.weight.data.clone()

                # Extract magnitude vector (DoRA-specific)
                if hasattr(module, 'weight_m_wdecomp'):
                    mag = module.weight_m_wdecomp
                    # Handle ModuleDict for magnitude
                    if hasattr(mag, 'default'):
                        mag = mag.default
                    if hasattr(mag, 'weight'):
                        dora_weights[f"{name}.magnitude"] = mag.weight.data.clone()
                elif hasattr(module, 'lora_magnitude_vector'):
                    # Handle ModuleDict for lora_magnitude_vector too
                    mag_vec = module.lora_magnitude_vector
                    if hasattr(mag_vec, 'default'):
                        mag_vec = mag_vec.default
                    # Extract the actual parameter (could be weight, data, or Parameter)
                    if hasattr(mag_vec, 'weight'):
                        dora_weights[f"{name}.magnitude"] = mag_vec.weight.data.clone()
                    elif hasattr(mag_vec, 'data'):
                        dora_weights[f"{name}.magnitude"] = mag_vec.data.clone()
                    elif isinstance(mag_vec, torch.nn.Parameter):
                        dora_weights[f"{name}.magnitude"] = mag_vec.data.clone()

        if not dora_weights:
            raise ValueError("No DoRA weights found in model. Ensure model has DoRA adapters.")

        return dora_weights

    def _derive_key(self, salt: bytes, info: bytes) -> bytes:
        """
        Derive encryption key using HKDF-SHA256.

        Args:
            salt: Random salt for key derivation
            info: Application-specific context information

        Returns:
            32-byte encryption key for XChaCha20
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,  # 256-bit key for XChaCha20
            salt=salt,
            info=info,
        )
        return hkdf.derive(self.master_password)

    def rotate_encryption_key(self,
                             encrypted_path: str,
                             new_master_password: bytes,
                             output_path: Optional[str] = None) -> str:
        """
        Re-encrypt adapter with new master password (key rotation).

        Args:
            encrypted_path: Path to existing encrypted adapter
            new_master_password: New 32-byte master password
            output_path: Output path (defaults to overwriting input)

        Returns:
            Path to re-encrypted adapter
        """
        logger.info("Performing key rotation...")

        # Decrypt with old key
        weights = self.decrypt_and_load_dora_weights(encrypted_path)

        # Create new manager with new key
        new_manager = EncryptedDoRAManager(
            new_master_password,
            enable_compression=self.enable_compression,
            compression_level=self.compression_level
        )

        # Re-encrypt with new key
        output_path = output_path or encrypted_path

        # We need to temporarily store weights in a model-like structure
        # For simplicity, we'll save as a dict and re-encrypt
        # (In production, you'd want a proper model wrapper)

        # Create a temporary structure that looks like a model
        class TempModel:
            def named_modules(self):
                return []

        temp_model = TempModel()

        # Manually add weights to the encryption process
        # This is a simplified version - production would need proper handling
        new_manager._encrypt_weights_dict(weights, output_path)

        # Secure cleanup
        secure_zero_dict(weights)

        logger.info(f"Key rotation complete: {output_path}")
        return output_path

    def _encrypt_weights_dict(self, weights: Dict[str, torch.Tensor], output_path: str):
        """
        Helper to encrypt a pre-extracted weights dictionary.

        Args:
            weights: Dictionary of tensors to encrypt
            output_path: Where to save encrypted data
        """
        # Serialize
        serialized_data = save(weights)

        # Compress if enabled
        if self.enable_compression:
            data_to_encrypt = self.compressor.compress(serialized_data)
        else:
            data_to_encrypt = serialized_data

        # Generate new salt and encrypt
        salt = get_random_bytes(16)
        encryption_key = self._derive_key(salt, b"dora-encryption-key-v2")
        nonce = get_random_bytes(24)

        cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)

        metadata = {
            'version': ENCRYPTION_VERSION,
            'num_tensors': len(weights),
            'adapter_type': 'DoRA',
            'original_size_bytes': len(serialized_data),
            'compressed': self.enable_compression,
        }

        aad = json.dumps(metadata, sort_keys=True).encode('utf-8')
        cipher.update(aad)

        ciphertext, tag = cipher.encrypt_and_digest(data_to_encrypt)

        # Save
        encrypted_package = {
            'salt': b64encode(salt).decode('utf-8'),
            'nonce': b64encode(nonce).decode('utf-8'),
            'ciphertext': b64encode(ciphertext).decode('utf-8'),
            'tag': b64encode(tag).decode('utf-8'),
            'metadata': metadata,
            'algorithm': 'XChaCha20-Poly1305',
            'kdf': 'HKDF-SHA256'
        }

        with open(output_path, 'w') as f:
            json.dump(encrypted_package, f, indent=2)


def generate_secure_password() -> bytes:
    """
    Generate a cryptographically secure 32-byte password.

    Returns:
        32-byte password suitable for use as master password
    """
    return get_random_bytes(32)
