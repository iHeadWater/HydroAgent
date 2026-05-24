"""
Tool: write_script_file
Skill: write_script_file
Description: Write a Python script to disk and then run it, capturing output.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def write_script_file(
    script_content: str,
    file_path: Optional[str] = None,
    *,
    _workspace: Optional[Path] = None,
    _cfg: Optional[dict] = None,
    _llm: Optional[object] = None,
) -> dict:
    """
    Write the provided Python script to a file and execute it.

    Args:
        script_content: The Python source code to be written and executed.
        file_path: Optional. Path (relative or absolute) where the script will be saved.
                   If not provided, a temporary file in the workspace (or current directory)
                   is created. If provided, the file is written at that location
                   (resolved against _workspace if relative).

    Returns:
        dict: Contains:
            - success (bool): Whether the operation succeeded.
            - output (str, optional): Combined stdout and stderr from script execution.
            - file_path (str, optional): Absolute path where the script was saved.
            - error (str, optional): Error message if something failed.
    """
    try:
        # Determine file path
        if file_path:
            path = Path(file_path)
            if not path.is_absolute():
                base = _workspace or Path.cwd()
                path = base / path
        else:
            # Create a temporary file in workspace or current directory
            import tempfile
            base = _workspace or Path.cwd()
            base.mkdir(parents=True, exist_ok=True)
            tmp = tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', dir=base, delete=False,
                encoding='utf-8'
            )
            path = Path(tmp.name)
            tmp.close()  # we'll write manually

        # Write the script
        path.write_text(script_content, encoding='utf-8')
        logger.info("Script written to %s", path)

        # Execute the script using subprocess
        import subprocess
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=60
        )

        # Combine stdout/stderr
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return {
            "success": result.returncode == 0,
            "output": output,
            "file_path": str(path),
            "returncode": result.returncode,
        }

    except FileNotFoundError as e:
        return {"success": False, "error": f"File not found: {e}"}
    except PermissionError as e:
        return {"success": False, "error": f"Permission denied: {e}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Script execution timed out (60s limit)"}
    except Exception as e:
        logger.exception("Unexpected error in write_script_file")
        return {"success": False, "error": f"Unexpected error: {e}"}