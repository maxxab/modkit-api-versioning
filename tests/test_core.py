import concurrent.futures
from dataclasses import FrozenInstanceError

import pytest

from modkit_api_versioning import PathVersionManager, UnsupportedVersion, VersionPolicy


def manager(**kw):
    return PathVersionManager(VersionPolicy(("stable", "preview-2"), **kw))


def test_configured_labels_and_prefixes():
    m = manager(prefix="/public/api")
    assert m.prefix("preview-2") == "/public/api/preview-2"
    assert m.versionless_prefix() == "/public/api"
    assert m.resolve("/public/api/stable/items/") == "stable"
    assert m.resolve("/public/api") is None
    assert m.resolve("/public/apix/stable") is None
    assert m.resolve("/health") is None
    with pytest.raises(UnsupportedVersion):
        m.resolve("/public/api/items")
    with pytest.raises(UnsupportedVersion):
        m.prefix("missing")


def test_service_mount_and_explicit_versionless_default():
    m = manager(service="inventory", default_version="stable", versionless="default")
    assert m.prefix("stable") == "/api/stable/inventory"
    assert m.versionless_prefix() == "/api/inventory"
    assert m.resolve("/api/inventory/items") == "stable"
    assert m.resolve("/api/preview-2/inventory/items") == "preview-2"
    assert m.resolve("/api/other-service/items") is None
    assert m.resolve("/api/stable/other-service/items") is None
    assert m.resolve("/api") is None
    with pytest.raises(UnsupportedVersion):
        m.resolve("/api/retired/inventory/items")
    assert manager(service="inventory", default_version="stable").resolve("/api/inventory") is None


@pytest.mark.parametrize(
    "versions", [(), ("a", "a"), ("",), ("../",), ("a/b",), ("a b",), ("é",), ("v%31",), ("..",)]
)
def test_invalid_versions(versions):
    with pytest.raises(ValueError):
        VersionPolicy(versions)


@pytest.mark.parametrize(
    "kw",
    [
        dict(prefix="/"),
        dict(prefix="api"),
        dict(prefix="/api/"),
        dict(prefix="/api//x"),
        dict(prefix="/api/.."),
        dict(service="stable"),
        dict(service=""),
        dict(default_version="absent"),
        dict(versionless="default"),
        dict(versionless="latest"),
    ],
)
def test_invalid_configuration(kw):
    with pytest.raises(ValueError):
        manager(**kw)


@pytest.mark.parametrize(
    "path",
    [
        "api/stable",
        "/api//stable",
        "/api/../stable",
        "/api/stable?x=1",
        "/api/stable#x",
        "/api/%73table",
        "/api/sta\\ble",
        "/api/\x00",
        "/api/./stable",
    ],
)
def test_invalid_paths(path):
    with pytest.raises(ValueError):
        manager().resolve(path)


def test_immutable_snapshot_and_concurrent_reads():
    versions = ["stable", "preview-2"]
    policy = VersionPolicy(versions)
    versions.append("later")
    assert policy.supported_versions == ("stable", "preview-2")
    with pytest.raises(FrozenInstanceError):
        policy.prefix = "/different"
    m = PathVersionManager(policy)
    paths = ["/api/stable/a", "/api/preview-2/b", "/health"] * 30
    with concurrent.futures.ThreadPoolExecutor() as pool:
        assert list(pool.map(m.resolve, paths)) == ["stable", "preview-2", None] * 30
