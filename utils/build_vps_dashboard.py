#!/usr/bin/env python3
"""
Build the Grafana dashboard ConfigMap for External VPS & 3x-ui.
"""
import json
import os
import yaml

PROMETHEUS_DS = {"type": "prometheus", "uid": "prometheus"}
LOKI_DS = {"type": "loki", "uid": "loki"}


def build_dashboard():
    dashboard = {
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                    "enable": True,
                    "hide": True,
                    "name": "Annotations & Alerts",
                    "type": "dashboard",
                }
            ]
        },
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            # Row 1: Header / Quick Health
            {
                "gridPos": {"h": 4, "w": 3, "x": 0, "y": 0},
                "id": 1,
                "title": "VPS Status",
                "type": "stat",
                "datasource": PROMETHEUS_DS,
                "options": {
                    "colorMode": "background",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                },
                "fieldConfig": {
                    "defaults": {
                        "mappings": [
                            {
                                "options": {
                                    "0": {"color": "red", "index": 0, "text": "OFFLINE"},
                                    "1": {"color": "green", "index": 1, "text": "ONLINE"},
                                },
                                "type": "value",
                            }
                        ],
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}],
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'up{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "instant": True,
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 3, "x": 3, "y": 0},
                "id": 2,
                "title": "3x-ui Service",
                "type": "stat",
                "datasource": PROMETHEUS_DS,
                "options": {
                    "colorMode": "background",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                },
                "fieldConfig": {
                    "defaults": {
                        "mappings": [
                            {
                                "options": {
                                    "0": {"color": "red", "index": 0, "text": "DOWN"},
                                    "1": {"color": "green", "index": 1, "text": "ACTIVE"},
                                },
                                "type": "value",
                            }
                        ],
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}],
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_systemd_unit_state{job="prometheus.scrape.node_exporter", instance=~"$instance", name="x-ui.service", state="active"}',
                        "instant": True,
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 3, "x": 6, "y": 0},
                "id": 3,
                "title": "Uptime",
                "type": "stat",
                "datasource": PROMETHEUS_DS,
                "options": {
                    "colorMode": "value",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                },
                "fieldConfig": {
                    "defaults": {
                        "unit": "s",
                        "color": {"mode": "palette-classic"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'time() - node_boot_time_seconds{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "instant": True,
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 3, "x": 9, "y": 0},
                "id": 4,
                "title": "CPU Usage",
                "type": "stat",
                "datasource": PROMETHEUS_DS,
                "options": {
                    "colorMode": "value",
                    "graphMode": "area",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                },
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "min": 0,
                        "max": 100,
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "#EAB839", "value": 70},
                                {"color": "red", "value": 85},
                            ],
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": '100 - (avg by (instance) (rate(node_cpu_seconds_total{job="prometheus.scrape.node_exporter", instance=~"$instance", mode="idle"}[5m])) * 100)',
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 4, "x": 12, "y": 0},
                "id": 5,
                "title": "RAM Usage",
                "type": "stat",
                "datasource": PROMETHEUS_DS,
                "options": {
                    "colorMode": "value",
                    "graphMode": "area",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                },
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "min": 0,
                        "max": 100,
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "#EAB839", "value": 75},
                                {"color": "red", "value": 90},
                            ],
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": '((node_memory_MemTotal_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes) * 100',
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 4, "x": 16, "y": 0},
                "id": 6,
                "title": "Root Disk Usage",
                "type": "stat",
                "datasource": PROMETHEUS_DS,
                "options": {
                    "colorMode": "value",
                    "graphMode": "area",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                },
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "min": 0,
                        "max": 100,
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "#EAB839", "value": 75},
                                {"color": "red", "value": 85},
                            ],
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": '(1 - (node_filesystem_avail_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance", mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100',
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 4, "x": 20, "y": 0},
                "id": 7,
                "title": "Active Conntrack",
                "type": "stat",
                "datasource": PROMETHEUS_DS,
                "options": {
                    "colorMode": "value",
                    "graphMode": "area",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                },
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "color": {"mode": "palette-classic"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_nf_conntrack_entries{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "refId": "A",
                    }
                ],
            },

            # Row 2: VPN & Network Traffic
            {
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 4},
                "id": 8,
                "title": "VPN & Network Traffic",
                "type": "row",
            },
            {
                "gridPos": {"h": 8, "w": 14, "x": 0, "y": 5},
                "id": 9,
                "title": "Network Bandwidth ($interface)",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "bps",
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "smooth",
                            "lineWidth": 2,
                            "fillOpacity": 15,
                        },
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Receive (Ingress)"},
                            "properties": [{"id": "color", "value": {"fixedColor": "#56A64B", "mode": "fixed"}}],
                        },
                        {
                            "matcher": {"id": "byName", "options": "Transmit (Egress)"},
                            "properties": [{"id": "color", "value": {"fixedColor": "#3274D9", "mode": "fixed"}}],
                        },
                    ],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_receive_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[1m]) * 8',
                        "legendFormat": "Receive (Ingress)",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_transmit_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[1m]) * 8',
                        "legendFormat": "Transmit (Egress)",
                        "refId": "B",
                    },
                ],
            },
            {
                "gridPos": {"h": 8, "w": 4, "x": 14, "y": 5},
                "id": 10,
                "title": "Traffic Volume ($__range)",
                "type": "stat",
                "datasource": PROMETHEUS_DS,
                "options": {
                    "colorMode": "value",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                },
                "fieldConfig": {
                    "defaults": {
                        "unit": "bytes",
                        "color": {"mode": "palette-classic"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'increase(node_network_receive_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[$__range])',
                        "legendFormat": "Ingress Volume",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'increase(node_network_transmit_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[$__range])',
                        "legendFormat": "Egress Volume",
                        "refId": "B",
                    },
                ],
            },
            {
                "gridPos": {"h": 8, "w": 6, "x": 18, "y": 5},
                "id": 11,
                "title": "Network Drops & Errors ($interface)",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "pps",
                        "custom": {"drawStyle": "line", "lineWidth": 2},
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_receive_drop_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[1m])',
                        "legendFormat": "RX Drops",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_transmit_drop_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[1m])',
                        "legendFormat": "TX Drops",
                        "refId": "B",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_receive_errs_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[1m])',
                        "legendFormat": "RX Errors",
                        "refId": "C",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_transmit_errs_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[1m])',
                        "legendFormat": "TX Errors",
                        "refId": "D",
                    },
                ],
            },

            # Row 3: Host Internals & System Resources
            {
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 13},
                "id": 12,
                "title": "Host Internals & System Resources",
                "type": "row",
            },
            {
                "gridPos": {"h": 7, "w": 8, "x": 0, "y": 14},
                "id": 13,
                "title": "CPU Breakdown by Mode",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "smooth",
                            "lineWidth": 1,
                            "fillOpacity": 40,
                            "stacking": {"group": "A", "mode": "normal"},
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'sum by (mode) (rate(node_cpu_seconds_total{job="prometheus.scrape.node_exporter", instance=~"$instance"}[5m]))',
                        "legendFormat": "{{mode}}",
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 7, "w": 8, "x": 8, "y": 14},
                "id": 14,
                "title": "Memory Breakdown",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "bytes",
                        "custom": {
                            "drawStyle": "line",
                            "lineWidth": 1,
                            "fillOpacity": 30,
                            "stacking": {"group": "A", "mode": "normal"},
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_memory_MemTotal_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} - node_memory_MemAvailable_bytes',
                        "legendFormat": "Used",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_memory_Buffers_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "Buffers",
                        "refId": "B",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_memory_Cached_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "Cached",
                        "refId": "C",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_memory_MemFree_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "Free",
                        "refId": "D",
                    },
                ],
            },
            {
                "gridPos": {"h": 7, "w": 8, "x": 16, "y": 14},
                "id": 15,
                "title": "Disk I/O Rate",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "Bps",
                        "custom": {"drawStyle": "line", "lineWidth": 2},
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_disk_read_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance"}[1m])',
                        "legendFormat": "Read",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_disk_written_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance"}[1m])',
                        "legendFormat": "Write",
                        "refId": "B",
                    },
                ],
            },

            # Row 4: Connection Stack & Security
            {
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 21},
                "id": 16,
                "title": "Connection Stack & Security",
                "type": "row",
            },
            {
                "gridPos": {"h": 6, "w": 12, "x": 0, "y": 22},
                "id": 17,
                "title": "TCP Sockets State",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "custom": {"drawStyle": "line", "lineWidth": 2},
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_sockstat_TCP_alloc{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "Allocated",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_sockstat_TCP_inuse{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "In Use",
                        "refId": "B",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_sockstat_TCP_tw{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "Time Wait",
                        "refId": "C",
                    },
                ],
            },
            {
                "gridPos": {"h": 6, "w": 12, "x": 12, "y": 22},
                "id": 18,
                "title": "Conntrack Table Saturation",
                "type": "gauge",
                "datasource": PROMETHEUS_DS,
                "options": {
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "showThresholdLabels": False,
                    "showThresholdMarkers": True,
                },
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "min": 0,
                        "max": 100,
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "#EAB839", "value": 70},
                                {"color": "red", "value": 85},
                            ],
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": '(node_nf_conntrack_entries{job="prometheus.scrape.node_exporter", instance=~"$instance"} / node_nf_conntrack_entries_limit{job="prometheus.scrape.node_exporter", instance=~"$instance"}) * 100',
                        "refId": "A",
                    }
                ],
            },

            # Row 5: Loki Live Logs Stream
            {
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 28},
                "id": 19,
                "title": "Loki Live Logs Stream",
                "type": "row",
            },
            {
                "gridPos": {"h": 5, "w": 24, "x": 0, "y": 29},
                "id": 20,
                "title": "Log Volume by Level",
                "type": "barchart",
                "datasource": LOKI_DS,
                "options": {
                    "stacking": "normal",
                    "xTickLabelRotation": 0,
                },
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "custom": {"fillOpacity": 80},
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "error"},
                            "properties": [{"id": "color", "value": {"fixedColor": "red", "mode": "fixed"}}],
                        },
                        {
                            "matcher": {"id": "byName", "options": "warn"},
                            "properties": [{"id": "color", "value": {"fixedColor": "#EAB839", "mode": "fixed"}}],
                        },
                        {
                            "matcher": {"id": "byName", "options": "info"},
                            "properties": [{"id": "color", "value": {"fixedColor": "#56A64B", "mode": "fixed"}}],
                        },
                    ],
                },
                "targets": [
                    {
                        "datasource": LOKI_DS,
                        "expr": 'sum by (detected_level) (count_over_time({job="systemd-journal", instance=~"$instance"}[$__interval]))',
                        "legendFormat": "{{detected_level}}",
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 14, "w": 24, "x": 0, "y": 34},
                "id": 21,
                "title": "Live Systemd & 3x-ui Logs",
                "type": "logs",
                "datasource": LOKI_DS,
                "options": {
                    "showLabels": False,
                    "wrapLogMessage": True,
                    "enableLogDetails": True,
                    "sortOrder": "Descending",
                    "dedupStrategy": "none",
                },
                "targets": [
                    {
                        "datasource": LOKI_DS,
                        "expr": '{job="systemd-journal", instance=~"$instance"} |~ "(?i)$log_search"',
                        "refId": "A",
                    }
                ],
            },
        ],
        "refresh": "10s",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["vps", "vpn", "3x-ui", "external"],
        "templating": {
            "list": [
                {
                    "current": {"selected": True, "text": "vpn-timeweb", "value": "vpn-timeweb"},
                    "datasource": PROMETHEUS_DS,
                    "definition": 'label_values(node_uname_info{job="prometheus.scrape.node_exporter"}, instance)',
                    "hide": 0,
                    "includeAll": False,
                    "label": "VPS Instance",
                    "multi": False,
                    "name": "instance",
                    "options": [],
                    "query": {
                        "query": 'label_values(node_uname_info{job="prometheus.scrape.node_exporter"}, instance)',
                        "refId": "StandardVariableQuery",
                    },
                    "refresh": 1,
                    "regex": "",
                    "skipUrlSync": False,
                    "sort": 1,
                    "type": "query",
                },
                {
                    "current": {"selected": True, "text": "eth0", "value": "eth0"},
                    "datasource": PROMETHEUS_DS,
                    "definition": 'label_values(node_network_receive_bytes_total{instance=~"$instance"}, device)',
                    "hide": 0,
                    "includeAll": False,
                    "label": "Interface",
                    "multi": False,
                    "name": "interface",
                    "options": [],
                    "query": {
                        "query": 'label_values(node_network_receive_bytes_total{instance=~"$instance"}, device)',
                        "refId": "StandardVariableQuery",
                    },
                    "refresh": 2,
                    "regex": "/^(eth.*|ens.*)$/",
                    "skipUrlSync": False,
                    "sort": 1,
                    "type": "query",
                },
                {
                    "current": {"selected": False, "text": "", "value": ""},
                    "hide": 0,
                    "label": "Log Search",
                    "name": "log_search",
                    "options": [],
                    "query": "",
                    "skipUrlSync": False,
                    "type": "textbox",
                },
            ]
        },
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "External VPS & 3x-ui Monitoring",
        "uid": "external-vps-3x-ui",
        "version": 1,
        "weekStart": "",
    }
    return dashboard


def str_presenter(dumper, data):
    if len(data.splitlines()) > 1:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


yaml.add_representer(str, str_presenter)
yaml.representer.SafeRepresenter.add_representer(str, str_presenter)


def main():
    dashboard = build_dashboard()
    dashboard_json = json.dumps(dashboard, indent=2, ensure_ascii=False)

    manifest = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "vps-nodes-dashboard",
            "namespace": "monitoring",
            "labels": {"grafana_dashboard": "1"},
            "annotations": {"kustomize.toolkit.fluxcd.io/substitute": "disabled"},
        },
        "data": {"vps-nodes-dashboard.json": dashboard_json},
    }

    target_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "clusters",
        "my-cluster",
        "releases",
        "apps",
        "vps-nodes-dashboard.yaml",
    )

    with open(target_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        yaml.dump(manifest, f, allow_unicode=True, sort_keys=False, width=1000)

    print(f"Generated {target_path} successfully.")


if __name__ == "__main__":
    main()
