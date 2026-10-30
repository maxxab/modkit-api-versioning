"""Base-wheel compatibility tests, also run without optional dependencies."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

import modkit_api_versioning


def test_core_import_does_not_load_optional_or_sibling_packages():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import modkit_api_versioning; assert not any(x.startswith(('fastapi', 'starlette', 'modkit_api_responses', 'modkit_diagnostics', 'operations_erp')) for x in sys.modules)",
        ],
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(Path(modkit_api_versioning.__file__).parent.parent),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_wheel", Path(__file__).parents[1] / "scripts" / "check_wheel.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checker_rejects_checkout_import_and_metadata_mismatch(tmp_path):
    checker = load_checker()
    env = tmp_path / "env"
    with pytest.raises(RuntimeError, match="outside"):
        checker.validate_install(tmp_path / "src" / "package.py", env, "0.1.0", "0.1.0")
    with pytest.raises(RuntimeError, match="version"):
        checker.validate_install(env / "package.py", env, "9.0", "0.1.0")
    checker.validate_install(env / "package.py", env, "0.1.0", "0.1.0")
