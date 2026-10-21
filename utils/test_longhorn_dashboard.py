#!/usr/bin/env python3
"""
Test suite for validating the Longhorn Grafana Dashboard ConfigMap.
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
    "longhorn-dashboard.yaml",
)


def test_longhorn_dashboard():
    assert os.path.exists(MANIFEST_PATH), f"Manifest file does not exist: {MANIFEST_PATH}"

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))

    assert len(docs) >= 1, "Manifest should contain at least one YAML document"
    doc = docs[0]

    assert doc.get("apiVersion") == "v1", f"Expected apiVersion v1, got {doc.get('apiVersion')}"
    assert doc.get("kind") == "ConfigMap", f"Expected kind ConfigMap, got {doc.get('kind')}"

    metadata = doc.get("metadata", {})
    assert metadata.get("name") == "longhorn-grafana-dashboard", f"Expected name longhorn-grafana-dashboard, got {metadata.get('name')}"
    assert metadata.get("namespace") == "apps", f"Expected namespace apps, got {metadata.get('namespace')}"

    labels = metadata.get("labels", {})
    assert labels.get("grafana_dashboard") == "1", "Label grafana_dashboard must be '1'"

    annotations = metadata.get("annotations", {})
    assert annotations.get("kustomize.toolkit.fluxcd.io/substitute") == "disabled", (
        "Annotation kustomize.toolkit.fluxcd.io/substitute must be 'disabled'"
    )

    data = doc.get("data", {})
    assert "longhorn-dashboard.json" in data, "data must contain 'longhorn-dashboard.json'"

    raw_json = data["longhorn-dashboard.json"]
    dashboard = json.loads(raw_json)

    assert "title" in dashboard, "Dashboard JSON must have a title"
    assert dashboard.get("graphTooltip") == 1, f"Expected graphTooltip 1 (shared crosshair), got {dashboard.get('graphTooltip')}"
    assert dashboard.get("refresh") in ["30s", "1m"], f"Expected refresh 30s or 1m, got {dashboard.get('refresh')}"

    # Check template variables
    templating = dashboard.get("templating", {}).get("list", [])
    var_names = {v.get("name") for v in templating}
    required_vars = {"datasource", "namespace", "pvc", "pv_name", "recurring_job", "stale_after"}
    assert required_vars.issubset(var_names), f"Missing variables: {required_vars - var_names}. Found: {var_names}"

    # Collect all panels (including nested inside rows)
    panels = dashboard.get("panels", [])
    all_panels = []
    for p in panels:
        all_panels.append(p)
        for sub in p.get("panels", []):
            all_panels.append(sub)

    # Collect all targets
    all_targets = []
    for p in all_panels:
        all_targets.extend(p.get("targets", []))

    all_exprs = " ".join([t.get("expr", "") for t in all_targets])

    # 1. Cluster storage pool metrics must be present
    assert "longhorn_node_storage_capacity_bytes" in all_exprs, "Missing node storage capacity query"
    assert "longhorn_node_storage_usage_bytes" in all_exprs, "Missing node storage usage query"

    # 2. Performance metrics (Throughput, IOPS, Latency) must be present
    assert "longhorn_volume_read_throughput" in all_exprs or "longhorn_volume_write_throughput" in all_exprs, "Missing volume throughput queries"
    assert "longhorn_volume_read_iops" in all_exprs or "longhorn_volume_write_iops" in all_exprs, "Missing volume IOPS queries"
    assert "longhorn_volume_read_latency" in all_exprs or "longhorn_volume_write_latency" in all_exprs, "Missing volume latency queries"

    # 3. Health & volume robustness metrics
    assert "longhorn_volume_robustness" in all_exprs, "Missing volume robustness query"
    assert "longhorn_volume_actual_size_bytes" in all_exprs, "Missing volume actual size query"
    assert "longhorn_volume_capacity_bytes" in all_exprs, "Missing volume capacity query"

    # 4. Check for invalid formula bug: (count(schedulable==1) - count(allowScheduling==0))
    assert 'count(longhorn_node_status{condition="allowScheduling"}==0)' not in all_exprs, (
        "Found buggy schedulable nodes formula that subtracts allowScheduling==0 from schedulable==1"
    )

    # 5. Check KPI heights: top stat panels should have h <= 4
    top_stat_panels = [
        p for p in panels
        if p.get("type") == "stat" and p.get("gridPos", {}).get("y", 100) < 5
    ]
    for sp in top_stat_panels:
        h = sp.get("gridPos", {}).get("h", 0)
        assert h <= 4, f"Top KPI stat panel '{sp.get('title')}' is too tall (h={h} > 4), harms scannability!"

    # 6. Check Table panel safety against Grafana Scenes runtime crashes:
    for p in all_panels:
        if p.get("type") == "table":
            footer = p.get("options", {}).get("footer")
            if footer and footer.get("show"):
                assert "reducer" in footer and isinstance(footer["reducer"], list) and len(footer["reducer"]) > 0, (
                    f"Table panel '{p.get('title')}' has invalid footer without reducer list: {footer}"
                )
            for ov in p.get("fieldConfig", {}).get("overrides", []):
                for prop in ov.get("properties", []):
                    if prop.get("id") == "custom.cellOptions":
                        copt = prop.get("value", {})
                        if copt.get("type") == "color-background":
                            assert "mode" in copt, (
                                f"Table panel '{p.get('title')}' override '{ov.get('matcher')}' has color-background cellOptions without 'mode' (causes Grafana React crash!)"
                            )

    print(f"Validation successful! Total panels checked: {len(all_panels)}")


if __name__ == "__main__":
    try:
        test_longhorn_dashboard()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
