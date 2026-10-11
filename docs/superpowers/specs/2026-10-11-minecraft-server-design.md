# Architecture Specification: Minecraft 1.20.1 Forge Server & Monitoring

## 1. Overview & Context

This document specifies the deployment of a dedicated modded Minecraft 1.20.1 server on Kubernetes via FluxCD GitOps in `my-cluster`. The cluster runs on k3s with Cilium (BGP LoadBalancer pool `10.10.0.0/24`), Longhorn CSI storage (`longhorn-low`), and Prometheus/Grafana (`kube-prometheus-stack`).

The server must run on the dedicated node `acemagic` (16 CPU cores, 32 GB RAM, NVMe storage).

## 2. Requirements & Intent

1. **Server Image & Version**:
   - Base image: `itzg/minecraft-server:latest`.
   - Engine: Forge 1.20.1 (`TYPE=FORGE`, `VERSION="1.20.1"`).
   - Java version: Automatically selected by `itzg/minecraft-server` (Java 17 for MC 1.20.1).
   - EULA accepted (`EULA=TRUE`).
   - Memory allocation: `MEMORY="10G"` JVM heap.
   - Resource requests: CPU `2000m`, Memory `8Gi`; limits: CPU `6000m`, Memory `12Gi`.
2. **Node Placement**:
   - Pinned to worker node `acemagic` via `nodeSelector: kubernetes.io/hostname: acemagic`.
3. **Storage**:
   - `PersistentVolumeClaim` 50Gi with storageClassName `longhorn-low` mounted at `/data`.
4. **Networking**:
   - Service of type `LoadBalancer` exposing port 25565 TCP (and optional UDP) via Cilium BGP pool (`10.10.0.0/24`).
5. **Monitoring (`itzg/mc-monitor` & Grafana)**:
   - Sidecar container: `itzg/mc-monitor:latest` running `export-for-prometheus` against `localhost:25565` exposing port `8080/metrics`.
   - Prometheus integration: `PodMonitor` CRD in `monitoring.coreos.com/v1` targeting the `mc-monitor` port `8080`.
   - Grafana dashboard: `ConfigMap` labeled `grafana_dashboard: "1"`, discovered by Grafana sidecar in any namespace.
6. **Modpack & Plugins Delivery**:
   - Source: `mods.7z` (~1.09 GB) containing 327 mods / 401 jar files for MC 1.20.1.
   - Filtration: 63 client-only mods (BadOptimizations, 3D Skin Layers, BHMenu, etc.) excluded using Packwiz `.pw.toml` `side = 'client'` metadata.
   - Server utilities ("Plugins"): Native Forge 1.20.1 equivalents added:
     - FTB Essentials (commands: `/home`, `/spawn`, `/tpa`, `/warp`, `/back`)
     - LuckPerms Forge (RBAC permissions & web editor)
     - Chunky Forge (chunk pre-generation)
     - Spark profiler (already present in `mods.7z`)
     - Open Parties and Claims (already present in `mods.7z`)
   - Preparation tool: `utils/prepare-minecraft-mods.py` to extract, filter, download extra utilities, and copy to the server.
7. **GitOps Integration**:
   - Manifests in `clusters/my-cluster/releases/apps/minecraft.yaml` and `clusters/my-cluster/releases/apps/minecraft-dashboard.yaml`.
   - Registered in `clusters/my-cluster/releases/apps/kustomization.yaml`.
   - Clean validation against repository tools (`kustomize build`).

## 3. Architecture & Components

```
+-------------------------------------------------------------+
|                      Node: acemagic                         |
|  +-------------------------------------------------------+  |
|  |                     Pod: minecraft-0                  |  |
|  |  +-------------------------------------------------+  |  |
|  |  | Container: itzg/minecraft-server (port 25565)   |  |  |
|  |  | Volume Mount: /data -> PVC (50Gi, longhorn-low)  |  |  |
|  |  +-------------------------------------------------+  |  |
|  |  +-------------------------------------------------+  |  |
|  |  | Sidecar: itzg/mc-monitor (port 8080)             |  |  |
|  |  | Scrapes localhost:25565 via Server List Ping    |  |  |
|  |  +-------------------------------------------------+  |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
```

## 4. Verification & Testing

- Manifests pass `kustomize build clusters/my-cluster/releases/apps`.
- Pod schedules onto node `acemagic`.
- `mc-monitor` successfully scrapes Minecraft server and Prometheus targets reflect the endpoint.
- Grafana automatically imports the Minecraft dashboard.
