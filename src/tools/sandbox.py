# src/tools/sandbox.py
import subprocess
import tempfile
import asyncio
from pathlib import Path
from typing import Tuple
import os
import sys

def _posix_limits():
    try:
        import resource
        # CPU time: 2s, Address space: 256MB, File size: 10MB, NOFILE: 64
        resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except Exception:
        pass

class CodeSandbox:
    """Best-effort isolated Python subprocess. Not a perfect sandbox."""
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def execute_python(self, code: str) -> Tuple[str, str, int]:
        def blocking_run():
            with tempfile.TemporaryDirectory() as tmpdir:
                script_path = Path(tmpdir) / "script.py"
                script_path.write_text(code)

                env = {}
                cmd = [sys.executable, "-I", "-S", str(script_path)]  # isolated mode, no site imports
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        cwd=tmpdir,
                        env=env,
                        preexec_fn=_posix_limits if os.name == "posix" else None,
                    )
                    return result.stdout, result.stderr, result.returncode
                except subprocess.TimeoutExpired:
                    return "", "Execution timeout", -1
                except Exception as e:
                    return "", f"Execution error: {e}", -1

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, blocking_run)