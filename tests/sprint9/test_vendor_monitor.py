import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/tprm-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.vendor_monitor import VendorMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vendor_row(name: str = "Acme Corp", website: str = "https://acme.com") -> dict:
    return {'id': uuid4(), 'name': name, 'website': website}


def _make_pool(vendors=None):
    """
    Build a mock pool whose conn.fetch returns the given vendors list for
    the initial 'SELECT id, name, website FROM vendors' query, and whose
    conn.execute is a no-op for everything else.
    """
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=vendors or [])
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


def _feedparser_result(entries):
    """Build a minimal feedparser-like result object."""
    mock_feed = MagicMock()
    mock_feed.entries = entries
    return mock_feed


def _feed_entry(title: str, summary: str = "", link: str = "https://example.com/news/1"):
    entry = MagicMock()
    entry.get = lambda key, default="": {
        'title': title,
        'summary': summary,
        'link': link,
        'id': 'entry-001',
    }.get(key, default)
    return entry


# ---------------------------------------------------------------------------
# TestVendorMonitor
# ---------------------------------------------------------------------------

class TestVendorMonitor:
    def test_no_api_key_skips_securityscorecard(self):
        """
        When securityscorecard_api_key is empty, _check_securityscorecard
        must never be called regardless of vendor count.
        """
        vendor = _vendor_row()
        pool, conn = _make_pool(vendors=[vendor])

        monitor = VendorMonitor(db_pool=pool, securityscorecard_api_key="")

        # Patch _check_securityscorecard to detect if it's called
        ssc_called = []

        async def _fake_ssc(v):
            ssc_called.append(v)
            return []

        monitor._check_securityscorecard = _fake_ssc

        # Also patch _check_news_feeds to return no events (so test stays isolated)
        async def _no_news(name):
            return []

        monitor._check_news_feeds = _no_news

        import asyncio
        asyncio.run(monitor.run_monitoring_cycle(uuid4()))

        assert ssc_called == [], (
            "_check_securityscorecard must not be called when ssc_key is empty"
        )

    @pytest.mark.asyncio
    async def test_news_feed_breach_keyword_creates_event(self):
        """
        When a feedparser entry contains the vendor name and a breach keyword
        in the title, _check_news_feeds should produce a breach_disclosed event.
        """
        vendor_name = "Acme Corp"
        entry = _feed_entry(
            title=f"Acme Corp suffers major data breach",
            summary="Attackers exfiltrated customer records from Acme Corp systems.",
        )

        feed_result = _feedparser_result(entries=[entry])

        monitor = VendorMonitor(db_pool=_make_pool()[0], securityscorecard_api_key="")

        mock_http_response = MagicMock()
        mock_http_response.text = "<rss/>"

        with patch.object(monitor._http, 'get', new=AsyncMock(return_value=mock_http_response)), \
             patch('feedparser.parse', return_value=feed_result):
            events = await monitor._check_news_feeds(vendor_name)

        assert len(events) >= 1
        event = events[0]
        assert event['event_type'] == 'breach_disclosed'
        assert event['event_source'] == 'news_feed'

    @pytest.mark.asyncio
    async def test_news_feed_unrelated_entry_ignored(self):
        """
        An entry whose title/summary does not contain the vendor name
        must not generate any events.
        """
        vendor_name = "Acme Corp"
        entry = _feed_entry(
            title="Major breach hits XYZ Ltd — thousands of records stolen",
            summary="XYZ Ltd customers affected by ransomware attack.",
        )

        feed_result = _feedparser_result(entries=[entry])

        monitor = VendorMonitor(db_pool=_make_pool()[0], securityscorecard_api_key="")

        mock_http_response = MagicMock()
        mock_http_response.text = "<rss/>"

        with patch.object(monitor._http, 'get', new=AsyncMock(return_value=mock_http_response)), \
             patch('feedparser.parse', return_value=feed_result):
            events = await monitor._check_news_feeds(vendor_name)

        assert events == []

    @pytest.mark.asyncio
    async def test_monitoring_cycle_returns_event_count(self):
        """
        A cycle with 1 vendor that produces 1 news event must return 1.
        """
        vendor = _vendor_row(name="TargetVendor")
        pool, conn = _make_pool(vendors=[vendor])

        monitor = VendorMonitor(db_pool=pool, securityscorecard_api_key="")

        news_event = {
            'event_source': 'news_feed',
            'event_type': 'breach_disclosed',
            'severity': 'high',
            'title': 'TargetVendor breach disclosed',
            'description': 'Details...',
            'source_url': 'https://example.com',
            'raw_data': {},
        }

        async def _fake_news(name):
            return [news_event]

        monitor._check_news_feeds = _fake_news

        count = await monitor.run_monitoring_cycle(uuid4())
        assert count == 1

    @pytest.mark.asyncio
    async def test_http_failure_does_not_crash(self):
        """
        When the HTTP client raises an exception for all feed URLs,
        the monitoring cycle must complete without crashing and return 0.
        """
        import httpx
        vendor = _vendor_row()
        pool, conn = _make_pool(vendors=[vendor])

        monitor = VendorMonitor(db_pool=pool, securityscorecard_api_key="")

        with patch.object(
            monitor._http, 'get',
            new=AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        ):
            count = await monitor.run_monitoring_cycle(uuid4())

        assert count == 0
