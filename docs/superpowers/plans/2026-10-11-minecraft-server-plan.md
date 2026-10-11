# Plan: Minecraft 1.20.1 Forge Server & Monitoring Deployment

Spec: docs/superpowers/specs/2026-10-11-minecraft-server-design.md

## Global Constraints

- Namespace: `apps`
- Node affinity / selector: `kubernetes.io/hostname: acemagic`
- Engine: Minecraft 1.20.1 Forge (`TYPE=FORGE`, `VERSION=1.20.1`)
- Environment: `EULA=TRUE`, `MEMORY=10G`, `JVM_XX_OPTS="-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC"`
- Server container image: `itzg/minecraft-server:latest`
- Sidecar container image: `itzg/mc-monitor:latest` with command `export-for-prometheus` and `-servers localhost:25565`
- Storage: 50Gi PersistentVolumeClaim with `storageClassName: longhorn-low` mounted at `/data`
- Service: `minecraft` type `LoadBalancer`, port 25565 TCP/UDP
- Monitoring: `PodMonitor` named `minecraft` in namespace `apps` scraping port `metrics` (8080)
- Dashboard: ConfigMap `minecraft-grafana-dashboard` in namespace `apps` with label `grafana_dashboard: "1"`
- Kustomization: Registered in `clusters/my-cluster/releases/apps/kustomization.yaml`

---

### Task 1: Create mod filtration and preparation utility (`utils/prepare-minecraft-mods.py`)
- **Files touched**: `utils/prepare-minecraft-mods.py`
- **Details**:
  - Script reads `mods.7z`.
  - Inspects `mods/.index/*.pw.toml` to identify mods where `side = 'client'` (63 mods identified).
  - Extracts only server-compatible and universal mods into target directory (`/tmp/mc-server-mods` or destination).
  - Skips `.duplicate` files.
  - Automatically downloads compatible 1.20.1 Forge server utility mods if not present:
    - FTB Essentials Forge 1.20.1 (commands)
    - LuckPerms Forge 1.20.1 (permissions)
    - Chunky Forge 1.20.1 (pregeneration)
  - Provides CLI options to inspect, extract, and upload/copy to server volume.
- **Verification**: Run `python3 utils/prepare-minecraft-mods.py --dry-run` and verify count of server mods, excluded client mods, and downloaded utilities.

---

### Task 2: Create Grafana Dashboard ConfigMap (`clusters/my-cluster/releases/apps/minecraft-dashboard.yaml`)
- **Files touched**: `clusters/my-cluster/releases/apps/minecraft-dashboard.yaml`
- **Details**:
  - Create a ConfigMap named `minecraft-grafana-dashboard` in namespace `apps`.
  - Label: `grafana_dashboard: "1"`.
  - Content: JSON dashboard sourced from `itzg/mc-monitor` Prometheus dashboard with panels:
    - Server Health / Status (`minecraft_status_healthy`)
    - Players Online (`minecraft_status_players_online_count` & `minecraft_status_players_max_count`)
    - Response Time (`minecraft_status_response_time_seconds`)
- **Verification**: Verify YAML syntax and confirm `grafana_dashboard: "1"` label matches Grafana sidecar search criteria.

---

### Task 3: Create Minecraft Kubernetes Manifests (`clusters/my-cluster/releases/apps/minecraft.yaml`)
- **Files touched**: `clusters/my-cluster/releases/apps/minecraft.yaml`
- **Details**:
  - Create `PersistentVolumeClaim` named `minecraft-data` (50Gi, `longhorn-low`, `ReadWriteOnce`).
  - Create `StatefulSet` named `minecraft` (1 replica):
    - `nodeSelector`: `kubernetes.io/hostname: acemagic`
    - Main container `minecraft` (`itzg/minecraft-server:latest`):
      - Ports: 25565/TCP, 25565/UDP
      - VolumeMount: `minecraft-data` -> `/data`
      - Env: `EULA="TRUE"`, `TYPE="FORGE"`, `VERSION="1.20.1"`, `MEMORY="10G"`, `MOTD="Modded Minecraft Server"`
      - Resources: requests: CPU `2000m`, Memory `8Gi`; limits: CPU `6000m`, Memory `12Gi`
      - Startup/Liveness/Readiness probes using `mc-monitor status` / `mc-health`
    - Sidecar container `mc-monitor` (`itzg/mc-monitor:latest`):
      - Args: `export-for-prometheus`, `-servers`, `localhost:25565`, `-port`, `8080`
      - Ports: 8080/TCP named `metrics`
      - Resources: requests: CPU `20m`, Memory `32Mi`; limits: CPU `100m`, Memory `128Mi`
  - Create `Service` named `minecraft`:
    - `type: LoadBalancer`
    - Ports: 25565 TCP, 25565 UDP
  - Create `PodMonitor` named `minecraft`:
    - Scrapes port `metrics` every 15s.
- **Verification**: Validate manifests with `kubectl dry-run` or kubeconform.

---

### Task 4: Integrate into Flux Kustomization and Validate
- **Files touched**: `clusters/my-cluster/releases/apps/kustomization.yaml`
- **Details**:
  - Add `minecraft.yaml` and `minecraft-dashboard.yaml` to `resources:` list in `clusters/my-cluster/releases/apps/kustomization.yaml`.
  - Run `kustomize build clusters/my-cluster/releases/apps` to ensure no syntax errors, duplication, or invalid YAML.
- **Verification**: `kustomize build clusters/my-cluster/releases/apps > /dev/null` succeeds with exit code 0.

---

### Task 5: Seed Server Mods & Verify Deployment
- **Files touched**: Target volume / cluster deployment
- **Details**:
  - Apply the manifests or let Flux sync.
  - Run `prepare-minecraft-mods.py` to populate `/data/mods` on `acemagic`.
  - Confirm Pod schedules to `acemagic` and starts container cleanly.
  - Check `mc-monitor` metrics endpoint and Grafana dashboard discovery.
- **Verification**: `kubectl get pod -n apps -l app.kubernetes.io/name=minecraft -o wide` shows Running on `acemagic`.
