"""
Enclave Prosumer Module
Privacy-first personal AI for health, finance, legal, and personal knowledge.

This module provides:
- Document categorization into personal vaults
- Domain-specific adapter presets
- Encrypted adapter backup/sharing
- Consumer-friendly onboarding flows

Copyright © 2025 Zygmunt Dyras. All rights reserved.
"""

from .vault_categories import VaultCategory, VAULT_CATEGORIES, get_category_for_document
from .document_classifier import DocumentClassifier, ClassificationResult
from .adapter_presets import AdapterPreset, PROSUMER_PRESETS, get_preset_for_category
from .adapter_backup import AdapterBackupManager, BackupFormat

__all__ = [
    "VaultCategory",
    "VAULT_CATEGORIES",
    "get_category_for_document",
    "DocumentClassifier",
    "ClassificationResult",
    "AdapterPreset",
    "PROSUMER_PRESETS",
    "get_preset_for_category",
    "AdapterBackupManager",
    "BackupFormat",
]
