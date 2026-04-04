# Stage 1: Build
FROM rust:1.77-slim-bullseye AS builder
WORKDIR /app

# Install system dependencies for librdkafka (cmake build) and OpenSSL
RUN apt-get update && apt-get install -y \
    cmake \
    libssl-dev \
    pkg-config \
    libsasl2-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Cache dependencies layer
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release
RUN rm -rf src

# Build actual source
COPY src/ ./src/
RUN touch src/main.rs
RUN cargo build --release

# Stage 2: Runtime
FROM debian:bullseye-slim
WORKDIR /app

RUN apt-get update && apt-get install -y \
    libssl1.1 \
    libsasl2-2 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/target/release/zk-proof-worker /usr/local/bin/

# ZK proof worker needs significant memory — document the resource requirement
LABEL memory.requirement="14GB minimum, 16GB recommended"
LABEL purpose="Zero-knowledge proof generation for Aegis compliance assertions"

EXPOSE 3006
CMD ["zk-proof-worker"]
