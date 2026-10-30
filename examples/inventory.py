"""Unrelated inventory application using only the public, framework-free API."""

from modkit_api_versioning import PathVersionManager, UnsupportedVersion, VersionPolicy

manager = PathVersionManager(VersionPolicy(("stable", "preview"), prefix="/inventory"))
assert manager.resolve("/inventory/stable/items/42") == "stable"
assert manager.resolve("/health") is None
try:
    manager.resolve("/inventory/retired/items/42")
except UnsupportedVersion:
    pass
else:
    raise AssertionError("unsupported version silently accepted")
print("Inventory sample passed")
