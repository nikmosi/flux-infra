# Backup of Kubernetes Node Data to /mnt/storage/nodes_backup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `/mnt/storage/nodes_backup` and perform a complete, verified backup of all surviving Kubernetes cluster data (live database SQL dumps, application PVC filesystems, system/k3s configs, and raw Longhorn block replicas) from nodes `note-nixos`, `note-acemagic`, and `note-dns`.

**Architecture:** A multi-layered backup strategy: (1) Live application-level dumps (`pg_dumpall` for PostgreSQL clusters `lab-postgres` and `immich-postgres`), (2) File-level archives of mounted CSI volumes (Forgejo, Vaultwarden, LLDAP, Homebox, Minecraft, etc.), (3) Host-level system/k3s configurations, and (4) Block-level `rsync` of raw Longhorn replicas (`/var/lib/longhorn/replicas/`) from all 3 nodes to `/mnt/storage/nodes_backup`.

**Tech Stack:** Bash, Python 3, `rsync`, `crictl`, `pg_dumpall`, `tar`, `zstd`, SSH.

**Spec:** User request: "Создай папку в /mnt/storage nodes_backup и сделай бекапп данных с нод. Переключением и тд займемся позднее. Используй superpowers"

## Global Constraints
- Target directory: `/mnt/storage/nodes_backup` on local host (`192.168.3.2`).
- Do not modify or stop any running containers on the nodes during backup (read-only operations / live dumps).
- Preserve all file permissions and ownerships (`tar -p`, `rsync -aHAX`).
- Verify every backup artifact with size checks and integrity checksums before marking tasks complete.

## Review Focus
- Check available disk space on `/mnt/storage` before and during each stage.
- Ensure SQL dumps are non-empty and syntactically valid PostgreSQL dumps.
- Ensure SQLite databases (Vaultwarden, Homebox) are copied consistently.
- Verify Longhorn replica directories are fully mirrored without corruption.

---

### Task 1: Initialize Backup Structure and Verify Host Storage
- [ ] Step 1: Create backup directory structure in `/mnt/storage/nodes_backup`
- [ ] Step 2: Verify directory existence, write permissions, and available disk space
- [ ] Step 3: Record initial metadata log (`backup_meta.json`) with cluster state and timestamp

---

### Task 2: Live Database Dumps (PostgreSQL Clusters)
- [ ] Step 1: Execute `pg_dumpall` on `immich-postgres-1` via `crictl exec` and stream compressed to storage
- [ ] Step 2: Verify `immich-postgres.sql.gz` size and gzip integrity (`gzip -t`)
- [ ] Step 3: Execute `pg_dumpall` on `lab-postgres-1` via `crictl exec` and stream compressed to storage
- [ ] Step 4: Verify `lab-postgres.sql.gz` size and gzip integrity (`gzip -t`)

---

### Task 3: Application Data File-Level Backup (Mounted Volumes)
- [ ] Step 1: Archive Vaultwarden data from `note-nixos`
- [ ] Step 2: Archive Forgejo git repos and config from `note-nixos`
- [ ] Step 3: Archive Homebox and LLDAP data from `note-acemagic` and `note-dns`
- [ ] Step 4: Archive Minecraft world and configs from `note-acemagic`
- [ ] Step 5: Verify all tarballs with `zstd -t` and verify non-zero contents

---

### Task 4: Node Configurations & k3s State Backup
- [ ] Step 1: Backup k3s agent state, tokens, and node keys from `note-nixos`
- [ ] Step 2: Backup k3s agent state and config from `note-acemagic`
- [ ] Step 3: Backup k3s agent state and config from `note-dns`
- [ ] Step 4: Verify config archives exist and are readable

---

### Task 5: Raw Longhorn Block Replicas Backup
- [ ] Step 1: Rsync Longhorn replicas from `note-nixos` (~1.7 GB)
- [ ] Step 2: Rsync Longhorn replicas from `note-acemagic` (~8.4 GB)
- [ ] Step 3: Rsync Longhorn replicas from `note-dns` (~29 GB)
- [ ] Step 4: Verify directory structures, disk space, and total file count against sources

---

### Task 6: Final Verification, Checksum Generation, and Summary Report
- [ ] Step 1: Generate SHA256 checksums for all archive files
- [ ] Step 2: Run verification checks on disk usage and integrity
- [ ] Step 3: Generate detailed recovery summary documentation
