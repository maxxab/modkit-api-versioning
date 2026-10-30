"""Framework-independent, explicit path-version selection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class UnsupportedVersion(ValueError):
    """A selected version is not supported by this policy."""


def _segment(value: str) -> bool:
    return isinstance(value, str) and _SEGMENT.fullmatch(value) is not None


@dataclass(frozen=True)
class VersionPolicy:
    """An immutable namespace policy; defaults never select a version implicitly."""

    supported_versions: tuple[str, ...]
    prefix: str = "/api"
    service: str | None = None
    default_version: str | None = None
    versionless: Literal["none", "default"] = "none"

    def __post_init__(self) -> None:
        if isinstance(self.supported_versions, str):
            raise ValueError("supported_versions must be a sequence of labels")
        versions = tuple(self.supported_versions)
        if not versions or not all(_segment(v) for v in versions):
            raise ValueError("versions must be nonempty safe path segments")
        if len(set(versions)) != len(versions):
            raise ValueError("duplicate supported versions")
        object.__setattr__(self, "supported_versions", versions)
        if not self.prefix.startswith("/") or not all(
            _segment(part) for part in self.prefix[1:].split("/")
        ):
            raise ValueError("prefix must be an absolute path of safe segments")
        if self.service is not None and (not _segment(self.service) or self.service in versions):
            raise ValueError("service must be a safe segment distinct from version labels")
        if self.default_version is not None and self.default_version not in versions:
            raise ValueError("default_version must be supported")
        if self.versionless not in ("none", "default"):
            raise ValueError("versionless must be 'none' or 'default'")
        if self.versionless == "default" and self.default_version is None:
            raise ValueError("versionless='default' requires default_version")


@dataclass(frozen=True)
class PathVersionManager:
    """Resolve decoded paths without global state or HTTP response dependencies."""

    policy: VersionPolicy

    def prefix(self, version: str) -> str:
        """Return the mount prefix for an explicitly supported version."""
        if version not in self.policy.supported_versions:
            raise UnsupportedVersion(version)
        suffix = f"/{self.policy.service}" if self.policy.service else ""
        return f"{self.policy.prefix}/{version}{suffix}"

    def versionless_prefix(self) -> str:
        """Return the explicitly unversioned mount prefix."""
        suffix = f"/{self.policy.service}" if self.policy.service else ""
        return f"{self.policy.prefix}{suffix}"

    def resolve(self, path: str) -> str | None:
        """Resolve within this namespace; unrelated paths and no selection return None.

        No-service namespaces reserve their first segment for a version label.
        Inputs are decoded paths, not URLs. Unknown selections never use a default.
        """
        if (
            not path.startswith("/")
            or any(ord(c) < 32 or ord(c) == 127 for c in path)
            or any(c in path for c in "?#%\\")
            or "//" in path
            or any(p in (".", "..") for p in path.split("/"))
        ):
            raise ValueError("expected an unambiguous decoded absolute path")
        base = self.policy.prefix
        if path != base and not path.startswith(base + "/"):
            return None
        parts = path[len(base) :].strip("/").split("/")
        service = self.policy.service
        if (service is None and parts == [""]) or (service and parts[0] == service):
            return self.policy.default_version if self.policy.versionless == "default" else None
        if service and (len(parts) < 2 or parts[1] != service):
            return None
        version = parts[0]
        if version not in self.policy.supported_versions:
            raise UnsupportedVersion(version)
        return version
