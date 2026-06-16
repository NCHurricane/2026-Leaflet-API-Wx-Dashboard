"""Static asset helpers for page and cache serving."""

import os
import re

from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app_core.paths import BASE_DIR


class CacheStaticFiles(StaticFiles):
    """StaticFiles with Cache-Control tuned for the overlay cache.

    Frame-keyed PNGs (YYYY_MM_DD_HH_MM_SS.png) are write-once, prune-only:
    serve them as long-lived immutable so scrubber/tab revisits hit the
    browser cache. Everything else - index.json, *_meta/_bounds sidecars, and
    overlay_{hash}.png which is overwritten in place at the same URL - gets
    no-cache so StaticFiles' native ETag/Last-Modified turns unchanged files
    into 304s instead of full re-downloads.
    """

    _FRAME_KEY_PNG = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}\.png$")

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        name = os.path.basename(str(full_path))
        if self._FRAME_KEY_PNG.match(name):
            response.headers["Cache-Control"] = "public, max-age=86400, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


def serve_page(filename: str):
    page_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(page_path):
        raise HTTPException(status_code=404, detail=f"Page not found: {filename}")
    return FileResponse(page_path)


def serve_product_shell_page(product_type: str):
    """Serve the shared weather shell with product-page metadata."""
    if not re.fullmatch(r"[a-z0-9_-]+", product_type):
        raise HTTPException(status_code=404, detail=f"Unknown product page: {product_type}")

    page_path = os.path.join(BASE_DIR, "weather.html")
    if not os.path.exists(page_path):
        raise HTTPException(status_code=404, detail="Page not found: weather.html")

    with open(page_path, encoding="utf-8") as page_file:
        content = page_file.read()

    meta = f'        <meta name="nch-product-page" content="{product_type}">\n'
    if meta not in content:
        content = content.replace("        <title>", f"{meta}        <title>", 1)

    return HTMLResponse(content, headers={"Cache-Control": "no-cache"})
