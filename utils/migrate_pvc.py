#!/usr/bin/env python3
"""Миграция PVC с local-path (или иного SC) на longhorn.

Интерактивная утилита для переноса данных одного PVC в новый PV с storageClassName
longhorn с последующим возвратом оригинального имени PVC.

Перед запуском:
  1. Задайте namespace:  export NAMESPACE=...  (или --namespace)
  2. Выполните:  flux suspend helmrelease -n <ns> <release>

После завершения:
  1. Обновите storageClassName в HelmRelease в git на longhorn
  2. Закоммитьте и:  flux resume helmrelease -n <ns> <release>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

LONGHORN_SC = "longhorn"
MIGRATOR_POD = "data-migrator"
MIGRATOR_IMAGE = "alpine:latest"
MIGRATOR_TIMEOUT_S = 1800  # 30 минут максимум на один PVC


# --------------------------------------------------------------------------- #
#  Logging
# --------------------------------------------------------------------------- #
def log(msg: str, *, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def step(n: int, total: int, title: str) -> None:
    log(f"--- Шаг {n}/{total}: {title} ---")


def confirm(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    answer = input(f"{prompt}{suffix}").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes", "да")


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
        display = " ".join(args)
        log(f"$ {display}")
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
                f"Команда завершилась с кодом {result.returncode}: {display}\n{stderr}"
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

    def apply_manifest(self, manifest: str) -> None:
        log(f" Applying manifest:\n{manifest}")
        if self.dry_run:
            return
        cp = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=manifest,
            capture_output=True,
            text=True,
            check=False,
        )
        log(f" {cp.stdout.strip()}")
        if cp.returncode != 0:
            raise RuntimeError(f"kubectl apply failed:\n{cp.stderr}")

    def delete_manifest(self, manifest: str) -> None:
        log(f" Deleting via manifest:\n{manifest}")
        if self.dry_run:
            return
        cp = subprocess.run(
            ["kubectl", "delete", "-f", "-"],
            input=manifest,
            capture_output=True,
            text=True,
            check=False,
        )
        log(f" {cp.stdout.strip()}")
        if cp.returncode != 0:
            raise RuntimeError(f"kubectl delete failed:\n{cp.stderr}")


# --------------------------------------------------------------------------- #
#  Interactive menus
# --------------------------------------------------------------------------- #
def menu(title: str, options: list[str]) -> int:
    if not options:
        raise RuntimeError(f"Нет вариантов для выбора: {title}")
    print(f"\n=== {title} ===")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = input(f"Выберите [1-{len(options)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print("Некорректный ввод, попробуйте снова.")


def choose_workload_type() -> str:
    idx = menu("Тип workload", ["Deployment", "StatefulSet"])
    return ["deployment", "statefulset"][idx]


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
    # PVC для STS имеют имена <sts>-<templateName>-<ordinal>
    all_pvc = runner.kubectl_json(
        ["get", "pvc", "-n", runner.namespace, "-o", "json"]
    )
    names = [item["metadata"]["name"] for item in all_pvc.get("items", [])]
    return [n for n in names if n.startswith(f"{sts}-")]


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
def wait_for_migrator(runner: Runner) -> None:
    """Стримим логи migrator, затем проверяем статус. Если не Succeeded — повторяем."""
    if runner.dry_run:
        log("dry-run: пропускаем ожидание migrator")
        return

    deadline = time.time() + MIGRATOR_TIMEOUT_S
    while time.time() < deadline:
        # Стрим логов (блокирует до завершения pod или таймаута)
        log("Стриминг логов migrator (kubectl logs -f)...")
        try:
            runner.kubectl(
                ["logs", "-n", runner.namespace, MIGRATOR_POD, "-f"],
                check=False,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            log("kubectl logs -f превысил таймаут, проверяем статус...", level="WARN")

        # Проверяем финальный статус
        phase = runner.kubectl_jsonpath(
            ["get", "pod", "-n", runner.namespace, MIGRATOR_POD],
            "{.status.phase}",
        )
        log(f"Статус migrator: {phase}")

        if phase == "Succeeded":
            return
        if phase == "Failed":
            raise RuntimeError(
                "Migrator завершился с ошибкой. Проверьте: "
                f"kubectl logs -n {runner.namespace} {MIGRATOR_POD}"
            )
        # Pending/Running/Unknown — продолжаем ждать
        log(f"Фаза {phase}, продолжаем ожидание...", level="WARN")
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
) -> None:
    total_steps = 9
    ns = runner.namespace

    # Получаем параметры старого PVC
    log(f"Чтение спецификации PVC {pvc_name}...")
    pvc_data = get_pvc_spec(runner, pvc_name)
    if runner.dry_run:
        pvc_data = {
            "spec": {
                "resources": {"requests": {"storage": "1Gi"}},
                "accessModes": ["ReadWriteOnce"],
            }
        }
    size = pvc_data["spec"]["resources"]["requests"]["storage"]
    access_modes = pvc_data["spec"].get("accessModes", ["ReadWriteOnce"])
    current_sc = pvc_data["spec"].get("storageClassName", "")
    log(f"  storage: {size}, accessModes: {access_modes}, SC: {current_sc}")

    if current_sc == LONGHORN_SC and not confirm(
        f"PVC {pvc_name} уже использует storageClassName={LONGHORN_SC}. "
        "Продолжить миграцию?",
        default=False,
    ):
        log("Пропуск по запросу пользователя.")
        return

    temp_pvc = f"{pvc_name}-longhorn"

    # --- Шаг 1: scale workload до 0 ---
    step(1, total_steps, f"Остановка {wtype} {workload} (replicas=0)")
    runner.kubectl(
        ["scale", wtype, workload, "-n", ns, "--replicas=0"],
        check=True,
    )

    # Ждём пока поды остановятся
    log("Ожидание остановки подов...")
    if not runner.dry_run:
        _wait_pods_gone(runner, ns, workload, wtype)

    # --- Шаг 2: создание временного PVC с longhorn ---
    step(2, total_steps, f"Создание временного PVC {temp_pvc} (longhorn)")
    manifest = build_pvc_manifest(temp_pvc, ns, size, access_modes, LONGHORN_SC)
    runner.apply_manifest(manifest)

    # Ждём Bound
    log(f"Ожидание PVC {temp_pvc} -> Bound...")
    if not runner.dry_run:
        _wait_pvc_bound(runner, ns, temp_pvc)

    # --- Шаг 3: запуск migrator pod ---
    step(3, total_steps, "Запуск pod-мигратора для копирования данных")
    pod_manifest = build_migrator_pod_manifest(ns, pvc_name, temp_pvc)
    runner.apply_manifest(pod_manifest)

    # --- Шаг 4: ожидание завершения копирования ---
    step(4, total_steps, "Ожидание завершения копирования данных")
    wait_for_migrator(runner)

    # --- Шаг 5: удаление migrator ---
    step(5, total_steps, "Удаление pod-мигратора")
    runner.kubectl(
        ["delete", "pod", MIGRATOR_POD, "-n", ns, "--ignore-not-found"],
        check=True,
    )

    # --- Шаг 6: PV -> Retain, удаление временного PVC ---
    step(6, total_steps, "PV -> Retain, удаление временного PVC")
    pv_name = runner.kubectl_jsonpath(
        ["get", "pvc", temp_pvc, "-n", ns], "{.spec.volumeName}"
    )
    log(f"  PV: {pv_name}")
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

    # --- Шаг 7: очистка claimRef у PV ---
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

    # --- Шаг 8: удаление старого PVC ---
    step(8, total_steps, f"Удаление старого PVC {pvc_name} (local-path)")
    runner.kubectl(["delete", "pvc", pvc_name, "-n", ns], check=True)

    # --- Шаг 9: создание нового PVC с оригинальным именем ---
    step(9, total_steps, f"Создание PVC {pvc_name} (longhorn)")
    new_manifest = build_pvc_manifest(
        pvc_name, ns, size, access_modes, LONGHORN_SC
    )
    runner.apply_manifest(new_manifest)

    log(f"Ожидание PVC {pvc_name} -> Bound...")
    if not runner.dry_run:
        _wait_pvc_bound(runner, ns, pvc_name)

    # Проверка
    final_pv = runner.kubectl_jsonpath(
        ["get", "pvc", pvc_name, "-n", ns], "{.spec.volumeName}"
    )
    final_sc = runner.kubectl_jsonpath(
        ["get", "pvc", pvc_name, "-n", ns], "{.spec.storageClassName}"
    )
    log(f"  PVC {pvc_name} -> PV {final_pv}, SC={final_sc}")

    log("=" * 60)
    log("Миграция PVC завершена.")
    log("ДАЛЬНЕЙШИЕ ШАГИ (вручную):")
    log(f"  1. Обновите storageClassName в HelmRelease в git: {LONGHORN_SC}")
    log(f"  2. Закоммитьте и: flux resume helmrelease -n {ns} <release>")
    log(f"  3. Проверьте: kubectl get pods -n {ns}")
    log(f"               kubectl get pvc -n {ns}")
    if wtype == "statefulset":
        log("  4. Для StatefulSet: обновите volumeClaimTemplates в HelmRelease")
    log("=" * 60)


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
            log(f"  PVC {pvc_name} Bound")
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
            log(f"  {wtype} {workload}: 0 ready replicas")
            return
        time.sleep(2)
    log(
        f"Поды {workload} не остановились за {timeout}с, продолжаем...",
        level="WARN",
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
    args = parser.parse_args()

    runner = Runner(dry_run=args.dry_run, namespace=args.namespace)

    log(f"Namespace: {args.namespace}")
    if args.dry_run:
        log("DRY-RUN режим: команды не выполняются", level="WARN")

    # Проверка доступности kubectl
    if not args.dry_run:
        try:
            runner.kubectl(["cluster-info"], capture=True, check=True)
        except Exception as e:
            log(f"Не удалось подключиться к кластеру: {e}", level="ERROR")
            return 1

    # Напоминание о flux suspend
    log("=" * 60)
    log("ВНИМАНИЕ: Перед миграцией необходимо приостановить HelmRelease:")
    log(f"  flux suspend helmrelease -n {args.namespace} <release-name>")
    log("=" * 60)
    if not confirm("Вы уже выполнили flux suspend helmrelease?", default=False):
        log("Сначала приостановьте HelmRelease, затем запустите скрипт снова.")
        return 1

    # Выбор типа workload
    wtype = args.workload_type or choose_workload_type()

    # Выбор workload
    if args.workload:
        workload = args.workload
    else:
        workloads = list_workloads(runner, wtype)
        if not workloads:
            log(f"Не найдено {wtype} в namespace {args.namespace}", level="ERROR")
            return 1
        idx = menu(f"Выберите {wtype}", workloads)
        workload = workloads[idx]

    log(f"Workload: {wtype}/{workload}")

    # Выбор PVC
    if args.pvc:
        pvc_name = args.pvc
    else:
        if wtype == "deployment":
            pvcs = list_pvc_for_deployment(runner, workload)
        else:
            pvcs = list_pvc_for_sts(runner, workload)
        if not pvcs:
            log(
                f"Не найдено PVC для {wtype}/{workload}. "
                "Возможно, workload не использует persistentVolumeClaim.",
                level="ERROR",
            )
            return 1
        if len(pvcs) == 1:
            pvc_name = pvcs[0]
            log(f"Найден один PVC: {pvc_name}")
        else:
            idx = menu("Выберите PVC для миграции", pvcs)
            pvc_name = pvcs[idx]

    log(f"PVC для миграции: {pvc_name}")

    # Финальное подтверждение
    print()
    log("СВОДКА МИГРАЦИИ:")
    log(f"  Namespace : {args.namespace}")
    log(f"  Workload  : {wtype}/{workload}")
    log(f"  PVC       : {pvc_name}")
    log(f"  Target SC : {LONGHORN_SC}")
    if args.dry_run:
        log("  Режим     : DRY-RUN")
    print()
    if not confirm("Начать миграцию?", default=False):
        log("Отменено пользователем.")
        return 0

    try:
        migrate_pvc(runner, pvc_name, wtype, workload)
    except KeyboardInterrupt:
        log("Прервано пользователем (Ctrl+C).", level="WARN")
        log(
            "ВНИМАНИЕ: миграция может быть в незавершённом состоянии. "
            "Проверьте: kubectl get pvc,pod,pv -n "
            f"{args.namespace}",
            level="ERROR",
        )
        return 130
    except Exception as e:
        log(f"Ошибка: {e}", level="ERROR")
        log(
            "Проверьте состояние ресурсов: "
            f"kubectl get pvc,pod,pv -n {args.namespace}",
            level="ERROR",
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
