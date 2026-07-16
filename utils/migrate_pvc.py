#!/usr/bin/env python3
"""Миграция PVC на longhorn (в т.ч. longhorn -> longhorn с изменением размера).

Интерактивная утилита для переноса данных одного PVC в новый PV с storageClassName
longhorn с последующим возвратом оригинального имени PVC. Поддерживает миграцию
с любого SC (включая сам longhorn) и изменение размера целевого PVC (shrink/grow).

Перед запуском:
  1. Задайте namespace:  export NAMESPACE=...  (или --namespace)
  2. Выполните:  flux suspend helmrelease -n <ns> <release>

После завершения:
  1. Обновите storageClassName (и size, если меняли) в HelmRelease в git
  2. Закоммитьте и:  flux resume helmrelease -n <ns> <release>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from typing import Any

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

LONGHORN_SC = "longhorn"
MIGRATOR_POD = "data-migrator"
MIGRATOR_IMAGE = "alpine:latest"
MIGRATOR_TIMEOUT_S = 1800  # 30 минут максимум на один PVC

# Валидация размера PVC: <число><суффикс>, суффиксы k8s (Ki/Mi/Gi/Ti/Pi/Ei)
_SIZE_RE = re.compile(r"^\d+(Ki|Mi|Gi|Ti|Pi|Ei)$")

console = Console()


# --------------------------------------------------------------------------- #
#  Logging setup (loguru -> rich sink)
# --------------------------------------------------------------------------- #
_LEVEL_STYLES: dict[str, str] = {
    "TRACE": "dim",
    "DEBUG": "dim cyan",
    "INFO": "bold cyan",
    "SUCCESS": "bold green",
    "WARNING": "bold yellow",
    "ERROR": "bold red",
    "CRITICAL": "bold white on red",
}


def _rich_sink(message: Any) -> None:
    """Loguru sink, рендерящий сообщения через rich Console с поддержкой markup."""
    record = message.record
    level_name = record["level"].name
    style = _LEVEL_STYLES.get(level_name, "white")
    time_str = record["time"].strftime("%Y-%m-%d %H:%M:%S")
    msg = record["message"]
    console.print(
        f"[dim]{time_str}[/dim] [{style}]{level_name:<8}[/] {msg}",
        markup=True,
        highlight=False,
    )


def setup_logging(dry_run: bool) -> None:
    logger.remove()
    logger.add(_rich_sink, level="DEBUG", colorize=False)
    if dry_run:
        logger.warning("DRY-RUN режим: команды не выполняются")


def log_cmd(args: list[str]) -> None:
    cmd = " ".join(args)
    logger.debug(f"$ [bold]{cmd}[/bold]")


def validate_size(size: str) -> bool:
    """Проверяет, что строка является корректным размером k8s (например, 15Gi)."""
    return bool(_SIZE_RE.match(size))


def parse_size_gib(size: str) -> float | None:
    """Парсит размер в Gi для сравнения. Возвращает None, если не удалось."""
    m = _SIZE_RE.match(size)
    if not m:
        return None
    value = int(m.group(0)[:-2])
    suffix = size[-2:]
    multipliers = {"Ki": 1 / (1024 * 1024), "Mi": 1 / 1024, "Gi": 1.0,
                   "Ti": 1024.0, "Pi": 1024 * 1024.0, "Ei": 1024 ** 3}
    return value * multipliers[suffix]


# --------------------------------------------------------------------------- #
#  Rich helpers
# --------------------------------------------------------------------------- #
def print_yaml(manifest: str, *, title: str = "Manifest") -> None:
    syntax = Syntax(manifest, "yaml", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title=title, border_style="cyan", expand=False))


def print_panel(msg: str, *, style: str = "cyan", title: str | None = None) -> None:
    console.print(Panel(msg, title=title, border_style=style, expand=False))


def print_summary(
    namespace: str,
    workload: str,
    wtype: str,
    pvc: str,
    source_size: str,
    target_size: str,
    dry_run: bool,
) -> None:
    table = Table(title="Сводка миграции", border_style="bold blue", show_header=True)
    table.add_column("Параметр", style="bold cyan", no_wrap=True)
    table.add_column("Значение", style="white")
    table.add_row("Namespace", namespace)
    table.add_row("Workload", f"{wtype}/{workload}")
    table.add_row("PVC", pvc)
    table.add_row("Source Size", source_size)
    if source_size != target_size:
        table.add_row("Target Size", f"[bold yellow]{target_size}[/bold yellow]")
    else:
        table.add_row("Target Size", target_size)
    table.add_row("Target SC", f"[bold green]{LONGHORN_SC}[/bold green]")
    if dry_run:
        table.add_row("Режим", "[bold yellow]DRY-RUN[/bold yellow]")
    console.print(table)


def print_final_instructions(
    ns: str, wtype: str, source_size: str, target_size: str
) -> None:
    lines = [
        "[bold green]Миграция PVC завершена.[/bold green]",
        "",
        "[bold]ДАЛЬНЕЙШИЕ ШАГИ (вручную):[/bold]",
        f"  1. Обновите [cyan]storageClassName[/cyan] в HelmRelease в git: "
        f"[bold]{LONGHORN_SC}[/bold]",
    ]
    if source_size != target_size:
        lines.append(
            f"  [bold yellow]2. Измените [cyan]size[/cyan] в HelmRelease в git: "
            f"[bold]{target_size}[/bold] (было: {source_size})[/bold yellow]"
        )
        lines.append(
            f"  3. Закоммитьте и: [bold]flux resume helmrelease -n {ns} <release>[/bold]"
        )
        lines.append(f"  4. Проверьте: [dim]kubectl get pods -n {ns}[/dim]")
        lines.append(f"               [dim]kubectl get pvc -n {ns}[/dim]")
    else:
        lines.append(
            f"  2. Закоммитьте и: [bold]flux resume helmrelease -n {ns} <release>[/bold]"
        )
        lines.append(f"  3. Проверьте: [dim]kubectl get pods -n {ns}[/dim]")
        lines.append(f"               [dim]kubectl get pvc -n {ns}[/dim]")
    if wtype == "statefulset":
        lines.append(
            "  + Для StatefulSet: обновите [cyan]volumeClaimTemplates[/cyan] в HelmRelease"
        )
    console.print(Panel("\n".join(lines), border_style="bold green", title="Готово"))


def print_warning_panel(msg: str, *, title: str = "Внимание") -> None:
    console.print(Panel(msg, title=title, border_style="bold yellow"))


def print_error_panel(msg: str, *, title: str = "Ошибка") -> None:
    console.print(Panel(msg, title=title, border_style="bold red"))


# --------------------------------------------------------------------------- #
#  Interactive menus (rich)
# --------------------------------------------------------------------------- #
def menu(title: str, options: list[str]) -> int:
    if not options:
        raise RuntimeError(f"Нет вариантов для выбора: {title}")
    console.print(f"\n[bold cyan]=== {title} ===[/bold cyan]")
    for i, opt in enumerate(options, 1):
        console.print(f"  [bold green]{i}.[/bold green] [white]{opt}[/white]")
    while True:
        raw = Prompt.ask(
            "[bold]Выберите[/bold]", default="1", console=console
        ).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        console.print("[red]Некорректный ввод, попробуйте снова.[/red]")


def choose_workload_type() -> str:
    idx = menu("Тип workload", ["Deployment", "StatefulSet"])
    return ["deployment", "statefulset"][idx]


def confirm(prompt: str, default: bool = False) -> bool:
    return Confirm.ask(f"[bold]{prompt}[/bold]", default=default, console=console)


# --------------------------------------------------------------------------- #
#  Shell helpers
# --------------------------------------------------------------------------- #
class Runner:
    def __init__(self, dry_run: bool, namespace: str) -> None:
        self.dry_run = dry_run
        self.namespace = namespace

    def run(
        self,
        args: list[str],
        *,
        capture: bool = False,
        check: bool = True,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        log_cmd(args)
        if self.dry_run:
            return subprocess.CompletedProcess(args, 0, "", "")
        result = subprocess.run(
            args,
            capture_output=capture,
            text=True,
            check=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            stderr = result.stderr.strip() if capture else ""
            raise RuntimeError(
                f"Команда завершилась с кодом {result.returncode}: "
                f"{' '.join(args)}\n{stderr}"
            )
        return result

    def kubectl(self, args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return self.run(["kubectl", *args], **kw)

    def kubectl_json(self, args: list[str]) -> dict[str, Any]:
        cp = self.kubectl(args, capture=True, check=True)
        if self.dry_run:
            return {}
        result: dict[str, Any] = json.loads(cp.stdout)
        return result

    def kubectl_jsonpath(self, args: list[str], jsonpath: str) -> str:
        full = [*args, "-o", f"jsonpath={jsonpath}"]
        cp = self.kubectl(full, capture=True, check=True)
        return cp.stdout.strip() if not self.dry_run else ""

    def apply_manifest(self, manifest: str, *, title: str = "Apply") -> None:
        print_yaml(manifest, title=title)
        if self.dry_run:
            return
        cp = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=manifest,
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.stdout.strip():
            logger.info(cp.stdout.strip())
        if cp.returncode != 0:
            raise RuntimeError(f"kubectl apply failed:\n{cp.stderr}")

    def delete_manifest(self, manifest: str) -> None:
        print_yaml(manifest, title="Delete")
        if self.dry_run:
            return
        cp = subprocess.run(
            ["kubectl", "delete", "-f", "-"],
            input=manifest,
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.stdout.strip():
            logger.info(cp.stdout.strip())
        if cp.returncode != 0:
            raise RuntimeError(f"kubectl delete failed:\n{cp.stderr}")


# --------------------------------------------------------------------------- #
#  Resource listing
# --------------------------------------------------------------------------- #
def list_workloads(runner: Runner, wtype: str) -> list[str]:
    if runner.dry_run:
        return ["dry-run-workload"]
    data = runner.kubectl_json(
        ["get", wtype, "-n", runner.namespace, "-o", "json"]
    )
    return [item["metadata"]["name"] for item in data.get("items", [])]


def list_pvc_for_deployment(runner: Runner, deploy: str) -> list[str]:
    if runner.dry_run:
        return ["dry-run-pvc"]
    data = runner.kubectl_json(
        ["get", "deployment", deploy, "-n", runner.namespace, "-o", "json"]
    )
    pvcs: list[str] = []
    for vol in data["spec"]["template"]["spec"].get("volumes", []):
        pvc = vol.get("persistentVolumeClaim")
        if pvc and "claimName" in pvc:
            pvcs.append(pvc["claimName"])
    return pvcs


def list_pvc_for_sts(runner: Runner, sts: str) -> list[str]:
    if runner.dry_run:
        return ["dry-run-pvc"]
    # PVC для STS имеют имена <templateName>-<stsName>-<ordinal>
    sts_data = runner.kubectl_json(
        ["get", "statefulset", sts, "-n", runner.namespace, "-o", "json"]
    )
    templates = sts_data["spec"].get("volumeClaimTemplates", [])
    template_names = [t["metadata"]["name"] for t in templates]
    replicas = sts_data["spec"].get("replicas", 1)
    pvcs: list[str] = []
    for tpl in template_names:
        for ordinal in range(replicas):
            pvcs.append(f"{tpl}-{sts}-{ordinal}")
    if not pvcs:
        return []
    all_pvc = runner.kubectl_json(
        ["get", "pvc", "-n", runner.namespace, "-o", "json"]
    )
    existing = {item["metadata"]["name"] for item in all_pvc.get("items", [])}
    return [p for p in pvcs if p in existing]


def get_pvc_spec(runner: Runner, pvc_name: str) -> dict[str, Any]:
    return runner.kubectl_json(
        ["get", "pvc", pvc_name, "-n", runner.namespace, "-o", "json"]
    )


# --------------------------------------------------------------------------- #
#  Manifest builders
# --------------------------------------------------------------------------- #
def build_pvc_manifest(
    name: str, namespace: str, size: str, access_modes: list[str], sc: str
) -> str:
    am = "\n".join(f"    - {m}" for m in access_modes)
    return f"""apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {name}
  namespace: {namespace}
spec:
  accessModes:
{am}
  storageClassName: {sc}
  resources:
    requests:
      storage: {size}
"""


def build_migrator_pod_manifest(
    namespace: str, source_pvc: str, dest_pvc: str
) -> str:
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {MIGRATOR_POD}
  namespace: {namespace}
spec:
  restartPolicy: Never
  containers:
    - name: migrator
      image: {MIGRATOR_IMAGE}
      command: ["sh", "-c", "cp -av /source/. /destination/ && echo DONE"]
      volumeMounts:
        - name: source
          mountPath: /source
        - name: destination
          mountPath: /destination
  volumes:
    - name: source
      persistentVolumeClaim:
        claimName: {source_pvc}
    - name: destination
      persistentVolumeClaim:
        claimName: {dest_pvc}
"""


# --------------------------------------------------------------------------- #
#  Migration steps
# --------------------------------------------------------------------------- #
def step(n: int, total: int, title: str) -> None:
    console.rule(f"[bold blue]Шаг {n}/{total}: {title}[/bold blue]")


def wait_for_migrator(runner: Runner) -> None:
    """Стримим логи migrator, затем проверяем статус. Если не Succeeded — повторяем."""
    if runner.dry_run:
        logger.info("dry-run: пропускаем ожидание migrator")
        return

    deadline = time.time() + MIGRATOR_TIMEOUT_S
    while time.time() < deadline:
        logger.info("Стриминг логей migrator (kubectl logs -f)...")
        try:
            runner.kubectl(
                ["logs", "-n", runner.namespace, MIGRATOR_POD, "-f"],
                check=False,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            logger.warning("kubectl logs -f превысил таймаут, проверяем статус...")

        phase = runner.kubectl_jsonpath(
            ["get", "pod", "-n", runner.namespace, MIGRATOR_POD],
            "{.status.phase}",
        )
        if phase == "Succeeded":
            logger.success(f"Migrator завершён: {phase}")
            return
        if phase == "Failed":
            raise RuntimeError(
                "Migrator завершился с ошибкой. Проверьте: "
                f"kubectl logs -n {runner.namespace} {MIGRATOR_POD}"
            )
        logger.warning(f"Фаза {phase}, продолжаем ожидание...")
        time.sleep(5)

    raise RuntimeError(
        f"Migrator не завершился за {MIGRATOR_TIMEOUT_S}с. "
        "Проверьте вручную и удалите pod после."
    )


def migrate_pvc(
    runner: Runner,
    pvc_name: str,
    wtype: str,
    workload: str,
    target_size: str | None = None,
) -> None:
    total_steps = 9
    ns = runner.namespace

    # Получаем параметры старого PVC
    logger.info(f"Чтение спецификации PVC [bold]{pvc_name}[/bold]...")
    pvc_data = get_pvc_spec(runner, pvc_name)
    if runner.dry_run:
        pvc_data = {
            "spec": {
                "resources": {"requests": {"storage": "1Gi"}},
                "accessModes": ["ReadWriteOnce"],
            }
        }
    source_size = pvc_data["spec"]["resources"]["requests"]["storage"]
    access_modes = pvc_data["spec"].get("accessModes", ["ReadWriteOnce"])
    current_sc = pvc_data["spec"].get("storageClassName", "")

    # Запрос целевого размера (аргумент или интерактивно)
    if target_size is None:
        target_size = Prompt.ask(
            "[bold]Размер целевого PVC[/bold]",
            default=source_size,
            console=console,
        ).strip()
    assert target_size is not None
    if not validate_size(target_size):
        print_error_panel(
            f"Некорректный размер PVC: '{target_size}'.\n"
            "Ожидается формат <число><суффикс>, например: 15Gi, 500Mi, 2Ti.\n"
            "Допустимые суффиксы: Ki, Mi, Gi, Ti, Pi, Ei."
        )
        raise RuntimeError(f"Некорректный размер PVC: {target_size}")

    size_changed = source_size != target_size

    logger.info(
        f"storage: [bold]{source_size}[/bold]"
        + (f" -> [bold yellow]{target_size}[/bold yellow]" if size_changed else "")
        + f", accessModes: [bold]{access_modes}[/bold], "
        f"SC: [bold yellow]{current_sc}[/bold yellow]"
        + (f" -> [bold green]{LONGHORN_SC}[/bold green]" if current_sc != LONGHORN_SC else "")
    )

    if current_sc == LONGHORN_SC and not confirm(
        f"PVC {pvc_name} уже использует storageClassName={LONGHORN_SC}. "
        "Продолжить миграцию?",
        default=False,
    ):
        logger.info("Пропуск по запросу пользователя.")
        return

    temp_pvc = f"{pvc_name}-longhorn"

    # --- Шаг 1 ---
    step(1, total_steps, f"Остановка {wtype} {workload} (replicas=0)")
    runner.kubectl(
        ["scale", wtype, workload, "-n", ns, "--replicas=0"],
        check=True,
    )
    logger.info("Ожидание остановки подов...")
    if not runner.dry_run:
        _wait_pods_gone(runner, ns, workload, wtype)

    # --- Шаг 2 ---
    step(2, total_steps, f"Создание временного PVC {temp_pvc} (longhorn)")
    manifest = build_pvc_manifest(temp_pvc, ns, target_size, access_modes, LONGHORN_SC)
    runner.apply_manifest(manifest, title=f"PVC {temp_pvc}")
    logger.info(f"Ожидание PVC {temp_pvc} -> Bound...")
    if not runner.dry_run:
        _wait_pvc_bound(runner, ns, temp_pvc)

    # --- Шаг 3 ---
    step(3, total_steps, "Запуск pod-мигратора для копирования данных")
    pod_manifest = build_migrator_pod_manifest(ns, pvc_name, temp_pvc)
    runner.apply_manifest(pod_manifest, title="Migrator Pod")

    # --- Шаг 4 ---
    step(4, total_steps, "Ожидание завершения копирования данных")
    wait_for_migrator(runner)

    # --- Шаг 5 ---
    step(5, total_steps, "Удаление pod-мигратора")
    runner.kubectl(
        ["delete", "pod", MIGRATOR_POD, "-n", ns, "--ignore-not-found"],
        check=True,
    )

    # --- Шаг 6 ---
    step(6, total_steps, "PV -> Retain, удаление временного PVC")
    pv_name = runner.kubectl_jsonpath(
        ["get", "pvc", temp_pvc, "-n", ns], "{.spec.volumeName}"
    )
    logger.info(f"PV: [bold cyan]{pv_name}[/bold cyan]")
    if pv_name:
        runner.kubectl(
            [
                "patch",
                "pv",
                pv_name,
                '-p',
                '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}',
            ],
            check=True,
        )
    runner.kubectl(["delete", "pvc", temp_pvc, "-n", ns], check=True)

    # --- Шаг 7 ---
    step(7, total_steps, "Очистка claimRef у PV (-> Available)")
    if pv_name:
        runner.kubectl(
            [
                "patch",
                "pv",
                pv_name,
                "--type=json",
                '-p=[{"op":"remove","path":"/spec/claimRef"}]',
            ],
            check=True,
        )

    # --- Шаг 8 ---
    step(8, total_steps, f"Удаление старого PVC {pvc_name} (local-path)")
    runner.kubectl(["delete", "pvc", pvc_name, "-n", ns], check=True)

    # --- Шаг 9 ---
    step(9, total_steps, f"Создание PVC {pvc_name} (longhorn)")
    new_manifest = build_pvc_manifest(
        pvc_name, ns, target_size, access_modes, LONGHORN_SC
    )
    runner.apply_manifest(new_manifest, title=f"PVC {pvc_name}")
    logger.info(f"Ожидание PVC {pvc_name} -> Bound...")
    if not runner.dry_run:
        _wait_pvc_bound(runner, ns, pvc_name)

    final_pv = runner.kubectl_jsonpath(
        ["get", "pvc", pvc_name, "-n", ns], "{.spec.volumeName}"
    )
    final_sc = runner.kubectl_jsonpath(
        ["get", "pvc", pvc_name, "-n", ns], "{.spec.storageClassName}"
    )
    logger.success(
        f"PVC {pvc_name} -> PV {final_pv}, SC={final_sc}"
    )

    print_final_instructions(ns, wtype, source_size, target_size)


# --------------------------------------------------------------------------- #
#  Wait helpers
# --------------------------------------------------------------------------- #
def _wait_pvc_bound(runner: Runner, ns: str, pvc_name: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        phase = runner.kubectl_jsonpath(
            ["get", "pvc", pvc_name, "-n", ns], "{.status.phase}"
        )
        if phase == "Bound":
            logger.success(f"PVC {pvc_name} -> Bound")
            return
        time.sleep(3)
    raise RuntimeError(
        f"PVC {pvc_name} не стал Bound за {timeout}с. "
        f"Проверьте: kubectl get pvc -n {ns} {pvc_name}"
    )


def _wait_pods_gone(
    runner: Runner, ns: str, workload: str, wtype: str, timeout: int = 120
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        cp = runner.kubectl(
            ["get", wtype, workload, "-n", ns, "-o", "jsonpath={.status.readyReplicas}"],
            capture=True,
            check=False,
        )
        ready = cp.stdout.strip() if cp.stdout else "0"
        if ready in ("", "0"):
            logger.success(f"{wtype} {workload}: 0 ready replicas")
            return
        time.sleep(2)
    logger.warning(
        f"Поды {workload} не остановились за {timeout}с, продолжаем..."
    )


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Миграция PVC на longhorn (интерактивный режим)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--namespace", "-n", required=True, help="Namespace (обязательно)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Показывать команды без выполнения"
    )
    parser.add_argument(
        "--workload-type",
        choices=["deployment", "statefulset"],
        help="Тип workload (иначе выбор через меню)",
    )
    parser.add_argument("--workload", help="Имя workload (иначе выбор через меню)")
    parser.add_argument("--pvc", help="Имя PVC (иначе выбор через меню)")
    parser.add_argument(
        "--target-size",
        help="Размер целевого PVC (например, 15Gi). Иначе — запрос интерактивно.",
    )
    args = parser.parse_args()

    setup_logging(args.dry_run)
    runner = Runner(dry_run=args.dry_run, namespace=args.namespace)

    logger.info(f"Namespace: [bold]{args.namespace}[/bold]")

    # Проверка доступности kubectl
    if not args.dry_run:
        try:
            runner.kubectl(["cluster-info"], capture=True, check=True)
        except Exception as e:
            print_error_panel(f"Не удалось подключиться к кластеру:\n{e}")
            return 1

    # Напоминание о flux suspend
    print_warning_panel(
        f"Перед миграцией необходимо приостановить HelmRelease:\n"
        f"[bold]flux suspend helmrelease -n {args.namespace} <release-name>[/bold]",
        title="Flux Suspend",
    )
    if not confirm("Вы уже выполнили flux suspend helmrelease?", default=False):
        logger.info("Сначала приостановьте HelmRelease, затем запустите скрипт снова.")
        return 1

    # Выбор типа workload
    wtype = args.workload_type or choose_workload_type()

    # Выбор workload
    if args.workload:
        workload = args.workload
    else:
        workloads = list_workloads(runner, wtype)
        if not workloads:
            print_error_panel(
                f"Не найдено {wtype} в namespace {args.namespace}"
            )
            return 1
        idx = menu(f"Выберите {wtype}", workloads)
        workload = workloads[idx]

    logger.info(f"Workload: [bold]{wtype}/{workload}[/bold]")

    # Выбор PVC
    if args.pvc:
        pvc_name = args.pvc
    else:
        if wtype == "deployment":
            pvcs = list_pvc_for_deployment(runner, workload)
        else:
            pvcs = list_pvc_for_sts(runner, workload)
        if not pvcs:
            print_error_panel(
                f"Не найдено PVC для {wtype}/{workload}.\n"
                "Возможно, workload не использует persistentVolumeClaim."
            )
            return 1
        if len(pvcs) == 1:
            pvc_name = pvcs[0]
            logger.info(f"Найден один PVC: [bold]{pvc_name}[/bold]")
        else:
            idx = menu("Выберите PVC для миграции", pvcs)
            pvc_name = pvcs[idx]

    logger.info(f"PVC для миграции: [bold]{pvc_name}[/bold]")

    # Чтение размера исходного PVC для сводки
    if args.dry_run:
        source_size = "1Gi"
    else:
        pvc_data = get_pvc_spec(runner, pvc_name)
        source_size = pvc_data["spec"]["resources"]["requests"]["storage"]

    # Запрос целевого размера
    target_size: str
    if args.target_size:
        target_size = args.target_size
        if not validate_size(target_size):
            print_error_panel(
                f"Некорректный --target-size: '{target_size}'.\n"
                "Ожидается формат <число><суффикс>, например: 15Gi, 500Mi, 2Ti.\n"
                "Допустимые суффиксы: Ki, Mi, Gi, Ti, Pi, Ei."
            )
            return 1
    else:
        target_size = Prompt.ask(
            "[bold]Размер целевого PVC[/bold]",
            default=source_size,
            console=console,
        ).strip()
        if not validate_size(target_size):
            print_error_panel(
                f"Некорректный размер PVC: '{target_size}'.\n"
                "Ожидается формат <число><суффикс>, например: 15Gi, 500Mi, 2Ti.\n"
                "Допустимые суффиксы: Ki, Mi, Gi, Ti, Pi, Ei."
            )
            return 1

    # Предупреждение при уменьшении
    src_gib = parse_size_gib(source_size)
    dst_gib = parse_size_gib(target_size)
    is_shrink = src_gib is not None and dst_gib is not None and dst_gib < src_gib
    if is_shrink:
        print_warning_panel(
            f"Уменьшение PVC: {source_size} -> {target_size}\n"
            "[bold]Убедитесь, что данные помещаются в новый размер![/bold]\n"
            "Проверьте занятое место перед миграцией, например:\n"
            f"  kubectl exec -n {args.namespace} <pod> -- du -sh /<mount-path>\n"
            f"  kubectl exec -n {args.namespace} <pod> -- df -h /<mount-path>",
            title="Уменьшение PVC",
        )

    # Финальное подтверждение
    console.print()
    print_summary(
        args.namespace, workload, wtype, pvc_name, source_size, target_size, args.dry_run
    )
    console.print()
    if not confirm("Начать миграцию?", default=False):
        logger.info("Отменено пользователем.")
        return 0

    try:
        migrate_pvc(runner, pvc_name, wtype, workload, target_size=target_size)
    except KeyboardInterrupt:
        logger.warning("Прервано пользователем (Ctrl+C).")
        print_error_panel(
            "Миграция может быть в незавершённом состоянии.\n"
            f"Проверьте: kubectl get pvc,pod,pv -n {args.namespace}",
            title="Прервано",
        )
        return 130
    except Exception as e:
        print_error_panel(
            f"Ошибка: {e}\n\n"
            f"Проверьте состояние ресурсов:\n"
            f"kubectl get pvc,pod,pv -n {args.namespace}",
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
