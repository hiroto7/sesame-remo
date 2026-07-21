from __future__ import annotations

from pathlib import Path
import plistlib
import subprocess

import pytest

from sesame_remo import macos_service


VALID_CONFIG = """\
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_name = "light"
"""


def _prepare_macos(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    executable = tmp_path / ".venv" / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(macos_service.sys, "platform", "darwin")
    monkeypatch.setattr(macos_service.sys, "executable", str(executable))
    monkeypatch.setattr(macos_service.os, "getuid", lambda: 501)
    monkeypatch.setattr(
        macos_service.Path, "home", classmethod(lambda _cls: tmp_path / "home")
    )
    return executable


def _completed(
    arguments: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)


def test_build_service_plist_uses_absolute_paths(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(VALID_CONFIG)
    executable = tmp_path / ".venv" / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.touch()

    payload = macos_service.build_service_plist(
        config, label="com.test.sesame-remo", executable=executable
    )

    assert payload["Label"] == "com.test.sesame-remo"
    assert payload["ProgramArguments"] == [
        str(executable),
        "-m",
        "sesame_remo",
        "monitor",
        "--config",
        str(config),
    ]
    assert payload["WorkingDirectory"] == str(tmp_path)


def test_install_service_creates_and_loads_plist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = _prepare_macos(monkeypatch, tmp_path)
    config = tmp_path / "config.toml"
    config.write_text(VALID_CONFIG)
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return _completed(arguments, 1 if arguments[1] == "print" else 0)

    monkeypatch.setattr(macos_service.subprocess, "run", fake_run)

    plist_path = macos_service.install_service(config)

    assert plist_path == (
        tmp_path / "home" / "Library" / "LaunchAgents" / "com.example.sesame-remo.plist"
    )
    with plist_path.open("rb") as plist_file:
        payload = plistlib.load(plist_file)
    assert payload["ProgramArguments"][0] == str(executable)
    assert calls == [
        ["launchctl", "print", "gui/501/com.example.sesame-remo"],
        ["launchctl", "bootstrap", "gui/501", str(plist_path)],
        ["launchctl", "kickstart", "-k", "gui/501/com.example.sesame-remo"],
    ]


def test_install_service_replaces_loaded_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_macos(monkeypatch, tmp_path)
    config = tmp_path / "config.toml"
    config.write_text(VALID_CONFIG)
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return _completed(arguments)

    monkeypatch.setattr(macos_service.subprocess, "run", fake_run)

    macos_service.install_service(config, label="com.test.sesame-remo")

    assert [call[1] for call in calls] == [
        "print",
        "bootout",
        "bootstrap",
        "kickstart",
    ]


def test_uninstall_service_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_macos(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return _completed(arguments, 1)

    monkeypatch.setattr(macos_service.subprocess, "run", fake_run)

    assert not macos_service.uninstall_service()
    assert calls == [["launchctl", "print", "gui/501/com.example.sesame-remo"]]


def test_uninstall_service_stops_loaded_service_and_removes_plist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_macos(monkeypatch, tmp_path)
    plist_path = (
        tmp_path / "home" / "Library" / "LaunchAgents" / "com.example.sesame-remo.plist"
    )
    plist_path.parent.mkdir(parents=True)
    plist_path.touch()
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return _completed(arguments)

    monkeypatch.setattr(macos_service.subprocess, "run", fake_run)

    assert macos_service.uninstall_service()
    assert not plist_path.exists()
    assert [call[1] for call in calls] == ["print", "bootout"]


def test_service_status_returns_launchctl_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_macos(monkeypatch, tmp_path)

    def fake_run(arguments: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        return _completed(arguments, stdout="service details\n")

    monkeypatch.setattr(macos_service.subprocess, "run", fake_run)

    result = macos_service.service_status()

    assert result.returncode == 0
    assert result.stdout == "service details\n"


def test_install_service_reports_launchctl_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_macos(monkeypatch, tmp_path)
    config = tmp_path / "config.toml"
    config.write_text(VALID_CONFIG)

    def fake_run(arguments: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        if arguments[1] == "print":
            return _completed(arguments, 1)
        if arguments[1] == "bootstrap":
            return _completed(arguments, 5, stderr="bootstrap failed")
        return _completed(arguments)

    monkeypatch.setattr(macos_service.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="bootstrap failed"):
        macos_service.install_service(config)


def test_install_service_validates_config_before_launchctl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_macos(monkeypatch, tmp_path)
    config = tmp_path / "config.toml"
    config.write_text(
        VALID_CONFIG.replace('nature_token = "token"', 'nature_token = "replace-me"')
    )

    def unexpected_run(*_args, **_kwargs):
        pytest.fail("launchctl must not run for invalid configuration")

    monkeypatch.setattr(macos_service.subprocess, "run", unexpected_run)

    with pytest.raises(ValueError, match="nature_token"):
        macos_service.install_service(config)


def test_service_commands_reject_non_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(macos_service.sys, "platform", "linux")

    with pytest.raises(RuntimeError, match="only supported on macOS"):
        macos_service.service_status()


def test_service_label_rejects_path_characters(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(VALID_CONFIG)
    executable = tmp_path / "python"
    executable.touch()

    with pytest.raises(ValueError, match="service label"):
        macos_service.build_service_plist(
            config, label="../other-service", executable=executable
        )
