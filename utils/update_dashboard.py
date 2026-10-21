#!/usr/bin/env python3
"""
Update Longhorn Dashboard ConfigMap:
1. Fix Table panel (ID 13):
   - options.footer reducer: ["count"]
   - custom.cellOptions mode: "basic" for color-background
   - column widths and organization for high readability
2. Performance panels (IDs 16, 17, 18):
   - sum/avg by (pvc_namespace, pvc)
   - legend format: Read: {{pvc_namespace}}/{{pvc}} / Write: {{pvc_namespace}}/{{pvc}}
3. Backup panels (IDs 26, 27):
   - options.footer reducer: ["count"]
   - custom.cellOptions mode: "basic" for color-background
   - PVC Backup Coverage: fallback for Last Backup Age to -1 (mapped to 'Never') and size to 0
4. Replicas WO panel (ID 34):
   - fallback to vector(0) so it does not show No Data when healthy
"""
import json
import os
import yaml

MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "clusters",
    "my-cluster",
    "releases",
    "apps",
    "longhorn-dashboard.yaml",
)


def update_dashboard():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    dash = json.loads(doc["data"]["longhorn-dashboard.json"])

    def find_all_panels(panels):
        res = []
        for p in panels:
            res.append(p)
            if "panels" in p:
                res.extend(find_all_panels(p["panels"]))
        return res

    for p in find_all_panels(dash.get("panels", [])):
        pid = p.get("id")

        # 1. Panel 13: Volume Inventory & Capacity
        if pid == 13:
            p["pluginVersion"] = "11.4.0"
            p["options"] = {
                "cellHeight": "sm",
                "footer": {
                    "countRows": True,
                    "fields": "",
                    "reducer": ["count"],
                    "show": True,
                },
                "showHeader": True,
                "sortBy": [{"desc": True, "displayName": "Usage"}],
            }

            p["fieldConfig"]["overrides"] = [
                {
                    "matcher": {"id": "byName", "options": "Usage"},
                    "properties": [
                        {
                            "id": "custom.cellOptions",
                            "value": {
                                "mode": "basic",
                                "type": "gauge",
                                "valueDisplayMode": "color",
                            },
                        },
                        {"id": "unit", "value": "percent"},
                        {"id": "min", "value": 0},
                        {"id": "max", "value": 100},
                        {"id": "custom.width", "value": 110},
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Robustness"},
                    "properties": [
                        {
                            "id": "custom.cellOptions",
                            "value": {
                                "mode": "basic",
                                "type": "color-background",
                            },
                        },
                        {"id": "custom.width", "value": 100},
                        {
                            "id": "mappings",
                            "value": [
                                {
                                    "options": {
                                        "1": {
                                            "color": "green",
                                            "index": 0,
                                            "text": "Healthy",
                                        }
                                    },
                                    "type": "value",
                                },
                                {
                                    "options": {
                                        "2": {
                                            "color": "orange",
                                            "index": 1,
                                            "text": "Degraded",
                                        }
                                    },
                                    "type": "value",
                                },
                                {
                                    "options": {
                                        "3": {
                                            "color": "red",
                                            "index": 2,
                                            "text": "Fault",
                                        }
                                    },
                                    "type": "value",
                                },
                                {
                                    "options": {
                                        "0": {
                                            "color": "gray",
                                            "index": 3,
                                            "text": "Unknown",
                                        }
                                    },
                                    "type": "value",
                                },
                            ],
                        },
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "State"},
                    "properties": [
                        {
                            "id": "custom.cellOptions",
                            "value": {
                                "mode": "basic",
                                "type": "color-background",
                            },
                        },
                        {"id": "custom.width", "value": 90},
                        {
                            "id": "mappings",
                            "value": [
                                {
                                    "options": {
                                        "1": {
                                            "color": "blue",
                                            "index": 0,
                                            "text": "Pending",
                                        }
                                    },
                                    "type": "value",
                                },
                                {
                                    "options": {
                                        "2": {
                                            "color": "green",
                                            "index": 1,
                                            "text": "Attached",
                                        }
                                    },
                                    "type": "value",
                                },
                                {
                                    "options": {
                                        "3": {
                                            "color": "semi-dark-blue",
                                            "index": 2,
                                            "text": "Detached",
                                        }
                                    },
                                    "type": "value",
                                },
                            ],
                        },
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Namespace"},
                    "properties": [{"id": "custom.width", "value": 130}],
                },
                {
                    "matcher": {"id": "byName", "options": "PVC"},
                    "properties": [{"id": "custom.width", "value": 200}],
                },
                {
                    "matcher": {"id": "byName", "options": "Capacity"},
                    "properties": [
                        {"id": "custom.width", "value": 95},
                        {"id": "unit", "value": "bytes"},
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Actual Size"},
                    "properties": [
                        {"id": "custom.width", "value": 95},
                        {"id": "unit", "value": "bytes"},
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Volume"},
                    "properties": [{"id": "custom.width", "value": 220}],
                },
            ]

            p["transformations"] = [
                {"id": "merge", "options": {}},
                {
                    "id": "organize",
                    "options": {
                        "excludeByName": {
                            "Time": True,
                            "Time 1": True,
                            "Time 2": True,
                            "Time 3": True,
                            "Time 4": True,
                        },
                        "includeByName": {},
                        "indexByName": {
                            "pvc_namespace": 0,
                            "pvc": 1,
                            "Value #robustness": 2,
                            "Value #state": 3,
                            "Value #usage_percent": 4,
                            "Value #actual_size": 5,
                            "Value #capacity": 6,
                            "volume": 7,
                        },
                        "renameByName": {
                            "Value #actual_size": "Actual Size",
                            "Value #capacity": "Capacity",
                            "Value #robustness": "Robustness",
                            "Value #state": "State",
                            "Value #usage_percent": "Usage",
                            "pvc": "PVC",
                            "pvc_namespace": "Namespace",
                            "volume": "Volume",
                        },
                    },
                },
                {
                    "id": "filterByValue",
                    "options": {
                        "filters": [
                            {
                                "config": {"id": "isNull", "options": {}},
                                "fieldName": "Volume",
                            }
                        ],
                        "match": "any",
                        "type": "exclude",
                    },
                },
            ]

        # 2. Performance panels: Throughput, IOPS, Latency
        elif pid == 16:
            p["targets"] = [
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": 'sum by (pvc_namespace, pvc) (longhorn_volume_read_throughput{pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"})',
                    "legendFormat": "Read: {{pvc_namespace}}/{{pvc}}",
                    "range": True,
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": 'sum by (pvc_namespace, pvc) (longhorn_volume_write_throughput{pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"})',
                    "legendFormat": "Write: {{pvc_namespace}}/{{pvc}}",
                    "range": True,
                    "refId": "B",
                },
            ]
        elif pid == 17:
            p["targets"] = [
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": 'sum by (pvc_namespace, pvc) (longhorn_volume_read_iops{pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"})',
                    "legendFormat": "Read: {{pvc_namespace}}/{{pvc}}",
                    "range": True,
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": 'sum by (pvc_namespace, pvc) (longhorn_volume_write_iops{pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"})',
                    "legendFormat": "Write: {{pvc_namespace}}/{{pvc}}",
                    "range": True,
                    "refId": "B",
                },
            ]
        elif pid == 18:
            p["targets"] = [
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": 'avg by (pvc_namespace, pvc) (longhorn_volume_read_latency{pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"})',
                    "legendFormat": "Read: {{pvc_namespace}}/{{pvc}}",
                    "range": True,
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": 'avg by (pvc_namespace, pvc) (longhorn_volume_write_latency{pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"})',
                    "legendFormat": "Write: {{pvc_namespace}}/{{pvc}}",
                    "range": True,
                    "refId": "B",
                },
            ]

        # 3. Backup panels: 26, 27
        elif pid == 26:
            p["pluginVersion"] = "11.4.0"
            p["options"] = {
                "cellHeight": "sm",
                "footer": {
                    "countRows": True,
                    "fields": "",
                    "reducer": ["count"],
                    "show": True,
                },
                "showHeader": True,
                "sortBy": [{"desc": True, "displayName": "Last Backup Age"}],
            }
            p["fieldConfig"]["overrides"] = [
                {
                    "matcher": {"id": "byName", "options": "Last Backup Age"},
                    "properties": [
                        {"id": "unit", "value": "dtdurations"},
                        {
                            "id": "thresholds",
                            "value": {
                                "mode": "absolute",
                                "steps": [
                                    {"color": "green", "value": 0},
                                    {"color": "orange", "value": 93600},
                                    {"color": "red", "value": 172800},
                                ],
                            },
                        },
                        {
                            "id": "custom.cellOptions",
                            "value": {
                                "mode": "basic",
                                "type": "color-background",
                            },
                        },
                        {
                            "id": "mappings",
                            "value": [
                                {
                                    "options": {
                                        "-1": {
                                            "color": "semi-dark-red",
                                            "index": 0,
                                            "text": "Never",
                                        }
                                    },
                                    "type": "value",
                                }
                            ],
                        },
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Backup Size"},
                    "properties": [{"id": "unit", "value": "bytes"}],
                },
            ]
            p["targets"] = [
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": 'max by (pvc_namespace, pvc, volume) ((time() - (longhorn_volume_last_backup_at{pvc!="",pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"} > 0)) or ((0 * longhorn_volume_last_backup_at{pvc!="",pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"}) - 1))',
                    "format": "table",
                    "instant": True,
                    "refId": "age",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": '(sum by (pvc_namespace, pvc, volume) ((longhorn_backup_actual_size_bytes * on(volume) group_left(pvc, pvc_namespace) (max by(volume, pvc, pvc_namespace)(longhorn_volume_capacity_bytes) > bool 0)) and on(volume) longhorn_volume_last_backup_at{pvc!="",pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"})) or (0 * avg by (pvc_namespace, pvc, volume) (longhorn_volume_capacity_bytes{pvc!="",pvc_namespace=~"$namespace",pvc=~"$pvc",volume=~"$pv_name"}))',
                    "format": "table",
                    "instant": True,
                    "refId": "size",
                },
            ]
        elif pid == 27:
            p["pluginVersion"] = "11.4.0"
            p["options"] = {
                "cellHeight": "sm",
                "footer": {
                    "countRows": True,
                    "fields": "",
                    "reducer": ["count"],
                    "show": True,
                },
                "showHeader": True,
                "sortBy": [{"desc": False, "displayName": "Recurring Job"}],
            }
            p["fieldConfig"]["overrides"] = [
                {
                    "matcher": {"id": "byName", "options": "Failed Backups"},
                    "properties": [
                        {
                            "id": "thresholds",
                            "value": {
                                "mode": "absolute",
                                "steps": [
                                    {"color": "green", "value": 0},
                                    {"color": "red", "value": 1},
                                ],
                            },
                        },
                        {
                            "id": "custom.cellOptions",
                            "value": {
                                "mode": "basic",
                                "type": "color-background",
                            },
                        },
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Total Size"},
                    "properties": [{"id": "unit", "value": "bytes"}],
                },
            ]

        # 4. Rebuilding Replicas (WO Mode): Panel 34
        elif pid == 34:
            p["targets"] = [
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": 'sum(longhorn_engine_replica_mode{mode="WO"} == 1) or vector(0)',
                    "legendFormat": "Active Rebuilding Replicas",
                    "range": True,
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "editorMode": "code",
                    "expr": 'count by (volume) (longhorn_engine_replica_mode{mode="WO"} == 1)',
                    "legendFormat": "Rebuilding: {{volume}}",
                    "range": True,
                    "refId": "B",
                },
            ]

    # Write back updated JSON formatted properly
    doc["data"]["longhorn-dashboard.json"] = json.dumps(dash, indent=2, ensure_ascii=False) + "\n"

    # Save YAML
    class Dumper(yaml.SafeDumper):
        pass

    def str_representer(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    Dumper.add_representer(str, str_representer)

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        yaml.dump(doc, f, Dumper=Dumper, default_flow_style=False, sort_keys=False)

    print("Successfully updated longhorn-dashboard.yaml")


if __name__ == "__main__":
    update_dashboard()
