"""
Tool: check_environment
Description: Check Python environment: installed packages, data files for basin 12025000, and directory structure.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def check_environment(
    _workspace: Optional[Path] = None,
    _cfg: Optional[dict] = None,
) -> dict:
    """
    Inspect the Python environment for installed packages, look for data files
    related to basin 12025000, and report the directory structure.

    Args:
        _workspace: Working directory path (injected by runtime). Uses current
                    working directory if not provided.
        _cfg: Global configuration dictionary (injected by runtime, not used here).

    Returns:
        dict with keys:
            - "success": bool
            - "python_version": str
            - "installed_packages": list of {"name": str, "version": str}
            - "basin_files": list of paths (str) found containing "12025000"
            - "workspace_structure": list of top-level entries (str)
            - "error": str (only on failure)
    """
    try:
        import subprocess  # lazy import
        import sys
        import os

        # Determine workspace
        workspace = _workspace if _workspace is not None else Path.cwd()
        workspace = workspace.resolve()
        logger.info("Using workspace: %s", workspace)

        # 1. Python version
        python_version = sys.version

        # 2. Installed packages via pip list
        installed_packages = []
        try:
            output = subprocess.check_output(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                text=True,
                stderr=subprocess.STDOUT,
            )
            import json
            pkgs = json.loads(output)
            installed_packages = [{"name": p["name"], "version": p["version"]} for p in pkgs]
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("Failed to retrieve installed packages: %s", e)
            installed_packages = [{"error": f"Could not list packages: {str(e)}"}]

        # 3. Basin 12025000 data files
        basin_files = []
        for entry in workspace.rglob("*"):
            if "12025000" in entry.name:
                basin_files.append(str(entry.relative_to(workspace)))
        basin_files.sort()
        logger.info("Found %d basin-related files", len(basin_files))

        # 4. Directory structure (top-level only)
        workspace_structure = []
        for entry in workspace.iterdir():
            if entry.is_dir():
                workspace_structure.append(f"[DIR] {entry.name}")
            elif entry.is_file():
                workspace_structure.append(f"[FILE] {entry.name}")
        workspace_structure.sort()

        return {
            "success": True,
            "python_version": python_version,
            "installed_packages": installed_packages,
            "basin_files": basin_files,
            "workspace_structure": workspace_structure,
        }

    except Exception as exc:
        logger.error("Unexpected error in check_environment: %s", exc)
        return {
            "success": False,
            "error": f"Unexpected error: {str(exc)}",
        }