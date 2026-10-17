# Architecture Specification: Rust MCP Servers for Forgejo & Homebox

**Date:** 2026-10-17
**Status:** Approved
**Classification:** Architectural

---

## 1. Executive Summary

This document specifies the design and implementation of two independent Model Context Protocol (MCP) servers:
1. **`forgejo-mcp`**: Provides an extensive toolset for interacting with Forgejo / Gitea instances.
2. **`homebox-mcp`**: Provides tools for inventory, locations, tags, and maintenance in Homebox instances.

Both servers are implemented in **Rust 1.99.1**, built as statically linked binaries (`x86_64-unknown-linux-musl`), containerized using **`FROM scratch`** minimal images, authenticated via **Authelia OAuth 2.0 (RFC 9728) + Static API Token**, automated via **Forgejo Actions** on Git tag pushes, and deployed into Kubernetes using **Flux GitOps Image Automation**.

---

## 2. System Architecture & Endpoints

### 2.1 Repository Structure
Two separate repositories are established in `~/git-repos/`:
- `~/git-repos/forgejo-mcp` (remote: `ssh://git.xinfra.ru/nikmosi/forgejo-mcp.git`)
- `~/git-repos/homebox-mcp` (remote: `ssh://git.xinfra.ru/nikmosi/homebox-mcp.git`)

Each repository follows a standard layout:
```text
├── Cargo.toml
├── Cargo.lock
├── Dockerfile                  # Multi-stage: rust:1.99.1 (musl) -> FROM scratch
├── .dockerignore
├── .forgejo/
│   └── workflows/
│       └── image.yml           # CI/CD: build and push to zot.xinfra.ru/<repo>:<tag>
├── src/
│   ├── main.rs                 # Axum HTTP server, graceful shutdown, configuration
│   ├── auth.rs                 # Hybrid auth middleware (Authelia JWKS + Static Key)
│   ├── mcp/
│   │   ├── protocol.rs         # JSON-RPC 2.0 types (Request, Response, Error)
│   │   ├── server.rs           # MCP method routing (initialize, tools/list, tools/call, ping)
│   │   └── types.rs            # Tool metadata & JSON schema definitions
│   ├── client.rs               # Client wrapper for downstream REST API (Forgejo/Homebox)
│   └── tools.rs                # Tool implementations and parameter parsing
└── tests/
    └── integration_test.rs     # Integration and auth test suite
```

### 2.2 Network Endpoints (Port 8000)

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `POST` | `/mcp` | Yes | Model Context Protocol Streamable HTTP transport (JSON-RPC 2.0). |
| `GET` | `/.well-known/oauth-protected-resource` | No | RFC 9728 metadata pointing to Authelia authorization server. |
| `GET` | `/healthz` | No | Health check for Kubernetes liveness & readiness probes. |

---

## 3. Authentication & Security Model

### 3.1 Environment Configuration
Each service receives the following environment variables:
- `PORT`: HTTP port to bind (default `8000`).
- `HOST`: Bind address (default `0.0.0.0`).
- `AUTHELIA_URL`: Base URL of Authelia (e.g. `https://auth.xinfra.ru`).
- `RESOURCE_URL`: Resource identifier (e.g. `https://mcp-forgejo.xinfra.ru/mcp` or `https://mcp-homebox.xinfra.ru/mcp`).
- `STATIC_API_KEY`: Optional pre-shared key for Claude Code / CLI / local agent access.
- `TARGET_URL`: Internal cluster URL of target service (e.g. `http://forgejo-http.developer-tools.svc.cluster.local:3000` or `http://homebox.apps.svc.cluster.local:7745`).
- `TARGET_TOKEN`: Service token for downstream authentication.

### 3.2 Authentication Flow in Axum Middleware
For every incoming request to `POST /mcp`:
1. **Header Check**:
   - Inspect `Authorization` header. If missing or not starting with `Bearer `, return HTTP `401 Unauthorized` with:
     ```http
     WWW-Authenticate: Bearer resource_metadata="https://<mcp-host>/.well-known/oauth-protected-resource"
     ```
2. **Static Key Comparison**:
   - If `STATIC_API_KEY` is configured and matches the bearer token using constant-time comparison (`subtle::ConstantTimeEq`), authorize request immediately.
3. **Authelia OAuth 2.0 JWT Validation**:
   - Parse JWT header to extract key ID (`kid`).
   - Query in-memory JWKS cache (fetched from `https://auth.xinfra.ru/jwks.json` and cached with TTL or refreshed on unknown `kid`).
   - Verify RS256 signature using public key.
   - Validate standard claims:
     - `iss == AUTHELIA_URL`
     - `aud` contains `RESOURCE_URL` or base host domain
     - `exp > now()` and `nbf <= now()`.
   - On success: proceed to MCP handler.
   - On failure: return HTTP `401 Unauthorized` with `error="invalid_token"`.

---

## 4. MCP Tools Specification

### 4.1 `forgejo-mcp` Tools
- **Repositories & Code:**
  - `search_repos`: Search repositories by keyword, owner, visibility.
  - `list_my_repos`: List authenticated user repositories.
  - `get_repo`: Get repository metadata.
  - `get_file_content`: Read file content or directory tree at ref.
  - `create_file`: Create a file with commit message.
  - `update_file`: Update an existing file with commit message.
  - `delete_file`: Delete a file from repository.
  - `get_repo_tree`: Get git tree (recursive/non-recursive).
  - `list_repo_commits`: List commits on branch/ref.
  - `list_branches`: List branches in repository.
  - `create_branch`: Create a new branch from reference.
  - `delete_branch`: Delete branch.
- **Issues & Milestones:**
  - `search_issues`: Query issues across repository.
  - `list_repo_issues`: List issues filtered by state (`open`/`closed`) and labels.
  - `get_issue_by_index`: Get issue details.
  - `create_issue`: Create new issue.
  - `update_issue`: Update issue title/body.
  - `issue_state_change`: Change state (`open`/`closed`).
  - `list_issue_comments`: List issue comments.
  - `create_issue_comment`: Add comment to issue/PR.
  - `list_repo_labels`: List labels available in repo.
  - `add_issue_labels`: Add labels to issue.
  - `remove_issue_labels`: Remove labels from issue.
  - `list_repo_milestones`: List milestones.
- **Pull Requests:**
  - `list_repo_pull_requests`: List PRs.
  - `get_pull_request_by_index`: Get PR metadata.
  - `get_pull_request_diff`: Get raw patch/diff of PR.
  - `create_pull_request`: Open a pull request between head and base branches.
  - `update_pull_request`: Update PR properties.
  - `merge_pull_request`: Merge PR (merge, squash, rebase).
- **Releases & Actions:**
  - `list_releases`: List releases.
  - `get_release_by_tag`: Retrieve release by tag name.
  - `create_release`: Create new release/tag.
  - `list_workflow_runs`: List Forgejo Actions workflow runs.
  - `get_workflow_run`: Get status of workflow run.
  - `dispatch_workflow`: Trigger workflow dispatch event.

### 4.2 `homebox-mcp` Tools
- **Inventory Items:**
  - `search_items`: Full-text search across items (name, description, serial number, model, manufacturer).
  - `get_item`: Detailed information on specific item by ID.
  - `create_item`: Create item with location, price, quantity, tags.
  - `set_item`: Update existing item attributes.
  - `delete_item`: Remove item from inventory.
  - `move_item`: Move item to target location.
  - `duplicate_item`: Clone item.
  - `mark_sold`: Mark item as sold/disposed.
- **Locations:**
  - `list_locations`: List all locations (rooms, cabinets, bins).
  - `location_contents`: List all items currently inside location.
  - `create_location`: Create new location.
  - `delete_location`: Delete location.
- **Tags & Custom Fields:**
  - `list_tags`: List tags.
  - `set_tag`: Create or attach tag.
  - `delete_tag`: Delete tag.
  - `list_custom_fields`: List custom fields.
  - `set_fields`: Update custom fields on item.
- **Maintenance & Warranties:**
  - `list_maintenance`: List maintenance logs for an item.
  - `log_maintenance`: Record maintenance entry.
  - `delete_maintenance`: Delete maintenance log.
  - `warranties_expiring`: Query items with expiring warranties.
  - `set_warranty`: Set warranty dates.
- **Attachments & Overview:**
  - `list_attachments`: List item attachments.
  - `attach_document`: Upload document reference.
  - `get_attachment`: Download attachment.
  - `delete_attachment`: Remove attachment.
  - `inventory_stats`: Overall statistics (item count, total value, location counts).
  - `export_csv`: Export inventory dataset.

---

## 5. Containerization (`scratch`) & CI/CD

### 5.1 Dockerfile (`rust:1.99.1` -> `FROM scratch`)
- Builder Stage:
  - Uses `rust:1.99.1` with `musl-tools` and target `x86_64-unknown-linux-musl`.
  - Generates `/etc/passwd_mcp` with `mcp:x:10001:10001:...`.
  - Statically compiles binaries using Cargo release profile with `strip = true` and `lto = true`.
- Final Stage:
  - Base `FROM scratch`.
  - Copies `/etc/ssl/certs/ca-certificates.crt`.
  - Copies `/etc/passwd_mcp` to `/etc/passwd`.
  - Copies single static binary `/mcp-server`.
  - Configures `USER 10001:10001` and `EXPOSE 8000`.
  - Result: ~12-15 MB container image.

### 5.2 CI/CD: Forgejo Actions (`.forgejo/workflows/image.yml`)
- Triggered on tag push: `on: push: tags: ["v*"]`.
- Builds Docker image on runner `ci-runners/forgejo-runner`.
- Pushes image tags:
  - `zot.xinfra.ru/<repo>:${TAG}`
  - `zot.xinfra.ru/<repo>:${TAG#v}`
  - `zot.xinfra.ru/<repo>:latest`

---

## 6. GitOps Automation via Flux

### 6.1 Sources Configuration (`clusters/my-cluster/sources/`)
- `forgejo-mcp.yaml`:
  - `ImageRepository`: `zot.xinfra.ru/forgejo-mcp`, interval 2m.
  - `ImagePolicy`: `^v(?P<semver>.*)`, SemVer `>=0.1.0`.
- `homebox-mcp.yaml`:
  - `ImageRepository`: `zot.xinfra.ru/homebox-mcp`, interval 2m.
  - `ImagePolicy`: `^v(?P<semver>.*)`, SemVer `>=0.1.0`.

### 6.2 App Manifests (`clusters/my-cluster/releases/apps/`)
- `forgejo-mcp.yaml` and `homebox-mcp.yaml` contain:
  - `Deployment`:
    - `image: zot.xinfra.ru/<app>:v0.1.0 # {"$imagepolicy": "flux-system:<app>:tag"}`
    - Security context: `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `drop: [ALL]`.
    - Probes: HTTP `/healthz` on port 8000.
  - `Service`: ClusterIP on port 8000.
  - `IngressRoute`: Host rule (`mcp-forgejo.xinfra.ru` / `mcp-homebox.xinfra.ru`), TLS with `wildcard-xinfra-ru-tls`.

---

## 7. Multi-Agent Development Execution Strategy

Development will be parallelized across specialized subagents:
1. **Agent 1 (`forgejo-mcp-builder`)**:
   - Initialize `/home/nik/git-repos/forgejo-mcp`.
   - Setup Cargo workspace/project with Axum, Serde, Reqwest, Jsonwebtoken.
   - Implement MCP protocol, Authelia auth middleware, and Forgejo toolset.
   - Multistage Dockerfile & Forgejo Actions workflow.
   - Run unit/integration tests with `cargo test`.
2. **Agent 2 (`homebox-mcp-builder`)**:
   - Initialize `/home/nik/git-repos/homebox-mcp`.
   - Setup Cargo project with Axum, Serde, Reqwest, Jsonwebtoken.
   - Implement MCP protocol, Authelia auth middleware, and Homebox toolset.
   - Multistage Dockerfile & Forgejo Actions workflow.
   - Run unit/integration tests with `cargo test`.
3. **Orchestrator**:
   - Setup remotes on `git.xinfra.ru` for both repositories.
   - Tag both repos with `v0.1.0` and trigger Forgejo Actions builds.
   - Verify image build and push in Zot.
   - Add Flux `ImageRepository`, `ImagePolicy`, `Deployment`, `Service`, `IngressRoute` in `/home/nik/git-repos/flux`.
   - Reconcile Flux and verify end-to-end MCP response and OAuth2 metadata.
