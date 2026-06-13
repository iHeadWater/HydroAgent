"""
Author: HydroAgent Team
Date: 2026-02-08
Description: Configuration loader and hydromodel config builder.
"""

import json
import os
from pathlib import Path
from typing import Any

import yaml


def _load_dotenv():
    """Load .env file from project root into os.environ (never overrides existing vars).

    Called once at import time so all downstream code sees the env vars.
    Lines are silently skipped if the file doesn't exist, is empty, or the
    line is a comment / malformed.
    """
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes (both single and double)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if key not in os.environ:
                os.environ[key] = value


# Load .env at module import time (idempotent — won't override existing env vars)
_load_dotenv()


# ── 内部完整默认值 ────────────────────────────────────────────────────────
# 这里是项目内部兜底配置，保证在 configs/config.py 未设置任何参数时也能正常运行。
# 用户自定义参数请在 configs/config.py 中修改，该文件的值会覆盖这里的默认值。
DEFAULTS = {
    "llm": {
        "model": "deepseek-v3.1",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "LLM_API_KEY",
        "temperature": 0.1,
        "max_tokens": 20000,
        "timeout": 120,      # seconds per request; increase if API is slow
        "max_retries": 1,    # openai SDK retries; default 2 causes 3-min stalls on timeout
        "supports_function_calling": None,  # None = auto-detect
    },
    "defaults": {
        # 数据集
        "data_source": "camels_us",              # 数据集类型: camels_us / camels_gb / camels_br / camels_aus 等
        # 模型与算法
        "model": "xaj",                          # 默认水文模型: gr4j / gr5j / gr6j / xaj
        "algorithm": "SCE_UA",                   # 默认优化算法: SCE_UA / GA / scipy
        "obj_func": "NSE",                       # 目标函数: NSE / KGE / RMSE
        # 时间配置
        "train_period": ["2000-01-01", "2009-12-31"],
        "test_period":  ["2010-01-01", "2014-12-31"],
        "warmup": 365,                           # 预热天数（从训练期开始前）
    },
    "algorithms": {
        "SCE_UA": {
            "rep": 500,          # 最大评估次数（用户建议 1000+）
            "ngs": 200,          # 复形数量
            "kstop": 500,        # 停止标准：连续无改进的迭代次数
            "peps": 0.1,         # 参数空间收敛阈值
            "pcento": 0.1,       # 目标函数收敛阈值（百分比）
            "random_seed": 1234,
        },
        "GA": {
            "pop_size": 40,
            "n_generations": 25,
            "cx_prob": 0.7,      # 交叉概率
            "mut_prob": 0.2,     # 变异概率
            "random_seed": 1234,
        },
        "scipy": {
            "method": "SLSQP",   # 可选: L-BFGS-B / SLSQP / Nelder-Mead
            "max_iterations": 500,
            "ftol": 1e-6,
            "gtol": 1e-5,
        },
    },
    "paths": {
        "dataset_dir": None,     # CAMELS 数据集根目录，必须在 configs/definitions_private.py 中设置
        "results_dir": "results",
        "project_dir": None,
        "selfmade_data_path": None,    # 自制数据集父目录（hydrodatasource）
        "selfmade_dataset_name": None, # 数据集文件夹名
    },
    "max_turns": 30,             # Agentic Loop 最大轮次
    "context_compress_threshold": 60_000,  # 上下文压缩触发阈值（估算 token 数）
}


def _ensure_hydro_setting(dataset_dir: str | None, cache_dir: str | None = None,
                          selfmade_data_path: str | None = None):
    """Sync ~/hydro_setting.yml with paths from configs/private.py.

    Priority:
      1. configs/private.py DATASET_DIR is set -> always write it to hydro_setting.yml
      2. DATASET_DIR not set -> fall back to whatever is already in hydro_setting.yml
    Always prints the effective paths for debugging.
    """
    import logging
    logger = logging.getLogger(__name__)

    setting_file = Path.home() / "hydro_setting.yml"

    # Read existing setting (preserve non-path keys)
    existing = {}
    if setting_file.exists():
        try:
            with open(setting_file, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            existing = {}

    current_local = existing.get("local_data_path", {})

    if dataset_dir:
        # private.py has DATASET_DIR — use it to fill/update hydro_setting.yml.
        # AquaFetch automatically appends the class name (e.g. "CAMELS_US") to
        # whatever path is passed, so DATASET_DIR should be the PARENT directory
        # (e.g. D:\data) and AquaFetch will look in D:\data\CAMELS_US\.
        dataset_path = Path(dataset_dir)
        root_path = dataset_path.parent
        cache_path = Path(cache_dir) if cache_dir else dataset_path / "cache"

        # Build updated local_data_path, preserving any extra keys already present.
        updated_local = dict(current_local)  # keep existing fields
        updated_local["root"] = str(root_path)
        updated_local["datasets-origin"] = str(dataset_path)
        # datasets-interim is required by hydromodel; default to same as datasets-origin
        if "datasets-interim" not in updated_local:
            updated_local["datasets-interim"] = str(dataset_path)
        updated_local["cache"] = str(cache_path)
        # basins-origin: parent directory of custom (selfmade) datasets
        if selfmade_data_path:
            updated_local["basins-origin"] = str(Path(selfmade_data_path))
            if "basins-interim" not in updated_local:
                updated_local["basins-interim"] = str(Path(selfmade_data_path))

        if updated_local != current_local:
            existing["local_data_path"] = updated_local
            try:
                with open(setting_file, "w", encoding="utf-8") as f:
                    yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)
            except Exception as e:
                logger.warning("[hydro_setting] Failed to write ~/hydro_setting.yml: %s", e)

        effective = updated_local
        source = "configs/private.py"
    else:
        # private.py has no DATASET_DIR — fall back to existing hydro_setting.yml
        required_keys = {"root", "datasets-origin", "datasets-interim", "cache"}
        if required_keys.issubset(current_local.keys()):
            effective = current_local
            source = "~/hydro_setting.yml (fallback)"
        else:
            print("[hydro_setting] WARNING: DATASET_DIR not set and ~/hydro_setting.yml is incomplete.")
            return

    # print(
    #     f"[hydro_setting] Paths ({source}):\n"
    #     f"  root:              {effective.get('root')}\n"
    #     f"  datasets-origin:   {effective.get('datasets-origin')}\n"
    #     f"  datasets-interim:  {effective.get('datasets-interim')}\n"
    #     f"  cache:             {effective.get('cache')}"
    # )


def _apply_env_overrides(cfg: dict):
    """Apply environment variables on top of cfg (env vars override private.py).

    Supported env vars:
      LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE,
      LLM_MAX_TOKENS, LLM_TIMEOUT, LLM_MAX_RETRIES,
      DATASET_DIR, RESULT_DIR, PROJECT_DIR, CACHE_DIR,
      SELFMADE_DATA_PATH, SELFMADE_DATASET_NAME,
      HYDROAGENT_MAX_TURNS
    """
    llm = cfg.setdefault("llm", {})
    paths = cfg.setdefault("paths", {})

    _set_if_present(llm, "api_key", "LLM_API_KEY")
    _set_if_present(llm, "base_url", "LLM_BASE_URL")
    _set_if_present(llm, "model", "LLM_MODEL")
    _set_if_present(llm, "temperature", "LLM_TEMPERATURE", _to_float)
    _set_if_present(llm, "max_tokens", "LLM_MAX_TOKENS", _to_int)
    _set_if_present(llm, "timeout", "LLM_TIMEOUT", _to_int)
    _set_if_present(llm, "max_retries", "LLM_MAX_RETRIES", _to_int)

    _set_if_present(paths, "dataset_dir", "DATASET_DIR")
    _set_if_present(paths, "results_dir", "RESULT_DIR")
    _set_if_present(paths, "project_dir", "PROJECT_DIR")
    _set_if_present(paths, "cache_dir", "CACHE_DIR")
    _set_if_present(paths, "selfmade_data_path", "SELFMADE_DATA_PATH")
    _set_if_present(paths, "selfmade_dataset_name", "SELFMADE_DATASET_NAME")

    _set_if_present(cfg, "max_turns", "HYDROAGENT_MAX_TURNS", _to_int)


def _set_if_present(d: dict, key: str, env_var: str, convert=None):
    """Set d[key] from os.environ[env_var] if the var exists."""
    val = os.environ.get(env_var)
    if val is not None:
        d[key] = convert(val) if convert else val


def _to_int(v: str) -> int:
    return int(v)


def _to_float(v: str) -> float:
    return float(v)


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from JSON file, falling back to defaults.

    Search order (highest priority last, so later overwrites earlier):
      1. Built-in DEFAULTS
      2. HydroAgent legacy configs/definitions*.py
      3. .env file  (env vars loaded at import time)
      4. ~/.hydroagent/config.json  (user-level, written by setup wizard)
      5. config_path argument       (explicit override, e.g. --config)
    """
    cfg = _deep_copy(DEFAULTS)

    # Try loading from HydroAgent's existing config (lowest external priority)
    _load_from_hydroagent(cfg)

    # Apply env vars from .env / OS environment (overrides private.py)
    _apply_env_overrides(cfg)

    # Load user-level config written by the setup wizard (saved in project root)
    user_cfg_path = Path(__file__).parent.parent / "hydroagent_config.json"
    if user_cfg_path.exists():
        with open(user_cfg_path, "r", encoding="utf-8") as f:
            _deep_merge(cfg, json.load(f))

    # Explicit config file has highest priority
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            _deep_merge(cfg, json.load(f))

    # Override API key from environment (uses api_key_env key if set)
    api_key_env = cfg["llm"].get("api_key_env", "LLM_API_KEY")
    env_key = os.environ.get(api_key_env)
    if env_key:
        cfg["llm"]["api_key"] = env_key

    return cfg


def _load_from_hydroagent(cfg: dict):
    """Try to load settings from existing HydroAgent configs."""
    # Load credentials and paths: try private -> definitions_private -> definitions
    _defs = None
    for _mod_name in ("configs.private", "configs.definitions_private", "configs.definitions"):
        try:
            import importlib
            _defs = importlib.import_module(_mod_name)
            break
        except ImportError:
            continue

    if _defs is not None:
        if not cfg["llm"].get("api_key"):
            cfg["llm"]["api_key"] = getattr(_defs, "OPENAI_API_KEY", None)
        base_url = getattr(_defs, "OPENAI_BASE_URL", None)
        if base_url and (not cfg["llm"].get("base_url") or cfg["llm"]["base_url"] == DEFAULTS["llm"]["base_url"]):
            cfg["llm"]["base_url"] = base_url
        llm_model = getattr(_defs, "LLM_MODEL", None)
        if llm_model:
            cfg["llm"]["model"] = llm_model
        llm_timeout = getattr(_defs, "LLM_TIMEOUT", None)
        if llm_timeout:
            cfg["llm"]["timeout"] = llm_timeout
        llm_max_retries = getattr(_defs, "LLM_MAX_RETRIES", None)
        if llm_max_retries is not None:
            cfg["llm"]["max_retries"] = llm_max_retries
        if not cfg["paths"]["dataset_dir"]:
            cfg["paths"]["dataset_dir"] = getattr(_defs, "DATASET_DIR", None)
        if not cfg["paths"]["project_dir"]:
            cfg["paths"]["project_dir"] = getattr(_defs, "PROJECT_DIR", None)
        result_dir = getattr(_defs, "RESULT_DIR", None)
        if result_dir:
            cfg["paths"]["results_dir"] = result_dir
        cache_dir = getattr(_defs, "CACHE_DIR", None) or None
        cfg["paths"]["cache_dir"] = cache_dir or None
        selfmade_data_path = getattr(_defs, "SELFMADE_DATA_PATH", None)
        selfmade_dataset_name = getattr(_defs, "SELFMADE_DATASET_NAME", None)
        if selfmade_data_path:
            cfg["paths"]["selfmade_data_path"] = selfmade_data_path
        if selfmade_dataset_name:
            cfg["paths"]["selfmade_dataset_name"] = selfmade_dataset_name

        # Auto-sync paths to ~/hydro_setting.yml so hydrodataset/hydrodatasource work out of the box
        _ensure_hydro_setting(cfg["paths"]["dataset_dir"], cache_dir,
                              selfmade_data_path=selfmade_data_path)

    # Load algorithm params: try model_config -> config (backward compat)
    _hcfg = None
    for _mod_name in ("configs.model_config", "configs.config"):
        try:
            import importlib
            _hcfg = importlib.import_module(_mod_name)
            break
        except ImportError:
            continue

    if _hcfg is not None:
        for algo_key, attr in [
            ("SCE_UA", "DEFAULT_SCE_UA_PARAMS"),
            ("GA",     "DEFAULT_GA_PARAMS"),
            ("scipy",  "DEFAULT_scipy_PARAMS"),
        ]:
            params = getattr(_hcfg, attr, None)
            if isinstance(params, dict):
                cfg["algorithms"][algo_key] = params
        for attr, keys in [
            ("DEFAULT_TRAIN_PERIOD", ("defaults", "train_period")),
            ("DEFAULT_TEST_PERIOD",  ("defaults", "test_period")),
            ("DEFAULT_WARMUP_DAYS",  ("defaults", "warmup")),
        ]:
            val = getattr(_hcfg, attr, None)
            if val is not None:
                cfg[keys[0]][keys[1]] = val
        obj_func = getattr(_hcfg, "DEFAULT_OBJ_FUNC", None)
        if obj_func:
            cfg["defaults"]["obj_func"] = obj_func
        data_source = getattr(_hcfg, "DEFAULT_DATA_SOURCE", None)
        if data_source:
            cfg["defaults"]["data_source"] = data_source


# Mapping from user-friendly objective function names to hydromodel's LOSS_DICT keys.
#
# hydromodel SCE-UA and GA both **minimize** the objective function (idxmin / FitnessMin).
# - RMSE:  lower is better → minimize directly ✓
# - NSE/KGE/LogNSE: higher is better → must negate so minimizing -f = maximizing f
#
# The "neg_*" keys are injected into LOSS_DICT at runtime by _inject_negated_losses()
# (called from calibrate_model before hm_calibrate).
_OBJ_FUNC_MAP = {
    "NSE":    "neg_nashsutcliffe",
    "KGE":    "neg_kge",
    "LOGNSE": "neg_lognashsutcliffe",
    "RMSE":   "RMSE",
    "MSE":    "spotpy_mse",
    "MAE":    "spotpy_mae",
}


def build_hydromodel_config(
    basin_ids: list[str],
    model_name: str = "xaj",
    algorithm: str = "SCE_UA",
    train_period: list[str] | None = None,
    test_period: list[str] | None = None,
    algorithm_params: dict | None = None,
    param_range_file: str | None = None,
    obj_func: str | None = None,
    warmup: int | None = None,
    output_dir: str | None = None,
    cfg: dict | None = None,
) -> dict[str, Any]:
    """Build a hydromodel-compatible configuration dictionary.

    Args:
        basin_ids: CAMELS basin IDs.
        model_name: Hydrological model name.
        algorithm: Calibration algorithm.
        train_period: Training period [start, end].
        test_period: Testing period [start, end].
        algorithm_params: Algorithm parameter overrides.
        param_range_file: Path to custom parameter range YAML file.
        obj_func: Objective function override. One of NSE, KGE, LOGNSE, RMSE.
            Takes precedence over cfg["defaults"]["obj_func"].
        warmup: Warmup days.
        output_dir: Output directory for results.
        cfg: Global config dict (from load_config).

    Returns:
        Dictionary ready for hydromodel.calibrate().
    """
    if cfg is None:
        cfg = load_config()

    defaults = cfg.get("defaults", DEFAULTS["defaults"])
    algo_defaults = cfg.get("algorithms", DEFAULTS["algorithms"])

    train_period = train_period or defaults["train_period"]
    test_period = test_period or defaults["test_period"]
    warmup = warmup if warmup is not None else defaults.get("warmup", 365)
    requested_obj_func = (obj_func or defaults.get("obj_func", "NSE")).upper()
    if requested_obj_func not in _OBJ_FUNC_MAP:
        raise ValueError(
            f"Unsupported obj_func '{requested_obj_func}'. "
            f"Supported values: {', '.join(sorted(_OBJ_FUNC_MAP))}"
        )

    # Build algorithm params
    algo_params = dict(algo_defaults.get(algorithm, {}))
    if algorithm_params:
        # LLM 有时会把 dict 序列化成 JSON 字符串传过来，尝试解析
        if isinstance(algorithm_params, str):
            import json as _json
            try:
                algorithm_params = _json.loads(algorithm_params)
            except (ValueError, TypeError):
                algorithm_params = None
        if isinstance(algorithm_params, dict):
            algo_params.update(algorithm_params)

    # random_seed lives in both places: training_cfgs.random_seed (read by
    # hydromodel's top-level config) AND inside algorithm_params (read by
    # SCE-UA via algorithm_config.get("random_seed") in
    # hydromodel/trainers/unified_calibrate.py:819). Using .pop() previously
    # removed it from algo_params and left only training_cfgs.random_seed,
    # so SCE-UA fell back to its hardcoded 1234 default on every trial —
    # making every same-menu, different-trial calibration identical even
    # though our budget_params() generated a different seed per trial.
    # Use .get() so the seed lives in both places.
    random_seed = algo_params.get("random_seed", 1234)

    # Determine output directory
    if not output_dir:
        results_dir = cfg.get("paths", {}).get("results_dir") or "results"
        output_dir = str(Path(results_dir) / f"{model_name}_{algorithm}_{basin_ids[0]}")

    # Determine data source type and path
    data_source = defaults.get("data_source", "camels_us")
    # Normalize alias: "selfmade" -> "selfmadehydrodataset"
    if data_source.lower() in ("selfmade", "selfmadehydrodataset"):
        data_source = "selfmadehydrodataset"
        data_source_path = cfg.get("paths", {}).get("selfmade_data_path")
    else:
        data_source_path = cfg.get("paths", {}).get("dataset_dir")

    # Extra kwargs for selfmade datasets
    selfmade_dataset_name = cfg.get("paths", {}).get("selfmade_dataset_name")

    config = {
        "data_cfgs": {
            "data_source_type": data_source,
            "data_source_path": data_source_path,
            "basin_ids": basin_ids,
            "train_period": train_period,
            "test_period": test_period,
            "warmup_length": warmup,
            "variables": [
                "precipitation",
                "potential_evapotranspiration",
                "streamflow",
            ],
            # selfmadehydrodataset requires dataset_name and time_unit
            **({"dataset_name": selfmade_dataset_name, "time_unit": ["1D"]}
               if data_source == "selfmadehydrodataset" and selfmade_dataset_name else {}),
        },
        "model_cfgs": {
            "model_name": model_name,
        },
        "training_cfgs": {
            "algorithm_name": algorithm,
            "algorithm_params": algo_params,
            "loss_config": {
                "type": "time_series",
                "obj_func": _OBJ_FUNC_MAP[requested_obj_func],
                "requested_obj_func": requested_obj_func,
            },
            "output_dir": output_dir,
            "experiment_name": "",
            "random_seed": random_seed,
            "save_config": True,
            **({"param_range_file": param_range_file} if param_range_file else {}),
        },
    }

    return config


def _deep_copy(d: dict) -> dict:
    """Simple deep copy for nested dicts/lists."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _deep_copy(v)
        elif isinstance(v, list):
            result[k] = list(v)
        else:
            result[k] = v
    return result


def _deep_merge(base: dict, override: dict):
    """Merge override into base, modifying base in place."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
