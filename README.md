# modkit-api-versioning

Small, framework-independent path-version policies with an optional FastAPI adapter.
Python 3.12+; MIT. No response-envelope, logging, diagnostics, or sibling Modkit dependency.

```sh
pip install modkit-api-versioning
# Optional routing/context integration:
pip install 'modkit-api-versioning[fastapi]'
```

## Explicit selection

```python
from modkit_api_versioning import PathVersionManager, VersionPolicy

manager = PathVersionManager(VersionPolicy(("stable", "preview"), prefix="/api"))
assert manager.prefix("stable") == "/api/stable"
assert manager.resolve("/api/preview/items") == "preview"
assert manager.resolve("/health") is None
```

The configured prefix reserves a namespace. Without `service`, its first segment
is always a version: `/api/users` raises `UnsupportedVersion` unless `users` is a
supported label. Put ordinary resource routes outside this namespace. `/api` alone
is versionless. No header/query selection, ordering, latest fallback, or semantic
interpretation of version labels occurs.

Optional `service="inventory"` uses `/api/stable/inventory` for versioned routes
and `/api/inventory` for versionless routes. Paths for other services return `None`.
A service name cannot also be a supported version. Versionless resolution returns
`None` unless both `default_version="stable"` and `versionless="default"` are set.
An explicit unknown version **never** uses that default. `default_version` alone
does not activate fallback. No service names or supported labels are built in.

Policies are immutable; supplied version sequences are copied to tuples. Labels
and service names must begin with ASCII alphanumeric and contain only those
characters, `.`, `_`, or `-`. Prefixes are absolute nonempty paths of those
segments without a trailing slash. Duplicate labels and invalid settings raise
`ValueError`. `UnsupportedVersion` subclasses `ValueError`.

`resolve` accepts decoded absolute paths, not URLs: query/fragment characters,
percent escapes, controls, backslashes, repeated separators and dot traversal are
rejected with `ValueError`. A trailing slash is accepted. It does not URL-decode,
normalize or redirect requests. ASGI servers supply decoded paths; query strings
remain separate. Core resolution never creates an HTTP response.

## Optional FastAPI integration

```python
from fastapi import APIRouter, FastAPI
from modkit_api_versioning import PathVersionManager, VersionPolicy
from modkit_api_versioning.fastapi import (
    VersionContext, VersionContextMiddleware, build_router,
)

manager = PathVersionManager(VersionPolicy(("stable", "preview")))
context = VersionContext()
items = APIRouter()

@items.get("/items")
async def list_items():
    return {"version": context.get(), "items": []}

app = FastAPI()
app.add_middleware(VersionContextMiddleware, manager=manager, context=context)
app.include_router(build_router(manager, version="stable", routers=[items]))
app.include_router(build_router(manager, version="preview", routers=[items]))
```

`build_router` creates a fresh router, leaving children unchanged. Native FastAPI
includes reference children rather than deep-copying them; finish route registration
before building/version-mounting routers. Collision validation is a build-time check,
not an ongoing registry. The adapter uses FastAPI's effective-route iterator for nested
include validation, so its FastAPI dependency is bounded to the tested minor series. Explicit
`version=None` creates a versionless mount. It checks duplicate child HTTP
path/method pairs (including equivalent parameter names). This check is conservative:
parameter converters are not distinguished, so same-shaped `int` and `uuid` routes
are also rejected. It does not inspect
routes already installed on your app. Parent conflicts, static/dynamic route
precedence, custom operation IDs, authentication, and response models remain
application-owned. Native FastAPI OpenAPI generation is preserved; do not reuse
explicit operation IDs across mounts. Tags are optional.

Middleware is opt-in and scoped to the configured prefix. It maps invalid or
unsupported paths **inside that prefix** to an empty 404, with no envelope or
version headers. Other paths pass through unchanged with no selected version.
It never redirects or rewrites successful responses. Context is instance-owned,
request-local, reset even after exceptions, and absent outside HTTP requests.
Use a distinct context per independently configured application. Install after
any path-rewriting middleware according to your application's ASGI ordering.

The first release intentionally excludes legacy redirects, version-discovery
endpoints, deprecation metadata, header/query negotiation, and schema transforms.
Migration-specific behavior stays with the application. This generic API is not
a drop-in replacement for any source application's helpers.

## Development and verification

```sh
python -m venv .venv
# Activate the venv using your platform's standard command.
python -m pip install -r requirements-dev.txt
python -m pytest
python -m ruff check src tests scripts examples
python -m ruff format --check src tests scripts examples
python -m mypy src
python -m build
python -m twine check dist/*
python scripts/check_wheel.py dist/modkit_api_versioning-0.1.0-py3-none-any.whl
python scripts/check_wheel.py dist/modkit_api_versioning-0.1.0-py3-none-any.whl --extras
```

The checker creates fresh environments outside the checkout, verifies import
provenance/metadata and dependency independence, runs copied behavioral tests,
and executes the unrelated inventory sample. CI builds again from the sdist and
checks both wheels with and without the FastAPI extra, on Linux, Windows and
macOS with Python 3.12–3.14. Configured CI is not a claim of completed hosted runs.

Version 0.1.0 is an initial API; breaking changes before 1.0 increment the minor
version. Derived path-routing/context mechanics retain the source MIT copyright
in LICENSE. Distribution artifacts exclude private development-policy files.

Portable Conventional Commit checks are vendored under `.development-standards`.
For a reviewed commit range, run
`python .development-standards/standards.py check --base BASE --head HEAD`.
These checks and CI require no external private policy checkout. Local instruction
files are intentionally not distributed.
