# ---------------------------------------------------------------------------
# Stage 1 — Builder
# Compiles TypeScript to JavaScript in a full Node image that has the
# native build toolchain available (for any native npm modules).
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests first so Docker layer cache is not busted
# every time source files change.
COPY package.json package-lock.json* ./

# Install ALL dependencies (including devDependencies — we need tsc and tsx).
RUN npm ci --ignore-scripts

# Copy source and compile
COPY tsconfig.json ./
COPY src/ ./src/

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — Runtime
# Only production artifacts are copied — no devDependencies, no source.
# Runs as the non-root `node` user for defence-in-depth.
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runtime

# Add tini as PID 1 so signals (SIGTERM/SIGINT) are forwarded correctly
# to the Node process, enabling graceful shutdown.
RUN apk add --no-cache tini

WORKDIR /app

# Copy compiled output and production node_modules from the builder stage.
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

# Drop privileges — never run production services as root.
USER node

EXPOSE 3001

# Use tini as the init process so that SIGTERM is properly forwarded.
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "dist/index.js"]
