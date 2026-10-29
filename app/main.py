import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api import router
from app.config import Settings
from app.context import Context, create_context, initialize, initialize_spatial
from app.db import Base
from app.domain.errors import DomainError
from app.jobs import worker_loop
from app.rate_limit import RateLimiter, principal


def create_app(settings: Settings | None = None, context: Context | None = None) -> FastAPI:
    ctx = context or create_context(settings or Settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if ctx.settings.auto_create_schema:
            Base.metadata.create_all(ctx.db.engine)
        with ctx.db.transaction() as session:
            initialize(session, ctx.clock.now())
            initialize_spatial(ctx, session)
        if ctx.settings.model_artifact_path:
            from pathlib import Path

            from research.models import load_bundle

            ctx.models = load_bundle(Path(ctx.settings.model_artifact_path))
        stop = threading.Event()
        worker = None
        if ctx.settings.run_worker:
            worker = threading.Thread(target=worker_loop, args=(ctx, stop), daemon=True)
            worker.start()
        yield
        stop.set()
        if worker:
            worker.join(timeout=10)
        ctx.db.engine.dispose()

    app = FastAPI(title="Rise Sharing · Revision 9", version="0.1.0", lifespan=lifespan)
    app.state.context = ctx
    app.include_router(router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ctx.settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )
    cache = None
    if ctx.settings.redis_url:
        from redis import Redis

        cache = Redis.from_url(ctx.settings.redis_url, socket_timeout=1)
    limiter = RateLimiter(cache)

    @app.middleware("http")
    async def protect(request: Request, call_next: Any):
        origin = request.headers.get("origin")
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and origin
            and origin not in ctx.settings.allowed_origins
        ):
            return JSONResponse({"detail": {"code": "ORIGIN_NOT_ALLOWED"}}, status_code=403)
        length = request.headers.get("content-length", "")
        if length and (not length.isdigit() or int(length) > 65536):
            return JSONResponse({"detail": {"code": "PAYLOAD_TOO_LARGE"}}, status_code=413)
        if request.url.path.startswith("/api/"):
            ip = request.client.host if request.client else "local"
            identity = principal(request.cookies.get("rise_access"), ctx.jwt_secret)
            auth = request.url.path.startswith("/api/auth/")
            credential = request.url.path in {"/api/auth/login", "/api/auth/register"}
            category = (
                "credentials"
                if credential
                else "session"
                if request.url.path in {"/api/auth/refresh", "/api/auth/logout"}
                else "read"
                if request.method == "GET"
                else "write"
            )
            # Auth still has an IP budget; valid people sharing one NAT do not
            # consume each other's read/write allowance. Revoked sessions remain
            # rejected by authenticate() in the route dependency.
            bucket = (
                identity
                if identity and request.url.path not in {"/api/auth/login", "/api/auth/register"}
                else ip
            )
            limit = 30 if credential else 300 if category == "read" else 60
            try:
                retry_after = limiter.take(f"{category}:{bucket}", limit)
                if not auth:
                    retry_after = max(retry_after, limiter.take(f"ip-ceiling:{ip}", 2000))
            except Exception:
                return JSONResponse(
                    {"detail": {"code": "RATE_LIMIT_UNAVAILABLE"}},
                    status_code=503,
                    headers={"Retry-After": "1"},
                )
            if retry_after:
                return JSONResponse(
                    {"detail": {"code": "RATE_LIMITED"}},
                    status_code=429,
                    headers={
                        "Retry-After": str(retry_after),
                        "X-Server-Time": str(int(ctx.clock.now() * 1000)),
                    },
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Server-Time"] = str(int(ctx.clock.now() * 1000))
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        return JSONResponse(
            {"detail": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )

    @app.exception_handler(IntegrityError)
    async def constraint_error(_: Request, exc: IntegrityError):
        return JSONResponse(
            {"detail": {"code": "CONCURRENT_OR_DUPLICATE_OPERATION"}}, status_code=409
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(
            {
                "detail": [
                    {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()
                ]
            },
            status_code=422,
        )

    return app


app = create_app()
