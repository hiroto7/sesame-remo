from __future__ import annotations

import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tempfile

from .automation import load_config


DEFAULT_SERVICE_LABEL = "com.example.sesame-remo"
STANDARD_OUT_PATH = "/tmp/sesame-remo.out.log"
STANDARD_ERROR_PATH = "/tmp/sesame-remo.err.log"
_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("macOS service management is only supported on macOS")


def _validate_label(label: str) -> None:
    if not _LABEL_PATTERN.fullmatch(label):
        raise ValueError(
            "service label must contain only letters, numbers, dots, and hyphens"
        )


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _target(label: str) -> str:
    return f"{_domain()}/{label}"


def _plist_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _run_launchctl(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_launchctl_checked(*arguments: str) -> subprocess.CompletedProcess[str]:
    result = _run_launchctl(*arguments)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"launchctl {' '.join(arguments)} failed: {detail}")
    return result


def _service_is_loaded(label: str) -> bool:
    return _run_launchctl("print", _target(label)).returncode == 0


def build_service_plist(
    config_path: Path,
    *,
    label: str = DEFAULT_SERVICE_LABEL,
    executable: Path | None = None,
) -> dict[str, object]:
    _validate_label(label)
    config = config_path.expanduser().resolve(strict=True)
    if not config.is_file():
        raise ValueError(f"config path is not a file: {config}")

    python = executable or Path(sys.executable)
    python = python.expanduser().absolute()
    if not python.is_file():
        raise ValueError(f"Python executable not found: {python}")

    return {
        "Label": label,
        "ProgramArguments": [
            str(python),
            "-m",
            "sesame_remo",
            "monitor",
            "--config",
            str(config),
        ],
        "WorkingDirectory": str(config.parent),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "StandardOutPath": STANDARD_OUT_PATH,
        "StandardErrorPath": STANDARD_ERROR_PATH,
    }


def install_service(
    config_path: str | Path, *, label: str = DEFAULT_SERVICE_LABEL
) -> Path:
    _require_macos()
    config = Path(config_path).expanduser().resolve(strict=True)
    load_config(config)
    payload = build_service_plist(config, label=label)

    plist_path = _plist_path(label)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=plist_path.parent,
            prefix=f".{label}.",
            suffix=".plist.tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            plistlib.dump(payload, temporary_file)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.chmod(0o644)

        if _service_is_loaded(label):
            _run_launchctl_checked("bootout", _target(label))

        os.replace(temporary_path, plist_path)
        temporary_path = None
        _run_launchctl_checked("bootstrap", _domain(), str(plist_path))
        _run_launchctl_checked("kickstart", "-k", _target(label))
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return plist_path


def uninstall_service(*, label: str = DEFAULT_SERVICE_LABEL) -> bool:
    _require_macos()
    _validate_label(label)
    plist_path = _plist_path(label)
    was_installed = plist_path.exists()

    if _service_is_loaded(label):
        was_installed = True
        _run_launchctl_checked("bootout", _target(label))

    plist_path.unlink(missing_ok=True)
    return was_installed


def service_status(
    *, label: str = DEFAULT_SERVICE_LABEL
) -> subprocess.CompletedProcess[str]:
    _require_macos()
    _validate_label(label)
    return _run_launchctl("print", _target(label))


def service_target(label: str = DEFAULT_SERVICE_LABEL) -> str:
    _validate_label(label)
    return _target(label)
