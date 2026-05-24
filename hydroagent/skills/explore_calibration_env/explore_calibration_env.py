"""
Tool: explore_calibration_env
Skill: explore_calibration_env
Description: Quick exploration of the Python environment to check available packages,
             calibration tools, and dataset configuration in the workspace.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Known calibration-related packages (safe list, verified to exist in PyPI)
_CALIBRATION_PACKAGES = [
    "pygmo",
    "pygmo_plugins_nonfree",
    "spotpy",
    "emcee",
    "pyabc",
    "hydrocalib",
    "scipy",
    "numpy",
    "pandas",
    "matplotlib",
]


def explore_calibration_env(
    _workspace: Optional[Path] = None, _cfg: Optional[dict] = None
) -> dict:
    """
    Explore the current Python environment and workspace to check for
    available calibration tools, common scientific packages, and
    dataset configuration files.

    Args:
        _workspace: Path to the working directory (injected by agent).
            Defaults to current working directory.
        _cfg: Global configuration dictionary (injected by agent).

    Returns:
        dict: Contains:
            - success (bool): True if exploration completed without errors.
            - packages (dict): Package name -> version for found calibration packages.
            - dataset_config_files (list): Paths of configuration files found in workspace.
            - warnings (list): Any warnings or missing items.
            - error (str, optional): Error message if success is False.
    """
    from importlib.metadata import distributions, version as get_version, PackageNotFoundError

    result: dict = {
        "success": False,
        "packages": {},
        "dataset_config_files": [],
        "warnings": [],
    }

    try:
        # Determine workspace
        workspace = _workspace or Path.cwd()
        if not workspace.is_dir():
            return {
                **result,
                "error": f"Workspace path does not exist or is not a directory: {workspace}",
            }

        # 1. Check for known packages
        installed_dists = {dist.metadata["Name"].lower(): dist for dist in distributions()}
        for pkg in _CALIBRATION_PACKAGES:
            pkg_lower = pkg.lower()
            if pkg_lower in installed_dists:
                try:
                    ver = get_version(pkg_lower)
                except PackageNotFoundError:
                    ver = "unknown"
                result["packages"][pkg_lower] = ver
            else:
                # Some packages may have different distribution names
                # Try fuzzy matching for "calib" substring
                matched = [
                    name for name in installed_dists if "calib" in name
                ]
                if matched:
                    for name in matched:
                        ver = get_version(name)
                        result["packages"][name] = ver
                # else silently ignore, warning added later if important

        # 2. Look for dataset configuration files (YAML, JSON, CFG, INI, TOML)
        config_extensions = {".yaml", ".yml", ".json", ".cfg", ".ini", ".toml"}
        for fpath in workspace.rglob("*"):
            if fpath.is_file() and fpath.suffix.lower() in config_extensions:
                result["dataset_config_files"].append(str(fpath.relative_to(workspace)))

        # 3. Additional warnings
        essential = ["numpy", "scipy", "pandas"]
        missing_essential = [p for p in essential if p not in result["packages"]]
        if missing_essential:
            result["warnings"].append(
                f"Missing essential packages: {', '.join(missing_essential)}"
            )

        result["success"] = True
        logger.info(
            "Environment exploration complete. Found %d packages, %d config files.",
            len(result["packages"]),
            len(result["dataset_config_files"]),
        )

    except Exception as e:
        logger.exception("Error exploring calibration environment")
        result["error"] = f"Unexpected error: {str(e)}"

    return result