# Loki + Alloy Logging Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Развернуть стек сбора и хранения логов (Loki 3.x в режиме SingleBinary с PVC 10Gi на Longhorn и Grafana Alloy DaemonSet) в кластере Kubernetes через Flux CD с подключением к Grafana и внешним защищенным Ingress через Traefik и Authelia.

**Architecture:** Все компоненты объявляются декларативно через Flux GitOps в пространстве имен `monitoring`. Репозиторий чартов `grafana-charts` (`oci://ghcr.io/grafana/helm-charts`) уже подключен. Сервер Loki разворачивается в режиме SingleBinary с хранилищем `filesystem` + `tsdb` на PVC 10Gi (`longhorn-low`) и retention 14 дней. Агент Grafana Alloy разворачивается как DaemonSet на всех узлах и отправляет логи подов в Loki. Сайдкар Grafana автоматически монтирует ConfigMap источника данных `loki-datasource`. Внешний доступ защищается через Traefik Ingress с middleware Authelia (поддерживает HTTP Basic Auth для логов с VPS).

**Tech Stack:** Flux CD v2 (HelmRelease, Kustomization), Helm, Grafana Loki 3.x, Grafana Alloy, Traefik, Authelia forward-auth, Longhorn CSI, cert-manager.

**Spec:** `docs/superpowers/specs/2026-10-18-loki-stack-design.md`

## Global Constraints

- Namespace: `monitoring`
- Domain: `loki.xinfra.ru`
- TLS Secret: `wildcard-xinfra-ru-tls`
- Traefik Middleware: `security-forwardauth-authelia@kubernetescrd`
- Traefik Entrypoint: `websecure`
- StorageClass: `longhorn-low` (1 replica, `allowVolumeExpansion: true`)
- PVC Capacity: `10Gi`
- Loki Deployment Mode: `SingleBinary` (1 реплика)
- Loki Storage Backend: `filesystem` + `tsdb` (schema v13)
- Loki Retention Period: `336h` (14 дней)
- Chart Repository: `grafana-charts` (`oci://ghcr.io/grafana/helm-charts` в `flux-system`)
- Alloy Mode: `daemonset` (с монтированием `/var/log/pods` и `/var/lib/docker/containers`)
- Grafana DataSource Label: `grafana_datasource: "1"`

## Review Focus

1. **Совместимость схемы Loki 3.x с файловой системой**: в Loki 3.x обязательна схема `tsdb` с `object_store: filesystem` и валидная секция `compactor` для работы `retention_period`.
2. **Права доступа Alloy к логам хоста**: неймспейс `monitoring` имеет `privileged` enforce, поды Alloy должны корректно монтировать `/var/log/pods` и запускаться с правами на чтение.
3. **Безопасность Ingress и Basic Auth**: внешний доступ к `https://loki.xinfra.ru/loki/api/v1/push` должен требовать аутентификацию Authelia, блокируя анонимные запросы (302/401).
4. **Авто-обнаружение DataSource сайдкаром Grafana**: ConfigMap должен содержать метку `grafana_datasource: "1"` и корректный внутренний URL `http://loki.monitoring.svc.cluster.local:3100`.
5. **Целостность сборки Kustomize**: все добавленные манифесты должны проходить `kustomize build` и валидацию pre-commit хуков без предупреждений и ошибок.

---

### Task 1: Создание манифеста HelmRelease для Loki

**Files:**
- Create: `clusters/my-cluster/releases/apps/loki.yaml`

**Interfaces:**
- Produces: Service `loki.monitoring.svc.cluster.local:3100`, Ingress `loki.xinfra.ru`

- [ ] **Step 1: Создать файл `clusters/my-cluster/releases/apps/loki.yaml`**
  Создать `HelmRelease` с параметрами:
  - `chart.spec.chart: loki`
  - `chart.spec.sourceRef.name: grafana-charts` (`namespace: flux-system`)
  - `values.deploymentMode: SingleBinary`
  - `values.loki.commonConfig.replication_factor: 1`
  - `values.loki.storage.type: filesystem`
  - `values.loki.schemaConfig` со схемой `tsdb` и `object_store: filesystem`
  - `values.loki.limits_config`: `retention_period: 336h`, `ingestion_rate_mb: 10`, `ingestion_burst_size_mb: 20`
  - `values.loki.compactor`: `retention_enabled: true`, `delete_request_store: filesystem`
  - `values.singleBinary.replicas: 1`
  - `values.singleBinary.persistence.enabled: true`
  - `values.singleBinary.persistence.storageClass: "longhorn-low"`
  - `values.singleBinary.persistence.size: 10Gi`
  - `values.ingress.enabled: true`
  - `values.ingress.ingressClassName: traefik`
  - `values.ingress.annotations`:
    - `traefik.ingress.kubernetes.io/router.entrypoints: websecure`
    - `traefik.ingress.kubernetes.io/router.middlewares: security-forwardauth-authelia@kubernetescrd`
  - `values.ingress.hosts: ["loki.xinfra.ru"]`
  - `values.ingress.tls`: `secretName: wildcard-xinfra-ru-tls`, `hosts: ["loki.xinfra.ru"]`
  - Отключить ненужные микросервисы (`backend.replicas: 0`, `read.replicas: 0`, `write.replicas: 0`, `gateway.enabled: false`).

- [ ] **Step 2: Валидировать корректность YAML-манифеста**
  Запустить: `yamllint clusters/my-cluster/releases/apps/loki.yaml`
  Ожидается: 0 ошибок.

---

### Task 2: Создание ConfigMap для автоматической регистрации DataSource в Grafana

**Files:**
- Create: `clusters/my-cluster/releases/apps/loki-datasource.yaml`

**Interfaces:**
- Consumes: Service `loki.monitoring.svc.cluster.local:3100`
- Produces: Grafana DataSource `Loki` (UID `loki`)

- [ ] **Step 1: Создать `clusters/my-cluster/releases/apps/loki-datasource.yaml`**
  Создать ConfigMap `loki-datasource` в неймспейсе `monitoring` с метками:
  `grafana_datasource: "1"`
  В `data.datasources.yaml` указать:
  ```yaml
  apiVersion: 1
  datasources:
    - name: Loki
      type: loki
      uid: loki
      access: proxy
      url: http://loki.monitoring.svc.cluster.local:3100
      isDefault: false
      jsonData:
        maxLines: 1000
  ```

- [ ] **Step 2: Валидировать корректность YAML-манифеста**
  Запустить: `yamllint clusters/my-cluster/releases/apps/loki-datasource.yaml`
  Ожидается: 0 ошибок.

---

### Task 3: Создание манифеста HelmRelease для Grafana Alloy DaemonSet

**Files:**
- Create: `clusters/my-cluster/releases/apps/alloy.yaml`

**Interfaces:**
- Consumes: Service `loki.monitoring.svc.cluster.local:3100`
- Produces: DaemonSet сбора логов `/var/log/pods` на нодах `acemagic`, `dns`, `note-nixos`

- [ ] **Step 1: Создать `clusters/my-cluster/releases/apps/alloy.yaml`**
  Создать `HelmRelease` с параметрами:
  - `chart.spec.chart: alloy`
  - `chart.spec.sourceRef.name: grafana-charts` (`namespace: flux-system`)
  - `values.alloy.clustering.enabled: false`
  - `values.controller.type: daemonset`
  - `values.alloy.configMap.content`: пайплайн Alloy, включающий:
    - `discovery.kubernetes "pods"` с фильтрацией по локальной ноде (`nodeName`)
    - `discovery.relabel "pod_logs"` с правилами извлечения `namespace`, `pod`, `container`
    - `loki.source.kubernetes "pod_logs"` с чтением из targets relabeling
    - `loki.write "local_loki"` на `http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push`
  - Монтирование `/var/log/pods` (readOnly) и `/var/lib/docker/containers` (readOnly).
  - Настройка `resources`: requests `50m/128Mi`, limits `200m/256Mi`.

- [ ] **Step 2: Валидировать корректность YAML-манифеста**
  Запустить: `yamllint clusters/my-cluster/releases/apps/alloy.yaml`
  Ожидается: 0 ошибок.

---

### Task 4: Регистрация ресурсов в Kustomize и проверка сборки

**Files:**
- Modify: `clusters/my-cluster/releases/apps/kustomization.yaml`

**Interfaces:**
- Consumes: `loki.yaml`, `alloy.yaml`, `loki-datasource.yaml`
- Produces: Полный скомпилированный k8s бандл для `releases` stage

- [ ] **Step 1: Добавить новые файлы в `clusters/my-cluster/releases/apps/kustomization.yaml`**
  Добавить в секцию `resources`:
  - `alloy.yaml`
  - `loki.yaml`
  - `loki-datasource.yaml`

- [ ] **Step 2: Проверить валидность сборки Kustomize**
  Запустить: `kubectl kustomize clusters/my-cluster/releases/apps > /dev/null`
  Ожидается: успешная компиляция без ошибок.

- [ ] **Step 3: Проверить статус Git и закоммитить манифесты**
  ```bash
  git add clusters/my-cluster/releases/apps/loki.yaml \
          clusters/my-cluster/releases/apps/alloy.yaml \
          clusters/my-cluster/releases/apps/loki-datasource.yaml \
          clusters/my-cluster/releases/apps/kustomization.yaml
  git commit -m "feat(monitoring): add Loki and Grafana Alloy logging stack"
  ```

---

### Task 5: Применение через Flux и верификация в кластере

**Files:**
- None (Runtime verification)

**Interfaces:**
- Проверяет все компоненты в живом кластере

- [ ] **Step 1: Инициировать согласование Flux**
  Запустить: `flux reconcile kustomization releases --with-source`
  Ожидается: `Applied revision: ...` без ошибок.

- [ ] **Step 2: Дождаться развертывания HelmRelease**
  Запустить:
  `flux get hr -n monitoring loki`
  `flux get hr -n monitoring alloy`
  Ожидается: статус `Release reconciliation succeeded` для обоих релизов.

- [ ] **Step 3: Проверить запуск подов и монтирование диска**
  Запустить:
  `kubectl get pods -n monitoring -l app.kubernetes.io/name=loki`
  `kubectl get pods -n monitoring -l app.kubernetes.io/name=alloy`
  `kubectl get pvc -n monitoring`
  Ожидается:
  - Loki под `1/1 Running`
  - Alloy 3 пода (по одному на каждой ноде) `1/1 Running`
  - PVC `loki` в статусе `Bound` к `longhorn-low`

- [ ] **Step 4: Проверить источник данных в Grafana и поток логов**
  Запустить запрос к локальному API Loki через порт-форвард или curl:
  `kubectl run -it --rm curl-test --image=curlimages/curl --restart=Never -n monitoring -- curl -s http://loki:3100/ready`
  Ожидается: `ready`.

- [ ] **Step 5: Проверить внешний Ingress и безопасность Authelia**
  Запустить:
  `curl -s -o /dev/null -w "%{http_code}" https://loki.xinfra.ru/loki/api/v1/push`
  Ожидается: `302` или `401` (перехват Authelia).
