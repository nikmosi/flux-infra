#!/usr/bin/env python3
"""Minecraft Forge 1.20.1 Mod Filtration and Preparation Utility.

Analyzes mods.7z, parses Packwiz metadata (.index/*.pw.toml) to identify and exclude
client-only mods (e.g. 3D Skin Layers, BadOptimizations, BHMenu), skips duplicate and
disabled files, downloads essential server utility mods (FTB Essentials, LuckPerms, Chunky),
and stages/uploads server-compatible mods to the target host/directory.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Optional Rich integration for pretty formatting
try:
    from rich.console import Console
    from rich.table import Table

    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None  # type: ignore[assignment]


# Default locations
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE = Path("/home/nik/git-repos/flux/mods.7z")
if not DEFAULT_ARCHIVE.is_file():
    fallback_archive = REPO_ROOT / "mods.7z"
    if fallback_archive.is_file():
        DEFAULT_ARCHIVE = fallback_archive

DEFAULT_EXTRACT_DIR = Path("/tmp/mc-server-mods")


@dataclass
class PackwizMod:
    """Metadata from a packwiz .pw.toml file."""

    slug: str
    name: str
    filename: str
    side: str
    version: str = ""
    download_url: str = ""


@dataclass
class ArchiveEntry:
    """An entry inside the 7z archive."""

    path: str
    filename: str
    size: int
    is_dir: bool


@dataclass
class UtilityMod:
    """Server utility mod to download/stage."""

    name: str
    purpose: str
    default_filename: str
    filename_pattern: str
    urls: list[str]


@dataclass
class FilterResult:
    """Results of mod classification and filtration."""

    total_index_mods: int
    client_mods_excluded: list[PackwizMod] = field(default_factory=list)
    server_mods_indexed: list[PackwizMod] = field(default_factory=list)
    unindexed_server_mods: list[ArchiveEntry] = field(default_factory=list)
    duplicate_files_skipped: list[str] = field(default_factory=list)
    total_server_mods_to_extract: list[ArchiveEntry] = field(default_factory=list)


# Essential Forge 1.20.1 server utilities
SERVER_UTILITIES: list[UtilityMod] = [
    UtilityMod(
        name="FTB Essentials Forge",
        purpose="Player & admin commands (/home, /spawn, /tpa, /warp, /back)",
        default_filename="ftb-essentials-forge-2001.2.2.jar",
        filename_pattern=r"^ftb-essentials-forge-.*\.jar$",
        urls=[
            # CurseForge direct download API (file 4896152 -> 2001.2.2)
            "https://www.curseforge.com/api/v1/mods/410811/files/4896152/download",
            # Fallback direct CurseForge CDN url from brief
            "https://edge.forgecdn.net/files/5436/275/ftb-essentials-forge-2001.2.2.jar",
            # Fallback newer 1.20.1 build (file 7609948 -> 2001.2.4)
            "https://www.curseforge.com/api/v1/mods/410811/files/7609948/download",
        ],
    ),
    UtilityMod(
        name="LuckPerms Forge",
        purpose="Permissions management & web editor (/lp)",
        default_filename="LuckPerms-Forge-5.4.102.jar",
        filename_pattern=r"^LuckPerms-Forge-.*\.jar$",
        urls=[
            # Official Modrinth build for Forge 1.20.1
            "https://cdn.modrinth.com/data/Vebnzrzj/versions/AudvOzqV/LuckPerms-Forge-5.4.102.jar",
            # Fallback direct Jenkins URL
            "https://download.luckperms.net/1572/forge/LuckPerms-Forge-5.4.156.jar",
        ],
    ),
    UtilityMod(
        name="Chunky Forge",
        purpose="World chunk pre-generation (/chunky start)",
        default_filename="Chunky-1.3.92.jar",
        filename_pattern=r"^Chunky-.*\.jar$",
        urls=[
            # Direct Modrinth CDN for exact Chunky 1.3.92 for Forge 1.20.1
            "https://cdn.modrinth.com/data/fALzjamp/versions/EUpM1fJU/Chunky-1.3.92.jar",
            # URL from brief
            "https://edge.forgecdn.net/files/4636/537/Chunky-1.3.92.jar",
            # Modrinth CDN fallback (Chunky 1.3.146)
            "https://cdn.modrinth.com/data/fALzjamp/versions/4FTDk9wv/Chunky-1.3.146.jar",
        ],
    ),
]

# Client-only mods present in archive that lack packwiz index entries
UNINDEXED_CLIENT_MODS: set[str] = {
    "citresewn-1.20.1-5.jar",
    "stop_rendering-forge-1.0.3.jar",
    "gpumemleakfix-1.20.1-1.8.jar",
    "farsight-1.20.1-5.1.jar",
    "biomemusic-1.20.1-3.5.jar",
    "clientcrafting-1.20.1-2.1.jar",
    "reset_controls_confirmation-forge-1.0.0-1.20.1.jar",
    "CrashAssistant-forge-1.19-1.20.1-1.11.10.jar",
    "ServerBrowser-1.20.1-FORGE-1.3.3.jar",
}


def check_7z_installed() -> str:
    """Verify 7z CLI availability."""
    for cmd in ["7z", "7zz"]:
        if shutil.which(cmd):
            return cmd
    raise RuntimeError("7z executable not found in PATH. Please install p7zip (7z) or 7zz.")


def list_archive_entries(seven_z: str, archive_path: Path) -> list[ArchiveEntry]:
    """Parse listing of 7z archive using `7z l -slt`."""
    cmd = [seven_z, "l", "-slt", str(archive_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    entries: list[ArchiveEntry] = []
    blocks = result.stdout.strip().split("\n\n")

    for block in blocks:
        data: dict[str, str] = {}
        for line in block.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()

        path = data.get("Path", "")
        if not path:
            continue

        size = int(data.get("Size", "0"))
        attrs = data.get("Attributes", "")
        is_dir = attrs.startswith("D") or data.get("Folder", "") == "+"
        filename = Path(path).name

        entries.append(
            ArchiveEntry(
                path=path,
                filename=filename,
                size=size,
                is_dir=is_dir,
            )
        )

    return entries


def parse_packwiz_index(seven_z: str, archive_path: Path) -> dict[str, PackwizMod]:
    """Extract and parse all mods/.index/*.pw.toml files from archive."""
    mods_by_filename: dict[str, PackwizMod] = {}

    with tempfile.TemporaryDirectory(prefix="pw_index_") as tmp_dir:
        cmd = [
            seven_z,
            "e",
            "-y",
            f"-o{tmp_dir}",
            str(archive_path),
            "mods/.index/*.pw.toml",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to extract .index from {archive_path}: {res.stderr}")

        for toml_path in Path(tmp_dir).glob("*.pw.toml"):
            slug = toml_path.name.replace(".pw.toml", "")
            try:
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)

                fn = data.get("filename")
                if not fn:
                    continue

                name = data.get("name", slug)
                side = (data.get("side") or "").strip().lower()
                version = data.get("x-prismlauncher-version-number", "")
                download_info = data.get("download", {})
                url = download_info.get("url", "")

                mod = PackwizMod(
                    slug=slug,
                    name=name,
                    filename=fn,
                    side=side,
                    version=version,
                    download_url=url,
                )
                mods_by_filename[fn] = mod
            except Exception as e:
                print(f"Warning: Failed to parse {toml_path.name}: {e}", file=sys.stderr)

    return mods_by_filename


def classify_archive_mods(
    archive_entries: list[ArchiveEntry],
    packwiz_mods: dict[str, PackwizMod],
) -> FilterResult:
    """Classify archive mods into client-only, server-compatible, duplicates, and unindexed."""
    result = FilterResult(total_index_mods=len(packwiz_mods))

    # Candidate mods: direct children of mods/ (excluding .index and .connector)
    mods_entries = [
        e
        for e in archive_entries
        if not e.is_dir
        and e.path.startswith("mods/")
        and not e.path.startswith("mods/.index")
        and not e.path.startswith("mods/.connector")
    ]

    for entry in mods_entries:
        fn = entry.filename

        # Skip duplicate and disabled files
        if fn.endswith(".duplicate") or fn.endswith(".disabled"):
            result.duplicate_files_skipped.append(entry.path)
            continue

        # Check if unindexed client mod
        if fn in UNINDEXED_CLIENT_MODS:
            result.client_mods_excluded.append(
                PackwizMod(
                    slug=fn.replace(".jar", ""),
                    name=fn.replace(".jar", ""),
                    filename=fn,
                    side="client",
                )
            )
            continue

        # Check if mapped by packwiz index
        if fn in packwiz_mods:
            mod_meta = packwiz_mods[fn]
            if mod_meta.side == "client":
                result.client_mods_excluded.append(mod_meta)
            else:
                result.server_mods_indexed.append(mod_meta)
                result.total_server_mods_to_extract.append(entry)
        else:
            # Unindexed file in mods/ (e.g. additional server mods or datapacks)
            result.unindexed_server_mods.append(entry)
            result.total_server_mods_to_extract.append(entry)

    return result


def download_utility(
    utility: UtilityMod,
    target_dir: Path,
    dry_run: bool = False,
) -> tuple[bool, str, Path | None]:
    """Download a utility mod trying fallback URLs in order, skipping if already present."""
    target_pattern = re.compile(utility.filename_pattern, re.IGNORECASE)

    # Check if matching jar already exists in target_dir
    if target_dir.is_dir():
        for existing in target_dir.glob("*.jar"):
            if target_pattern.match(existing.name) and existing.stat().st_size > 0:
                return True, f"Already present ({existing.name})", existing

    target_path = target_dir / utility.default_filename
    if dry_run:
        return True, f"Planned download -> {utility.default_filename}", target_path

    target_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }

    last_error = ""
    for url in utility.urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()

                # Infer final filename if redirected and matches jar
                final_url = resp.geturl()
                final_name = Path(urllib.parse.urlparse(final_url).path).name
                if final_name.endswith(".jar") and "download" not in final_name:
                    dest_file = target_dir / final_name
                else:
                    dest_file = target_path

                with open(dest_file, "wb") as f:
                    f.write(data)

                return (
                    True,
                    f"Downloaded from {url} ({len(data):,} bytes -> {dest_file.name})",
                    dest_file,
                )
        except Exception as e:
            last_error = str(e)
            continue

    return False, f"Failed all download attempts: {last_error}", None


def extract_server_mods(
    seven_z: str,
    archive_path: Path,
    target_dir: Path,
    entries_to_extract: list[ArchiveEntry],
    clean: bool = False,
) -> bool:
    """Extract server mods from 7z archive directly into target directory."""
    if clean and target_dir.exists():
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w", prefix="extract_list_", suffix=".txt", delete=False
    ) as list_file:
        for entry in entries_to_extract:
            list_file.write(f"{entry.path}\n")
        list_file_path = list_file.name

    try:
        # 7z e extracts all files into target_dir flatly without directory hierarchy
        cmd = [
            seven_z,
            "e",
            "-y",
            f"-o{target_dir}",
            str(archive_path),
            f"@{list_file_path}",
        ]
        start_time = time.time()
        res = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.time() - start_time

        if res.returncode != 0:
            print(f"Error during 7z extraction: {res.stderr}", file=sys.stderr)
            return False

        msg = (
            f"Extraction completed in {elapsed:.1f}s: "
            f"{len(entries_to_extract)} files extracted to {target_dir}"
        )
        print(msg)
        return True
    finally:
        if os.path.exists(list_file_path):
            os.remove(list_file_path)


def patch_mod_incompatibilities(target_dir: Path) -> None:
    """Fix upstream mod incompatibilities in staged jars."""
    create_jar = next(target_dir.glob("create-*.jar"), None)
    if create_jar:
        bad_files = {
            "data/create/recipes/blasting/silver_ingot_compat_galosphere.json",
            "data/create/recipes/smelting/silver_ingot_compat_galosphere.json",
            "data/create/advancements/recipes/misc/blasting/silver_ingot_compat_galosphere.json",
            "data/create/advancements/recipes/misc/smelting/silver_ingot_compat_galosphere.json",
        }
        temp_jar = create_jar.with_suffix(".tmp.jar")
        modified = False
        with zipfile.ZipFile(create_jar, "r") as zin, zipfile.ZipFile(temp_jar, "w") as zout:
            for item in zin.infolist():
                if item.filename in bad_files:
                    modified = True
                    continue
                zout.writestr(item, zin.read(item.filename))
        if modified:
            temp_jar.replace(create_jar)
            print("  [OK] Patched Create mod: removed incompatible galosphere silver recipes")
        elif temp_jar.exists():
            temp_jar.unlink()


def patch_connectivity_config(target_dir: Path) -> None:
    """Disable malformed traffic detection in Connectivity mod if config exists."""
    import json

    config_candidates = [
        target_dir / "connectivity.json",
        target_dir.parent / "config" / "connectivity.json",
        target_dir / "config" / "connectivity.json",
    ]
    for cfg in config_candidates:
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                malformed = data.get("malformedtraffic", {})
                changed = False
                if malformed.get("enabled") is not False:
                    malformed["enabled"] = False
                    changed = True
                whitelist = set(malformed.get("proxywhitelist", []))
                loopbacks = {"127.0.0.1", "::1", "0:0:0:0:0:0:0:1"}
                if not loopbacks.issubset(whitelist):
                    malformed["proxywhitelist"] = list(whitelist | loopbacks)
                    changed = True
                if changed:
                    data["malformedtraffic"] = malformed
                    cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    print(
                        f"  [OK] Patched {cfg.name}: disabled malformed traffic check"
                    )
            except Exception as e:
                print(f"  [WARN] Failed to patch {cfg}: {e}", file=sys.stderr)


def upload_via_rsync_or_scp(source_dir: Path, remote_dest: str, dry_run: bool = False) -> bool:
    """Upload staged mods to remote destination using rsync (with scp fallback)."""
    # remote_dest can be e.g. "192.168.3.5:/var/lib/minecraft-mods" or "acemagic:/data/mods"
    src = str(source_dir).rstrip("/") + "/"
    dest = remote_dest.rstrip("/") + "/"

    has_rsync = bool(shutil.which("rsync"))
    if has_rsync:
        cmd = ["rsync", "-avz", "--progress", src, dest]
    else:
        cmd = ["scp", "-r", f"{src}*", remote_dest]

    cmd_str = " ".join(cmd)
    if dry_run:
        print(f"[DRY-RUN] Upload command: {cmd_str}")
        return True

    print(f"Executing: {cmd_str}")
    start = time.time()
    res = subprocess.run(cmd)
    elapsed = time.time() - start

    if res.returncode == 0:
        print(f"Upload completed successfully in {elapsed:.1f}s.")
        return True
    else:
        print(f"Upload failed with exit code {res.returncode}.", file=sys.stderr)
        return False


def print_summary(
    archive_path: Path,
    target_dir: Path,
    filter_res: FilterResult,
    utilities: list[UtilityMod],
    dry_run: bool,
    verbose: bool = False,
    upload_dest: str | None = None,
) -> None:
    """Print detailed summary of filtration and preparation."""
    arch_size_mb = archive_path.stat().st_size / (1024 * 1024)

    total_server_mods = len(filter_res.total_server_mods_to_extract)
    total_excluded = len(filter_res.client_mods_excluded)
    total_duplicates = len(filter_res.duplicate_files_skipped)
    total_utilities = len(utilities)
    total_final = total_server_mods + total_utilities

    if HAS_RICH and console:
        table_summary = Table(
            title="Minecraft 1.20.1 Forge Server Mod Preparation",
            title_style="bold green",
        )
        table_summary.add_column("Category", style="cyan")
        table_summary.add_column("Count / Details", style="bold white")

        table_summary.add_row("Source Archive", f"{archive_path} ({arch_size_mb:.1f} MB)")
        table_summary.add_row("Target Directory", str(target_dir))
        table_summary.add_row("Packwiz Indexed Mods", str(filter_res.total_index_mods))
        table_summary.add_row(
            "[bold red]Client-Only Mods Excluded[/]",
            f"[bold red]{total_excluded}[/] (e.g. 3D Skin Layers, BadOptimizations, BHMenu)",
        )
        table_summary.add_row(
            "[bold yellow]Duplicates / Disabled Skipped[/]",
            f"[bold yellow]{total_duplicates}[/] (.duplicate files)",
        )
        indexed_n = len(filter_res.server_mods_indexed)
        unindexed_n = len(filter_res.unindexed_server_mods)
        table_summary.add_row(
            "[bold green]Server Mods from Archive[/]",
            f"[bold green]{total_server_mods}[/] ({indexed_n} indexed + {unindexed_n} unindexed)",
        )
        table_summary.add_row(
            "[bold cyan]Server Utility Mods Added[/]",
            f"[bold cyan]{total_utilities}[/] (FTB Essentials, LuckPerms, Chunky)",
        )
        table_summary.add_row(
            "[bold magenta]Total Server Mods Prepared[/]",
            f"[bold magenta]{total_final}[/] mods",
        )
        if upload_dest:
            table_summary.add_row("Upload Destination", upload_dest)

        console.print(table_summary)

        # Table of excluded client mods
        table_client = Table(
            title=f"Excluded Client-Only Mods ({total_excluded})",
            title_style="bold red",
        )
        table_client.add_column("#", justify="right", style="dim")
        table_client.add_column("Mod Name", style="bold yellow")
        table_client.add_column("Jar Filename", style="dim white")

        for idx, mod in enumerate(sorted(filter_res.client_mods_excluded, key=lambda m: m.name), 1):
            table_client.add_row(str(idx), mod.name, mod.filename)

        console.print(table_client)

        # Table of server utilities
        table_utils = Table(
            title=f"Essential Server Utilities ({total_utilities})",
            title_style="bold cyan",
        )
        table_utils.add_column("Utility Mod", style="bold green")
        table_utils.add_column("Purpose", style="white")
        table_utils.add_column("Target Filename", style="dim cyan")

        for u in utilities:
            table_utils.add_row(u.name, u.purpose, u.default_filename)

        console.print(table_utils)

        if verbose and filter_res.unindexed_server_mods:
            table_unindexed = Table(
                title=f"Unindexed Server Mods / Assets ({len(filter_res.unindexed_server_mods)})",
                title_style="bold blue",
            )
            table_unindexed.add_column("#", justify="right", style="dim")
            table_unindexed.add_column("Filename", style="white")
            table_unindexed.add_column("Size (KB)", justify="right", style="dim")
            for idx, entry in enumerate(filter_res.unindexed_server_mods, 1):
                table_unindexed.add_row(str(idx), entry.filename, f"{entry.size // 1024:,}")
            console.print(table_unindexed)

    else:
        # Standard ASCII output
        print("=" * 78)
        print(" MINECRAFT 1.20.1 FORGE SERVER MOD PREPARATION SUMMARY")
        print("=" * 78)
        print(f"Archive:               {archive_path} ({arch_size_mb:.1f} MB)")
        print(f"Target Directory:      {target_dir}")
        print(f"Packwiz Indexed Mods:  {filter_res.total_index_mods}")
        print(f"Client Mods Excluded:  {total_excluded}")
        print(f"Duplicates Skipped:    {total_duplicates}")
        idx_str = f"{len(filter_res.server_mods_indexed)} indexed"
        unidx_str = f"{len(filter_res.unindexed_server_mods)} unindexed"
        print(f"Server Mods (Archive): {total_server_mods} ({idx_str}, {unidx_str})")
        print(f"Server Utilities:      {total_utilities} (FTB Essentials, LuckPerms, Chunky)")
        print(f"Total Server Mods:     {total_final}")
        if upload_dest:
            print(f"Upload Target:         {upload_dest}")
        print("-" * 78)
        print(f"Excluded Client-Only Mods ({total_excluded}):")
        for idx, mod in enumerate(sorted(filter_res.client_mods_excluded, key=lambda m: m.name), 1):
            print(f"  {idx:2d}. {mod.name:<40} -> {mod.filename}")
        print("-" * 78)
        print(f"Server Utilities to Stage ({total_utilities}):")
        for u in utilities:
            print(f"  * {u.name:<25} ({u.default_filename}): {u.purpose}")
        print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Filter client-only mods from mods.7z and prepare Minecraft 1.20.1 Forge server mods."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=DEFAULT_ARCHIVE,
        help=f"Path to mods.7z archive (default: {DEFAULT_ARCHIVE})",
    )
    parser.add_argument(
        "--extract-dir",
        type=Path,
        default=DEFAULT_EXTRACT_DIR,
        help=f"Destination directory for server mods (default: {DEFAULT_EXTRACT_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary of excluded client mods and included server mods without writing.",
    )
    parser.add_argument(
        "--upload-ssh",
        type=str,
        default=None,
        metavar="HOST:DIR",
        help="Upload server mods via rsync/scp (e.g. 192.168.3.5:/var/lib/minecraft-mods).",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip downloading server utility mods (FTB Essentials, LuckPerms, Chunky).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean target extract directory before extracting.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed list of unindexed mods and extended file details.",
    )

    args = parser.parse_args()

    archive_path: Path = args.archive
    if not archive_path.is_file():
        print(f"Error: Archive not found at {archive_path}", file=sys.stderr)
        return 1

    try:
        seven_z = check_7z_installed()
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    # 1. Inspect archive entries
    archive_entries = list_archive_entries(seven_z, archive_path)

    # 2. Extract and parse packwiz index
    packwiz_mods = parse_packwiz_index(seven_z, archive_path)

    # 3. Classify mods
    filter_result = classify_archive_mods(archive_entries, packwiz_mods)

    # 4. Print summary
    print_summary(
        archive_path=archive_path,
        target_dir=args.extract_dir,
        filter_res=filter_result,
        utilities=SERVER_UTILITIES if not args.skip_download else [],
        dry_run=args.dry_run,
        verbose=args.verbose,
        upload_dest=args.upload_ssh,
    )

    if args.dry_run:
        print("\n[DRY-RUN] Execution completed. No files were written.")
        if args.upload_ssh:
            upload_via_rsync_or_scp(args.extract_dir, args.upload_ssh, dry_run=True)
        return 0

    # 5. Extract server mods
    n_mods = len(filter_result.total_server_mods_to_extract)
    print(f"\nExtracting {n_mods} server mods to {args.extract_dir}...")
    success = extract_server_mods(
        seven_z=seven_z,
        archive_path=archive_path,
        target_dir=args.extract_dir,
        entries_to_extract=filter_result.total_server_mods_to_extract,
        clean=args.clean,
    )
    if not success:
        return 2

    # 6. Download / stage server utility mods
    if not args.skip_download:
        print("\nDownloading and staging server utility mods...")
        for utility in SERVER_UTILITIES:
            ok, msg, _path = download_utility(utility, args.extract_dir, dry_run=False)
            status_tag = "[OK]" if ok else "[FAILED]"
            print(f"  {status_tag} {utility.name}: {msg}")
            if not ok:
                print(
                    f"Warning: Failed to download {utility.name}, manual placement needed.",
                    file=sys.stderr,
                )

    # 7. Apply mod compatibility patches
    patch_mod_incompatibilities(args.extract_dir)
    patch_connectivity_config(args.extract_dir)

    # 8. Upload if requested
    if args.upload_ssh:
        print(f"\nUploading server mods to {args.upload_ssh}...")
        ok = upload_via_rsync_or_scp(args.extract_dir, args.upload_ssh, dry_run=False)
        if not ok:
            return 3

    print(f"\nAll operations completed successfully! Server mods are ready in {args.extract_dir}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
