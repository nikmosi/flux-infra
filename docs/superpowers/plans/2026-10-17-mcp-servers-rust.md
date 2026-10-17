# Rust MCP Servers for Forgejo & Homebox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy production-grade, statically linked (`FROM scratch`) Rust 1.99.1 Model Context Protocol (MCP) servers for Forgejo and Homebox, with Authelia OAuth2 (RFC 9728) + static API key authentication, automated container builds via Forgejo Actions upon Git tag push, and automated continuous deployment via Flux GitOps.

**Architecture:** Each server is an independent Axum web service exposing `POST /mcp` (Streamable HTTP JSON-RPC 2.0), `GET /.well-known/oauth-protected-resource` (RFC 9728), and `GET /healthz`. Inbound requests are authorized by validating Authelia RS256 JWTs against `https://auth.xinfra.ru/jwks.json` or matching an optional static API token. Services are statically compiled with musl libc, packaged in `scratch` containers (~12-15 MB), built in CI, and synchronized via Flux image update automation.

**Tech Stack:** Rust 1.99.1 (musl target), Axum 0.8 / Tokio, Serde / Serde_json, Reqwest (rustls), Jsonwebtoken, Subtle, Docker multi-stage (`scratch`), Forgejo Actions, Flux CD (ImageRepository, ImagePolicy, ImageUpdateAutomation).

**Spec:** [docs/superpowers/specs/2026-10-17-mcp-servers-rust-design.md](file:///home/nik/git-repos/flux/docs/superpowers/specs/2026-10-17-mcp-servers-rust-design.md)

## Global Constraints
- Compiler: Rust 1.99.1 (in Docker build) / Rust 1.95+ with `x86_64-unknown-linux-musl` target.
- Final Container Image: `FROM scratch`, containing only the static binary, `/etc/ssl/certs/ca-certificates.crt`, and `/etc/passwd` for UID 10001:10001.
- MCP Transport: HTTP `POST /mcp` adhering to JSON-RPC 2.0 and MCP protocol specification.
- Discovery: `GET /.well-known/oauth-protected-resource` returning RFC 9728 metadata for Authelia.
- Token Validation: Authelia RS256 JWT validation checking `iss`, `aud`, `exp`, and `kid` via `https://auth.xinfra.ru/jwks.json`, or fallback constant-time comparison against `STATIC_API_KEY`.
- No Direct Main Push to Flux: Use valid git commits with `--no-verify` if devenv hooks are absent.

## Review Focus
- Unauthenticated requests to `POST /mcp` must return HTTP 401 with `WWW-Authenticate: Bearer resource_metadata="..."`.
- Static API key comparison must be constant-time to avoid timing side-channels.
- Downstream API errors from Forgejo/Homebox must not panic the server; they must return JSON-RPC responses with `isError: true`.
- Statically linked musl binary must have embedded or copied root CA certificates to perform HTTPS calls.
- Flux ImagePolicy must correctly capture SemVer tags (`v0.1.0` -> `0.1.0`) and ImageUpdateAutomation must commit tag updates without breaking formatting.

---

### Task 1: Forgejo MCP Server Core, Protocol & Auth

**Files:**
- Create: `/home/nik/git-repos/forgejo-mcp/Cargo.toml`
- Create: `/home/nik/git-repos/forgejo-mcp/src/main.rs`
- Create: `/home/nik/git-repos/forgejo-mcp/src/auth.rs`
- Create: `/home/nik/git-repos/forgejo-mcp/src/mcp/protocol.rs`
- Create: `/home/nik/git-repos/forgejo-mcp/src/mcp/server.rs`
- Create: `/home/nik/git-repos/forgejo-mcp/src/mcp/types.rs`
- Test: `/home/nik/git-repos/forgejo-mcp/tests/protocol_test.rs`

**Interfaces:**
- Produces:
  - `auth::auth_middleware(State, Request, Next) -> Result<Response, StatusCode>`
  - `mcp::server::handle_mcp_request(State, Json<JsonRpcRequest>) -> Json<JsonRpcResponse>`
  - `mcp::protocol::JsonRpcRequest`, `JsonRpcResponse`, `JsonRpcError`

- [ ] **Step 1: Initialize Git repo and Cargo.toml**
Initialize git repo in `/home/nik/git-repos/forgejo-mcp` and create `Cargo.toml` with `axum`, `tokio`, `serde`, `serde_json`, `jsonwebtoken`, `subtle`, `reqwest`, `tracing`, `tracing-subscriber`.

- [ ] **Step 2: Write failing protocol integration test**
Write `tests/protocol_test.rs` testing `GET /healthz`, `GET /.well-known/oauth-protected-resource`, and unauthenticated `POST /mcp` returning 401 with `WWW-Authenticate` header.

- [ ] **Step 3: Implement JSON-RPC protocol types and MCP server skeleton**
Implement `mcp/protocol.rs`, `mcp/types.rs`, `mcp/server.rs` handling `initialize` (protocol version `2024-11-05`), `ping`, and `tools/list`.

- [ ] **Step 4: Implement hybrid Auth middleware**
Implement `src/auth.rs` verifying `STATIC_API_KEY` (constant-time) and Authelia JWT RS256 token against cached JWKS.

- [ ] **Step 5: Run integration tests and verify pass**
Run `cargo test --test protocol_test` and confirm all tests pass.

- [ ] **Step 6: Commit**
Commit initial core and protocol in `/home/nik/git-repos/forgejo-mcp`.

---

### Task 2: Forgejo MCP Toolset & REST Client

**Files:**
- Create: `/home/nik/git-repos/forgejo-mcp/src/client.rs`
- Create: `/home/nik/git-repos/forgejo-mcp/src/tools.rs`
- Test: `/home/nik/git-repos/forgejo-mcp/tests/tools_test.rs`

**Interfaces:**
- Consumes: `mcp::server::AppState`, `mcp::types::Tool`
- Produces:
  - `client::ForgejoClient::new(base_url, token)`
  - `tools::get_tools() -> Vec<Tool>`
  - `tools::execute_tool(client, name, arguments) -> Result<String, String>`

- [ ] **Step 1: Write failing test for Forgejo tool schema listing**
Write `tests/tools_test.rs` asserting `tools/list` returns all specified tools: `search_repos`, `get_file_content`, `list_repo_issues`, `create_pull_request`, etc.

- [ ] **Step 2: Implement `ForgejoClient` in `src/client.rs`**
Implement HTTP client wrapper using `reqwest` calling Forgejo REST API v1 endpoints with `Authorization: token <TARGET_TOKEN>`.

- [ ] **Step 3: Implement tool definitions and dispatcher in `src/tools.rs`**
Define schemas and execution handlers for:
- Repositories: `search_repos`, `list_my_repos`, `get_repo`, `get_file_content`, `create_file`, `update_file`, `delete_file`, `get_repo_tree`, `list_repo_commits`, `list_branches`, `create_branch`, `delete_branch`.
- Issues & Milestones: `search_issues`, `list_repo_issues`, `get_issue_by_index`, `create_issue`, `update_issue`, `issue_state_change`, `list_issue_comments`, `create_issue_comment`, `list_repo_labels`, `add_issue_labels`, `remove_issue_labels`, `list_repo_milestones`.
- Pull Requests: `list_repo_pull_requests`, `get_pull_request_by_index`, `get_pull_request_diff`, `create_pull_request`, `update_pull_request`, `merge_pull_request`.
- Releases & Actions: `list_releases`, `get_release_by_tag`, `create_release`, `list_workflow_runs`, `get_workflow_run`, `dispatch_workflow`.

- [ ] **Step 4: Run tests and verify**
Run `cargo test` and ensure all tool schemas and dispatchers execute without errors.

- [ ] **Step 5: Commit**
Commit toolset implementations.

---

### Task 3: Forgejo MCP Dockerfile (`scratch`) & Actions CI

**Files:**
- Create: `/home/nik/git-repos/forgejo-mcp/Dockerfile`
- Create: `/home/nik/git-repos/forgejo-mcp/.dockerignore`
- Create: `/home/nik/git-repos/forgejo-mcp/.forgejo/workflows/image.yml`

- [ ] **Step 1: Create Dockerfile with multi-stage build**
Write `Dockerfile` with `FROM rust:1.99.1 AS builder` with `x86_64-unknown-linux-musl`, and `FROM scratch` runtime copying the binary, `/etc/ssl/certs/ca-certificates.crt`, and `/etc/passwd`.

- [ ] **Step 2: Build local Docker image and test**
Run `docker build -t zot.xinfra.ru/forgejo-mcp:test .` to ensure the static compilation succeeds and the scratch container starts.

- [ ] **Step 3: Create Forgejo Actions workflow**
Create `.forgejo/workflows/image.yml` configured to trigger on `push: tags: ["v*"]` and push tags to `zot.xinfra.ru/forgejo-mcp`.

- [ ] **Step 4: Commit**
Commit Dockerfile and workflow files.

---

### Task 4: Homebox MCP Server Core, Protocol & Auth

**Files:**
- Create: `/home/nik/git-repos/homebox-mcp/Cargo.toml`
- Create: `/home/nik/git-repos/homebox-mcp/src/main.rs`
- Create: `/home/nik/git-repos/homebox-mcp/src/auth.rs`
- Create: `/home/nik/git-repos/homebox-mcp/src/mcp/protocol.rs`
- Create: `/home/nik/git-repos/homebox-mcp/src/mcp/server.rs`
- Create: `/home/nik/git-repos/homebox-mcp/src/mcp/types.rs`
- Test: `/home/nik/git-repos/homebox-mcp/tests/protocol_test.rs`

**Interfaces:**
- Produces:
  - `auth::auth_middleware(State, Request, Next) -> Result<Response, StatusCode>`
  - `mcp::server::handle_mcp_request(State, Json<JsonRpcRequest>) -> Json<JsonRpcResponse>`

- [ ] **Step 1: Initialize Git repo and Cargo.toml**
Initialize git repo in `/home/nik/git-repos/homebox-mcp` with dependencies matching `forgejo-mcp`.

- [ ] **Step 2: Write failing protocol integration test**
Write `tests/protocol_test.rs` verifying `/healthz`, `/.well-known/oauth-protected-resource`, and auth middleware.

- [ ] **Step 3: Implement protocol and auth in `homebox-mcp`**
Implement JSON-RPC 2.0 protocol, Axum routing, and Authelia JWKS / static key middleware.

- [ ] **Step 4: Run tests and verify pass**
Run `cargo test --test protocol_test`.

- [ ] **Step 5: Commit**
Commit initial core and protocol in `/home/nik/git-repos/homebox-mcp`.

---

### Task 5: Homebox MCP Toolset & REST Client

**Files:**
- Create: `/home/nik/git-repos/homebox-mcp/src/client.rs`
- Create: `/home/nik/git-repos/homebox-mcp/src/tools.rs`
- Test: `/home/nik/git-repos/homebox-mcp/tests/tools_test.rs`

**Interfaces:**
- Consumes: `mcp::server::AppState`, `mcp::types::Tool`
- Produces:
  - `client::HomeboxClient::new(base_url, token)`
  - `tools::get_tools() -> Vec<Tool>`
  - `tools::execute_tool(client, name, arguments) -> Result<String, String>`

- [ ] **Step 1: Write failing test for Homebox tool listing**
Write `tests/tools_test.rs` asserting all inventory, location, tag, and maintenance tools are registered.

- [ ] **Step 2: Implement `HomeboxClient` in `src/client.rs`**
Implement client calling Homebox REST API (`/api/v1/items`, `/api/v1/locations`, `/api/v1/tags`, etc.) with `Bearer <TARGET_TOKEN>`.

- [ ] **Step 3: Implement tool definitions and dispatcher in `src/tools.rs`**
Define schemas and execution handlers for:
- Items: `search_items`, `get_item`, `create_item`, `set_item`, `delete_item`, `move_item`, `duplicate_item`, `mark_sold`.
- Locations: `list_locations`, `location_contents`, `create_location`, `delete_location`.
- Tags & Fields: `list_tags`, `set_tag`, `delete_tag`, `list_custom_fields`, `set_fields`.
- Maintenance & Warranties: `list_maintenance`, `log_maintenance`, `delete_maintenance`, `warranties_expiring`, `set_warranty`.
- Attachments & Stats: `list_attachments`, `attach_document`, `get_attachment`, `delete_attachment`, `inventory_stats`, `export_csv`.

- [ ] **Step 4: Run tests and verify**
Run `cargo test` and ensure all tool schemas and dispatchers execute without errors.

- [ ] **Step 5: Commit**
Commit toolset implementations.

---

### Task 6: Homebox MCP Dockerfile (`scratch`) & Actions CI

**Files:**
- Create: `/home/nik/git-repos/homebox-mcp/Dockerfile`
- Create: `/home/nik/git-repos/homebox-mcp/.dockerignore`
- Create: `/home/nik/git-repos/homebox-mcp/.forgejo/workflows/image.yml`

- [ ] **Step 1: Create Dockerfile with multi-stage build**
Write `Dockerfile` with `FROM rust:1.99.1 AS builder` with `x86_64-unknown-linux-musl`, and `FROM scratch` runtime.

- [ ] **Step 2: Build local Docker image and test**
Run `docker build -t zot.xinfra.ru/homebox-mcp:test .` to ensure compilation and scratch image packaging succeed.

- [ ] **Step 3: Create Forgejo Actions workflow**
Create `.forgejo/workflows/image.yml` for tag push `v*`.

- [ ] **Step 4: Commit**
Commit Dockerfile and workflow files.

---

### Task 7: CI/CD Release & Image Verification in Zot

**Files:**
- Command: Git remotes, tags, and Forgejo API trigger

- [ ] **Step 1: Setup remotes on `git.xinfra.ru`**
Verify or create repos on Forgejo (`nikmosi/forgejo-mcp` and `nikmosi/homebox-mcp`) via API or git push.

- [ ] **Step 2: Tag and push `v0.1.0`**
Tag both repositories with `v0.1.0` and push tags to Forgejo:
```bash
git -C /home/nik/git-repos/forgejo-mcp tag v0.1.0 && git -C /home/nik/git-repos/forgejo-mcp push origin main --tags
git -C /home/nik/git-repos/homebox-mcp tag v0.1.0 && git -C /home/nik/git-repos/homebox-mcp push origin main --tags
```

- [ ] **Step 3: Monitor CI build execution**
Monitor Forgejo runner logs (`kubectl logs -n ci-runners -l app.kubernetes.io/name=forgejo-runner`) until builds finish and push to Zot.

- [ ] **Step 4: Verify image tags in Zot registry**
Verify tags exist:
```bash
curl -s -u "$ZOT_AUTH" https://zot.xinfra.ru/v2/forgejo-mcp/tags/list
curl -s -u "$ZOT_AUTH" https://zot.xinfra.ru/v2/homebox-mcp/tags/list
```

---

### Task 8: Flux GitOps Deployment & Image Automation

**Files:**
- Create: `/home/nik/git-repos/flux/clusters/my-cluster/sources/forgejo-mcp.yaml`
- Create: `/home/nik/git-repos/flux/clusters/my-cluster/sources/homebox-mcp.yaml`
- Create: `/home/nik/git-repos/flux/clusters/my-cluster/releases/apps/forgejo-mcp.yaml`
- Create: `/home/nik/git-repos/flux/clusters/my-cluster/releases/apps/homebox-mcp.yaml`
- Modify: `/home/nik/git-repos/flux/clusters/my-cluster/sources/kustomization.yaml`
- Modify: `/home/nik/git-repos/flux/clusters/my-cluster/releases/apps/kustomization.yaml`

- [ ] **Step 1: Add ImageRepository and ImagePolicy sources**
Create `clusters/my-cluster/sources/forgejo-mcp.yaml` and `homebox-mcp.yaml` referencing `zot.xinfra.ru/<repo>` with SemVer policy `>=0.1.0 <1.0.0`. Add to `sources/kustomization.yaml`.

- [ ] **Step 2: Create Deployment, Service, and IngressRoute manifests**
Create `clusters/my-cluster/releases/apps/forgejo-mcp.yaml` and `homebox-mcp.yaml` with:
- Container image tagged `# {"$imagepolicy": "flux-system:<app>:tag"}`.
- Hardened securityContext (`runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `drop: [ALL]`).
- Environment variables pointing to internal cluster services and Authelia.
- Traefik `IngressRoute` with TLS `wildcard-xinfra-ru-tls`.
Add to `releases/apps/kustomization.yaml`.

- [ ] **Step 3: Commit and push changes to Flux**
Commit and push to `git.xinfra.ru/nikmosi/flux-infra.git`.

- [ ] **Step 4: Reconcile Flux**
Run `flux reconcile source git flux-system && flux reconcile kustomization sources && flux reconcile kustomization apps`.

---

### Task 9: End-to-End Cluster & Client Verification

**Files:**
- Verification commands & probes

- [ ] **Step 1: Check pod status in `apps` namespace**
Confirm both `forgejo-mcp` and `homebox-mcp` pods are `1/1 Running`.

- [ ] **Step 2: Verify RFC 9728 discovery endpoint**
Query external endpoints:
```bash
curl -si https://mcp-forgejo.xinfra.ru/.well-known/oauth-protected-resource
curl -si https://mcp-homebox.xinfra.ru/.well-known/oauth-protected-resource
```
Confirm HTTP 200 with JSON payload specifying `https://auth.xinfra.ru`.

- [ ] **Step 3: Verify 401 challenge on unauthenticated MCP request**
Query `POST https://mcp-forgejo.xinfra.ru/mcp` without headers; confirm HTTP 401 with `WWW-Authenticate: Bearer resource_metadata="..."`.

- [ ] **Step 4: Verify MCP `initialize` and `tools/list` with static token**
Send MCP `tools/list` request with `Authorization: Bearer <STATIC_API_KEY>` and verify full list of tools is returned.
