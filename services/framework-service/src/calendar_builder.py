"""
Compliance Calendar Builder

Generates calendar events for a tenant based on their active frameworks.
Event types:
- filing_deadline: annual filing due dates (SOC 2 report, PCI DSS annual assessment)
- cert_renewal: certification expiry dates
- control_review: periodic control review reminders (quarterly, annual)
- periodic_activity: framework-mandated recurring activities
- audit_window: suggested audit window start/end dates
"""
from datetime import date, timedelta
from typing import List
from uuid import UUID
import logging
from .models import CalendarEvent

logger = logging.getLogger(__name__)


class CalendarBuilder:
    def __init__(self, db_pool):
        self._pool = db_pool

    async def build_for_tenant(self, tenant_id: UUID) -> List[CalendarEvent]:
        """
        Generate (or refresh) all calendar events for a tenant's active frameworks.
        Clears existing unresolved events and regenerates them.
        """
        async with self._pool.acquire() as conn:
            await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))

            active = await conn.fetch("""
                SELECT tf.framework_id, tf.activated_at, tf.target_cert_date,
                       cf.name, cf.slug, cf.metadata
                FROM tenant_frameworks tf
                JOIN compliance_frameworks cf ON cf.id = tf.framework_id
                WHERE tf.tenant_id = $1 AND tf.is_active = TRUE
            """, tenant_id)

            today = date.today()
            events = []

            async with conn.transaction():
                # Clear old uncompleted events
                await conn.execute("""
                    DELETE FROM compliance_calendar_events
                    WHERE tenant_id = $1 AND is_completed = FALSE
                """, tenant_id)

                for fw in active:
                    fw_events = self._generate_events(fw, today)
                    for ev in fw_events:
                        await conn.execute("""
                            INSERT INTO compliance_calendar_events
                                (tenant_id, framework_id, event_type, title, due_date, description)
                            VALUES ($1, $2, $3, $4, $5, $6)
                        """, tenant_id, fw['framework_id'], ev['event_type'],
                            ev['title'], ev['due_date'], ev.get('description'))

                        events.append(CalendarEvent(
                            framework_id=fw['framework_id'],
                            framework_name=fw['name'],
                            event_type=ev['event_type'],
                            title=ev['title'],
                            due_date=ev['due_date'],
                            description=ev.get('description'),
                            is_completed=False,
                            days_until_due=(ev['due_date'] - today).days
                        ))

            return sorted(events, key=lambda e: e.due_date)

    def _generate_events(self, fw: dict, today: date) -> list:
        """Generate events for a single framework based on its metadata."""
        import json
        metadata = fw['metadata'] if isinstance(fw['metadata'], dict) else json.loads(fw['metadata'] or '{}')
        slug = fw['slug']
        name = fw['name']
        events = []

        renewal_days = metadata.get('renewal_period_days', 365)

        # Certification renewal
        if fw['target_cert_date']:
            cert_date = fw['target_cert_date'].date() if hasattr(fw['target_cert_date'], 'date') else fw['target_cert_date']
            events.append({'event_type': 'cert_renewal', 'title': f'{name} Certification Renewal', 'due_date': cert_date, 'description': f'Target certification date for {name}'})
            # 90-day pre-warning
            events.append({'event_type': 'audit_window', 'title': f'{name} Audit Window Opens', 'due_date': cert_date - timedelta(days=90), 'description': f'Begin audit evidence collection for {name} renewal'})

        # Quarterly control reviews for continuous-testing controls
        for q in range(1, 5):
            quarter_end = date(today.year, q * 3, [31, 28, 31, 30][q-1])
            if quarter_end >= today:
                events.append({'event_type': 'control_review', 'title': f'{name} Q{q} Control Review', 'due_date': quarter_end, 'description': f'Review and attest quarterly controls for {name}'})

        # Annual periodic activity
        annual_date = date(today.year + 1, 1, 31) if today.month > 1 else date(today.year, 12, 31)
        events.append({'event_type': 'periodic_activity', 'title': f'{name} Annual Risk Assessment', 'due_date': annual_date, 'description': f'Complete annual risk assessment required by {name}'})

        return events
