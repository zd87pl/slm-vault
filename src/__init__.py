"""
DoRA-Based Weight-Delta Vault Adapter (WDVA) Implementation

Complete implementation of secure DoRA adapter training, encryption, and inference.
"""

__version__ = "2.0.0"

from .dora_crypto import EncryptedDoRAManager, generate_secure_password
from .ephemeral_inference import EphemeralDoRAInference
from .utils import AdapterCache

__all__ = [
    'EncryptedDoRAManager',
    'generate_secure_password',
    'EphemeralDoRAInference',
    'AdapterCache',
]
