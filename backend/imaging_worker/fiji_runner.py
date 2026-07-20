"""Real headless Fiji execution for the Mundi imaging MVP."""

from __future__ import annotations

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


class FijiRunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class FijiRunResult:
    executable: str
    input_path: str
    output_path: str
    returncode: int
    elapsed_ms: int
    stdout: str
    stderr: str


class FijiRunner:
    def __init__(self, executable: str | Path, timeout_seconds: int = 120) -> None:
        self.executable = Path(executable)
        self.timeout_seconds = timeout_seconds
        self.macro_path = Path(__file__).resolve().parent / "scripts" / "generate_preview.ijm"

    def health_check(self) -> dict[str, object]:
        if not self.executable.exists():
            raise FijiRunnerError(f"Executable not found: {self.executable}")
        if not self.macro_path.exists():
            raise FijiRunnerError(f"Preview macro not found: {self.macro_path}")
        with tempfile.TemporaryDirectory(prefix="mundi-fiji-health-") as tmpdir:
            work_dir = Path(tmpdir)
            input_path = work_dir / "input.tif"
            output_path = work_dir / "preview.png"
            input_path.write_bytes(tiny_tiff())
            result = self.generate_preview(input_path=input_path, output_path=output_path)
            return {
                "executable_found": True,
                "fiji_launched": True,
                "macro_executed": result.returncode == 0,
                "preview_generated": output_path.exists() and output_path.stat().st_size > 0,
                "fiji_exited": True,
                "elapsed_ms": result.elapsed_ms,
            }

    def generate_preview(self, *, input_path: str | Path, output_path: str | Path) -> FijiRunResult:
        input_file = Path(input_path).resolve()
        output_file = Path(output_path).resolve()
        if not self.executable.exists():
            raise FijiRunnerError(f"Executable not found: {self.executable}")
        if not input_file.exists():
            raise FijiRunnerError(f"Input TIFF not found: {input_file}")
        if not self.macro_path.exists():
            raise FijiRunnerError(f"Preview macro not found: {self.macro_path}")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        if output_file.exists():
            output_file.unlink()
        args = [
            str(self.executable),
            "--headless",
            "--console",
            "-macro",
            str(self.macro_path),
            f"input={input_file}|output={output_file}",
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FijiRunnerError(f"Fiji timed out after {self.timeout_seconds} seconds.") from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "Fiji exited with an error.").strip().splitlines()
            raise FijiRunnerError(message[0][:240] if message else "Fiji exited with an error.")
        if not output_file.exists() or output_file.stat().st_size <= 0:
            raise FijiRunnerError("Fiji completed but preview.png was not generated.")
        return FijiRunResult(
            executable=str(self.executable),
            input_path=str(input_file),
            output_path=str(output_file),
            returncode=completed.returncode,
            elapsed_ms=elapsed_ms,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def tiny_tiff() -> bytes:
    """Return a minimal 1x1 8-bit little-endian TIFF."""
    return bytes.fromhex(
        "49492a00080000000a00000104000100000001000000010104000100000001000000"
        "02010300010000000800000003010300010000000100000006010300010000000100"
        "00001101040001000000860000001501030001000000010000001601040001000000"
        "010000001701040001000000010000001c01030001000000010000000000000000"
    ) + b"\x80"

