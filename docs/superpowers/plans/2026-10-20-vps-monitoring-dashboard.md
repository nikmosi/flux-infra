# External VPS & 3x-ui Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a comprehensive, production-grade Grafana dashboard and Prometheus alerting rules for external VPS servers running 3x-ui VPN, correlating Prometheus host metrics and Loki log streams via Flux CD GitOps.

**Architecture:** A unified Grafana dashboard is delivered as a Kubernetes ConfigMap with the label `grafana_dashboard: "1"` for the Grafana sidecar. Alerting rules are packaged as a `PrometheusRule` CRD with label `role: alert-rules` in the `monitoring` namespace, which routes alerts to Alertmanager and `ntfy`. Both resources are integrated into the cluster's GitOps lifecycle via Kustomize and Flux CD.

**Tech Stack:** Kubernetes (k3s), Flux CD v2, Grafana 13.x, Prometheus (kube-prometheus-stack), Loki 3.x, PromQL, LogQL, Kustomize, Python 3.14.

**Spec:** [docs/superpowers/specs/2026-10-20-vps-monitoring-dashboard-design.md](file:///home/nik/git-repos/flux/docs/superpowers/specs/2026-10-20-vps-monitoring-dashboard-design.md)

## Global Constraints

- Dashboards must be declared in Kubernetes ConfigMap manifests with `annotations: { kustomize.toolkit.fluxcd.io/substitute: disabled }` to prevent Flux variable substitution from breaking Grafana variables (such as `$instance`, `$interface`).
- Grafana dashboard ConfigMap must carry `labels: { grafana_dashboard: "1" }` in namespace `monitoring`.
- PrometheusRule must be in `apiVersion: monitoring.coreos.com/v1`, `kind: PrometheusRule`, namespace `monitoring`, with `labels: { role: alert-rules }`.
- Host identifiers in Prometheus (`instance`) and Loki (`instance`) are `vpn-timeweb` and `vpn-finka`; queries must bind directly to `instance=~"$instance"`.
- Primary network interfaces are `eth0` on `vpn-timeweb` and `ens3` on `vpn-finka`; the interface filter regex must be `/^(eth.*|ens.*)$/`.

## Review Focus

1. **Grafana variable substitution collision with Flux**: Flux envsubst could corrupt `$instance` or `$__range` inside JSON if `kustomize.toolkit.fluxcd.io/substitute: disabled` is omitted.
2. **Missing `x-ui` service metric state**: When `x-ui.service` stops, `node_systemd_unit_state{state="active"}` becomes 0; the query must check `== 1` for UP and `== 0` for alert.
3. **LogQL syntax validation**: Loki queries with regex `$log_search` must properly handle empty search string (`|~ "(?i)$log_search"`).
4. **Network device regex filtering**: Interface variable must automatically filter out `docker0`, `br-*`, and `veth*` virtual devices to keep throughput stats accurate.
5. **Kustomize build integrity**: All new resources must compile cleanly through `kustomize build clusters/my-cluster/releases/apps`.

---

### Task 1: Generate and Validate Grafana Dashboard Manifest

**Files:**
- Create: `clusters/my-cluster/releases/apps/vps-nodes-dashboard.yaml`
- Test: `utils/test_vps_dashboard.py`

**Interfaces:**
- Consumes: Prometheus datasource `prometheus`, Loki datasource `loki`, labels `instance="vpn-timeweb|vpn-finka"`.
- Produces: Kubernetes ConfigMap `vps-nodes-dashboard` in namespace `monitoring` containing `vps-nodes-dashboard.json`.

- [ ] **Step 1: Write dashboard validation test script**

Create `utils/test_vps_dashboard.py` to validate:
- YAML structure of `vps-nodes-dashboard.yaml` (apiVersion `v1`, kind `ConfigMap`, metadata namespace `monitoring`, label `grafana_dashboard: "1"`, annotation `kustomize.toolkit.fluxcd.io/substitute: disabled`).
- Embedded JSON parsing and required Grafana fields (`title`, `panels`, `templating.list`, `schemaVersion`).
- Verification that required template variables (`instance`, `interface`, `log_search`) exist.
- Verification that panels cover Rows 1 through 5 (Status, Network, Host Resources, Sockets/Conntrack, Loki Logs).

- [ ] **Step 2: Run test to verify it fails before creation**

Run: `python3 utils/test_vps_dashboard.py`
Expected: FAIL (file does not exist).

- [ ] **Step 3: Implement `clusters/my-cluster/releases/apps/vps-nodes-dashboard.yaml`**

Construct the complete Grafana dashboard JSON with:
- Variables:
  - `instance`: `label_values(node_uname_info{job="prometheus.scrape.node_exporter"}, instance)`
  - `interface`: `label_values(node_network_receive_bytes_total{instance=~"$instance"}, device)` with regex `/^(eth.*|ens.*)$/`
  - `log_search`: text box variable
- Row 1: Stat panels for Node Status, `x-ui.service` status, Uptime, CPU %, RAM %, Root Disk %, and Conntrack count.
- Row 2: Network Bandwidth In/Out (bps), Total volume transferred (bytes), and Drops/Errors time series.
- Row 3: Collapsible Row with CPU usage breakdown (stacked modes), Memory & Swap breakdown, and Disk I/O.
- Row 4: TCP Sockets breakdown and Conntrack % utilization gauge.
- Row 5: Loki log volume histogram and Live logs stream panel with query `{job="systemd-journal", instance=~"$instance"} |~ "(?i)$log_search"`.

- [ ] **Step 4: Run validation test to verify it passes**

Run: `python3 utils/test_vps_dashboard.py`
Expected: PASS with 0 errors.

- [ ] **Step 5: Commit dashboard manifest and test**

```bash
git add utils/test_vps_dashboard.py clusters/my-cluster/releases/apps/vps-nodes-dashboard.yaml
git commit -m "feat(monitoring): add external VPS and 3x-ui Grafana dashboard"
```

---

### Task 2: Create PrometheusRule Manifest for VPS & 3x-ui Alerts

**Files:**
- Create: `clusters/my-cluster/releases/apps/vps-alerts.yaml`
- Test: `utils/test_vps_alerts.py`

**Interfaces:**
- Consumes: Metrics `up`, `node_systemd_unit_state`, `node_filesystem_*`, `node_cpu_*`, `node_memory_*`, `node_nf_conntrack_*`, `node_network_*`.
- Produces: `PrometheusRule` resource `vps-alert-rules` in namespace `monitoring`.

- [ ] **Step 1: Write alert rules validation test script**

Create `utils/test_vps_alerts.py` to validate:
- YAML parsing of `clusters/my-cluster/releases/apps/vps-alerts.yaml`.
- Resource kind `PrometheusRule`, apiVersion `monitoring.coreos.com/v1`, labels `role: alert-rules`.
- Presence of rule group `vps.rules`.
- All 7 alert rules present: `VpsNodeDown`, `VpsXuiServiceDown`, `VpsDiskSpaceWarning`, `VpsDiskSpaceCritical`, `VpsHighCpuUsage`, `VpsHighMemoryUsage`, `VpsConntrackTableAlmostFull`, `VpsNetworkPacketDrops`.
- Each rule has valid PromQL expressions, `for` durations, `labels.severity`, and `annotations.summary`.

- [ ] **Step 2: Run test to verify it fails before creation**

Run: `python3 utils/test_vps_alerts.py`
Expected: FAIL (file does not exist).

- [ ] **Step 3: Implement `clusters/my-cluster/releases/apps/vps-alerts.yaml`**

Create `vps-alerts.yaml` according to the spec definitions:
- `VpsNodeDown`: `up{job="prometheus.scrape.node_exporter"} == 0` for 2m, severity `critical`.
- `VpsXuiServiceDown`: `node_systemd_unit_state{job="prometheus.scrape.node_exporter", name="x-ui.service", state="active"} == 0` for 1m, severity `critical`.
- `VpsDiskSpaceWarning` (< 15%) & `VpsDiskSpaceCritical` (< 5%) for 5m.
- `VpsHighCpuUsage`: idle < 10% for 10m, severity `warning`.
- `VpsHighMemoryUsage`: used > 90% for 5m, severity `warning`.
- `VpsConntrackTableAlmostFull`: entries / limit > 85% for 5m, severity `critical`.
- `VpsNetworkPacketDrops`: drops rate > 50 for 5m, severity `warning`.

- [ ] **Step 4: Run validation test to verify it passes**

Run: `python3 utils/test_vps_alerts.py`
Expected: PASS with 0 errors.

- [ ] **Step 5: Commit alerts manifest and test**

```bash
git add utils/test_vps_alerts.py clusters/my-cluster/releases/apps/vps-alerts.yaml
git commit -m "feat(monitoring): add external VPS and 3x-ui Prometheus alerting rules"
```

---

### Task 3: Register in Kustomize and Verify GitOps Deployment

**Files:**
- Modify: `clusters/my-cluster/releases/apps/kustomization.yaml`

**Interfaces:**
- Consumes: `vps-nodes-dashboard.yaml`, `vps-alerts.yaml`.
- Produces: Reconciled Flux releases kustomization in the cluster.

- [ ] **Step 1: Update Kustomization resource list**

Edit `clusters/my-cluster/releases/apps/kustomization.yaml` to include:
```yaml
resources:
  ...
  - vps-alerts.yaml
  - vps-nodes-dashboard.yaml
```

- [ ] **Step 2: Run Kustomize static build check**

Run: `kustomize build clusters/my-cluster/releases/apps > /dev/null`
Expected: Return code 0 with no errors.

- [ ] **Step 3: Commit Kustomization changes**

```bash
git add clusters/my-cluster/releases/apps/kustomization.yaml
git commit -m "feat(monitoring): register vps-nodes-dashboard and vps-alerts in kustomization"
```

- [ ] **Step 4: Reconcile Flux and verify cluster deployment**

Run:
1. `flux reconcile kustomization releases --with-source`
2. Verify ConfigMap: `kubectl get cm -n monitoring vps-nodes-dashboard -o wide`
3. Verify PrometheusRule: `kubectl get prometheusrule -n monitoring vps-alert-rules -o wide`
4. Verify Prometheus rule evaluation: query port-forward to Prometheus API for rule group `vps.rules` and verify state is OK.
