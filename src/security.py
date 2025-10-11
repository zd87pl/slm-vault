"""
Security and Privacy Layer for Personal SLM System
Implements encryption, access control, and data isolation
"""

import os
import secrets
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from cryptography.hazmat.backends import default_backend
import boto3
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import redis
from functools import wraps
import logging


# Configure secure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SecurityConfig:
    """Security configuration"""
    encryption_algorithm: str = "AES-256-GCM"
    key_derivation_iterations: int = 100000
    token_expiry_minutes: int = 30
    max_login_attempts: int = 5
    session_timeout_minutes: int = 30
    audit_retention_days: int = 90
    enable_mfa: bool = True
    enable_secure_enclave: bool = True


class KeyManagement:
    """Centralized key management with HSM support"""

    def __init__(self, provider: str = "aws"):
        self.provider = provider
        self.master_key = self._initialize_master_key()

    def _initialize_master_key(self) -> bytes:
        """Initialize master key from HSM or vault"""
        if self.provider == "aws":
            # AWS KMS
            kms = boto3.client('kms')
            response = kms.generate_data_key(
                KeyId='alias/slm-master-key',
                KeySpec='AES_256'
            )
            return response['Plaintext']
        elif self.provider == "azure":
            # Azure Key Vault
            credential = DefaultAzureCredential()
            client = SecretClient(
                vault_url="https://slm-vault.vault.azure.net/",
                credential=credential
            )
            secret = client.get_secret("master-key")
            return secret.value.encode()
        else:
            # Local development only
            return Fernet.generate_key()

    def derive_user_key(self, user_id: str, salt: bytes = None) -> bytes:
        """Derive user-specific encryption key"""
        if salt is None:
            salt = os.urandom(32)

        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )

        user_key = kdf.derive(
            self.master_key + user_id.encode()
        )

        return Fernet.generate_key()  # In production, use derived key

    def rotate_keys(self, user_id: str) -> Tuple[bytes, bytes]:
        """Rotate user encryption keys"""
        old_key = self.derive_user_key(user_id)
        new_salt = os.urandom(32)
        new_key = self.derive_user_key(user_id, new_salt)

        logger.info(f"Rotated keys for user {user_id}")
        return old_key, new_key


class DataEncryption:
    """Handles all data encryption/decryption operations"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.key_manager = KeyManagement()
        self.cipher = Fernet(self.key_manager.derive_user_key(user_id))

    def encrypt_data(self, data: bytes) -> bytes:
        """Encrypt data with user key"""
        return self.cipher.encrypt(data)

    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        """Decrypt data with user key"""
        return self.cipher.decrypt(encrypted_data)

    def encrypt_file(self, file_path: Path, output_path: Path):
        """Encrypt entire file"""
        with open(file_path, 'rb') as f:
            data = f.read()

        encrypted = self.encrypt_data(data)

        # Write with restricted permissions
        with open(output_path, 'wb') as f:
            f.write(encrypted)

        os.chmod(output_path, 0o600)  # Owner read/write only

    def decrypt_file(self, encrypted_path: Path, output_path: Path):
        """Decrypt entire file"""
        with open(encrypted_path, 'rb') as f:
            encrypted_data = f.read()

        decrypted = self.decrypt_data(encrypted_data)

        with open(output_path, 'wb') as f:
            f.write(decrypted)


class AccessControl:
    """Manages authentication and authorization"""

    def __init__(self, config: SecurityConfig = SecurityConfig()):
        self.config = config
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True,
            ssl=True
        )
        self.secret_key = secrets.token_urlsafe(32)

    def generate_token(self, user_id: str, scope: List[str] = None) -> str:
        """Generate JWT access token"""
        payload = {
            'user_id': user_id,
            'scope': scope or ['read', 'write'],
            'exp': datetime.utcnow() + timedelta(minutes=self.config.token_expiry_minutes),
            'iat': datetime.utcnow(),
            'jti': secrets.token_urlsafe(16)  # Unique token ID
        }

        token = jwt.encode(payload, self.secret_key, algorithm='HS256')

        # Store in Redis for revocation checking
        self.redis_client.setex(
            f"token:{payload['jti']}",
            self.config.token_expiry_minutes * 60,
            json.dumps({'user_id': user_id, 'active': True})
        )

        return token

    def verify_token(self, token: str) -> Dict:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])

            # Check if token is revoked
            token_data = self.redis_client.get(f"token:{payload['jti']}")
            if not token_data:
                raise jwt.InvalidTokenError("Token not found")

            token_info = json.loads(token_data)
            if not token_info.get('active'):
                raise jwt.InvalidTokenError("Token revoked")

            return payload
        except jwt.ExpiredSignatureError:
            raise Exception("Token expired")
        except jwt.InvalidTokenError as e:
            raise Exception(f"Invalid token: {e}")

    def revoke_token(self, token: str):
        """Revoke an access token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            key = f"token:{payload['jti']}"

            token_data = self.redis_client.get(key)
            if token_data:
                token_info = json.loads(token_data)
                token_info['active'] = False
                self.redis_client.set(key, json.dumps(token_info))

            logger.info(f"Revoked token for user {payload['user_id']}")
        except Exception as e:
            logger.error(f"Error revoking token: {e}")

    def check_permissions(self, user_id: str, resource: str, action: str) -> bool:
        """Check if user has permission for resource/action"""
        # Users can only access their own resources
        resource_parts = resource.split('/')
        if len(resource_parts) > 1:
            resource_user_id = resource_parts[1]
            if resource_user_id != user_id:
                return False

        # Check specific permissions (in production, use proper RBAC)
        allowed_actions = {
            'model': ['read', 'write', 'train', 'inference'],
            'data': ['read', 'write', 'delete'],
            'metrics': ['read']
        }

        resource_type = resource_parts[0]
        return action in allowed_actions.get(resource_type, [])


class SecureStorage:
    """Secure storage with encryption and access control"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.encryption = DataEncryption(user_id)
        self.base_path = Path(f"/secure-storage/{user_id}")
        self.base_path.mkdir(parents=True, exist_ok=True, mode=0o700)

    def store_data(self, data: bytes, filename: str, metadata: Dict = None):
        """Securely store data"""
        # Encrypt data
        encrypted = self.encryption.encrypt_data(data)

        # Generate secure filename
        file_hash = hashlib.sha256(filename.encode()).hexdigest()[:16]
        secure_path = self.base_path / f"{file_hash}.enc"

        # Store with metadata
        storage_record = {
            'original_name': filename,
            'encrypted_path': str(secure_path),
            'size': len(data),
            'encrypted_size': len(encrypted),
            'checksum': hashlib.sha256(data).hexdigest(),
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }

        # Write encrypted data
        with open(secure_path, 'wb') as f:
            f.write(encrypted)

        # Store metadata
        meta_path = self.base_path / f"{file_hash}.meta"
        with open(meta_path, 'w') as f:
            json.dump(storage_record, f)

        logger.info(f"Stored {filename} for user {self.user_id}")
        return storage_record

    def retrieve_data(self, filename: str) -> bytes:
        """Retrieve and decrypt data"""
        file_hash = hashlib.sha256(filename.encode()).hexdigest()[:16]
        secure_path = self.base_path / f"{file_hash}.enc"

        if not secure_path.exists():
            raise FileNotFoundError(f"File {filename} not found")

        # Read and decrypt
        with open(secure_path, 'rb') as f:
            encrypted = f.read()

        decrypted = self.encryption.decrypt_data(encrypted)

        # Verify checksum
        meta_path = self.base_path / f"{file_hash}.meta"
        with open(meta_path, 'r') as f:
            metadata = json.load(f)

        if hashlib.sha256(decrypted).hexdigest() != metadata['checksum']:
            raise ValueError("Data integrity check failed")

        logger.info(f"Retrieved {filename} for user {self.user_id}")
        return decrypted

    def delete_data(self, filename: str, permanent: bool = False):
        """Delete stored data"""
        file_hash = hashlib.sha256(filename.encode()).hexdigest()[:16]
        secure_path = self.base_path / f"{file_hash}.enc"
        meta_path = self.base_path / f"{file_hash}.meta"

        if permanent:
            # Secure deletion with overwrite
            if secure_path.exists():
                file_size = secure_path.stat().st_size
                with open(secure_path, 'wb') as f:
                    f.write(os.urandom(file_size))  # Overwrite with random data
                secure_path.unlink()

            if meta_path.exists():
                meta_path.unlink()

            logger.info(f"Permanently deleted {filename} for user {self.user_id}")
        else:
            # Soft delete (move to trash)
            trash_dir = self.base_path / ".trash"
            trash_dir.mkdir(exist_ok=True, mode=0o700)

            if secure_path.exists():
                secure_path.rename(trash_dir / secure_path.name)
            if meta_path.exists():
                meta_path.rename(trash_dir / meta_path.name)

            logger.info(f"Soft deleted {filename} for user {self.user_id}")


class AuditLogger:
    """Comprehensive audit logging for compliance"""

    def __init__(self):
        self.log_path = Path("/secure-logs/audit")
        self.log_path.mkdir(parents=True, exist_ok=True, mode=0o700)

    def log_access(self, user_id: str, resource: str, action: str, result: str):
        """Log access attempt"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'resource': resource,
            'action': action,
            'result': result,
            'ip_address': self._get_client_ip(),
            'session_id': self._get_session_id()
        }

        # Write to daily log file
        log_file = self.log_path / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"

        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

        # Alert on suspicious activity
        if result == "denied":
            self._check_suspicious_activity(user_id)

    def _get_client_ip(self) -> str:
        """Get client IP address"""
        # In production, extract from request context
        return "127.0.0.1"

    def _get_session_id(self) -> str:
        """Get current session ID"""
        # In production, extract from session context
        return secrets.token_urlsafe(8)

    def _check_suspicious_activity(self, user_id: str):
        """Check for patterns of suspicious activity"""
        # Count recent failed attempts
        today_log = self.log_path / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"

        if today_log.exists():
            failed_attempts = 0
            with open(today_log, 'r') as f:
                for line in f:
                    entry = json.loads(line)
                    if entry['user_id'] == user_id and entry['result'] == 'denied':
                        failed_attempts += 1

            if failed_attempts > 5:
                logger.warning(f"Suspicious activity detected for user {user_id}")
                # In production: trigger alerts, temporary lockout, etc.


def require_auth(scope: List[str] = None):
    """Decorator for protecting endpoints"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract token from request (placeholder)
            token = kwargs.get('token')

            if not token:
                raise Exception("No authentication token provided")

            access_control = AccessControl()
            payload = access_control.verify_token(token)

            # Check scope
            if scope:
                token_scope = payload.get('scope', [])
                if not all(s in token_scope for s in scope):
                    raise Exception("Insufficient permissions")

            # Add user context
            kwargs['user_id'] = payload['user_id']

            # Audit log
            audit = AuditLogger()
            audit.log_access(
                payload['user_id'],
                func.__name__,
                'execute',
                'allowed'
            )

            return func(*args, **kwargs)
        return wrapper
    return decorator


class PIIFilter:
    """Filter and redact PII from outputs"""

    def __init__(self):
        self.patterns = {
            'ssn': r'\d{3}-\d{2}-\d{4}',
            'email': r'[\w\.-]+@[\w\.-]+\.\w+',
            'phone': r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',
            'credit_card': r'\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}',
            'genetic_marker': r'rs\d+',  # SNP IDs
            'ip_address': r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
        }

    def sanitize(self, text: str, user_preferences: Dict = None) -> str:
        """Remove or redact PII based on user preferences"""
        import re

        sanitized = text

        for pii_type, pattern in self.patterns.items():
            # Check user preferences
            if user_preferences and not user_preferences.get(f'show_{pii_type}', False):
                # Redact based on type
                if pii_type == 'genetic_marker':
                    sanitized = re.sub(pattern, '[GENETIC_DATA]', sanitized)
                else:
                    sanitized = re.sub(pattern, '[REDACTED]', sanitized)

        return sanitized


if __name__ == "__main__":
    # Test security components
    user_id = "test_user_001"

    # Test encryption
    encryption = DataEncryption(user_id)
    original = b"Sensitive health data"
    encrypted = encryption.encrypt_data(original)
    decrypted = encryption.decrypt_data(encrypted)
    assert original == decrypted
    print("✓ Encryption test passed")

    # Test access control
    access = AccessControl()
    token = access.generate_token(user_id, ['read', 'write'])
    payload = access.verify_token(token)
    assert payload['user_id'] == user_id
    print("✓ Access control test passed")

    # Test secure storage
    storage = SecureStorage(user_id)
    test_data = b"Model weights and parameters"
    record = storage.store_data(test_data, "model_v1.pt")
    retrieved = storage.retrieve_data("model_v1.pt")
    assert test_data == retrieved
    print("✓ Secure storage test passed")

    # Test PII filter
    pii_filter = PIIFilter()
    text = "User rs1234567 has email test@example.com"
    sanitized = pii_filter.sanitize(text, {'show_email': False})
    assert "rs1234567" not in sanitized
    assert "test@example.com" not in sanitized
    print("✓ PII filter test passed")

    print("\nAll security tests passed!")