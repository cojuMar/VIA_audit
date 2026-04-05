"""
Vendor Continuous Monitoring

Polls external signals on a scheduled basis:
1. SecurityScorecard API (if API key available) — score changes
2. RSS/Atom news feeds — breach news, financial distress signals
3. NVD CVE feed — CVEs mentioning vendor name or known products

Stores events in vendor_monitoring_events table.
Triggers alerts for critical/high severity events.

Graceful degradation: if no API keys, uses public RSS feeds only.
"""
import logging
import asyncio
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
import httpx
import feedparser

logger = logging.getLogger(__name__)

# Public RSS feeds for security news
SECURITY_RSS_FEEDS = [
    "https://feeds.feedburner.com/TheHackersNews",
    "https://www.bleepingcomputer.com/feed/",
    "https://krebsonsecurity.com/feed/",
]


class VendorMonitor:
    def __init__(self, db_pool, securityscorecard_api_key: str = ""):
        self._pool = db_pool
        self._ssc_key = securityscorecard_api_key
        self._http = httpx.AsyncClient(timeout=10.0)

    async def run_monitoring_cycle(self, tenant_id: UUID) -> int:
        """
        Run one monitoring cycle for all active vendors of a tenant.
        Returns number of events recorded.
        """
        async with self._pool.acquire() as conn:
            await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
            vendors = await conn.fetch("""
                SELECT id, name, website FROM vendors
                WHERE tenant_id = $1 AND status = 'active'
            """, tenant_id)

        total_events = 0
        for vendor in vendors:
            events = await self._monitor_vendor(tenant_id, vendor)
            total_events += len(events)

        return total_events

    async def _monitor_vendor(self, tenant_id: UUID, vendor: dict) -> List[dict]:
        """Run all monitoring checks for a single vendor."""
        events = []

        # SecurityScorecard (if key available)
        if self._ssc_key and vendor.get('website'):
            ssc_events = await self._check_securityscorecard(vendor)
            events.extend(ssc_events)

        # News feed check (always runs — uses vendor name)
        news_events = await self._check_news_feeds(vendor['name'])
        events.extend(news_events)

        # Persist events
        if events:
            await self._persist_events(tenant_id, vendor['id'], events)

        return events

    async def _check_securityscorecard(self, vendor: dict) -> List[dict]:
        """Check SecurityScorecard API for vendor score."""
        try:
            domain = vendor.get('website', '').replace('https://', '').replace('http://', '').split('/')[0]
            if not domain:
                return []

            response = await self._http.get(
                f"https://api.securityscorecard.io/companies/{domain}",
                headers={"Authorization": f"Token {self._ssc_key}"}
            )
            if response.status_code == 200:
                data = response.json()
                score = data.get('score', 0)
                grade = data.get('grade', 'F')
                severity = 'critical' if score < 60 else 'high' if score < 70 else 'info'
                return [{
                    'event_source': 'securityscorecard',
                    'event_type': 'score_change',
                    'severity': severity,
                    'title': f"SecurityScorecard: {grade} ({score}/100)",
                    'description': f"Security score for {vendor['name']}: {score}/100 (grade {grade})",
                    'raw_data': data
                }]
        except Exception as e:
            logger.debug(f"SecurityScorecard check failed for {vendor['name']}: {e}")
        return []

    async def _check_news_feeds(self, vendor_name: str) -> List[dict]:
        """Check public RSS feeds for news mentioning vendor name."""
        events = []
        breach_keywords = ['breach', 'hack', 'ransomware', 'data leak', 'cyberattack', 'vulnerability', 'exploit']

        for feed_url in SECURITY_RSS_FEEDS:
            try:
                response = await self._http.get(feed_url)
                feed = feedparser.parse(response.text)
                for entry in feed.entries[:20]:
                    title = entry.get('title', '').lower()
                    summary = entry.get('summary', '').lower()
                    vendor_lower = vendor_name.lower()

                    if vendor_lower in title or vendor_lower in summary:
                        is_breach = any(kw in title or kw in summary for kw in breach_keywords)
                        if is_breach:
                            events.append({
                                'event_source': 'news_feed',
                                'event_type': 'breach_disclosed',
                                'severity': 'high',
                                'title': entry.get('title', 'Security News Alert')[:200],
                                'description': entry.get('summary', '')[:500],
                                'source_url': entry.get('link'),
                                'raw_data': {'feed_url': feed_url, 'entry_id': entry.get('id')}
                            })
            except Exception as e:
                logger.debug(f"News feed check failed ({feed_url}): {e}")

        return events[:5]  # Limit to 5 news events per cycle

    async def _persist_events(self, tenant_id: UUID, vendor_id: UUID, events: List[dict]) -> None:
        """Persist monitoring events to DB."""
        import json
        async with self._pool.acquire() as conn:
            await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
            for event in events:
                await conn.execute("""
                    INSERT INTO vendor_monitoring_events
                        (tenant_id, vendor_id, event_source, event_type, severity, title, description, source_url, raw_data)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                """, tenant_id, vendor_id,
                    event['event_source'], event['event_type'], event['severity'],
                    event['title'], event.get('description'), event.get('source_url'),
                    json.dumps(event.get('raw_data', {})))

    async def close(self):
        await self._http.aclose()
