# Дизайн-документ: Развертывание стека сбора и хранения логов (Loki + Grafana Alloy) через Flux CD

## 1. Цели и Контекст
- **Цель**: Обеспечить централизованный сбор, долговременное хранение и удобный поиск логов для подов кластера Kubernetes и внешних VPS через единый стек Grafana + Loki.
- **Инфраструктура**:
  - **Кластер**: 3-узловой k3s кластер (`acemagic`, `dns`, `note-nixos`).
  - **GitOps**: Flux CD v2 (`HelmRelease`, `HelmRepository`, `Kustomization`).
  - **Хранилище**: Longhorn CSI (storageClass `longhorn-low`, 1 реплика).
  - **Ingress**: Traefik + cert-manager (`wildcard-xinfra-ru-tls`), хост `loki.xinfra.ru`.
  - **Безопасность внешнего доступа**: Traefik Middleware `security-forwardauth-authelia@kubernetescrd` (с поддержкой HTTP Basic Auth для внешних агентов сбора логов).
  - **Визуализация**: Существующий `kube-prometheus-stack` с Grafana на `grafana.xinfra.ru` (с активным `sidecar.datasources`).

---

## 2. Архитектура и Компоненты

### 2.1. Сервер хранения логов (Loki 3.x)
- **Файл**: `clusters/my-cluster/releases/apps/loki.yaml`
- **Источник чарта**: HelmRepository `grafana-charts` (`oci://ghcr.io/grafana/helm-charts`), чарт `loki`.
- **Namespace**: `monitoring`.
- **Режим развертывания**: `deploymentMode: SingleBinary` (StatefulSet, 1 реплика).
- **Хранилище и Retention**:
  - **StorageClass**: `longhorn-low` (1 реплика, поддержка `allowVolumeExpansion: true`).
  - **Размер PVC**: `10Gi` (с возможностью расширения при заполнении).
  - **Движок хранения**: `filesystem` с индексацией `tsdb` (актуальная схема v13).
  - **Период хранения (retention)**: `336h` (14 дней).
  - **Compactor**: включен режим `retention_enabled: true`, автоматическая очистка чанков старше 14 дней с интервалом проверки `2h`.
- **Лимиты приема (Rate Limiting)**:
  - `ingestion_rate_mb: 10`
  - `ingestion_burst_size_mb: 20`
  - `max_query_length: 721h` (до 30 дней)
- **Сетевой доступ и Ingress**:
  - Внутренний сервис: `http://loki.monitoring.svc.cluster.local:3100` (ClusterIP).
  - Внешний Ingress:
    - Хост: `loki.xinfra.ru`.
    - IngressClassName: `traefik`.
    - TLS: Secret `wildcard-xinfra-ru-tls` (зеркалируется reflector'ом в `monitoring`).
    - Annotations:
      - `traefik.ingress.kubernetes.io/router.entrypoints: websecure`
      - `traefik.ingress.kubernetes.io/router.middlewares: security-forwardauth-authelia@kubernetescrd`
- **Ресурсы**:
  - Requests: CPU `100m`, Memory `256Mi`.
  - Limits: CPU `1000m`, Memory `1536Mi`.

---

### 2.2. Агент сбора логов в кластере (Grafana Alloy)
- **Файл**: `clusters/my-cluster/releases/apps/alloy.yaml`
- **Источник чарта**: HelmRepository `grafana-charts`, чарт `alloy`.
- **Namespace**: `monitoring`.
- **Режим развертывания**: `DaemonSet` (разворачивается на всех рабочих нодах: `acemagic`, `dns`, `note-nixos`).
- **Безопасность и доступы**:
  - Запуск в неймспейсе `monitoring` с `pod-security.kubernetes.io/enforce: privileged`.
  - Монтирование системных путей нод через `hostPath`: `/var/log/pods` и `/var/lib/docker/containers`.
- **Пайплайн сбора и доставки (`config.alloy`)**:
  - `discovery.kubernetes "pods"`: обнаружение всех контейнеров на ноде через kubelet API.
  - `discovery.relabel "pod_logs"`: извлечение метаданных k8s (`namespace`, `pod`, `container`, `app_kubernetes_io_name`, `node`).
  - `loki.source.kubernetes "pod_logs"`: чтение и отслеживание (tailing) файлов логов контейнеров.
  - `loki.write "default"`: отправка батчей логов во внутренний сервис:
    `http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push`.
- **Ресурсы на ноду**:
  - Requests: CPU `50m`, Memory `128Mi`.
  - Limits: CPU `200m`, Memory `256Mi`.

---

### 2.3. Интеграция с Grafana (DataSource)
- **Файл**: `clusters/my-cluster/releases/apps/loki-datasource.yaml`
- **Ресурс**: `ConfigMap` в namespace `monitoring`.
- **Метки**: `grafana_datasource: "1"`.
- **Спецификация DataSource**:
  - Name: `Loki`
  - Type: `loki`
  - UID: `loki`
  - Access: `proxy`
  - URL: `http://loki.monitoring.svc.cluster.local:3100`
  - IsDefault: `false`
  - JsonData:
    - `maxLines: 1000`
- **Механизм загрузки**: Сайдкар Grafana (`sidecar.datasources.enabled: true`) в фоновом режиме монтирует этот ConfigMap и регистрирует источник без перезагрузки подов Grafana.

---

### 2.4. Сбор логов с внешних VPS
Для хостов вне кластера отправка логов осуществляется по HTTPS на внешний Ingress:
- **URL**: `https://loki.xinfra.ru/loki/api/v1/push`
- **Аутентификация**: HTTP Basic Auth (передача заголовка `Authorization: Basic <base64(user:pass)>`).
- **Валидация**: Traefik направляет запрос в Authelia forward-auth, которая проверяет учетные данные пользователя в LLDAP.
- **Пример настройки клиента (Alloy/Vector/Promtail на VPS)**:
  ```alloy
  loki.write "remote_loki" {
    endpoint {
      url = "https://loki.xinfra.ru/loki/api/v1/push"
      basic_auth {
        username = "YOUR_AUTHELIA_USER"
        password = "YOUR_AUTHELIA_PASSWORD"
      }
    }
    external_labels = {
      environment = "external",
      host        = "vps-01",
    }
  }
  ```

---

## 3. План реализации и структура файлов

1. **Манифест сервера Loki**:
   `clusters/my-cluster/releases/apps/loki.yaml` — `HelmRelease` чарта `loki` (SingleBinary, 10Gi PVC `longhorn-low`, 14d retention, Traefik Ingress).
2. **Манифест агента Alloy**:
   `clusters/my-cluster/releases/apps/alloy.yaml` — `HelmRelease` чарта `alloy` (DaemonSet, монтирование `/var/log/pods`, отправка в Loki).
3. **Манифест источника данных**:
   `clusters/my-cluster/releases/apps/loki-datasource.yaml` — `ConfigMap` с лейблом `grafana_datasource: "1"`.
4. **Регистрация в Kustomize**:
   `clusters/my-cluster/releases/apps/kustomization.yaml` — добавление 3 новых файлов в `resources:`.

---

## 4. Верификация и тестирование

1. **Статическая валидация**:
   - Проверка форматирования и структуры Kustomize: `kustomize build clusters/my-cluster/releases/apps > /dev/null`.
2. **Применение через Flux**:
   - `flux reconcile kustomization releases --with-source`
   - Контроль статуса релизов: `flux get hr -n monitoring loki alloy`.
3. **Проверка подов и хранилища**:
   - `kubectl get pods -n monitoring -l app.kubernetes.io/name=loki` $\rightarrow$ статус `Running 1/1`.
   - `kubectl get pvc -n monitoring` $\rightarrow$ PVC `loki` в статусе `Bound`, storageClass `longhorn-low`.
   - `kubectl get ds -n monitoring -l app.kubernetes.io/name=alloy` $\rightarrow$ 3/3 ready.
4. **Проверка визуализации в Grafana**:
   - Переход в `https://grafana.xinfra.ru/explore`.
   - Выбор источника данных `Loki`.
   - Выполнение запроса `{namespace="monitoring"}` $\rightarrow$ просмотр поступающих логов контейнеров.
5. **Проверка внешнего Ingress и авторизации**:
   - Тест неавторизованного доступа: `curl -I https://loki.xinfra.ru/loki/api/v1/push` (ожидается 302/401).
   - Тест авторизованного пуша: отправка пустого пакета с валидными Basic Auth креденшлами.

---

## 5. Граничные случаи и защита от сбоев
- **Переполнение диска**:
  - Loki compactor автоматически удаляет блоки старше 14 дней.
  - При неожиданном росте объема логов PVC на `longhorn-low` поддерживает онлайновое расширение (достаточно изменить `size: 10Gi` на `20Gi` в `loki.yaml`).
- **Шторм логов (Log Spikes)**:
  - `ingestion_rate_mb: 10` и `ingestion_burst_size_mb: 20` предохраняют узел от исчерпания памяти при зависании или спаме в логи одного из подов.
- **Временная недоступность Loki**:
  - Alloy буферизирует логи в оперативной памяти и повторяет попытки отправки, предотвращая потерю логов во время рестарта или обновления Loki.
