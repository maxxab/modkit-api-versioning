import asyncio

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from modkit_api_versioning import PathVersionManager, VersionPolicy
from modkit_api_versioning.fastapi import VersionContext, VersionContextMiddleware, build_router


def manager():
    return PathVersionManager(VersionPolicy(("stable", "preview"), service="inventory"))


def test_route_isolation_openapi_and_context():
    m = manager()
    context = VersionContext()
    child = APIRouter()

    @child.get("/items")
    async def items():
        return {"version": context.get(), "items": []}

    app = FastAPI()
    app.add_middleware(VersionContextMiddleware, manager=m, context=context)
    for label in ("stable", "preview", None):
        app.include_router(build_router(m, version=label, routers=[child], tags=["inventory"]))

    @app.get("/health")
    def health():
        return {"ok": True}

    client = TestClient(app)
    for label in ("stable", "preview"):
        assert client.get(f"/api/{label}/inventory/items").json() == {"version": label, "items": []}
    assert client.get("/api/inventory/items").json()["version"] is None
    assert client.get("/api/old/inventory/items").status_code == 404
    assert client.get("/health").json() == {"ok": True}
    assert context.get() is None
    assert child.routes[0].path == "/items"
    schema = app.openapi()
    ids = [op["operationId"] for item in schema["paths"].values() for op in item.values()]
    assert len(ids) == len(set(ids))
    assert set(schema["paths"]) == {
        "/api/stable/inventory/items",
        "/api/preview/inventory/items",
        "/api/inventory/items",
        "/health",
    }
    assert schema["paths"]["/api/stable/inventory/items"]["get"]["tags"] == ["inventory"]


def test_duplicate_routes_rejected_but_distinct_methods_allowed():
    one, two = APIRouter(), APIRouter()
    one.add_api_route("/items/{item_id}", lambda: {}, methods=["GET"])
    two.add_api_route("/items/{other}", lambda: {}, methods=["GET"])
    with pytest.raises(ValueError, match="duplicate"):
        build_router(manager(), version="stable", routers=[one, two])
    three = APIRouter()
    three.add_api_route("/items/{item_id}", lambda: {}, methods=["POST"])
    assert len(build_router(manager(), version="stable", routers=[one, three]).routes) == 2


def test_context_concurrency_exception_reset_and_non_http():
    async def exercise():
        context = VersionContext()
        started = asyncio.Event()
        results = []
        count = 0

        async def inner(scope, receive, send):
            nonlocal count
            if scope["type"] != "http":
                results.append(("non-http", context.get()))
                return
            count += 1
            if count == 2:
                started.set()
            await started.wait()
            results.append((scope["path"], context.get()))
            if "preview" in scope["path"]:
                raise RuntimeError("endpoint failed")

        app = VersionContextMiddleware(inner, manager=manager(), context=context)

        async def invoke(path):
            try:
                await app({"type": "http", "path": path}, None, None)
            except RuntimeError:
                pass
            assert context.get() is None

        await asyncio.gather(
            invoke("/api/stable/inventory/items"), invoke("/api/preview/inventory/items")
        )
        await app({"type": "lifespan"}, None, None)
        assert set(results) == {
            ("/api/stable/inventory/items", "stable"),
            ("/api/preview/inventory/items", "preview"),
            ("non-http", None),
        }
        assert VersionContext().get() is None

    asyncio.run(exercise())


def test_service_less_namespace_and_explicit_404_response():
    m = PathVersionManager(VersionPolicy(("r7",)))
    app = FastAPI()
    app.add_middleware(VersionContextMiddleware, manager=m, context=VersionContext())
    child = APIRouter()
    child.add_api_route("/items", lambda: {"raw": True})
    app.include_router(build_router(m, version="r7", routers=[child]))
    client = TestClient(app)
    assert client.get("/api/r7/items").json() == {"raw": True}
    response = client.get("/api/unknown/items")
    assert response.status_code == 404
    assert response.content == b""
    assert "x-api-version" not in response.headers


def test_nested_router_collision_uses_effective_paths():
    child = APIRouter()
    child.add_api_route("/items/{item_id}", lambda: {"ok": True})
    nested = APIRouter()
    nested.include_router(child, prefix="/warehouse")
    with pytest.raises(ValueError, match="duplicate"):
        build_router(manager(), version="stable", routers=[nested, nested])
    equivalent = APIRouter()
    equivalent.add_api_route("/warehouse/items/{other}", lambda: {"ok": True})
    with pytest.raises(ValueError, match="duplicate"):
        build_router(manager(), version="stable", routers=[nested, equivalent])
    different = APIRouter()
    different.include_router(child, prefix="/other")
    app = FastAPI()
    app.include_router(build_router(manager(), version="stable", routers=[nested, different]))
    client = TestClient(app)
    assert client.get("/api/stable/inventory/warehouse/items/42").status_code == 200
    assert client.get("/api/stable/inventory/other/items/42").status_code == 200


def test_mounted_app_uses_route_relative_path():
    context = VersionContext()
    m = PathVersionManager(VersionPolicy(("stable",)))
    subapp = FastAPI()
    subapp.add_middleware(VersionContextMiddleware, manager=m, context=context)
    child = APIRouter()

    @child.get("/items")
    def items():
        return {"version": context.get()}

    subapp.include_router(build_router(m, version="stable", routers=[child]))

    @subapp.get("/api/{rest:path}")
    def catchall(rest: str):
        return {"unexpected": rest}

    app = FastAPI()
    app.mount("/tenant", subapp)
    client = TestClient(app)
    assert client.get("/tenant/api/stable/items").json() == {"version": "stable"}
    assert client.get("/tenant/api/old/items").status_code == 404
    assert context.get() is None
