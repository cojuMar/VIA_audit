use config::{ConfigError, Environment};

#[derive(Debug, Clone)]
pub struct Config {
    pub database_url: String,
    pub kafka_bootstrap_servers: String,
    pub kafka_consumer_group: String,       // "zk-proof-worker-group"
    pub minio_endpoint: String,
    pub minio_access_key: String,
    pub minio_secret_key: String,
    pub minio_zk_bucket: String,            // "aegis-zk-proofs"
    pub server_port: u16,                    // 3006
    pub worker_max_ram_gb: usize,           // 14 (leaves 2GB headroom in 16GB container)
    pub worker_max_batch_size: usize,       // 262144 = 2^18 (safe for 16GB RAM per batch)
    pub kafka_topic_proof_requested: String, // "aegis.zk.proof.requested"
    pub kafka_topic_proof_completed: String, // "aegis.zk.proof.completed"
    pub max_concurrent_proofs: usize,        // 1 (proofs are memory-intensive, serialize)
}

impl Config {
    pub fn from_env() -> Result<Self, ConfigError> {
        let builder = config::Config::builder()
            // Defaults
            .set_default("kafka_consumer_group", "zk-proof-worker-group")?
            .set_default("minio_zk_bucket", "aegis-zk-proofs")?
            .set_default("server_port", 3006)?
            .set_default("worker_max_ram_gb", 14)?
            .set_default("worker_max_batch_size", 262144)?
            .set_default("kafka_topic_proof_requested", "aegis.zk.proof.requested")?
            .set_default("kafka_topic_proof_completed", "aegis.zk.proof.completed")?
            .set_default("max_concurrent_proofs", 1)?
            // Override from environment variables (prefix-free for simplicity)
            .add_source(Environment::default().separator("__"));

        let cfg = builder.build()?;

        Ok(Config {
            database_url: cfg.get_string("database_url")?,
            kafka_bootstrap_servers: cfg.get_string("kafka_bootstrap_servers")?,
            kafka_consumer_group: cfg.get_string("kafka_consumer_group")?,
            minio_endpoint: cfg.get_string("minio_endpoint")?,
            minio_access_key: cfg.get_string("minio_access_key")?,
            minio_secret_key: cfg.get_string("minio_secret_key")?,
            minio_zk_bucket: cfg.get_string("minio_zk_bucket")?,
            server_port: cfg.get_int("server_port")? as u16,
            worker_max_ram_gb: cfg.get_int("worker_max_ram_gb")? as usize,
            worker_max_batch_size: cfg.get_int("worker_max_batch_size")? as usize,
            kafka_topic_proof_requested: cfg.get_string("kafka_topic_proof_requested")?,
            kafka_topic_proof_completed: cfg.get_string("kafka_topic_proof_completed")?,
            max_concurrent_proofs: cfg.get_int("max_concurrent_proofs")? as usize,
        })
    }
}
