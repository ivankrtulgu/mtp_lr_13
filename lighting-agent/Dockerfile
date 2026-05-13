# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — Build
# ──────────────────────────────────────────────────────────────────────────────
FROM golang:1.21-alpine AS builder

# Install CA certificates (needed for TLS if NATS uses TLS in the future).
RUN apk --no-cache add ca-certificates

WORKDIR /src

# Copy dependency files first for optimal layer caching.
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the source code.
COPY . .

# Build a statically-linked Linux binary.
#   - CGO_ENABLED=0  → pure Go, no C dependencies → smaller, portable binary.
#   - GOOS=linux     → explicit Linux target (safe even if Docker build host is Linux).
#   - -trimpath      → strip build-time paths for smaller binary.
#   - -ldflags="-s -w" → strip debug info (dwarf tables) for smaller binary.
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /app/lighting-agent .

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — Runtime
# ──────────────────────────────────────────────────────────────────────────────
FROM alpine:latest

# Install CA certificates (useful if the binary ever makes outbound HTTPS calls).
RUN apk --no-cache add ca-certificates

# Create a non-root user for security.
RUN adduser -D -h /app appuser

WORKDIR /app

# Copy the compiled binary from the builder stage.
COPY --from=builder /app/lighting-agent .

# Drop privileges.
USER appuser

# The Lighting Agent is a NATS client — no ports to expose.
# EXPOSE <none>

# Default command — runs the agent with NATS_URL from the environment
# (falls back to nats://localhost:4222 inside the container if not set).
ENTRYPOINT ["/app/lighting-agent"]
