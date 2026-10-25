"""
Module: code_executor.py
Purpose: Opt-in Python code execution tool for the LLMWatch agent.
WHY: Lets the agent run Python for calculations and data wrangling.

WARNING: This is NOT a sandbox. The code runs as a child process of the backend, as
the same OS user, with the same filesystem and network access. It is disabled unless
ENABLE_CODE_EXECUTION=true. The hardening below (isolated interpreter, empty
environment, throwaway working directory, resource limits, timeout) reduces the
damage of accidents, not of a determined attacker. Only enable it when the backend
itself runs in an isolated, disposable environment.
"""

import os
import signal
import subprocess
import sys
import tempfile

from langchain_core.tools import tool

from config import logger, settings

# Maximum output size in characters
MAX_OUTPUT_BYTES = 10_240
# Wall-clock timeout in seconds (CPU time is limited to the same value)
EXECUTION_TIMEOUT = 15
# Address-space limit for the child process
MAX_MEMORY_BYTES = 512 * 1024 * 1024
# Largest file the child may write
MAX_FILE_BYTES = 10 * 1024 * 1024
# Open file descriptors allowed in the child
MAX_OPEN_FILES = 64

DISABLED_MESSAGE = (
    "Python code execution is disabled on this server "
    "(set ENABLE_CODE_EXECUTION=true to enable it)."
)

# WHY: Limits are applied by the child itself before user code runs, instead of via
# subprocess preexec_fn, which is unsafe when the parent has threads (this tool runs
# in a worker thread). Soft == hard, so user code cannot raise them again.
_LAUNCHER = """
import resource, runpy, sys
def _limit(name, value):
    res = getattr(resource, name, None)
    if res is None:
        return
    try:
        resource.setrlimit(res, (value, value))
    except (ValueError, OSError):
        pass
_limit("RLIMIT_CPU", {cpu})
_limit("RLIMIT_AS", {mem})
_limit("RLIMIT_FSIZE", {fsize})
_limit("RLIMIT_NOFILE", {nofile})
_limit("RLIMIT_CORE", 0)
path = sys.argv[1]
sys.argv = [path]
runpy.run_path(path, run_name="__main__")
"""


def _run_isolated(code: str, timeout: int) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="llmwatch-exec-") as workdir:
        script = os.path.join(workdir, "main.py")
        with open(script, "w") as f:
            f.write(code)

        launcher = _LAUNCHER.format(
            cpu=timeout,
            mem=MAX_MEMORY_BYTES,
            fsize=MAX_FILE_BYTES,
            nofile=MAX_OPEN_FILES,
        )
        # WHY: -I = isolated mode (ignores PYTHON* env vars and the user site dir,
        # and doesn't put the script's directory on sys.path). The environment is
        # rebuilt from scratch so no backend secrets leak into the child.
        proc = subprocess.Popen(
            [sys.executable, "-I", "-c", launcher, script],
            cwd=workdir,
            env={
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": workdir,
                "LANG": "C.UTF-8",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # WHY: New session, so on timeout we can kill anything the code spawned.
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise
        return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)


@tool
def execute_python(code: str) -> str:
    """Execute Python code and return what it prints.
    Use this tool when you need to perform calculations, data analysis, or run Python scripts.
    The code should use print() to output results."""
    # WHY: Checked at call time as well as when tools are built (defense in depth).
    if not settings.enable_code_execution:
        return DISABLED_MESSAGE

    try:
        result = _run_isolated(code, EXECUTION_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"Error: Code execution timed out after {EXECUTION_TIMEOUT} seconds."
    except Exception as e:
        logger.error(f"Code execution error: {str(e)}")
        return f"Code execution failed: {str(e)}"

    stdout = result.stdout[:MAX_OUTPUT_BYTES] if result.stdout else ""
    stderr = result.stderr[:MAX_OUTPUT_BYTES] if result.stderr else ""

    if result.returncode != 0:
        # SIGXCPU / SIGKILL from the CPU limit show up as negative return codes.
        if result.returncode in (-signal.SIGXCPU, -signal.SIGKILL):
            return f"Error: Code execution timed out after {EXECUTION_TIMEOUT} seconds."
        return f"Code execution error (exit code {result.returncode}):\n{stderr}"

    output = stdout.strip()
    if not output and not stderr:
        return "Code executed successfully with no output."

    if stderr:
        return f"Output:\n{output}\n\nWarnings:\n{stderr}"

    return output
