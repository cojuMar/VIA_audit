mod circuits;
mod config;
mod kafka_consumer;
mod prover;
mod storage;
mod verifier;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::Json,
    routing::{get, post},
    Router,
};
use std::sync::Arc;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[derive(Clone)]
struct AppState {
    prover: Arc<prover::Prover>,
    storage: Arc<storage::ProofStorageClient>,
    config: Arc<config::Config>,
}

#[tokio::main]
async fn main() {
    // Initialize structured logging
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "info".into()),
        ))
        .with(tracing_subscriber::fmt::layer().json())
        .init();

    let config = Arc::new(config::Config::from_env().expect("Failed to load config"));

    let storage = Arc::new(
        storage::ProofStorageClient::new(
            &config.minio_endpoint,
            &config.minio_access_key,
            &config.minio_secret_key,
            &config.minio_zk_bucket,
            "aegis-evidence-worm",
        )
        .await,
    );

    let prover = Arc::new(prover::Prover::new(Arc::clone(&config), Arc::clone(&storage)));

    // Start Kafka consumer in background
    let kafka_prover = Arc::clone(&prover);
    let kafka_config = Arc::clone(&config);
    tokio::spawn(async move {
        let producer: rdkafka::producer::FutureProducer = rdkafka::ClientConfig::new()
            .set("bootstrap.servers", &kafka_config.kafka_bootstrap_servers)
            .set("message.timeout.ms", "10000")
            .create()
            .expect("Failed to create Kafka producer");

        let consumer = kafka_consumer::ProofJobConsumer::new(&kafka_config, kafka_prover);
        consumer.consume_loop(&producer).await;
    });

    let state = AppState {
        prover,
        storage,
        config: Arc::clone(&config),
    };

    let app = Router::new()
        .route("/health", get(health_handler))
        .route("/proofs/verify", post(verify_handler))
        .route("/proofs/:proof_id/status", get(proof_status_handler))
        .with_state(state);

    let addr = format!("0.0.0.0:{}", config.server_port);
    tracing::info!("zk-proof-worker listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("Failed to bind TCP listener");

    axum::serve(listener, app).await.expect("Server failed");
}

async fn health_handler() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "status": "ok",
        "service": "zk-proof-worker",
        "circuits": ["sum_threshold", "access_log_membership", "policy_compliance"]
    }))
}

async fn verify_handler(
    State(state): State<AppState>,
    Json(req): Json<serde_json::Value>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let circuit_type: circuits::CircuitType = serde_json::from_value(
        req.get("circuit_type").cloned().unwrap_or_default(),
    )
    .map_err(|_| StatusCode::BAD_REQUEST)?;

    let proof_blob_uri = req
        .get("proof_blob_uri")
        .and_then(|v| v.as_str())
        .ok_or(StatusCode::BAD_REQUEST)?;

    let public_inputs = req.get("public_inputs").ok_or(StatusCode::BAD_REQUEST)?;

    let proof_bytes = state
        .storage
        .download_proof(proof_blob_uri)
        .await
        .map_err(|_| StatusCode::NOT_FOUND)?;

    match verifier::Verifier::verify(&circuit_type, &proof_bytes, public_inputs) {
        Ok(()) => Ok(Json(
            serde_json::json!({ "valid": true, "circuit_type": circuit_type }),
        )),
        Err(e) => Ok(Json(
            serde_json::json!({ "valid": false, "error": e.to_string() }),
        )),
    }
}

async fn proof_status_handler(Path(proof_id): Path<String>) -> Json<serde_json::Value> {
    // In production: query the DB for proof status
    // Here: return a placeholder
    Json(serde_json::json!({
        "proof_id": proof_id,
        "status": "unknown",
        "message": "Query the evidence-store service for proof status"
    }))
}
