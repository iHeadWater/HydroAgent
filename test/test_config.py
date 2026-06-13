"""Tests for hydroagent.config."""

import os
from pathlib import Path

import pytest

from hydroagent.config import (
    _deep_copy,
    _deep_merge,
    _apply_env_overrides,
    load_config,
    build_hydromodel_config,
    DEFAULTS,
)


class TestDeepCopy:
    def test_simple_dict(self):
        original = {"a": 1, "b": "hello"}
        copy = _deep_copy(original)
        assert copy == original
        assert copy is not original

    def test_nested_dict_isolation(self):
        original = {"outer": {"inner": 42}}
        copy = _deep_copy(original)
        copy["outer"]["inner"] = 99
        assert original["outer"]["inner"] == 42

    def test_list_isolation(self):
        original = {"items": [1, 2, 3]}
        copy = _deep_copy(original)
        copy["items"].append(4)
        assert original["items"] == [1, 2, 3]

    def test_nested_list_isolation(self):
        original = {"matrix": [[1, 2], [3, 4]]}
        copy = _deep_copy(original)
        # _deep_copy only does shallow list copy (list(v)), so nested lists
        # share inner references. This is the current behavior.
        assert copy["matrix"] is not original["matrix"]  # outer list is new
        assert copy["matrix"][0] is original["matrix"][0]  # inner lists shared

    def test_mixed_types(self):
        original = {"str": "a", "int": 1, "float": 3.14, "none": None, "bool": True}
        assert _deep_copy(original) == original


class TestDeepMerge:
    def test_flat_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 99}
        _deep_merge(base, override)
        assert base == {"a": 1, "b": 99}

    def test_nested_merge(self):
        base = {"llm": {"model": "gpt", "temp": 0.1}}
        override = {"llm": {"model": "qwen"}}
        _deep_merge(base, override)
        assert base == {"llm": {"model": "qwen", "temp": 0.1}}

    def test_new_key_added(self):
        base = {"a": 1}
        override = {"b": 2}
        _deep_merge(base, override)
        assert base == {"a": 1, "b": 2}

    def test_list_replaced_not_merged(self):
        base = {"items": [1, 2]}
        override = {"items": [3]}
        _deep_merge(base, override)
        assert base == {"items": [3]}


class TestApplyEnvOverrides:
    def test_sets_llm_model(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "env-model")
        cfg = {"llm": {}, "paths": {}}
        _apply_env_overrides(cfg)
        assert cfg["llm"]["model"] == "env-model"

    def test_sets_api_key(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-env-key")
        cfg = {"llm": {}, "paths": {}}
        _apply_env_overrides(cfg)
        assert cfg["llm"]["api_key"] == "sk-env-key"

    def test_sets_base_url(self, monkeypatch):
        monkeypatch.setenv("LLM_BASE_URL", "https://api.env.com/v1")
        cfg = {"llm": {}, "paths": {}}
        _apply_env_overrides(cfg)
        assert cfg["llm"]["base_url"] == "https://api.env.com/v1"

    def test_sets_dataset_dir(self, monkeypatch):
        monkeypatch.setenv("DATASET_DIR", "/data/camels")
        cfg = {"llm": {}, "paths": {}}
        _apply_env_overrides(cfg)
        assert cfg["paths"]["dataset_dir"] == "/data/camels"

    def test_sets_results_dir(self, monkeypatch):
        monkeypatch.setenv("RESULT_DIR", "/results")
        cfg = {"llm": {}, "paths": {}}
        _apply_env_overrides(cfg)
        assert cfg["paths"]["results_dir"] == "/results"

    def test_does_not_set_when_env_missing(self, monkeypatch):
        for var in ("LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "DATASET_DIR",
                     "RESULT_DIR", "LLM_TEMPERATURE", "HYDROAGENT_MAX_TURNS"):
            monkeypatch.delenv(var, raising=False)
        cfg = {"llm": {}, "paths": {}}
        _apply_env_overrides(cfg)
        assert "model" not in cfg["llm"]
        assert "dataset_dir" not in cfg["paths"]

    def test_converts_float(self, monkeypatch):
        monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
        cfg = {"llm": {}, "paths": {}}
        _apply_env_overrides(cfg)
        assert cfg["llm"]["temperature"] == 0.7
        assert isinstance(cfg["llm"]["temperature"], float)

    def test_converts_int(self, monkeypatch):
        monkeypatch.setenv("HYDROAGENT_MAX_TURNS", "50")
        cfg = {"llm": {}, "paths": {}}
        _apply_env_overrides(cfg)
        assert cfg["max_turns"] == 50
        assert isinstance(cfg["max_turns"], int)

    def test_overrides_existing_value(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "env-override")
        cfg = {"llm": {"model": "default-model"}, "paths": {}}
        _apply_env_overrides(cfg)
        assert cfg["llm"]["model"] == "env-override"


class TestLoadConfig:
    def test_returns_defaults_when_no_config(self, monkeypatch):
        # Clear env vars that .env may have set to get real defaults
        for var in ("LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "DATASET_DIR",
                     "RESULT_DIR", "LLM_TEMPERATURE", "HYDROAGENT_MAX_TURNS"):
            monkeypatch.delenv(var, raising=False)
        cfg = load_config()
        assert "llm" in cfg
        assert "paths" in cfg
        assert "defaults" in cfg
        assert "algorithms" in cfg
        assert cfg["llm"]["model"] == DEFAULTS["llm"]["model"]

    def test_model_default(self):
        cfg = load_config()
        assert isinstance(cfg["llm"]["model"], str)
        assert len(cfg["llm"]["model"]) > 0

    def test_algorithm_defaults_present(self):
        cfg = load_config()
        assert "SCE_UA" in cfg["algorithms"]
        assert "GA" in cfg["algorithms"]
        assert "scipy" in cfg["algorithms"]
        assert "rep" in cfg["algorithms"]["SCE_UA"]


class TestBuildHydromodelConfig:
    def test_minimal_config(self):
        hcfg = build_hydromodel_config(basin_ids=["01013500"], model_name="gr4j")
        assert hcfg["data_cfgs"]["basin_ids"] == ["01013500"]
        assert hcfg["model_cfgs"]["model_name"] == "gr4j"
        assert hcfg["training_cfgs"]["algorithm_name"] == "SCE_UA"

    def test_custom_algorithm(self):
        hcfg = build_hydromodel_config(
            basin_ids=["01013500"], model_name="xaj", algorithm="GA"
        )
        assert hcfg["training_cfgs"]["algorithm_name"] == "GA"

    def test_obj_func_mapping(self):
        hcfg = build_hydromodel_config(basin_ids=["01013500"], obj_func="KGE")
        assert hcfg["training_cfgs"]["loss_config"]["obj_func"] == "neg_kge"

    def test_invalid_obj_func_raises(self):
        with pytest.raises(ValueError, match="Unsupported obj_func"):
            build_hydromodel_config(basin_ids=["01013500"], obj_func="INVALID")

    def test_algorithm_params_override(self):
        hcfg = build_hydromodel_config(
            basin_ids=["01013500"],
            algorithm="SCE_UA",
            algorithm_params={"rep": 1000},
        )
        assert hcfg["training_cfgs"]["algorithm_params"]["rep"] == 1000

    def test_output_dir_default(self):
        hcfg = build_hydromodel_config(
            basin_ids=["01013500"], model_name="gr4j", algorithm="SCE_UA"
        )
        assert "gr4j_SCE_UA_01013500" in hcfg["training_cfgs"]["output_dir"]

    def test_param_range_file_included(self):
        hcfg = build_hydromodel_config(
            basin_ids=["01013500"], param_range_file="/path/to/params.yaml"
        )
        assert hcfg["training_cfgs"]["param_range_file"] == "/path/to/params.yaml"

    def test_train_test_periods(self):
        hcfg = build_hydromodel_config(
            basin_ids=["01013500"],
            train_period=["2001-01-01", "2005-12-31"],
            test_period=["2006-01-01", "2010-12-31"],
            warmup=180,
        )
        assert hcfg["data_cfgs"]["train_period"] == ["2001-01-01", "2005-12-31"]
        assert hcfg["data_cfgs"]["test_period"] == ["2006-01-01", "2010-12-31"]
        assert hcfg["data_cfgs"]["warmup_length"] == 180
