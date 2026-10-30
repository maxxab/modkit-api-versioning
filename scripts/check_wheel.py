"""Verify a non-editable wheel in fresh base/extra environments outside the checkout."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path
from zipfile import ZipFile


def validate_install(module_file: Path, environment: Path, actual: str, expected: str) -> None:
    if not module_file.resolve().is_relative_to(environment.resolve()):
        raise RuntimeError("package imported from outside isolated environment")
    if actual != expected:
        raise RuntimeError(f"installed version {actual} differs from wheel {expected}")


def check(wheel: Path, *, extras: bool = False) -> None:
    wheel = wheel.resolve(strict=True)
    with ZipFile(wheel) as archive:
        metadata = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        text = archive.read(metadata).decode()
        expected = next(line[9:] for line in text.splitlines() if line.startswith("Version: "))
        if "Name: modkit-api-versioning\n" not in text:
            raise RuntimeError("unexpected wheel distribution")
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="modkit-versioning-wheel-") as temporary:
        work = Path(temporary)
        environment = work / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env["PIP_NO_CACHE_DIR"] = "1"

        def run(*args: str) -> str:
            result = subprocess.run(
                [str(python), *args],
                cwd=work,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if result.returncode:
                raise RuntimeError(result.stdout)
            return result.stdout

        target = f"{wheel}[fastapi]" if extras else str(wheel)
        deps = [target, "pytest==9.2.0"] + (["httpx2==2.16.0"] if extras else [])
        run("-m", "pip", "install", "--index-url", "https://pypi.org/simple", *deps)
        probe = run(
            "-c",
            "import json, importlib.metadata as m, importlib.util as u; "
            "import modkit_api_versioning as p; "
            "print(json.dumps([p.__file__, m.version('modkit-api-versioning'), "
            "[d.metadata['Name'] for d in m.distributions()], bool(u.find_spec('fastapi'))]))",
        )
        path, actual, distributions, has_fastapi = json.loads(probe)
        validate_install(Path(path), environment, actual, expected)
        if any(
            d.lower().replace("_", "-").startswith("modkit-")
            and d.lower().replace("_", "-") != "modkit-api-versioning"
            for d in distributions
        ):
            raise RuntimeError("unexpected sibling modkit distribution")
        if has_fastapi != extras:
            raise RuntimeError("optional integration isolation failed")
        (work / "tests").mkdir()
        (work / "scripts").mkdir()
        names = ["test_core.py", "test_isolation.py"] + (["test_fastapi.py"] if extras else [])
        for name in names:
            shutil.copy2(root / "tests" / name, work / "tests" / name)
        shutil.copy2(__file__, work / "scripts" / "check_wheel.py")
        shutil.copy2(root / "examples" / "inventory.py", work / "inventory.py")
        print(run("-m", "pip", "check").strip())
        print(run("-m", "pytest", "tests", "-q").strip())
        print(run("inventory.py").strip())
        print(f"Verified {wheel.name}: {'fastapi' if extras else 'base'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--extras", action="store_true")
    args = parser.parse_args()
    check(args.wheel, extras=args.extras)
