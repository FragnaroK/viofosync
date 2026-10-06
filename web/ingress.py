"""Home Assistant ingress support: the proxy strips its path prefix and
passes it in ``X-Ingress-Path``; absolute redirects and the HTML
``<base>`` must carry it."""
from __future__ import annotations

import html
import re

from fastapi import Request

# Only a plain path is accepted: the header is client-controlled when the
# app is reached directly, and the value lands in HTML and Location.
_PREFIX_RE = re.compile(r"^/[A-Za-z0-9_\-./]*$")


def ingress_prefix(request: Request) -> str:
    raw = request.headers.get("x-ingress-path", "").rstrip("/")
    if raw and "//" not in raw and ".." not in raw and _PREFIX_RE.match(raw):
        return raw
    return ""


def inject_base(request: Request, page: str) -> str:
    base = html.escape(ingress_prefix(request) + "/", quote=True)
    return page.replace("<head>", f'<head>\n  <base href="{base}" />', 1)
