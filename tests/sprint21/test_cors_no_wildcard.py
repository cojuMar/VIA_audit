"""
Pre-Sprint-21 bug: CORSMiddleware configured with `allow_origins=["*"]` and
`allow_credentials=True` — credential-theft misconfig.

Post-Sprint-21 contract: CORS_ORIGINS env drives an explicit allow-list;
wildcard is never set; in prod, wildcard causes startup failure.
"""
from __future__ import annotations


def test_preflight_denies_unknown_origin(http):
    """A random evil origin must NOT receive Access-Control-Allow-Origin."""
    r = http.options(
        "/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Starlette returns 200 for preflight; the critical check is the header.
    allow_origin = r.headers.get("access-control-allow-origin", "")
    assert allow_origin != "*", "CORS wildcard is still enabled"
    assert "evil.example.com" not in allow_origin


def test_preflight_allows_known_dev_origin(http):
    r = http.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    allow_origin = r.headers.get("access-control-allow-origin", "")
    assert allow_origin == "http://localhost:5173"
