# Fix VPS Prometheus Remote Write Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore telemetry delivery from external VPS servers (`vpn-timeweb`, `vpn-finka`) to cluster Prometheus and fix the [External VPS & 3x-ui Monitoring](https://grafana.xinfra.ru/d/external-vps-3x-ui/external-vps-and-3x-ui-monitoring) dashboard by replacing Authelia ForwardAuth on `/api/v1/write` with Traefik native BasicAuth middleware.

---

## Proposed Changes

### Monitoring / Ingress & Middleware

#### [NEW] `clusters/my-cluster/secrets/prometheus-remote-write-basic-auth.enc.yaml`
- Secret `prometheus-remote-write-basic-auth` in namespace `monitoring`.
- Contains `users: | prometheus:<hash>` matching VPS alloy credentials.
- Encrypted via SOPS with Age recipient.

#### [NEW] `clusters/my-cluster/releases/apps/prometheus-remote-write-auth.yaml`
- Traefik `Middleware` `prometheus-remote-write-basic-auth` in namespace `monitoring`.
- References Secret `prometheus-remote-write-basic-auth`.

#### `clusters/my-cluster/releases/apps/kustomization.yaml`
- Register `prometheus-remote-write-auth.yaml` in resources.

#### `clusters/my-cluster/releases/apps/kube-prometheus-stack.yaml`
- Update Prometheus ingress annotation:
  `traefik.ingress.kubernetes.io/router.middlewares: monitoring-prometheus-remote-write-basic-auth@kubernetescrd`.

#### `clusters/my-cluster/releases/apps/authelia.yaml`
- Set `prometheus.xinfra.ru` `/api/v1/write` policy to `bypass`.

---

## Plan Tasks

- [ ] **Task 1: Generate Encrypted Secret for Traefik BasicAuth**
  - Compute htpasswd hash for `prometheus` user password.
  - Create `clusters/my-cluster/secrets/prometheus-remote-write-basic-auth.enc.yaml`.
  - Encrypt with SOPS.
  - Apply Secret to cluster via `sops exec-file ... kubectl apply -f -` or commit for Flux.

- [ ] **Task 2: Create Traefik BasicAuth Middleware Manifest**
  - Create `clusters/my-cluster/releases/apps/prometheus-remote-write-auth.yaml`.
  - Register it in `clusters/my-cluster/releases/apps/kustomization.yaml`.
  - Apply to cluster to verify CRD validity.

- [ ] **Task 3: Update Prometheus Ingress & Authelia Rules**
  - Switch middleware on `kube-prometheus-stack-prometheus` ingress to `monitoring-prometheus-remote-write-basic-auth@kubernetescrd`.
  - Set `policy: bypass` for `prometheus.xinfra.ru/api/v1/write` in `authelia.yaml`.
  - Apply / reconcile changes.

- [ ] **Task 4: Restart Authelia Pod to Clear Lock Contention & Ban State**
  - Restart pod `authelia-f64d949c5-...` in namespace `security`.
  - Verify clean restart and no lock errors.

- [ ] **Task 5: Verification & End-to-End Validation**
  - Test curl POST to `https://prometheus.xinfra.ru/api/v1/write` with basic auth. Expect 204 No Content.
  - Test curl POST to `https://prometheus.xinfra.ru/api/v1/write` without auth. Expect 401 Unauthorized from Traefik.
  - Check alloy logs on `vpn-timeweb` and `vpn-finka` via SSH.
  - Query Prometheus vector for `up{job="prometheus.scrape.node_exporter"}`.
  - Verify Grafana dashboard variables and panels load with real data.
