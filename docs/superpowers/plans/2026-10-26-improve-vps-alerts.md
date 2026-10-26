# Improve VPS & 3x-ui Prometheus Alerting Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix and harden Prometheus alerting rules for external VPS servers in `clusters/my-cluster/releases/apps/vps-alerts.yaml` so that loss of telemetry (staleness / heartbeat failure) in the push-based `remote_write` architecture reliably triggers `VpsNodeDown`, scope all PromQL queries strictly to `job="prometheus.scrape.node_exporter"`, and add a dedicated `VpsCadvisorDown` alert.

---

## Proposed Changes

### `clusters/my-cluster/releases/apps/vps-alerts.yaml`
1. **`VpsNodeDown`**:
   - Change `expr` to detect both `up == 0` AND push staleness:
     ```promql
     up{job="prometheus.scrape.node_exporter"} == 0 or max by (instance) (time() - max_over_time(timestamp(node_uname_info{job="prometheus.scrape.node_exporter"})[1h:30s])) > 120
     ```
   - Adjust `for: 1m` so alert fires after 2 minutes of silence.
2. **`VpsDockerServiceDown`**:
   - Check `state="active" == 0` instead of `state="failed" == 1` to catch both stopped and failed Docker service.
3. **`VpsCadvisorDown` [NEW]**:
   - Detect if cAdvisor container metrics stop arriving from VPS:
     ```promql
     max by (instance) (time() - max_over_time(timestamp(container_last_seen{job="prometheus.scrape.cadvisor", instance=~"vpn-.*"})[1h:30s])) > 120
     ```
4. **Scope label matching in arithmetic expressions**:
   - Add `{job="prometheus.scrape.node_exporter"}` to right-hand sides of divisions and additions in `VpsDiskSpaceWarning`, `VpsDiskSpaceCritical`, `VpsHighMemoryUsage`, `VpsConntrackTableAlmostFull`, `VpsNetworkPacketDrops`.

### `utils/test_vps_alerts.py`
- Add `VpsCadvisorDown` to `expected_alerts`.

---

## Plan Tasks

- [ ] **Task 1: Update `utils/test_vps_alerts.py` with the New Alert Requirement**
  - Add `VpsCadvisorDown` to expected alerts set.
  - Run test to verify it fails (Red stage).

- [ ] **Task 2: Update `vps-alerts.yaml` Manifest**
  - Update `VpsNodeDown`, `VpsDockerServiceDown`, `VpsCadvisorDown`, and all scoped expressions.
  - Run test to verify it passes (Green stage).

- [ ] **Task 3: Apply & Verify in Kubernetes Cluster**
  - Apply manifest to cluster via `kubectl apply -f clusters/my-cluster/releases/apps/vps-alerts.yaml`.
  - Verify Prometheus rule group `vps.rules` evaluates cleanly with no syntax errors.
  - Commit and push to `origin/main`.
