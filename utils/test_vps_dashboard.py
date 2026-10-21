#!/usr/bin/env python3
"""
Test suite for validating the Grafana Dashboard ConfigMap for External VPS & 3x-ui.
"""
import json
import os
import sys

import yaml

MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "clusters",
    "my-cluster",
    "releases",
    "apps",
    "vps-nodes-dashboard.yaml",
)


def test_manifest_structure() -> None:
    assert os.path.exists(MANIFEST_PATH), f"Manifest file does not exist: {MANIFEST_PATH}"

    with open(MANIFEST_PATH, encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))

    assert len(docs) >= 1, "Manifest should contain at least one YAML document"
    doc = docs[0]

    assert doc.get("apiVersion") == "v1", f"Expected apiVersion v1, got {doc.get('apiVersion')}"
    assert doc.get("kind") == "ConfigMap", f"Expected kind ConfigMap, got {doc.get('kind')}"

    metadata = doc.get("metadata", {})
    assert metadata.get("name") == "vps-nodes-dashboard", f"Expected name vps-nodes-dashboard, got {metadata.get('name')}"
    assert metadata.get("namespace") == "monitoring", f"Expected namespace monitoring, got {metadata.get('namespace')}"

    labels = metadata.get("labels", {})
    assert labels.get("grafana_dashboard") == "1", "Label grafana_dashboard must be '1'"

    annotations = metadata.get("annotations", {})
    assert annotations.get("kustomize.toolkit.fluxcd.io/substitute") == "disabled", (
        "Annotation kustomize.toolkit.fluxcd.io/substitute must be 'disabled' to prevent Flux envsubst"
    )

    data = doc.get("data", {})
    assert "vps-nodes-dashboard.json" in data, "data must contain 'vps-nodes-dashboard.json'"

    raw_json = data["vps-nodes-dashboard.json"]
    dashboard = json.loads(raw_json)

    assert "title" in dashboard, "Dashboard JSON must have a title"
    assert "VPS" in dashboard["title"], f"Title should mention VPS, got {dashboard['title']}"

    # Check template variables
    templating = dashboard.get("templating", {}).get("list", [])
    var_names = {v.get("name") for v in templating}
    required_vars = {"instance", "interface", "container", "log_search"}
    assert required_vars.issubset(var_names), f"Missing variables: {required_vars - var_names}. Found: {var_names}"

    interface_var = next(v for v in templating if v.get("name") == "interface")
    assert "enp" in interface_var.get("regex", "") and "eth" in interface_var.get("regex", ""), (
        f"Interface variable regex should filter eth/ens/enp devices, got {interface_var.get('regex')}"
    )

    # Check panels & queries
    panels = dashboard.get("panels", [])
    assert len(panels) >= 20, f"Expected at least 20 panels, got {len(panels)}"

    # Check panel ID uniqueness
    panel_ids = [p.get("id") for p in panels]
    assert len(panel_ids) == len(set(panel_ids)), f"Duplicate panel IDs detected: {panel_ids}"

    # Check for grid overlaps between non-row panels
    non_row_panels = [p for p in panels if p.get("type") != "row"]
    for i, p1 in enumerate(non_row_panels):
        g1 = p1.get("gridPos", {})
        x1, y1, w1, h1 = g1.get("x", 0), g1.get("y", 0), g1.get("w", 0), g1.get("h", 0)
        for p2 in non_row_panels[i + 1 :]:
            g2 = p2.get("gridPos", {})
            x2, y2, w2, h2 = g2.get("x", 0), g2.get("y", 0), g2.get("w", 0), g2.get("h", 0)
            # Check AABB intersection:
            overlap = not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)
            assert not overlap, (
                f"Grid overlap detected between panel '{p1.get('title')}' (id={p1.get('id')}, pos={g1}) "
                f"and '{p2.get('title')}' (id={p2.get('id')}, pos={g2})"
            )

    all_targets = []
    for p in panels:
        all_targets.extend(p.get("targets", []))
        for nested in p.get("panels", []):
            all_targets.extend(nested.get("targets", []))

    all_exprs = " ".join([t.get("expr", "") for t in all_targets])

    # Check required telemetry expressions
    assert "node_uname_info" in all_exprs or "up{" in all_exprs, "Missing node status query"
    assert "x-ui.service" in all_exprs, "Missing x-ui.service status query"
    assert "docker.service" in all_exprs, "Missing docker.service status query"
    assert "prometheus.scrape.cadvisor" in all_exprs or "container_last_seen" in all_exprs, "Missing cadvisor query"
    assert "container_cpu_usage_seconds_total" in all_exprs, "Missing container cpu query"
    assert "container_memory_working_set_bytes" in all_exprs, "Missing container memory working set query"
    assert "container_memory_usage_bytes" in all_exprs, "Missing container memory total query"
    assert "container_network_receive_bytes_total" in all_exprs, "Missing container network receive bandwidth query"
    assert 'interface!="lo"' in all_exprs, "Missing container interface loopback filter"
    assert "node_load1" in all_exprs, "Missing load average query"
    assert "Tcp_RetransSegs" in all_exprs, "Missing TCP retransmission rate query"
    assert "node_network_receive_bytes_total" in all_exprs, "Missing network receive bandwidth query"
    assert "node_network_transmit_bytes_total" in all_exprs, "Missing network transmit bandwidth query"
    assert "node_nf_conntrack_entries" in all_exprs, "Missing conntrack connections query"
    assert "systemd-journal" in all_exprs or "instance=" in all_exprs, "Missing Loki log stream query"
    assert 'job="docker"' in all_exprs and "container=~" in all_exprs, "Missing container log stream query"
    assert "line_format" in all_exprs, "Missing line_format for container logs"

    print("All dashboard assertions passed successfully!")


if __name__ == "__main__":
    try:
        test_manifest_structure()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
