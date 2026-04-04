import logging

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


def _score_to_color(score_pct: float) -> str:
    if score_pct >= 80:
        return "green"
    if score_pct >= 60:
        return "amber"
    return "red"


def _score_to_badge_text(score_pct: float) -> str:
    if score_pct >= 80:
        return "Compliant"
    if score_pct >= 60:
        return "In Progress"
    return "Non-Compliant"


class ComplianceBadgeService:
    def __init__(self, settings: Settings) -> None:
        self._framework_url = settings.framework_service_url
        self._http = httpx.AsyncClient(timeout=15.0)

    async def get_badges(
        self, tenant_id: str, framework_slugs: list[str]
    ) -> list[dict]:
        """Fetch scores from framework-service and return formatted badge dicts.

        Returns an empty list on any error (graceful degradation).
        """
        if not framework_slugs:
            return []

        try:
            frameworks_param = ",".join(framework_slugs)
            resp = await self._http.get(
                f"{self._framework_url}/scores/{tenant_id}",
                params={"frameworks": frameworks_param},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "framework-service unavailable for tenant %s: %s", tenant_id, exc
            )
            return []

        # Normalise — framework-service may return a list or a dict of scores
        scores: list[dict] = []
        if isinstance(data, list):
            scores = data
        elif isinstance(data, dict):
            # Support {"scores": [...]} or {"framework_slug": score_pct, ...}
            if "scores" in data:
                scores = data["scores"]
            else:
                for slug, value in data.items():
                    if isinstance(value, (int, float)):
                        scores.append({"slug": slug, "score_pct": float(value)})
                    elif isinstance(value, dict):
                        scores.append({**value, "slug": slug})

        badges: list[dict] = []
        for item in scores:
            score_pct = float(item.get("score_pct") or item.get("score") or 0)
            slug = item.get("slug", "")
            name = item.get("framework_name") or item.get("name") or slug.upper()
            badges.append(
                {
                    "framework_name": name,
                    "slug": slug,
                    "score_pct": score_pct,
                    "color": _score_to_color(score_pct),
                    "badge_text": _score_to_badge_text(score_pct),
                }
            )

        return badges
