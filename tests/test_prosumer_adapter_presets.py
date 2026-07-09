"""
Tests for prosumer adapter presets.
"""

import pytest
from advanced_vault.prosumer.adapter_presets import (
    get_preset_for_category,
    get_preset,
    list_presets,
    list_presets_for_category,
    HEALTH_ADVISOR,
    TAX_ASSISTANT,
    LEGAL_COMPANION,
    LIFE_ARCHIVIST,
    GENERAL_ASSISTANT,
    TrainingMethod,
)


class TestAdapterPresets:

    def test_health_advisor_preset(self):
        assert HEALTH_ADVISOR.id == "health_advisor"
        assert HEALTH_ADVISOR.category_id == "health"
        assert HEALTH_ADVISOR.training_method == TrainingMethod.DPO
        assert HEALTH_ADVISOR.require_disclaimer is True
        assert "medical_disclaimer" in HEALTH_ADVISOR.safety_checks
        assert HEALTH_ADVISOR.lora_rank == 16

    def test_tax_assistant_preset(self):
        assert TAX_ASSISTANT.id == "tax_assistant"
        assert TAX_ASSISTANT.category_id == "finance"
        assert "calculation_accuracy" in TAX_ASSISTANT.reward_functions
        assert TAX_ASSISTANT.estimated_training_time_minutes == 15

    def test_legal_companion_preset(self):
        assert LEGAL_COMPANION.id == "legal_companion"
        assert LEGAL_COMPANION.category_id == "legal"
        assert LEGAL_COMPANION.max_seq_length == 4096
        assert LEGAL_COMPANION.require_disclaimer is True
        assert "legal_disclaimer" in LEGAL_COMPANION.safety_checks

    def test_life_archivist_preset(self):
        assert LIFE_ARCHIVIST.id == "life_archivist"
        assert LIFE_ARCHIVIST.category_id == "personal"
        assert LIFE_ARCHIVIST.require_disclaimer is False
        assert "empathy" in LIFE_ARCHIVIST.reward_functions

    def test_general_preset(self):
        assert GENERAL_ASSISTANT.id == "general"
        assert GENERAL_ASSISTANT.training_method == TrainingMethod.SFT

    def test_get_preset_for_category(self):
        assert get_preset_for_category("health").id == "health_advisor"
        assert get_preset_for_category("finance").id == "tax_assistant"
        assert get_preset_for_category("legal").id == "legal_companion"
        assert get_preset_for_category("personal").id == "life_archivist"
        assert get_preset_for_category("unknown").id == "general"

    def test_get_preset(self):
        preset = get_preset("tax_assistant")
        assert preset is not None
        assert preset.id == "tax_assistant"

    def test_get_preset_invalid(self):
        assert get_preset("nonexistent") is None

    def test_list_presets(self):
        presets = list_presets()
        assert len(presets) == 5

    def test_list_presets_for_category(self):
        health_presets = list_presets_for_category("health")
        assert len(health_presets) == 1
        assert health_presets[0].id == "health_advisor"

    def test_preset_to_training_config(self):
        config = HEALTH_ADVISOR.to_training_config()
        assert config["base_model"] == HEALTH_ADVISOR.base_model
        assert config["training_method"] == "dpo"
        assert config["lora_config"]["rank"] == 16
        assert "citation" in config["reward_functions"]

    def test_estimate_time(self):
        time_5_docs = HEALTH_ADVISOR.estimate_time(5)
        time_20_docs = HEALTH_ADVISOR.estimate_time(20)
        assert time_5_docs > 0
        assert time_20_docs >= time_5_docs
        assert time_20_docs <= HEALTH_ADVISOR.estimated_training_time_minutes * 2
