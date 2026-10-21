#!/usr/bin/env python3
"""
Build the Grafana dashboard ConfigMap for External VPS & 3x-ui.
"""
import json
import os
from typing import Any

import yaml

PROMETHEUS_DS = {"type": "prometheus", "uid": "prometheus"}
LOKI_DS = {"type": "loki", "uid": "loki"}


def build_dashboard() -> dict[str, Any]:
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
            # Row 1: Header / Quick Health (y: 0, h: 4, 8 stat cards of w: 3 = 24)
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
                        "noValue": "OFFLINE",
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
                        "noValue": "NOT INSTALLED",
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
                        "expr": '100 - (avg by (instance) (rate(node_cpu_seconds_total{job="prometheus.scrape.node_exporter", instance=~"$instance", mode="idle"}[$__rate_interval])) * 100)',
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 3, "x": 12, "y": 0},
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
                        "expr": '((node_memory_MemTotal_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} - node_memory_MemAvailable_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"}) / node_memory_MemTotal_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"}) * 100',
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 3, "x": 15, "y": 0},
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
                        "expr": '(1 - (node_filesystem_avail_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance", mountpoint="/"} / node_filesystem_size_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance", mountpoint="/"})) * 100',
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 3, "x": 18, "y": 0},
                "id": 7,
                "title": "Load Average",
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
                        "expr": 'node_load1{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "1m",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_load5{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "5m",
                        "refId": "B",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_load15{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "15m",
                        "refId": "C",
                    },
                ],
            },
            {
                "gridPos": {"h": 4, "w": 3, "x": 21, "y": 0},
                "id": 8,
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

            # Row 2: VPN & Network Traffic (y: 4..13)
            {
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 4},
                "id": 9,
                "title": "VPN & Network Traffic",
                "type": "row",
            },
            {
                "gridPos": {"h": 8, "w": 14, "x": 0, "y": 5},
                "id": 10,
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
                            "properties": [
                                {"id": "color", "value": {"fixedColor": "#3274D9", "mode": "fixed"}},
                                {"id": "custom.transform", "value": "negative-Y"},
                            ],
                        },
                    ],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_receive_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[$__rate_interval]) * 8',
                        "legendFormat": "Receive (Ingress)",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_transmit_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[$__rate_interval]) * 8',
                        "legendFormat": "Transmit (Egress)",
                        "refId": "B",
                    },
                ],
            },
            {
                "gridPos": {"h": 8, "w": 4, "x": 14, "y": 5},
                "id": 11,
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
                "id": 12,
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
                        "expr": 'rate(node_network_receive_drop_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[$__rate_interval])',
                        "legendFormat": "RX Drops",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_transmit_drop_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[$__rate_interval])',
                        "legendFormat": "TX Drops",
                        "refId": "B",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_receive_errs_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[$__rate_interval])',
                        "legendFormat": "RX Errors",
                        "refId": "C",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'rate(node_network_transmit_errs_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[$__rate_interval])',
                        "legendFormat": "TX Errors",
                        "refId": "D",
                    },
                ],
            },

            # Row 3: Host Internals & System Resources (y: 13..21)
            {
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 13},
                "id": 13,
                "title": "Host Internals & System Resources",
                "type": "row",
            },
            {
                "gridPos": {"h": 7, "w": 8, "x": 0, "y": 14},
                "id": 14,
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
                        "expr": 'sum by (mode) (rate(node_cpu_seconds_total{job="prometheus.scrape.node_exporter", instance=~"$instance"}[$__rate_interval]))',
                        "legendFormat": "{{mode}}",
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 7, "w": 8, "x": 8, "y": 14},
                "id": 15,
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
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Swap Used"},
                            "properties": [
                                {"id": "custom.stacking", "value": {"group": "B", "mode": "none"}},
                                {"id": "custom.lineStyle", "value": {"dash": [4, 4]}},
                                {"id": "color", "value": {"fixedColor": "#E24D42", "mode": "fixed"}},
                            ],
                        }
                    ],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_memory_MemTotal_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} - node_memory_MemFree_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} - node_memory_Buffers_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} - node_memory_Cached_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} - node_memory_SReclaimable_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
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
                        "expr": 'node_memory_Cached_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} + node_memory_SReclaimable_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "Cached",
                        "refId": "C",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_memory_MemFree_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "Free",
                        "refId": "D",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_memory_SwapTotal_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} - node_memory_SwapFree_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"}',
                        "legendFormat": "Swap Used",
                        "refId": "E",
                    },
                ],
            },
            {
                "gridPos": {"h": 7, "w": 8, "x": 16, "y": 14},
                "id": 16,
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
                        "expr": 'sum by (device) (rate(node_disk_read_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"vd[a-z]|sd[a-z]|nvme[0-9]n[0-9]|xvd[a-z]"}[$__rate_interval]))',
                        "legendFormat": "{{device}} Read",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'sum by (device) (rate(node_disk_written_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"vd[a-z]|sd[a-z]|nvme[0-9]n[0-9]|xvd[a-z]"}[$__rate_interval]))',
                        "legendFormat": "{{device}} Write",
                        "refId": "B",
                    },
                ],
            },

            # Row 4: Connection Stack & Security (y: 21..29)
            {
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 21},
                "id": 17,
                "title": "Connection Stack & Security",
                "type": "row",
            },
            {
                "gridPos": {"h": 7, "w": 8, "x": 0, "y": 22},
                "id": 18,
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
                "gridPos": {"h": 7, "w": 8, "x": 8, "y": 22},
                "id": 19,
                "title": "TCP Retransmission Rate (%)",
                "description": "Percentage of retransmitted TCP packets. Elevated retransmissions (>1-2%) indicate packet loss or network degradation directly impacting VPN tunnel quality.",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "custom": {"drawStyle": "line", "lineWidth": 2},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "#EAB839", "value": 1.0},
                                {"color": "red", "value": 3.0},
                            ],
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": '(rate(node_netstat_Tcp_RetransSegs{job="prometheus.scrape.node_exporter", instance=~"$instance"}[$__rate_interval]) / (rate(node_netstat_Tcp_OutSegs{job="prometheus.scrape.node_exporter", instance=~"$instance"}[$__rate_interval]) + 0.001)) * 100',
                        "legendFormat": "TCP Retransmit %",
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 7, "w": 8, "x": 16, "y": 22},
                "id": 20,
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

            # Row 5: Docker & Containers (cAdvisor) (y: 29..42, symmetric 3x3 layout)
            {
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 29},
                "id": 21,
                "title": "Docker & Containers (cAdvisor)",
                "type": "row",
            },
            {
                "gridPos": {"h": 4, "w": 8, "x": 0, "y": 30},
                "id": 22,
                "title": "Docker Daemon",
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
                        "noValue": "NOT INSTALLED",
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
                            "steps": [{"color": "gray", "value": None}, {"color": "green", "value": 1}],
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'node_systemd_unit_state{job="prometheus.scrape.node_exporter", instance=~"$instance", name="docker.service", state="active"}',
                        "instant": True,
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 8, "x": 8, "y": 30},
                "id": 23,
                "title": "cAdvisor Agent",
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
                        "noValue": "NOT INSTALLED",
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
                            "steps": [{"color": "gray", "value": None}, {"color": "green", "value": 1}],
                        },
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'up{job="prometheus.scrape.cadvisor", instance=~"$instance"}',
                        "instant": True,
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 4, "w": 8, "x": 16, "y": 30},
                "id": 24,
                "title": "Running Containers",
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
                        "unit": "short",
                        "color": {"mode": "palette-classic"},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'count(count by (name) (container_last_seen{job="prometheus.scrape.cadvisor", instance=~"$instance", name=~"$container", name!=""})) or vector(0)',
                        "instant": True,
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 8, "w": 8, "x": 0, "y": 34},
                "id": 25,
                "title": "Container CPU Usage",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "lineWidth": 2},
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'sum by (name) (rate(container_cpu_usage_seconds_total{job="prometheus.scrape.cadvisor", instance=~"$instance", name=~"$container", name!=""}[$__rate_interval])) * 100',
                        "legendFormat": "{{name}}",
                        "refId": "A",
                    }
                ],
            },
            {
                "gridPos": {"h": 8, "w": 8, "x": 8, "y": 34},
                "id": 26,
                "title": "Container Memory Usage",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "bytes",
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "lineWidth": 2},
                    },
                    "overrides": [],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'sum by (name) (container_memory_working_set_bytes{job="prometheus.scrape.cadvisor", instance=~"$instance", name=~"$container", name!=""})',
                        "legendFormat": "{{name}} (Working Set)",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'sum by (name) (container_memory_usage_bytes{job="prometheus.scrape.cadvisor", instance=~"$instance", name=~"$container", name!=""})',
                        "legendFormat": "{{name}} (Total)",
                        "refId": "B",
                    },
                ],
            },
            {
                "gridPos": {"h": 8, "w": 8, "x": 16, "y": 34},
                "id": 27,
                "title": "Container Network Throughput",
                "type": "timeseries",
                "datasource": PROMETHEUS_DS,
                "fieldConfig": {
                    "defaults": {
                        "unit": "bps",
                        "custom": {"drawStyle": "line", "lineInterpolation": "smooth", "lineWidth": 2},
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byRegexp", "options": ".*\\(TX\\).*"},
                            "properties": [
                                {"id": "custom.transform", "value": "negative-Y"},
                            ],
                        }
                    ],
                },
                "targets": [
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'sum by (name) (rate(container_network_receive_bytes_total{job="prometheus.scrape.cadvisor", instance=~"$instance", name=~"$container", name!="", interface!="lo"}[$__rate_interval])) * 8',
                        "legendFormat": "{{name}} (RX)",
                        "refId": "A",
                    },
                    {
                        "datasource": PROMETHEUS_DS,
                        "expr": 'sum by (name) (rate(container_network_transmit_bytes_total{job="prometheus.scrape.cadvisor", instance=~"$instance", name=~"$container", name!="", interface!="lo"}[$__rate_interval])) * 8',
                        "legendFormat": "{{name}} (TX)",
                        "refId": "B",
                    },
                ],
            },

            # Row 6: Loki Live Logs Stream (y: 42..62)
            {
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 42},
                "id": 28,
                "title": "Loki Live Logs Stream",
                "type": "row",
            },
            {
                "gridPos": {"h": 5, "w": 24, "x": 0, "y": 43},
                "id": 29,
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
                "gridPos": {"h": 14, "w": 24, "x": 0, "y": 48},
                "id": 30,
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
        "tags": ["vps", "vpn", "3x-ui", "external", "docker"],
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
                    "definition": 'label_values(node_network_receive_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance"}, device)',
                    "hide": 0,
                    "includeAll": False,
                    "label": "Interface",
                    "multi": False,
                    "name": "interface",
                    "options": [],
                    "query": {
                        "query": 'label_values(node_network_receive_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance"}, device)',
                        "refId": "StandardVariableQuery",
                    },
                    "refresh": 2,
                    "regex": "/^(eth.*|ens.*|enp.*|eno.*)$/",
                    "skipUrlSync": False,
                    "sort": 1,
                    "type": "query",
                },
                {
                    "current": {"selected": True, "text": "All", "value": "$__all"},
                    "datasource": PROMETHEUS_DS,
                    "definition": 'label_values(container_last_seen{job="prometheus.scrape.cadvisor", instance=~"$instance", name!=""}, name)',
                    "hide": 0,
                    "includeAll": True,
                    "allValue": ".*",
                    "label": "Container",
                    "multi": True,
                    "name": "container",
                    "options": [],
                    "query": {
                        "query": 'label_values(container_last_seen{job="prometheus.scrape.cadvisor", instance=~"$instance", name!=""}, name)',
                        "refId": "StandardVariableQuery",
                    },
                    "refresh": 2,
                    "regex": "",
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


def str_presenter(dumper: Any, data: str) -> Any:
    if len(data.splitlines()) > 1:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


yaml.add_representer(str, str_presenter)
yaml.representer.SafeRepresenter.add_representer(str, str_presenter)


def main() -> None:
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
