"""
Tests for AdapterPackager.

Verifies packaging, encryption, and unpacking without requiring MLX.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


try:
    from advanced_vault.training.adapter_packager import (
        AdapterPackager,
        AdapterMetadata,
    )
    PACKAGER_AVAILABLE = True
except ImportError:
    PACKAGER_AVAILABLE = False


@pytest.mark.skipif(not PACKAGER_AVAILABLE, reason="adapter_packager not available")
class TestAdapterMetadata:
    def test_to_dict(self):
        meta = AdapterMetadata(name="test", version="1.0")
        d = meta.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "1.0"
        assert d["qat_enabled"] is False

    def test_from_dict(self):
        data = {"name": "test", "train_mode": "dpo", "unknown_key": "ignore"}
        meta = AdapterMetadata.from_dict(data)
        assert meta.name == "test"
        assert meta.train_mode == "dpo"
        # unknown_key should be ignored
        assert not hasattr(meta, "unknown_key")


@pytest.mark.skipif(not PACKAGER_AVAILABLE, reason="adapter_packager not available")
class TestAdapterPackager:
    def test_package_and_unpack_enclave(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "my_adapter"
            adapter_dir.mkdir()
            # Create fake safetensors file
            (adapter_dir / "adapter_model.safetensors").write_bytes(b"FAKE_WEIGHTS")
            (adapter_dir / "adapter_config.json").write_text('{"rank": 8}')

            output = Path(tmp) / "package.enclave"
            packager = AdapterPackager()

            result = packager.package_adapter(
                adapter_dir=str(adapter_dir),
                output_path=str(output),
                password="secret123",
                metadata={"name": "my_adapter", "train_mode": "dpo"},
                format="enclave",
            )
            assert Path(result).exists()

            # Unpack
            unpack_dir = Path(tmp) / "unpacked"
            meta = packager.unpack_adapter(
                package_path=result,
                output_dir=str(unpack_dir),
                password="secret123",
            )
            assert meta.name == "my_adapter"
            assert meta.train_mode == "dpo"
            assert (unpack_dir / "adapter_model.safetensors").exists()
            assert (unpack_dir / "adapter_config.json").exists()

    def test_package_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            adapter_dir.mkdir()
            (adapter_dir / "adapter_model.safetensors").write_bytes(b"FAKE")

            output = Path(tmp) / "package.zip"
            packager = AdapterPackager()

            result = packager.package_adapter(
                adapter_dir=str(adapter_dir),
                output_path=str(output),
                format="zip",
            )
            assert Path(result).exists()
            assert result.endswith(".zip")

    def test_verify_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            adapter_dir.mkdir()
            (adapter_dir / "adapter_model.safetensors").write_bytes(b"FAKE")

            output = Path(tmp) / "package.enclave"
            packager = AdapterPackager()
            packager.package_adapter(
                adapter_dir=str(adapter_dir),
                output_path=str(output),
                password="testpass",
            )

            result = packager.verify_package(str(output), password="testpass")
            assert result["valid"] is True
            assert result["checksum_match"] is True

    def test_verify_wrong_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            adapter_dir.mkdir()
            (adapter_dir / "adapter_model.safetensors").write_bytes(b"FAKE")

            output = Path(tmp) / "package.enclave"
            packager = AdapterPackager()
            packager.package_adapter(
                adapter_dir=str(adapter_dir),
                output_path=str(output),
                password="rightpass",
            )

            result = packager.verify_package(str(output), password="wrongpass")
            assert result["valid"] is False

    def test_package_no_safetensors(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "empty"
            adapter_dir.mkdir()
            packager = AdapterPackager()
            with pytest.raises(ValueError):
                packager.package_adapter(
                    adapter_dir=str(adapter_dir),
                    output_path="out.enclave",
                    password="pass",
                )
