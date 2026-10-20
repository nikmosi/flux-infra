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


def test_manifest_structure():
    assert os.path.exists(MANIFEST_PATH), f"Manifest file does not exist: {MANIFEST_PATH}"

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
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
    required_vars = {"instance", "interface", "log_search"}
    assert required_vars.issubset(var_names), f"Missing variables: {required_vars - var_names}. Found: {var_names}"

    interface_var = next(v for v in templating if v.get("name") == "interface")
    assert "eth" in interface_var.get("regex", "") or "ens" in interface_var.get("regex", ""), (
        f"Interface variable regex should filter eth/ens devices, got {interface_var.get('regex')}"
    )

    # Check panels & queries
    panels = dashboard.get("panels", [])
    assert len(panels) >= 5, f"Expected at least 5 panels, got {len(panels)}"

    all_targets = []
    for p in panels:
        all_targets.extend(p.get("targets", []))
        for nested in p.get("panels", []):
            all_targets.extend(nested.get("targets", []))

    all_exprs = " ".join([t.get("expr", "") for t in all_targets])

    # Check required telemetry expressions
    assert "node_uname_info" in all_exprs or "up{" in all_exprs, "Missing node status query"
    assert "x-ui.service" in all_exprs, "Missing x-ui.service status query"
    assert "node_network_receive_bytes_total" in all_exprs, "Missing network receive bandwidth query"
    assert "node_network_transmit_bytes_total" in all_exprs, "Missing network transmit bandwidth query"
    assert "node_nf_conntrack_entries" in all_exprs, "Missing conntrack connections query"
    assert "systemd-journal" in all_exprs or "instance=" in all_exprs, "Missing Loki log stream query"

    print("All dashboard assertions passed successfully!")


if __name__ == "__main__":
    try:
        test_manifest_structure()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
