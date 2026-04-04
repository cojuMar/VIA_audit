#!/bin/sh
# ---------------------------------------------------------------------------
# init-vault.sh – Idempotent Vault bootstrap for Project Aegis
#
# Runs as a one-shot container after the vault service is healthy.
# Requires: VAULT_ADDR, VAULT_TOKEN set in the environment.
# ---------------------------------------------------------------------------
set -euo pipefail

: "${VAULT_ADDR:=http://vault:8200}"
: "${VAULT_TOKEN:=aegis-dev-root-token}"

export VAULT_ADDR VAULT_TOKEN

# ---------------------------------------------------------------------------
# 1. Wait for Vault to be ready
# ---------------------------------------------------------------------------
echo "[init-vault] Waiting for Vault at ${VAULT_ADDR} ..."
MAX_WAIT=60
ELAPSED=0
until vault status > /dev/null 2>&1; do
  if [ "${ELAPSED}" -ge "${MAX_WAIT}" ]; then
    echo "[init-vault] ERROR: Vault did not become healthy within ${MAX_WAIT}s. Aborting." >&2
    exit 1
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done
echo "[init-vault] Vault is ready."

# ---------------------------------------------------------------------------
# 2. Enable PKI secrets engine at pki/
# ---------------------------------------------------------------------------
echo "[init-vault] Enabling PKI secrets engine at pki/ ..."
if vault secrets list | grep -q '^pki/'; then
  echo "[init-vault] pki/ already enabled – skipping."
else
  vault secrets enable pki
fi

# ---------------------------------------------------------------------------
# 3. Tune PKI max lease TTL to 87600h (10 years)
# ---------------------------------------------------------------------------
echo "[init-vault] Tuning pki/ max_lease_ttl to 87600h ..."
vault secrets tune -max-lease-ttl=87600h pki

# ---------------------------------------------------------------------------
# 4. Generate root CA certificate
# ---------------------------------------------------------------------------
echo "[init-vault] Generating root CA certificate ..."
vault write -format=json pki/root/generate/internal \
  common_name="Aegis Root CA" \
  ttl=87600h \
  > /tmp/root_ca.json

ROOT_CERT=$(cat /tmp/root_ca.json | grep -o '"certificate":"[^"]*"' | sed 's/"certificate":"//;s/"$//' | sed 's/\\n/\n/g')
echo "[init-vault] Root CA certificate generated."

# ---------------------------------------------------------------------------
# 5. Configure CRL and issuing certificate URLs for root PKI
# ---------------------------------------------------------------------------
echo "[init-vault] Configuring PKI URLs ..."
vault write pki/config/urls \
  issuing_certificates="${VAULT_ADDR}/v1/pki/ca" \
  crl_distribution_points="${VAULT_ADDR}/v1/pki/crl"

# ---------------------------------------------------------------------------
# 6. Enable PKI secrets engine at pki_int/ (intermediate CA)
# ---------------------------------------------------------------------------
echo "[init-vault] Enabling intermediate PKI secrets engine at pki_int/ ..."
if vault secrets list | grep -q '^pki_int/'; then
  echo "[init-vault] pki_int/ already enabled – skipping."
else
  vault secrets enable -path=pki_int pki
fi

vault secrets tune -max-lease-ttl=43800h pki_int

# ---------------------------------------------------------------------------
# 7. Generate intermediate CSR, sign with root, import signed cert
# ---------------------------------------------------------------------------
echo "[init-vault] Generating intermediate CA CSR ..."
vault write -format=json pki_int/intermediate/generate/internal \
  common_name="Aegis Intermediate CA" \
  > /tmp/pki_int_csr.json

INT_CSR=$(cat /tmp/pki_int_csr.json | grep -o '"csr":"[^"]*"' | sed 's/"csr":"//;s/"$//' | sed 's/\\n/\n/g')

echo "[init-vault] Signing intermediate CSR with root CA ..."
vault write -format=json pki/root/sign-intermediate \
  csr="${INT_CSR}" \
  common_name="Aegis Intermediate CA" \
  ttl=43800h \
  format=pem_bundle \
  > /tmp/signed_int.json

SIGNED_CERT=$(cat /tmp/signed_int.json | grep -o '"certificate":"[^"]*"' | sed 's/"certificate":"//;s/"$//' | sed 's/\\n/\n/g')

echo "[init-vault] Importing signed intermediate certificate ..."
vault write pki_int/intermediate/set-signed certificate="${SIGNED_CERT}"

vault write pki_int/config/urls \
  issuing_certificates="${VAULT_ADDR}/v1/pki_int/ca" \
  crl_distribution_points="${VAULT_ADDR}/v1/pki_int/crl"

# ---------------------------------------------------------------------------
# 8. Create PKI role: auditor-role
# ---------------------------------------------------------------------------
echo "[init-vault] Creating PKI role auditor-role ..."
vault write pki_int/roles/auditor-role \
  allowed_domains="aegis.local" \
  allow_subdomains=true \
  max_ttl=8h \
  ttl=4h \
  key_type=ec \
  key_bits=256

# ---------------------------------------------------------------------------
# 9. Create PKI role: infra-role
# ---------------------------------------------------------------------------
echo "[init-vault] Creating PKI role infra-role ..."
vault write pki_int/roles/infra-role \
  allowed_domains="aegis.local" \
  allow_subdomains=true \
  max_ttl=15m \
  ttl=5m \
  key_type=ec \
  key_bits=256

# ---------------------------------------------------------------------------
# 10. Enable database secrets engine
# ---------------------------------------------------------------------------
echo "[init-vault] Enabling database secrets engine ..."
if vault secrets list | grep -q '^database/'; then
  echo "[init-vault] database/ already enabled – skipping."
else
  vault secrets enable database
fi

# ---------------------------------------------------------------------------
# 11. Configure postgresql connection
# ---------------------------------------------------------------------------
echo "[init-vault] Configuring postgresql database connection ..."
vault write database/config/postgresql \
  plugin_name=postgresql-database-plugin \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/aegis" \
  allowed_roles="auditor-db-role,infra-db-role" \
  username="aegis_admin" \
  password="aegis_dev_pw"

# ---------------------------------------------------------------------------
# 12. Create database role: auditor-db-role
# ---------------------------------------------------------------------------
echo "[init-vault] Creating database role auditor-db-role ..."
vault write database/roles/auditor-db-role \
  db_name=postgresql \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl=4h \
  max_ttl=8h

# ---------------------------------------------------------------------------
# 13. Create database role: infra-db-role
# ---------------------------------------------------------------------------
echo "[init-vault] Creating database role infra-db-role ..."
vault write database/roles/infra-db-role \
  db_name=postgresql \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl=5m \
  max_ttl=15m

# ---------------------------------------------------------------------------
# 14. Enable KV v2 secrets engine at secret/
# ---------------------------------------------------------------------------
echo "[init-vault] Enabling KV v2 secrets engine at secret/ ..."
if vault secrets list | grep -q '^secret/'; then
  echo "[init-vault] secret/ already enabled – skipping."
else
  vault secrets enable -version=2 -path=secret kv
fi

# ---------------------------------------------------------------------------
# 15. Write placeholder JWT private key secret
# ---------------------------------------------------------------------------
echo "[init-vault] Writing placeholder JWT private key at secret/data/aegis/jwt-private-key ..."
vault kv put secret/aegis/jwt-private-key \
  placeholder="replace-with-real-key"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo "[init-vault] Vault initialization complete."
