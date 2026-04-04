"""
MAESTRO Sprint 7 — Security Middleware

Applies to all POST/PUT requests:
1. Rate limiting check (before any processing)
2. Prompt injection check on request body 'query' or 'question' fields

Returns 429 with Retry-After for rate limit exceeded.
Returns 400 with error detail for injection blocked.
Passes InjectionCheckResult as request.state.injection_result for downstream logging.
"""

import json
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .prompt_injection_filter import InjectionBlockedError, PromptInjectionFilter
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class MAESTROSecurityMiddleware(BaseHTTPMiddleware):
    """Integrates sliding-window rate limiting and multi-layer prompt injection
    detection for all mutating (POST/PUT) requests.

    Order of operations per request:
      1. Extract X-Tenant-ID header.  Missing header → 400.
      2. Rate limit check → 429 if exceeded (fail-open on Redis unavailability).
      3. For POST/PUT: parse body, locate 'query' or 'question' field, run
         injection filter → 400 if blocked.
      4. Forward to the next handler.
      5. Attach security response headers before returning.
    """

    def __init__(
        self,
        app,
        rate_limiter: RateLimiter,
        injection_filter: PromptInjectionFilter,
    ):
        super().__init__(app)
        self._rate_limiter = rate_limiter
        self._injection_filter = injection_filter

    async def dispatch(self, request: Request, call_next) -> Response:
        # ----------------------------------------------------------------
        # 1. Extract tenant_id
        # ----------------------------------------------------------------
        tenant_id: Optional[str] = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={"detail": "Missing required header: X-Tenant-ID"},
            )

        # Extract optional user_id from headers (set by auth gateway, best-effort)
        user_id: Optional[str] = request.headers.get("X-User-ID")

        # ----------------------------------------------------------------
        # 2. Rate limiting — fail open on infrastructure errors
        # ----------------------------------------------------------------
        rate_result = None
        try:
            rate_result = await self._rate_limiter.check_and_increment(
                tenant_id=tenant_id,
                endpoint=request.url.path,
            )
        except Exception as exc:
            # Redis unavailable or other infrastructure failure — allow request
            logger.error(
                "maestro_middleware: rate limiter unavailable, failing open: %s", exc
            )

        if rate_result is not None and not rate_result.allowed:
            headers = {
                "Retry-After": str(rate_result.retry_after),
                "X-MAESTRO-Rate-Limit": str(rate_result.limit),
                "X-MAESTRO-Rate-Remaining": "0",
                "X-MAESTRO-Rate-Reset": rate_result.reset_at.isoformat(),
            }
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": rate_result.retry_after,
                },
                headers=headers,
            )

        # ----------------------------------------------------------------
        # 3. Prompt injection check (POST / PUT only)
        # ----------------------------------------------------------------
        injection_result = None

        if request.method in ("POST", "PUT"):
            query_text = await self._extract_query_field(request)

            if query_text is not None:
                try:
                    injection_result = await self._injection_filter.check(
                        query=query_text,
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
                    # Attach to request state for downstream route handlers
                    request.state.injection_result = injection_result

                except InjectionBlockedError as exc:
                    injection_result = exc.result
                    return JSONResponse(
                        status_code=400,
                        content={
                            "detail": "Request blocked: prompt injection detected",
                            "injection_score": round(exc.result.score, 3),
                        },
                        headers={
                            "X-MAESTRO-Injection-Score": f"{exc.result.score:.3f}",
                        },
                    )

                except Exception as exc:
                    # Injection filter failure — log and allow (fail-open)
                    logger.error(
                        "maestro_middleware: injection filter error, failing open: %s",
                        exc,
                    )

        # ----------------------------------------------------------------
        # 4. Forward to the route handler
        # ----------------------------------------------------------------
        response = await call_next(request)

        # ----------------------------------------------------------------
        # 5. Attach security response headers
        # ----------------------------------------------------------------
        if rate_result is not None:
            response.headers["X-MAESTRO-Rate-Remaining"] = str(rate_result.remaining)
            response.headers["X-MAESTRO-Rate-Limit"] = str(rate_result.limit)

        if injection_result is not None:
            response.headers["X-MAESTRO-Injection-Score"] = (
                f"{injection_result.score:.3f}"
            )

        return response

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _extract_query_field(self, request: Request) -> Optional[str]:
        """Parse the request body and return the value of 'query' or 'question'.

        Returns None if the body is not JSON, is empty, or contains neither field.
        Consumes the body and re-injects it so the downstream handler can still
        read it normally via Starlette's body caching.
        """
        try:
            body_bytes = await request.body()
            if not body_bytes:
                return None

            body = json.loads(body_bytes)
            if not isinstance(body, dict):
                return None

            for field in ("query", "question"):
                value = body.get(field)
                if isinstance(value, str) and value.strip():
                    return value

            return None

        except (json.JSONDecodeError, UnicodeDecodeError):
            # Non-JSON body — not our concern
            return None
        except Exception as exc:
            logger.debug("maestro_middleware: body parse failed: %s", exc)
            return None
