"""
Tests for prosumer vault categories.
"""

import pytest
from advanced_vault.prosumer.vault_categories import (
    get_category_for_document,
    get_category_by_id,
    list_categories,
    HEALTH_VAULT,
    FINANCE_VAULT,
    LEGAL_VAULT,
    PERSONAL_VAULT,
)


class TestVaultCategories:
    
    def test_health_category_properties(self):
        assert HEALTH_VAULT.id == "health"
        assert HEALTH_VAULT.privacy_level.value == "critical"
        assert "pdf" in HEALTH_VAULT.file_extensions
        assert "medical" in HEALTH_VAULT.keywords
    
    def test_finance_category_properties(self):
        assert FINANCE_VAULT.id == "finance"
        assert FINANCE_VAULT.recommended_preset == "tax_assistant"
        assert "bank" in FINANCE_VAULT.keywords
    
    def test_legal_category_properties(self):
        assert LEGAL_VAULT.id == "legal"
        assert LEGAL_VAULT.chunk_size == 1024  # Legal docs need larger chunks
    
    def test_personal_category_properties(self):
        assert PERSONAL_VAULT.id == "personal"
        assert PERSONAL_VAULT.privacy_level.value == "standard"
    
    def test_file_matching_health(self):
        score = HEALTH_VAULT.matches_file("blood_test_results.pdf", "application/pdf")
        assert score > 0.5
    
    def test_file_matching_finance(self):
        score = FINANCE_VAULT.matches_file("chase_statement_march.pdf", "application/pdf")
        assert score > 0.5
    
    def test_file_matching_legal(self):
        score = LEGAL_VAULT.matches_file("employment_contract.pdf", "application/pdf")
        assert score > 0.5
    
    def test_content_classification_health(self):
        text = "Patient: John Doe. Diagnosis: Type 2 Diabetes. Medication: Metformin 500mg."
        score = HEALTH_VAULT.classify_content(text)
        assert score > 0.5
    
    def test_content_classification_finance(self):
        text = "Bank Statement. Account ending in 4521. Balance: $12,450.00."
        score = FINANCE_VAULT.classify_content(text)
        assert score > 0.5
    
    def test_get_category_for_document_with_content(self):
        category, confidence = get_category_for_document(
            filename="lab_results.pdf",
            mime_type="application/pdf",
            content_preview="Patient ID: 12345. Blood glucose: 95 mg/dL. Cholesterol: 180."
        )
        assert category.id == "health"
        assert confidence > 0.5
    
    def test_get_category_for_document_finance(self):
        category, confidence = get_category_for_document(
            filename="tax_return_2024.pdf",
            mime_type="application/pdf",
            content_preview="Form 1040. Adjusted gross income: $75,000. Deductions: $15,000."
        )
        assert category.id == "finance"
        assert confidence > 0.5
    
    def test_get_category_by_id(self):
        cat = get_category_by_id("health")
        assert cat is not None
        assert cat.id == "health"
    
    def test_get_category_by_id_invalid(self):
        cat = get_category_by_id("nonexistent")
        assert cat is None
    
    def test_list_categories(self):
        cats = list_categories()
        assert len(cats) == 4
        ids = [c.id for c in cats]
        assert "health" in ids
        assert "finance" in ids
        assert "legal" in ids
        assert "personal" in ids
