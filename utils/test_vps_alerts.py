#!/usr/bin/env python3
"""
Test suite for validating the PrometheusRule manifest for External VPS & 3x-ui.
"""
import os
import sys
import yaml

MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "clusters",
    "my-cluster",
    "releases",
    "apps",
    "vps-alerts.yaml",
)


def test_alerts_manifest():
    assert os.path.exists(MANIFEST_PATH), f"Alerts manifest does not exist: {MANIFEST_PATH}"

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))

    assert len(docs) >= 1, "Manifest should contain at least one YAML document"
    doc = docs[0]

    assert doc.get("apiVersion") == "monitoring.coreos.com/v1", f"Expected monitoring.coreos.com/v1, got {doc.get('apiVersion')}"
    assert doc.get("kind") == "PrometheusRule", f"Expected kind PrometheusRule, got {doc.get('kind')}"

    metadata = doc.get("metadata", {})
    assert metadata.get("name") == "vps-alert-rules", f"Expected name vps-alert-rules, got {metadata.get('name')}"
    assert metadata.get("namespace") == "monitoring", f"Expected namespace monitoring, got {metadata.get('namespace')}"

    labels = metadata.get("labels", {})
    assert labels.get("role") == "alert-rules", f"Label role must be 'alert-rules', got {labels.get('role')}"

    spec = doc.get("spec", {})
    groups = spec.get("groups", [])
    assert len(groups) >= 1, "Must contain at least one alert group"

    vps_group = next((g for g in groups if g.get("name") == "vps.rules"), None)
    assert vps_group is not None, "Rule group 'vps.rules' not found"

    rules = vps_group.get("rules", [])
    alert_names = {r.get("alert") for r in rules}

    expected_alerts = {
        "VpsNodeDown",
        "VpsXuiServiceDown",
        "VpsDiskSpaceWarning",
        "VpsDiskSpaceCritical",
        "VpsHighCpuUsage",
        "VpsHighMemoryUsage",
        "VpsConntrackTableAlmostFull",
        "VpsNetworkPacketDrops",
    }

    missing = expected_alerts - alert_names
    assert not missing, f"Missing expected alert rules: {missing}. Present: {alert_names}"

    for r in rules:
        name = r.get("alert")
        assert "expr" in r and r["expr"], f"Rule {name} has empty expr"
        assert "for" in r and r["for"], f"Rule {name} missing 'for' duration"
        assert "labels" in r and "severity" in r["labels"], f"Rule {name} missing labels.severity"
        assert r["labels"]["severity"] in ("warning", "critical"), f"Invalid severity in rule {name}"
        assert "annotations" in r and "summary" in r["annotations"], f"Rule {name} missing annotations.summary"

    print("All PrometheusRule assertions passed successfully!")


if __name__ == "__main__":
    try:
        test_alerts_manifest()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
