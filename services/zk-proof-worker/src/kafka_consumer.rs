use rdkafka::{
    consumer::{CommitMode, Consumer, StreamConsumer},
    ClientConfig, Message,
};
use std::sync::Arc;
use crate::{config::Config, prover::{Prover, ProofJob}};

pub struct ProofJobConsumer {
    consumer: StreamConsumer,
    prover: Arc<Prover>,
    completed_topic: String,
}

impl ProofJobConsumer {
    pub fn new(config: &Config, prover: Arc<Prover>) -> Self {
        let consumer: StreamConsumer = ClientConfig::new()
            .set("bootstrap.servers", &config.kafka_bootstrap_servers)
            .set("group.id", &config.kafka_consumer_group)
            .set("auto.offset.reset", "earliest")
            .set("enable.auto.commit", "false")
            .set("max.poll.interval.ms", "3600000") // 1 hour — proofs can take minutes
            .create()
            .expect("Failed to create Kafka consumer");

        consumer
            .subscribe(&[&config.kafka_topic_proof_requested])
            .expect("Failed to subscribe to proof topic");

        Self {
            consumer,
            prover,
            completed_topic: config.kafka_topic_proof_completed.clone(),
        }
    }

    pub async fn consume_loop(&self, producer: &rdkafka::producer::FutureProducer) {
        use futures::StreamExt;
        let mut stream = self.consumer.stream();

        while let Some(msg_result) = stream.next().await {
            match msg_result {
                Ok(msg) => {
                    if let Some(payload) = msg.payload() {
                        match serde_json::from_slice::<ProofJob>(payload) {
                            Ok(job) => {
                                let proof_id = job.proof_id;
                                tracing::info!(%proof_id, "Processing proof job");

                                let result = self.prover.generate(job).await;

                                // Publish result to completed topic
                                let result_json = serde_json::to_string(&result)
                                    .unwrap_or_else(|_| "{}".to_string());

                                let _ = producer
                                    .send(
                                        rdkafka::producer::FutureRecord::to(&self.completed_topic)
                                            .key(&result.tenant_id.to_string())
                                            .payload(&result_json),
                                        std::time::Duration::from_secs(10),
                                    )
                                    .await;

                                // Commit only after publishing result
                                self.consumer
                                    .commit_message(&msg, CommitMode::Async)
                                    .unwrap_or_else(|e| tracing::warn!("Commit failed: {}", e));
                            }
                            Err(e) => {
                                tracing::error!("Failed to deserialize proof job: {}", e);
                                // Commit to skip unparseable messages
                                self.consumer.commit_message(&msg, CommitMode::Async).ok();
                            }
                        }
                    }
                }
                Err(e) => tracing::error!("Kafka error: {}", e),
            }
        }
    }
}
