import asyncio
import json
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from uuid import UUID
from .config import settings
from .scorer import AnomalyScorer

logger = structlog.get_logger()

TOPIC_IN  = 'aegis.ml.anomaly.requested'
TOPIC_OUT = 'aegis.evidence.normalized'  # Enriches with DRI score


class MLKafkaConsumer:
    def __init__(self, scorer: AnomalyScorer):
        self.scorer = scorer
        self._consumer: AIOKafkaConsumer | None = None
        self._producer: AIOKafkaProducer | None = None

    async def start(self):
        self._consumer = AIOKafkaConsumer(
            TOPIC_IN,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id='forensic-ml-service-group',
            enable_auto_commit=False,
            auto_offset_reset='earliest',
            value_deserializer=lambda v: json.loads(v.decode()),
        )
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode(),
        )
        await self._consumer.start()
        await self._producer.start()

    async def stop(self):
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()

    async def consume_loop(self):
        async for msg in self._consumer:
            try:
                record = msg.value
                tenant_id = record.get('tenant_id', '')
                framework = record.get('framework', 'soc2')

                dri_result = await self.scorer.score(tenant_id, record, framework)

                # Publish enriched record with anomaly score
                enriched = {
                    **record,
                    'anomaly_score': dri_result.dynamic_risk_index,
                    'risk_level': dri_result.risk_level,
                    'dri_components': dri_result.to_dict(),
                }
                await self._producer.send_and_wait(
                    TOPIC_OUT,
                    value=enriched,
                    key=tenant_id.encode() if isinstance(tenant_id, str) else tenant_id,
                )
                await self._consumer.commit()
            except Exception as e:
                logger.error("Failed to score evidence record", error=str(e))
                # Do NOT commit — let Kafka redeliver
