"""Tool to explore the Python environment and check available packages/modules.

This tool wraps standard library `os` and `sys` to provide environmental
information such as directory listings, environment variables, Python version,
and system paths. It is intended for calibration and debugging workflows.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def explore_environment(
    action: str,
    path: Optional[str] = None,
    name: Optional[str] = None,
    _workspace: Optional[Path] = None,
    _cfg: Optional[dict] = None,
    _llm: object = None,
) -> dict:
    """Explore the Python environment and query system or environment info.

    Args:
        action: One of the following actions:
            - 'list_dir': List files/directories in the given `path`.
              If `path` is None, list the workspace directory.
            - 'env_vars': Return all environment variables as a dictionary.
            - 'get_env': Return the value of a specific environment variable
              by its `name`.
            - 'cwd': Return the current working directory.
            - 'python_version': Return the Python version (using sys).
            - 'sys_path': Return the module search paths (sys.path).
        path: Path for 'list_dir' action. Ignored for other actions.
        name: Environment variable name for 'get_env' action.
        _workspace: Injected workspace path (hidden from LLM).
        _cfg: Injected configuration (hidden from LLM).
        _llm: Injected LLM client (hidden from LLM, not used here).

    Returns:
        A dict with at least a "success" key. On success, the result is
        stored under a key corresponding to the action (e.g., "entries"
        for list_dir, "env_vars" for env_vars, "value" for get_env,
        "cwd" for cwd, "python_version" for python_version, "sys_path"
        for sys_path). On failure, returns an error dict with "success"
        set to False and an "error" message.
    """
    import os
    import sys

    try:
        # Normalize workspace
        ws = _workspace if _workspace is not None else Path.cwd()

        if action == "list_dir":
            target = Path(path) if path else ws
            if not target.is_dir():
                return {"error": f"Not a directory: {target}", "success": False}
            entries = os.listdir(str(target))
            return {"success": True, "entries": entries}

        elif action == "env_vars":
            return {"success": True, "env_vars": dict(os.environ)}

        elif action == "get_env":
            if not name:
                return {"error": "Missing 'name' parameter for get_env action", "success": False}
            value = os.environ.get(name, None)
            return {"success": True, "value": value}

        elif action == "cwd":
            return {"success": True, "cwd": os.getcwd()}

        elif action == "python_version":
            version = sys.version
            return {"success": True, "python_version": version}

        elif action == "sys_path":
            return {"success": True, "sys_path": sys.path}

        else:
            return {
                "error": f"Unknown action '{action}'. Valid actions: list_dir, env_vars, get_env, cwd, python_version, sys_path",
                "success": False,
            }

    except Exception as e:
        logger.exception("Error in explore_environment tool")
        return {"error": str(e), "success": False}