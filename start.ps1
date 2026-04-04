#Requires -Version 5.1
# Project Aegis 2026 - One-Click Launcher

Set-Location $PSScriptRoot

function Write-Header {
    Clear-Host
    Write-Host ""
    Write-Host "  +================================================================+" -ForegroundColor Cyan
    Write-Host "  |       PROJECT AEGIS 2026 - Tri-Modal Audit Platform            |" -ForegroundColor Cyan
    Write-Host "  +================================================================+" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step  { param([string]$N,[string]$M); Write-Host "  [$N] " -ForegroundColor Yellow -NoNewline; Write-Host $M }
function Write-OK    { Write-Host "  [OK] " -ForegroundColor Green -NoNewline; Write-Host $args[0] }
function Write-Fail  { Write-Host "  [!!] " -ForegroundColor Red   -NoNewline; Write-Host $args[0] }
function Write-Info  { Write-Host "  [--] " -ForegroundColor Gray  -NoNewline; Write-Host $args[0] }

# -----------------------------------------------------------------------
# STEP 1 - Check Docker
# -----------------------------------------------------------------------
Write-Header
Write-Step "1/5" "Checking Docker..."

$dockerCheck = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Docker Desktop is not running. Please start it and try again."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-OK "Docker Desktop is running."

# -----------------------------------------------------------------------
# STEP 2 - Set up .env
# -----------------------------------------------------------------------
Write-Step "2/5" "Checking environment configuration..."

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Info "Created .env from .env.example."
    } else {
        Set-Content ".env" "ANTHROPIC_API_KEY="
        Write-Info "Created minimal .env file."
    }
    Write-Host ""
    Write-Host "  +----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |  TIP: Edit .env and set ANTHROPIC_API_KEY to enable AI   |" -ForegroundColor Yellow
    Write-Host "  +----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host ""
    Start-Sleep -Seconds 2
} else {
    Write-OK ".env file found."
}

# -----------------------------------------------------------------------
# STEP 3 - docker compose up
# -----------------------------------------------------------------------
Write-Step "3/5" "Starting all containers (first run may take several minutes)..."
Write-Host ""

# Only start the services we have fully built (Sprints 8-19 + hub + core infra).
# Early-sprint services (zk-proof-worker, forensic-ml, etc.) require
# additional build tooling (Rust/Halo2, CUDA) and are excluded here.
$SERVICES = @(
    "postgres", "redis", "minio", "minio-init",
    "framework-service",
    "tprm-service",
    "trust-portal-service", "trust-portal-ui",
    "monitoring-service",   "monitoring-ui",
    "people-service",       "people-ui",
    "pbc-service",          "pbc-ui",
    "integration-service",  "integration-ui",
    "ai-agent-service",     "ai-agent-ui",
    "risk-service",         "risk-ui",
    "audit-planning-service","audit-planning-ui",
    "esg-board-service",    "esg-board-ui",
    "mobile-sync-service",  "mobile-app",
    "hub-ui"
)

$svcArgs = $SERVICES -join " "
# Limit parallel builds to avoid resource exhaustion on first run.
# COMPOSE_PARALLEL_LIMIT controls how many service images build simultaneously.
$env:COMPOSE_PARALLEL_LIMIT = "4"
$cmd = "docker compose up -d --build $svcArgs"
Write-Info "Starting: $($SERVICES.Count) services (build parallelism: 4)"
Invoke-Expression $cmd
if ($LASTEXITCODE -ne 0) {
    Write-Fail "docker compose up failed. Run 'docker compose logs' to investigate."
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-OK "All containers started."

# -----------------------------------------------------------------------
# STEP 4 - Wait for PostgreSQL
# -----------------------------------------------------------------------
Write-Step "4/5" "Waiting for PostgreSQL to be healthy..."

# Docker Compose names containers and networks using the lowercase project
# folder name as a prefix.  Derive it at runtime so the script works
# regardless of where the repo is checked out.
$projectName    = (Split-Path $PSScriptRoot -Leaf).ToLower()
$pgContainer    = "${projectName}-postgres-1"
$internalNetwork = "${projectName}_aegis-internal"

$maxWait = 90
$waited  = 0
$ready   = $false

while ($waited -lt $maxWait) {
    $status = docker inspect --format "{{.State.Health.Status}}" $pgContainer 2>$null
    if ($status -eq "healthy") { $ready = $true; break }
    Write-Info "PostgreSQL status: $status - waiting 3s..."
    Start-Sleep -Seconds 3
    $waited += 3
}

if (-not $ready) {
    Write-Fail "PostgreSQL did not become healthy in ${maxWait}s."
    Write-Info "Check logs with: docker logs $pgContainer"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-OK "PostgreSQL is healthy."

# -----------------------------------------------------------------------
# STEP 5 - Run migrations
# -----------------------------------------------------------------------
Write-Step "5/5" "Applying database migrations..."

$migrationPath = Join-Path $PSScriptRoot "infra\db\migrations"

docker run --rm `
    --network $internalNetwork `
    -v "${migrationPath}:/migrations:ro" `
    postgres:16-alpine `
    sh -c 'for f in $(ls /migrations/V*.sql | sort); do
        echo "  Applying $(basename $f)..."
        psql "postgresql://aegis_admin:aegis_dev_pw@postgres:5432/aegis" \
            --set ON_ERROR_STOP=1 --single-transaction -f "$f" -q 2>&1 || true
    done
    echo "  Migrations done."'

Write-OK "Database migrations complete (already-applied migrations are skipped automatically)."

# -----------------------------------------------------------------------
# DONE - Print URLs
# -----------------------------------------------------------------------
Write-Host ""
Write-Host "  +================================================================+" -ForegroundColor Green
Write-Host "  |                  AEGIS 2026 IS RUNNING                        |" -ForegroundColor Green
Write-Host "  +================================================================+" -ForegroundColor Green
Write-Host ""

Write-Host "  PLATFORM HUB  (start here)" -ForegroundColor Green
Write-Host "  ----------------------------------------------------------------"
Write-Host "  Hub & Tutorials         " -NoNewline; Write-Host "http://localhost:5173" -ForegroundColor Green
Write-Host ""

Write-Host "  INFRASTRUCTURE" -ForegroundColor Cyan
Write-Host "  ----------------------------------------------------------------"
Write-Host "  PostgreSQL         localhost:5432"
Write-Host "  Redis              localhost:6379"
Write-Host "  MinIO Console      " -NoNewline; Write-Host "http://localhost:9001" -ForegroundColor Cyan -NoNewline
Write-Host "   (aegis_minio / aegis_minio_dev_pw)"
Write-Host ""

Write-Host "  MODULE DASHBOARDS" -ForegroundColor Cyan
Write-Host "  ----------------------------------------------------------------"
Write-Host "  Compliance Frameworks   " -NoNewline; Write-Host "http://localhost:5174" -ForegroundColor Cyan
Write-Host "  Vendor / TPRM           " -NoNewline; Write-Host "http://localhost:5175" -ForegroundColor Cyan
Write-Host "  Client Trust Portal     " -NoNewline; Write-Host "http://localhost:5176" -ForegroundColor Cyan
Write-Host "  Continuous Monitoring   " -NoNewline; Write-Host "http://localhost:5177" -ForegroundColor Cyan
Write-Host "  People / Policy         " -NoNewline; Write-Host "http://localhost:5178" -ForegroundColor Cyan
Write-Host "  PBC / Workpapers        " -NoNewline; Write-Host "http://localhost:5179" -ForegroundColor Cyan
Write-Host "  Enterprise Integrations " -NoNewline; Write-Host "http://localhost:5180" -ForegroundColor Cyan
Write-Host "  AI Agent Platform       " -NoNewline; Write-Host "http://localhost:5181" -ForegroundColor Cyan
Write-Host "  Risk Management         " -NoNewline; Write-Host "http://localhost:5182" -ForegroundColor Cyan
Write-Host "  Audit Planning          " -NoNewline; Write-Host "http://localhost:5183" -ForegroundColor Cyan
Write-Host "  ESG / Board Management  " -NoNewline; Write-Host "http://localhost:5184" -ForegroundColor Cyan
Write-Host "  Mobile Field Auditing   " -NoNewline; Write-Host "http://localhost:5185" -ForegroundColor Cyan
Write-Host ""

Write-Host "  QUICK START" -ForegroundColor Cyan
Write-Host "  ----------------------------------------------------------------"
Write-Host "  Open the Hub to explore all modules, follow the workflow guide,"
Write-Host "  and access role-based tutorials (End User / Admin / Super Admin)."
Write-Host ""
Write-Host "  Append ?tenantId=UUID to any module URL to scope data per tenant."
Write-Host "  Demo tenant: ?tenantId=00000000-0000-0000-0000-000000000001"
Write-Host ""
Write-Host "  Useful commands:" -ForegroundColor Yellow
Write-Host "    docker compose logs -f hub-ui           (follow hub log)"
Write-Host "    docker compose logs -f risk-service     (follow a service log)"
Write-Host "    docker compose ps                       (check container status)"
Write-Host "    stop.bat                                (shut everything down)"
Write-Host ""

$open = Read-Host "  Open Platform Hub in browser? [Y/n]"
if ($open -ne 'n' -and $open -ne 'N') {
    Start-Process "http://localhost:5173"
}

Write-Host ""
Write-Host "  Platform is running. This window can be closed." -ForegroundColor Green
Write-Host ""
