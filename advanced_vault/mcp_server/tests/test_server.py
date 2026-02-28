"""
Tests for Vault MCP Server
"""

import json
import os
import pytest
import tempfile
from pathlib import Path

from advanced_vault.mcp_server.server import VaultMCPServer


class TestVaultMCPServer:
    """Test MCP server initialization and basic operations."""

    @pytest.fixture
    def temp_vault_path(self):
        """Create temporary vault directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def server(self, temp_vault_path):
        """Create MCP server instance."""
        return VaultMCPServer(vault_path=temp_vault_path)

    def test_server_initialization(self, server, temp_vault_path):
        """Test server initializes correctly."""
        assert server.vault_path == Path(temp_vault_path)
        assert server.server is not None
        assert server.vault is None  # Lazy loaded

    def test_master_key_generation(self, server, temp_vault_path):
        """Test master key is generated on first vault access."""
        vault = server._get_vault()

        assert vault is not None
        assert server._master_key is not None
        assert len(server._master_key) == 32

        # Check key file was created
        key_path = Path(temp_vault_path) / "master.key"
        assert key_path.exists()

        # Check permissions (Unix only)
        if os.name != 'nt':
            stat_info = key_path.stat()
            assert oct(stat_info.st_mode)[-3:] == '600'

    def test_master_key_persistence(self, temp_vault_path):
        """Test master key persists across server instances."""
        # Create first server and generate key
        server1 = VaultMCPServer(vault_path=temp_vault_path)
        vault1 = server1._get_vault()
        key1 = server1._master_key

        # Create second server with same path
        server2 = VaultMCPServer(vault_path=temp_vault_path)
        vault2 = server2._get_vault()
        key2 = server2._master_key

        # Keys should be identical
        assert key1 == key2

    @pytest.mark.asyncio
    async def test_vault_store_secret(self, server):
        """Test storing a secret via MCP tool."""
        args = {
            "content": "sk_test_ABC123",
            "data_type": "secret",
            "service": "stripe",
            "tags": ["payment", "test"],
            "description": "Test Stripe key"
        }

        result = await server._handle_store(server._get_vault(), args)

        assert len(result) == 1
        assert "✅ Stored stripe secret" in result[0].text
        assert "stripe" in result[0].text

    @pytest.mark.asyncio
    async def test_vault_store_knowledge(self, server):
        """Test storing knowledge via MCP tool."""
        args = {
            "content": "Chose Stripe for best developer experience",
            "data_type": "knowledge"
        }

        result = await server._handle_store(server._get_vault(), args)

        assert len(result) == 1
        assert "✅ Stored knowledge" in result[0].text

    @pytest.mark.asyncio
    async def test_vault_recall_exact(self, server):
        """Test recalling exact data."""
        vault = server._get_vault()

        # Store a secret first
        vault.store(
            content="sk_live_ABC123",
            data_type="secret",
            service="stripe"
        )

        # Recall it
        args = {"query": "What's my Stripe API key?"}
        result = await server._handle_recall(vault, args)

        assert len(result) == 1
        assert "✅ Found result" in result[0].text
        assert "sk_live_ABC123" in result[0].text
        assert "exact" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_vault_list_entries(self, server):
        """Test listing vault entries."""
        vault = server._get_vault()

        # Store multiple entries
        vault.store("key1", "secret", "service1", ["tag1"])
        vault.store("key2", "secret", "service2", ["tag2"])
        vault.store("key3", "secret", "service3", ["tag1"])

        # List all
        args = {}
        result = await server._handle_list(vault, args)

        assert len(result) == 1
        assert "Found 3 entries" in result[0].text

        # Filter by tag
        args = {"tag": "tag1"}
        result = await server._handle_list(vault, args)

        assert len(result) == 1
        assert "Found 2 entries" in result[0].text

    @pytest.mark.asyncio
    async def test_vault_delete(self, server):
        """Test deleting an entry."""
        vault = server._get_vault()

        # Store an entry
        vault.store("key1", "secret", "testservice")

        # Delete it
        args = {"service": "testservice"}
        result = await server._handle_delete(vault, args)

        assert len(result) == 1
        assert "✅ Deleted" in result[0].text
        assert "testservice" in result[0].text

        # Try to delete again (should fail)
        result = await server._handle_delete(vault, args)
        assert "❌ No entry found" in result[0].text

    @pytest.mark.asyncio
    async def test_vault_stats(self, server):
        """Test vault statistics."""
        vault = server._get_vault()

        # Store some entries
        vault.store("key1", "secret", "service1")
        vault.store("key2", "secret", "service2")

        args = {}
        result = await server._handle_stats(vault, args)

        assert len(result) == 1
        assert "📊 Vault Statistics" in result[0].text
        assert "Total entries: 2" in result[0].text
        assert "service1" in result[0].text
        assert "service2" in result[0].text

    @pytest.mark.asyncio
    async def test_error_handling(self, server):
        """Test error handling for invalid inputs."""
        vault = server._get_vault()

        # Try to store secret without service
        args = {
            "content": "some_key",
            "data_type": "secret"
            # Missing 'service'
        }

        result = await server._handle_store(vault, args)
        assert "Error" in result[0].text

    @pytest.mark.asyncio
    async def test_recall_nonexistent(self, server):
        """Test recalling non-existent entry."""
        vault = server._get_vault()

        args = {"query": "What's my nonexistent key?"}
        result = await server._handle_recall(vault, args)

        assert len(result) == 1
        # Should return an error or "not found" message
        assert ("❌" in result[0].text or "❓" in result[0].text or "No" in result[0].text)

    @pytest.mark.asyncio
    async def test_sheriff_access_read_revoke_flow(self, server, monkeypatch):
        """Test sheriff lease lifecycle through MCP handlers."""
        critical_file = Path(server.vault_path) / "tax_records_2025.pem"
        critical_file.write_text("password=supersecret")

        monkeypatch.setattr(server.consent_manager, "request_consent", lambda **_: True)

        request_result = await server._handle_sheriff_request_access(
            {
                "resource": str(critical_file),
                "purpose": "summarize for user",
                "ttl_seconds": 300,
            },
            app_identifier="test-app",
        )
        payload = json.loads(request_result[0].text)
        assert payload["decision"] == "ALLOW_WITH_LEASE"
        assert payload["lease"] is not None
        lease_id = payload["lease"]["lease_id"]

        read_result = await server._handle_sheriff_read(
            {
                "resource": str(critical_file),
                "lease_id": lease_id,
                "redact": True,
            },
            app_identifier="test-app",
        )
        assert "[REDACTED]" in read_result[0].text

        revoke_result = await server._handle_sheriff_revoke({"lease_id": lease_id})
        assert "✅ Lease revoked" in revoke_result[0].text

        denied_read = await server._handle_sheriff_read(
            {
                "resource": str(critical_file),
                "lease_id": lease_id,
            },
            app_identifier="test-app",
        )
        assert "❌ Access denied" in denied_read[0].text

    @pytest.mark.asyncio
    async def test_sheriff_list_audit(self, server, monkeypatch):
        """Test sheriff audit listing handler."""
        critical_file = Path(server.vault_path) / "passport_copy.pem"
        critical_file.write_text("dummy")
        monkeypatch.setattr(server.consent_manager, "request_consent", lambda **_: True)

        await server._handle_sheriff_request_access(
            {
                "resource": str(critical_file),
                "purpose": "read metadata",
                "ttl_seconds": 120,
            },
            app_identifier="test-audit-app",
        )
        audit_result = await server._handle_sheriff_list_audit({"limit": 10, "subject": "test-audit-app"})
        audit_payload = json.loads(audit_result[0].text)
        assert "items" in audit_payload
        assert len(audit_payload["items"]) >= 1
        assert any(item["subject"] == "test-audit-app" for item in audit_payload["items"])

    @pytest.mark.asyncio
    async def test_sheriff_risk_summary_and_protect_now(self, server):
        """Test risk scanning summary and rule creation handlers."""
        scan_dir = Path(server.vault_path) / "scan-root"
        scan_dir.mkdir(parents=True, exist_ok=True)
        (scan_dir / "medical_notes.txt").write_text("basic note")

        risk_result = await server._handle_sheriff_risk_summary(
            {"paths": [str(scan_dir)], "max_files": 100}
        )
        risk_payload = json.loads(risk_result[0].text)
        assert risk_payload["total_files"] >= 1
        assert "recommendations" in risk_payload

        protect_result = await server._handle_sheriff_protect_now({"paths": [str(scan_dir)]})
        protect_payload = json.loads(protect_result[0].text)
        assert protect_payload["count"] == 1
        assert len(protect_payload["rules"]) == 1

    @pytest.mark.asyncio
    async def test_sheriff_hardening_and_enforcement_status(self, server):
        """Test hardening/enforcement status handlers."""
        hardening_result = await server._handle_sheriff_hardening_report({})
        hardening_payload = json.loads(hardening_result[0].text)
        assert "alerts" in hardening_payload
        assert isinstance(hardening_payload["alerts"], list)

        enforcement_result = await server._handle_sheriff_enforcement_status({})
        enforcement_payload = json.loads(enforcement_result[0].text)
        assert "backend" in enforcement_payload
        assert "enabled" in enforcement_payload


class TestMCPToolDefinitions:
    """Test MCP tool definitions are correct."""

    @pytest.fixture
    def server(self):
        """Create server with temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield VaultMCPServer(vault_path=tmpdir)

    @pytest.mark.asyncio
    async def test_list_tools(self, server):
        """Test tool listing."""
        # Get the list_tools handler
        from mcp.server import Server

        # Tools should be registered
        assert server.server is not None

        # We can't directly call async decorated methods, but we can verify
        # the server was initialized with tools
        assert hasattr(server, '_handle_store')
        assert hasattr(server, '_handle_recall')
        assert hasattr(server, '_handle_list')
        assert hasattr(server, '_handle_delete')
        assert hasattr(server, '_handle_stats')
        assert hasattr(server, '_handle_sheriff_request_access')
        assert hasattr(server, '_handle_sheriff_read')
        assert hasattr(server, '_handle_sheriff_list_audit')
        assert hasattr(server, '_handle_sheriff_revoke')
        assert hasattr(server, '_handle_sheriff_risk_summary')
        assert hasattr(server, '_handle_sheriff_protect_now')
        assert hasattr(server, '_handle_sheriff_hardening_report')
        assert hasattr(server, '_handle_sheriff_enforcement_status')


class TestVaultIntegration:
    """Integration tests for full vault workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete store-recall-delete workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = VaultMCPServer(vault_path=tmpdir)
            vault = server._get_vault()

            # 1. Store a secret
            store_args = {
                "content": "sk_live_PRODUCTION_KEY",
                "data_type": "secret",
                "service": "stripe",
                "tags": ["payment", "production"],
                "description": "Production Stripe key"
            }
            result = await server._handle_store(vault, store_args)
            assert "✅ Stored stripe secret" in result[0].text

            # 2. Recall the secret
            recall_args = {"query": "What's my Stripe API key?"}
            result = await server._handle_recall(vault, recall_args)
            assert "sk_live_PRODUCTION_KEY" in result[0].text

            # 3. List entries
            list_args = {"tag": "payment"}
            result = await server._handle_list(vault, list_args)
            assert "Found 1 entries" in result[0].text

            # 4. Get stats
            stats_args = {}
            result = await server._handle_stats(vault, stats_args)
            assert "Total entries: 1" in result[0].text

            # 5. Delete the entry
            delete_args = {"service": "stripe"}
            result = await server._handle_delete(vault, delete_args)
            assert "✅ Deleted" in result[0].text

            # 6. Verify it's gone
            result = await server._handle_recall(vault, recall_args)
            assert "❌" in result[0].text or "❓" in result[0].text
