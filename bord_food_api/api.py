import hmac
import sqlite3
import time
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import __version__, catalog
from .settings import Settings

DataType = Literal["Branded", "Foundation", "Survey (FNDDS)", "SR Legacy"]


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=200)
    pageNumber: int = Field(default=1, ge=1, le=10000, strict=True)
    pageSize: int = Field(default=20, ge=1, le=200, strict=True)
    dataType: list[DataType] | None = Field(default=None, max_length=4)

    @field_validator("query")
    @classmethod
    def bound_terms(cls, value):
        if len(value.split()) > 20:
            raise ValueError("Use at most 20 search terms")
        return value


class BodyLimit:
    """Bound the body even when the client omits Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 16384:
                return await JSONResponse({"detail": "Request body too large"}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body", False):
                break

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        delivered = False
        await self.app(scope, replay, send)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    app = FastAPI(
        title="Bòrd Food API",
        version=__version__,
        description="Local USDA FoodData Central search and details. Data: USDA, CC0 1.0.",
    )
    app.add_middleware(BodyLimit)
    key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)

    def authenticate(key: Annotated[str | None, Depends(key_header)]):
        if settings.api_key and not hmac.compare_digest(
            (key or "").encode(), settings.api_key.encode()
        ):
            raise HTTPException(401, "Invalid or missing X-Api-Key")

    def database():
        if not settings.database.exists():
            raise HTTPException(503, "No catalog available; import USDA datasets first")
        try:
            with catalog.connect(settings.database) as connection:
                deadline = time.monotonic() + 5
                connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
                yield connection
        except (sqlite3.Error, ValueError) as error:
            raise HTTPException(
                503, "Catalog unavailable or query timed out; check server logs/catalog"
            ) from error

    DB = Annotated[sqlite3.Connection, Depends(database)]
    protected = [Depends(authenticate)]

    @app.get("/health")
    def health(connection: DB):
        count = connection.execute("SELECT value FROM metadata WHERE key = 'totalFoods'").fetchone()
        if not count or int(count[0]) == 0:
            raise HTTPException(503, "Catalog is empty")
        return {"status": "ok", "totalFoods": int(count[0])}

    @app.get("/status", dependencies=protected)
    def status(connection: DB):
        return catalog.metadata(connection)

    @app.post("/fdc/v1/foods/search", dependencies=protected)
    def search_post(body: SearchInput, connection: DB):
        return catalog.search(connection, body.query, body.pageNumber, body.pageSize, body.dataType)

    @app.get("/fdc/v1/foods/search", dependencies=protected)
    def search_get(
        connection: DB,
        query: Annotated[str, Query(min_length=1, max_length=200)],
        pageNumber: Annotated[int, Query(ge=1, le=10000)] = 1,
        pageSize: Annotated[int, Query(ge=1, le=200)] = 20,
        dataType: Annotated[list[DataType] | None, Query(max_length=4)] = None,
    ):
        # GET uses repeated dataType parameters, e.g. ?dataType=Foundation&dataType=Branded.
        from pydantic import ValidationError

        try:
            body = SearchInput(
                query=query, pageNumber=pageNumber, pageSize=pageSize, dataType=dataType
            )
        except ValidationError as error:
            raise HTTPException(422, "Invalid search input") from error
        return search_post(body, connection)

    @app.get("/fdc/v1/food/{fdc_id}", dependencies=protected)
    def detail(fdc_id: int, connection: DB):
        if not 0 < fdc_id < 2**63:
            raise HTTPException(422, "fdcId must be a positive 64-bit integer")
        row = connection.execute("SELECT payload FROM foods WHERE fdc_id = ?", (fdc_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Food not found")
        return catalog.unpack(row["payload"])

    return app
