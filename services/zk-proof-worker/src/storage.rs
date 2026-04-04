use aws_sdk_s3::{Client as S3Client, config::Credentials, config::Region};
use sha2::{Sha256, Digest};

pub struct ProofStorageClient {
    client: S3Client,
    bucket: String,
    evidence_bucket: String,
}

impl ProofStorageClient {
    pub async fn new(
        endpoint: &str,
        access_key: &str,
        secret_key: &str,
        bucket: &str,
        evidence_bucket: &str,
    ) -> Self {
        let creds = Credentials::new(access_key, secret_key, None, None, "minio");
        let config = aws_config::from_env()
            .credentials_provider(creds)
            .region(Region::new("us-east-1"))
            .endpoint_url(endpoint)
            .load()
            .await;
        Self {
            client: S3Client::new(&config),
            bucket: bucket.to_string(),
            evidence_bucket: evidence_bucket.to_string(),
        }
    }

    pub async fn upload_proof(
        &self,
        tenant_id: &str,
        proof_id: &str,
        proof_bytes: &[u8],
    ) -> Result<String, String> {
        let key = format!("proofs/{}/{}.bin", tenant_id, proof_id);
        let hash = hex::encode(Sha256::digest(proof_bytes));

        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(&key)
            .body(proof_bytes.to_vec().into())
            .content_type("application/octet-stream")
            .metadata("x-amz-meta-sha256", &hash)
            .send()
            .await
            .map_err(|e| e.to_string())?;

        Ok(format!("s3://{}/{}", self.bucket, key))
    }

    pub async fn download_proof(&self, proof_blob_uri: &str) -> Result<Vec<u8>, String> {
        let key = proof_blob_uri
            .strip_prefix(&format!("s3://{}/", self.bucket))
            .ok_or("Invalid proof URI")?;

        let output = self.client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| e.to_string())?;

        output
            .body
            .collect()
            .await
            .map(|b| b.into_bytes().to_vec())
            .map_err(|e| e.to_string())
    }
}
