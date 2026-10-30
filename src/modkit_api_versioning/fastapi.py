"""Opt-in FastAPI route composition and request-local version context."""

from __future__ import annotations

import re
from collections.abc import Iterable
from contextvars import ContextVar

from fastapi import APIRouter
from fastapi.routing import _iter_routes_with_context
from starlette._utils import get_route_path
from starlette.responses import Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .core import PathVersionManager


class VersionContext:
    """Instance-owned request context, with no default process-wide singleton."""

    def __init__(self) -> None:
        self._value: ContextVar[str | None] = ContextVar("api_version", default=None)

    def get(self) -> str | None:
        """Return this request's selected version, or None outside a request."""
        return self._value.get()


class VersionContextMiddleware:
    """Bind HTTP request context; invalid/unsupported owned paths receive empty 404.

    It does not redirect, select from headers, or change successful responses.
    """

    def __init__(
        self, app: ASGIApp, *, manager: PathVersionManager, context: VersionContext
    ) -> None:
        self.app = app
        self.manager = manager
        self.context = context

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = get_route_path(scope)
        prefix = self.manager.policy.prefix
        try:
            # Do not validate or claim paths belonging to other applications.
            version = (
                self.manager.resolve(path)
                if path == prefix or path.startswith(prefix + "/")
                else None
            )
        except ValueError:
            await Response(status_code=404)(scope, receive, send)
            return
        token = self.context._value.set(version)
        try:
            await self.app(scope, receive, send)
        finally:
            self.context._value.reset(token)


def build_router(
    manager: PathVersionManager,
    *,
    version: str | None,
    routers: Iterable[APIRouter] = (),
    tags: list[str] | None = None,
) -> APIRouter:
    """Include child routes under a versioned or explicitly versionless mount.

    Duplicate child path/method pairs fail early. Conflicts with routes already
    installed on a parent application remain the application's responsibility.
    """
    prefix = manager.versionless_prefix() if version is None else manager.prefix(version)
    children = tuple(routers)
    seen: set[tuple[str, str]] = set()
    for child in children:
        for route, context in _iter_routes_with_context(child.routes):
            if isinstance(route, Route):
                # FastAPI 0.162 uses lazy includes. Its own OpenAPI iterator
                # preserves effective nested prefixes; the extra is minor-bounded.
                effective_path = context.path if context is not None else route.path
                path = re.sub(r"\{[^{}]+\}", "{}", effective_path)
                for method in route.methods or ():
                    key = (path, method)
                    if key in seen:
                        raise ValueError(f"duplicate route: {method} {route.path}")
                    seen.add(key)
    router = APIRouter(prefix=prefix, tags=list(tags or []))
    for child in children:
        router.include_router(child)
    return router
