# Alerting System & ntfy Delivery Improvements Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix critical bugs in Longhorn PrometheusRules, Alertmanager inhibition, and ntfy webhook adapter; resolve alert fatigue, emoji collisions, and delivery limits across the alerting pipeline.

**Architecture:**
1. PrometheusRule fixes for Longhorn and VPS metrics evaluation in GitOps manifests.
2. Alertmanager routing, inhibition rules, and repeat intervals updates in `kube-prometheus-stack`.
3. Python `alertmanager-ntfy-adapter` enhancements: safe batch handling, byte limits, Markdown support, emoji ordering, and probe log hygiene.
4. ntfy server configuration: proxy header handling and increased message payload limits.

**Tech Stack:** Prometheus (PromQL), Alertmanager, Python 3.13 (`urllib`, `http.server`), Kubernetes / Flux CD, ntfy.

**Spec / Audit:** Based on comprehensive 4-agent audit findings from November 22, 2026.

## Global Constraints

- Edits must be strictly valid YAML and Python (syntax checkable before commit).
- Never break existing Flux Kustomizations or HelmReleases.
- Preserve backward compatibility with existing Prometheus and Alertmanager schemas.

---

## Phase 1: Must Fix (Critical Bugs & Outage Risks)

### Task 1: Fix Broken Longhorn Volume Alerts & Annotation Defect
- [x] Edit `clusters/my-cluster/releases/apps/longhorn-alerts.yaml`:
  - Replace `longhorn_volume_robustness == 2` with `longhorn_volume_robustness{state="degraded"} == 1`
  - Replace `longhorn_volume_robustness == 3` with `longhorn_volume_robustness{state="faulted"} == 1`
  - In `LonghornBackupFailed`, fix annotation `(recurring job: {{ $labels.recurring_job }})` to remove nonexistent label.
- [x] Verify PromQL against Prometheus in cluster.
- [x] Commit changes (`9029d3e`).

### Task 2: Fix Alertmanager `inhibit_rules` (Unbreak InfoInhibitor)
- [x] Edit `clusters/my-cluster/releases/apps/kube-prometheus-stack.yaml`:
  - Remove broken 4th rule from `inhibit_rules`: `- target_matchers: [ alertname = InfoInhibitor ]`.
- [x] Verify Alertmanager config syntax.
- [x] Commit changes (`9029d3e`).

### Task 3: Fix ntfy Adapter Message Size Truncation & ntfy Server Limit
- [x] Edit `clusters/my-cluster/releases/apps/kube-prometheus-stack.yaml` (`adapter.py`):
  - In `message()`, slice `alerts[:6]` and cap total bytes to 3800 (`MAX_MESSAGE_BYTES = 3800`) with `... [truncated]` notice.
  - Add exception handling in `do_POST()` for `ValueError` and malformed payload, and safe dictionary access in `label()` and `annotation()`.
- [x] Edit `clusters/my-cluster/releases/apps/ntfy.yaml`:
  - Add/ensure `message-size-limit: 16k` in configuration values.
- [x] Run syntax check on `adapter.py` using `python3 -m py_compile`.
- [x] Commit changes (`9029d3e`).

---

## Phase 2: Should Fix (Reliability, UX & Noise Suppression)

### Task 4: Fix ntfy Tags Order (Resolved Icon Fix) & Enable Markdown
- [x] Edit `clusters/my-cluster/releases/apps/kube-prometheus-stack.yaml` (`adapter.py`):
  - In `tags()`, place `base` (`white_check_mark` / `rotating_light`) first before `severities`.
  - In `publish()`, add `"markdown": True` in the JSON request body.
- [x] Verify Python syntax.
- [x] Commit changes (`a3f859c`).

### Task 5: Fix VPS Down Alert Subquery Window
- [x] Edit `clusters/my-cluster/releases/apps/vps-alerts.yaml`:
  - In `VpsNodeDown` and `VpsCadvisorDown`, change subquery `[1h:30s]` to `[24h:1m]`.
- [x] Commit changes (`a3f859c`).

### Task 6: Enable `behind-proxy: true` in ntfy Server
- [x] Edit `clusters/my-cluster/releases/apps/ntfy.yaml`:
  - Add `behind-proxy: true` to ntfy server configuration.
- [x] Commit changes (`a3f859c`).

### Task 7: Configure Critical Repeat Interval in Alertmanager
- [x] Edit `clusters/my-cluster/releases/apps/kube-prometheus-stack.yaml`:
  - Under `route.routes`, add a subroute for `severity = "critical"` with `repeat_interval: 2h`.
- [x] Commit changes (`a3f859c`).

### Task 8: Suppress Chronic Homelab Noise
- [x] Edit `clusters/my-cluster/releases/apps/kube-prometheus-stack.yaml`:
  - In `defaultRules.rules`, set `kubeMemoryOvercommit: false`.
- [x] Clean up failed completed pod/job `forgesync-codeberg-29916540` in `developer-tools` namespace via kubectl.
- [x] Commit changes (`a3f859c`).

---

## Phase 3: Nice to Have (Enhancements & Polish)

### Task 9: Suppress `/healthz` Probe Logs & Add Action Buttons
- [x] Edit `clusters/my-cluster/releases/apps/kube-prometheus-stack.yaml` (`adapter.py`):
  - In `log_message()`, ignore `/healthz` requests.
  - In `publish()`, add `actions` array with buttons for Grafana Explore and Runbook/Alerts.
- [x] Run syntax check on `adapter.py`.
- [x] Commit changes (`d54c860`).

### Task 10: Qingping Sensor Inhibition When Device is Stale / Offline
- [x] Edit `clusters/my-cluster/releases/apps/kube-prometheus-stack.yaml`:
  - Add `inhibit_rules` so `QingpingDataStale` and `QingpingDeviceOffline` suppress `QingpingHigh.*` and `QingpingLow.*` alerts by `device_name`.
- [x] Validate entire manifest with yamllint and `kubectl apply --dry-run=client`.
- [x] Commit changes (`d54c860`).
