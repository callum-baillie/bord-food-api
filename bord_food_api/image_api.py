"""Authenticated local image responses; lazy misses use only reviewed public sources."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, Response

from .domain import normalize_gtin
from .native_api import ErrorEnvelope
from .product_images import ATTRIBUTION, ImageCache, ImageUnavailable
from .settings import load_policy


def install_image_routes(app, settings, authenticate, platform):
    from .product_images import image_policy

    router = APIRouter(dependencies=[Depends(authenticate)])
    cache = ImageCache(
        settings.data_dir,
        image_policy(load_policy(settings)),
        denied=platform.control.hidden_sources,
    )
    errors = {s: {"model": ErrorEnvelope} for s in (401, 403, 404, 422, 503)}
    errors[422]["description"] = "Unprocessable Content"

    def failure(error):
        status = (
            404 if error.missing else 403 if error.reason == "image_source_rights_blocked" else 503
        )
        return JSONResponse(
            {
                "error": {
                    "code": error.reason.upper(),
                    "message": "Product image is not currently available.",
                    "retryable": status == 503,
                    "details": {},
                }
            },
            status_code=status,
            headers={"Retry-After": str(error.retry_after), "Cache-Control": "no-store"},
        )

    @router.get("/v1/product-images/status", response_model=dict, responses=errors)
    def status():
        return cache.status()

    @router.get("/v1/product-images/{gtin}/metadata", response_model=dict, responses=errors)
    def metadata(gtin: str):
        if not normalize_gtin(gtin):
            return JSONResponse(
                {
                    "error": {
                        "code": "INVALID_GTIN",
                        "message": "Use a valid GTIN.",
                        "retryable": False,
                        "details": {},
                    }
                },
                status_code=422,
            )
        try:
            _, meta = cache.get(gtin, fetch=False)
            return meta
        except ImageUnavailable as error:
            return failure(error)

    @router.get("/v1/product-images/{gtin}", response_class=Response, responses=errors)
    def product_image(gtin: str, if_none_match: Annotated[str | None, Header()] = None):
        if not normalize_gtin(gtin):
            return JSONResponse(
                {
                    "error": {
                        "code": "INVALID_GTIN",
                        "message": "Use a valid GTIN.",
                        "retryable": False,
                        "details": {},
                    }
                },
                status_code=422,
            )
        try:
            data, meta = cache.get(gtin)
            etag = '"' + meta["sha256"] + '"'
            headers = {
                "ETag": etag,
                "Cache-Control": "private, max-age=86400",
                "X-Content-Type-Options": "nosniff",
                "X-Image-Attribution": ATTRIBUTION,
                "Link": f'<{meta["license"]}>; rel="license", <{meta["product_url"]}>; rel="describedby"',
            }
            return (
                Response(status_code=304, headers=headers)
                if if_none_match == etag
                else Response(data, media_type="image/jpeg", headers=headers)
            )
        except ImageUnavailable as error:
            return failure(error)

    app.include_router(router)
