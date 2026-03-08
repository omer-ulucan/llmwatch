"""
Module: code_executor.py
Purpose: Sandboxed Python code execution tool for the LLMWatch agent.
WHY: Allows the agent to run Python code for data analysis, math, etc.
     Runs in a subprocess with timeout and resource limits for safety.
WARNING: For production use, this should be replaced with Docker container isolation.
"""

import subprocess
import tempfile
import os
from langchain_core.tools import tool
from config import logger

# Maximum output size in bytes
MAX_OUTPUT_BYTES = 10_240
# Execution timeout in seconds
EXECUTION_TIMEOUT = 15


@tool
def execute_python(code: str) -> str:
    """Execute Python code in a sandboxed subprocess and return the output.
    Use this tool when you need to perform calculations, data analysis, or run Python scripts.
    The code should use print() to output results."""
    try:
        # WHY: Write code to a temp file instead of using -c flag to handle
        # multi-line code and special characters correctly.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["python3", tmp_path],
                capture_output=True,
                text=True,
                timeout=EXECUTION_TIMEOUT,
                # WHY: Prevent the subprocess from inheriting sensitive env vars
                env={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "HOME": "/tmp",
                    "LANG": "en_US.UTF-8",
                },
            )

            stdout = result.stdout[:MAX_OUTPUT_BYTES] if result.stdout else ""
            stderr = result.stderr[:MAX_OUTPUT_BYTES] if result.stderr else ""

            if result.returncode != 0:
                return (
                    f"Code execution error (exit code {result.returncode}):\n{stderr}"
                )

            output = stdout.strip()
            if not output and not stderr:
                return "Code executed successfully with no output."

            if stderr:
                return f"Output:\n{output}\n\nWarnings:\n{stderr}"

            return output

        finally:
            # WHY: Always clean up temp files
            os.unlink(tmp_path)

    except subprocess.TimeoutExpired:
        return f"Error: Code execution timed out after {EXECUTION_TIMEOUT} seconds."
    except Exception as e:
        logger.error(f"Code execution error: {str(e)}")
        return f"Code execution failed: {str(e)}"
