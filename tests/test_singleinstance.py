"""Тесты для chatcore.singleinstance: flock-захват, отказ, повторный захват."""
import subprocess
import sys

import pytest

from chatcore import singleinstance


def test_acquire_success(tmp_path):
    lock_file = tmp_path / "bot.db.lock"
    f = singleinstance.acquire(lock_file)
    assert f is not None
    f.close()


def test_acquire_second_instance_fails(tmp_path):
    """Второй процесс с тем же lock-файлом завершается с кодом 1."""
    lock_file = tmp_path / "bot.db.lock"
    # Держим лок в текущем процессе
    f = singleinstance.acquire(lock_file)
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"from chatcore import singleinstance; from pathlib import Path; "
                f"singleinstance.acquire(Path(r'{lock_file}'))",
            ],
            capture_output=True,
        )
        assert result.returncode == 1
    finally:
        f.close()


def test_acquire_after_release(tmp_path):
    """После закрытия файла лок можно взять снова."""
    lock_file = tmp_path / "bot.db.lock"
    f = singleinstance.acquire(lock_file)
    f.close()
    f2 = singleinstance.acquire(lock_file)
    assert f2 is not None
    f2.close()


def test_acquire_permission_error(tmp_path, monkeypatch):
    """PermissionError при открытии → SystemExit(1) с CRITICAL-логом."""
    lock_file = tmp_path / "bot.db.lock"

    def _raise_permission(*_a, **_kw):
        raise PermissionError("no write access")

    monkeypatch.setattr("builtins.open", _raise_permission)
    with pytest.raises(SystemExit) as exc_info:
        singleinstance.acquire(lock_file)
    assert exc_info.value.code == 1
