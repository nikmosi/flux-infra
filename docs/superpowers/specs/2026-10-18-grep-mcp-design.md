# Architecture Specification: Rust MCP Server for Grep.app (`grep-mcp`)

**Date:** 2026-10-18
**Status:** In Review
**Classification:** Architectural

---

## 1. Executive Summary

This document specifies the design and implementation of **`grep-mcp`**, a high-performance Model Context Protocol (MCP) server written in **Rust 1.95+ / 1.99.1**, acting as an authenticated proxy for `https://mcp.grep.app`.

### Problem Statement
When connecting Google Gemini Spark or other strict MCP clients to `https://mcp.grep.app`:
1. `GET` reachability probes fail with `HTTP 405 Method Not Allowed`.
2. Standard `POST` requests without `Accept: text/event-stream` are rejected by upstream Vercel with `HTTP 406 Not Acceptable: Client must accept both application/json and text/event-stream`.
3. Upstream lacks user authorization, making it impossible to restrict or integrate into private enterprise/homelab SSO.

### Solution
`grep-mcp` solves these issues by:
- Serving as a standalone Rust microservice in `~/git-repos/grep-mcp`.
- Providing `GET /mcp` returning `200 OK` for reachability probes.
- Normalizing upstream headers by forcing `Accept: application/json, text/event-stream` and handling JSON-RPC 2.0 dispatching.
- Enforcing **Authelia OAuth 2.0 (RFC 9728) + Static API Token** hybrid authentication.
- Packaging as a minimal **`FROM scratch`** container with bundled CA certificates.
- Building via **Forgejo Actions** and deploying to Kubernetes via **Flux GitOps** at `https://mcp-grep.xinfra.ru/mcp`.

---

## 2. System Architecture & Endpoints

### 2.1 Repository Structure
A dedicated repository is initialized at `~/git-repos/grep-mcp` (remote: `ssh://git.xinfra.ru/nik/grep-mcp.git`):

```text
grep-mcp/
├── Cargo.toml
├── Cargo.lock
├── Dockerfile                  # Multi-stage: rust:1.99.1 (musl) -> FROM scratch
├── .dockerignore
├── .forgejo/
│   └── workflows/
│       └── image.yml           # CI/CD: build and push to zot.xinfra.ru/xinfra/grep-mcp:<tag>
├── src/
│   ├── main.rs                 # Axum HTTP server, graceful shutdown, configuration
│   ├── config.rs               # Environment parsing (port, authelia_url, upstream_url, etc.)
│   ├── state.rs                # AppState (JwksCache, GrepClient, Config)
│   ├── auth.rs                 # Hybrid auth middleware (Authelia JWKS + Static Key)
│   ├── mcp/
│   │   ├── mod.rs
│   │   ├── protocol.rs         # JSON-RPC 2.0 types (Request, Response, Error, Id)
│   │   └── server.rs           # MCP method routing (initialize, ping, tools/list, tools/call)
│   └── client.rs               # Upstream GrepClient calling https://mcp.grep.app with header rewrite
└── tests/
    ├── protocol_test.rs        # Healthz, metadata, and probe endpoint tests
    ├── auth_test.rs            # 401 unauthenticated, static key, and invalid token tests
    └── client_test.rs          # Mocked upstream tool calling and error formatting tests
```

### 2.2 Network Endpoints (Port 8000)

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `GET` | `/healthz` | No | Health check for Kubernetes liveness & readiness probes. |
| `GET` | `/.well-known/oauth-protected-resource` | No | RFC 9728 discovery metadata pointing to Authelia. |
| `GET` | `/mcp` | No | Returns `200 OK` with JSON description to satisfy client reachability checks. |
| `POST` | `/mcp` | Yes | Model Context Protocol Streamable HTTP transport (JSON-RPC 2.0). |

---

## 3. Authentication & Security Model

### 3.1 Environment Configuration
The service is configured via environment variables:
- `PORT`: HTTP port to bind (default `8000`).
- `HOST`: Bind address (default `0.0.0.0`).
- `AUTHELIA_URL`: Base URL of Authelia (default `https://auth.xinfra.ru`).
- `RESOURCE_URL`: Resource identifier (default `https://mcp-grep.xinfra.ru/mcp`).
- `STATIC_API_KEY`: Optional pre-shared key for direct agent access.
- `UPSTREAM_URL`: Upstream MCP endpoint (default `https://mcp.grep.app`).

### 3.2 Authentication Flow
Every request to `POST /mcp` passes through `auth_middleware`:
1. **Header Check**:
   - Inspect `Authorization` header. If missing or not starting with `Bearer `, return HTTP `401 Unauthorized` with:
     ```http
     WWW-Authenticate: Bearer resource_metadata="https://mcp-grep.xinfra.ru/.well-known/oauth-protected-resource"
     ```
2. **Static Key Comparison**:
   - If `STATIC_API_KEY` is configured and matches the bearer token using constant-time comparison (`subtle::ConstantTimeEq`), authorize request immediately.
3. **Authelia OAuth 2.0 JWT Validation**:
   - Extract `kid` and `alg` from header (must be `RS256`).
   - Query in-memory `JwksCache` (refreshed from `https://auth.xinfra.ru/jwks.json` with a 60-second cooldown on cache-misses).
   - Validate standard claims:
     - `iss == AUTHELIA_URL`
     - `aud` contains `RESOURCE_URL`, `https://mcp-grep.xinfra.ru`, or `mcp-grep.xinfra.ru`
     - `exp > now()` and `nbf <= now()`
   - On failure: return HTTP `401 Unauthorized` with `error="invalid_token"`.

---

## 4. Upstream Integration & MCP Tool Specification

### 4.1 MCP Handshake & Methods
- **`initialize`**:
  Returns protocol version `2024-11-05`, capabilities `{"tools": {"listChanged": false}}`, and serverInfo:
  ```json
  {
    "name": "grep-mcp",
    "version": "0.1.0"
  }
  ```
- **`ping`**:
  Returns `{}`.
- **`tools/list`**:
  Returns the declaration for `searchGitHub` with full JSON schema.

### 4.2 Tool Definition: `searchGitHub`
- **Description:** Search literal code patterns or regular expressions across >1,000,000 public GitHub repositories.
- **Input Schema:**
  - `query` (string, required): Literal code pattern or regex.
  - `matchCase` (boolean, optional, default false): Case-sensitive match.
  - `matchWholeWords` (boolean, optional, default false): Whole words only.
  - `useRegexp` (boolean, optional, default false): Interpret query as regex.
  - `repo` (string, optional): Filter by repo (e.g. `facebook/react`).
  - `path` (string, optional): Filter by file path (e.g. `src/components/`).
  - `language` (array of strings, optional): Filter by language (e.g. `['TypeScript', 'Rust', 'Python', 'Nix']`).

### 4.3 Tool Execution & Upstream Call
When `tools/call` for `searchGitHub` is received:
1. `GrepClient` dispatches a JSON-RPC request to `UPSTREAM_URL` with headers:
   - `Content-Type: application/json`
   - `Accept: application/json, text/event-stream`
2. The response stream (SSE / JSON) is read and parsed.
3. The result is converted into MCP standard content format:
   ```json
   {
     "content": [
       {
         "type": "text",
         "text": "Repository: ...\nPath: ...\nSnippets:\n..."
       }
     ],
     "isError": false
   }
   ```
4. If upstream returns an error or fails network connection, `isError: true` is returned with an informative message. The server never panics or drops the connection.

---

## 5. Containerization & Scratch Image

### 5.1 Multi-Stage Dockerfile
- **Build stage (`rust:1.99.1-alpine` or `clux/musl-compile`):**
  - Targets `x86_64-unknown-linux-musl`.
  - Cargo build with `--release`.
  - Strip binary (`strip /app/target/x86_64-unknown-linux-musl/release/grep-mcp`).
  - Extract `/etc/ssl/certs/ca-certificates.crt`.
- **Final stage (`FROM scratch`):**
  - Copy `ca-certificates.crt` to `/etc/ssl/certs/ca-certificates.crt`.
  - Copy `grep-mcp` to `/grep-mcp`.
  - `USER 65532:65532`.
  - `ENTRYPOINT ["/grep-mcp"]`.
  - Image size: ~15-20 MB.

---

## 6. CI/CD & Automation

### 6.1 Forgejo Actions Workflow (`.forgejo/workflows/image.yml`)
- Triggered on tag push (`v*`) or manual dispatch.
- Steps:
  1. Checkout code.
  2. Run `cargo test` using Nix or Rust container.
  3. Build container with `docker buildx`.
  4. Authenticate and push to `zot.xinfra.ru/xinfra/grep-mcp:<tag>` and `zot.xinfra.ru/xinfra/grep-mcp:latest`.

---

## 7. GitOps Deployment & Ingress

### 7.1 Kubernetes Manifests (`flux/clusters/my-cluster/releases/apps/grep-mcp.yaml`)
- **Deployment:** 1 replica, resource requests: `20m` CPU / `32Mi` memory; limits: `200m` CPU / `128Mi` memory.
- **Service:** Port 8000 -> targetPort 8000.
- **Secret (`grep-mcp-secrets`):** Contains `STATIC_API_KEY`.
- **Traefik IngressRoute:**
  - Host: `mcp-grep.xinfra.ru`
  - TLS secret: `mcp-grep-tls` via Let's Encrypt / `cert-manager`.

### 7.2 Authelia Configuration (`authelia.yaml`)
- Update `clusters/my-cluster/releases/apps/authelia.yaml` under `identity_providers.oidc.clients`:
  - In `client_id: gemini-spark`, add `https://mcp-grep.xinfra.ru/mcp` and `https://mcp-grep.xinfra.ru` to `audience`.

---

## 8. Verification & Acceptance Criteria

1. **Protocol Verification:**
   - `curl -i http://localhost:8000/healthz` returns `200 OK`.
   - `curl -i http://localhost:8000/.well-known/oauth-protected-resource` returns RFC 9728 JSON.
   - `curl -i http://localhost:8000/mcp` (GET) returns `200 OK`.
2. **Auth Verification:**
   - `POST /mcp` without token returns `401 Unauthorized` with `WWW-Authenticate` header.
   - `POST /mcp` with `Authorization: Bearer <STATIC_API_KEY>` returns `200 OK`.
3. **Tool Verification:**
   - `tools/call` for `searchGitHub` with `{"query": "Colmena apply"}` returns actual GitHub snippets.
4. **End-to-End Gemini Spark Verification:**
   - Gemini Spark reaches `https://mcp-grep.xinfra.ru/mcp` without "Could not be reached" errors.
