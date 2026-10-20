# Дизайн-документ: Мониторинг внешних VPS-серверов и VPN 3x-ui (Prometheus + Loki + Grafana)

## 1. Контекст и Цели
- **Цель**: Создать единый, информативный и удобный Grafana Dashboard для мониторинга состояния, сетевого трафика, устойчивости и логов внешних VPS-серверов (`vpn-timeweb`, `vpn-finka`), обслуживающих VPN на базе `3x-ui` (Xray).
- **Стек телеметрии**:
  - Метрики: `node_exporter` на внешних VPS, отправляющий метрики в Prometheus кластера через `remote_write` (`job="prometheus.scrape.node_exporter"`).
  - Логи: `grafana alloy` на внешних VPS, отправляющий системные логи (`systemd-journal`) в Loki кластера (`instance="vpn-timeweb"`, `instance="vpn-finka"`).
  - Алертинг: `PrometheusRule` в namespace `monitoring`, уведомления через существующий Alertmanager в `ntfy`.
  - Управление: GitOps через Flux CD v2.

---

## 2. Архитектура интеграции и связка данных (Correlation)

### 2.1. Идентификаторы и сопоставление сущностей
В ходе проверки реального кластера зафиксировано 100% совпадение ключевых лейблов между источниками данных:
- В **Prometheus**:
  - `instance`: `vpn-timeweb`, `vpn-finka`
  - `job`: `prometheus.scrape.node_exporter`
- В **Loki**:
  - `instance`: `vpn-timeweb`, `vpn-finka`
  - `job`: `systemd-journal`
  - `service_name`: `systemd-journal`

Это позволяет использовать единую переменную дашборда `$instance` для одновременной и синхронной фильтрации графиков метрик и окна логов.

### 2.2. Переменные дашборда (Dashboard Variables)
1. **`$instance`** (Query, Multi-value: false, Include All: true):
   - Запрос: `label_values(node_uname_info{job="prometheus.scrape.node_exporter"}, instance)`
   - Значения: `vpn-timeweb`, `vpn-finka`
2. **`$interface`** (Query, Multi-value: false, Include All: false):
   - Запрос: `label_values(node_network_receive_bytes_total{instance=~"$instance"}, device)`
   - Regex фильтр: `/^(eth.*|ens.*)$/` (автоматически отсекает `lo`, `docker0`, `br-*`, `veth*`)
   - Текущие интерфейсы: `eth0` на timeweb, `ens3` на finka.
3. **`$log_search`** (Text box):
   - Свободный текстовый поиск по содержимому логов с регистронезависимой фильтрацией: `|~ "(?i)$log_search"`.

---

## 3. Структура и состав дашборда Grafana

Дашборд реализуется в одном JSON-документе, разбитом на 5 логических строк (Rows):

### Строка 1: Главный статус и здоровье хоста (Quick Health Bar)
Компактные карточки `stat`:
1. **VPS Status**:
   - Запрос: `up{job="prometheus.scrape.node_exporter", instance=~"$instance"}`
   - Отображение: 1 $\rightarrow$ `ONLINE` (зеленый), 0 $\rightarrow$ `OFFLINE` (красный).
2. **3x-ui Service**:
   - Запрос: `node_systemd_unit_state{job="prometheus.scrape.node_exporter", instance=~"$instance", name="x-ui.service", state="active"}`
   - Отображение: 1 $\rightarrow$ `ACTIVE` (зеленый), 0 $\rightarrow$ `FAILED/DOWN` (красный).
3. **Host Uptime**:
   - Запрос: `time() - node_boot_time_seconds{job="prometheus.scrape.node_exporter", instance=~"$instance"}`
   - Формат: `time: d"d" h"h" m"m"`.
4. **CPU Usage %**:
   - Запрос: `100 - (avg by (instance) (rate(node_cpu_seconds_total{job="prometheus.scrape.node_exporter", instance=~"$instance", mode="idle"}[5m])) * 100)`
   - Пороги: 0-70% (зеленый), 70-85% (желтый), 85-100% (красный).
5. **RAM Usage %**:
   - Запрос: `((node_memory_MemTotal_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance"} - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes) * 100`
   - Пороги: 0-75% (зеленый), 75-90% (желтый), 90-100% (красный).
6. **Disk Root Usage %**:
   - Запрос: `(1 - (node_filesystem_avail_bytes{job="prometheus.scrape.node_exporter", instance=~"$instance", mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100`
   - Пороги: 0-75% (зеленый), 75-85% (желтый), 85-100% (красный).
7. **Active Connections (Conntrack)**:
   - Запрос: `node_nf_conntrack_entries{job="prometheus.scrape.node_exporter", instance=~"$instance"}`
   - Индикатор нагрузки VPN-сессий.

### Строка 2: Сеть и трафик VPN (Network & Bandwidth)
1. **Network Bandwidth (Mbps)** (Time series):
   - Ingress: `rate(node_network_receive_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[1m]) * 8`
   - Egress: `rate(node_network_transmit_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[1m]) * 8`
   - Единицы: `bps (bits/sec)` с автошкалированием (Kbps, Mbps, Gbps).
2. **Total Transferred Volume** (Bar gauge / Stat):
   - Запрос: `increase(node_network_receive_bytes_total{job="prometheus.scrape.node_exporter", instance=~"$instance", device=~"$interface"}[$__range]) + increase(node_network_transmit_bytes_total{device=~"$interface"}[$__range])`
   - Единицы: `bytes` (GB, TB за период).
3. **Packets Rate & Drops/Errors** (Time series):
   - Запросы:
     - Drops: `rate(node_network_receive_drop_total{instance=~"$instance", device=~"$interface"}[1m])` и `rate(node_network_transmit_drop_total[1m])`
     - Errors: `rate(node_network_receive_errs_total{instance=~"$instance", device=~"$interface"}[1m])` и `rate(node_network_transmit_errs_total[1m])`

### Строка 3: Ресурсы и системный стек (Host Internals — Collapsible Row)
1. **CPU Usage Breakdown** (Time series, stacked):
   - Запрос: `sum by (mode) (rate(node_cpu_seconds_total{job="prometheus.scrape.node_exporter", instance=~"$instance"}[5m]))`
   - Разделение: user, system, iowait, softirq.
2. **Memory Breakdown** (Time series, stacked):
   - Запросы: Used, Buffers, Cached, Free, Swap Used.
3. **Disk I/O Rate & Utilization** (Time series):
   - Запросы: `rate(node_disk_read_bytes_total[1m])`, `rate(node_disk_written_bytes_total[1m])`.

### Строка 4: Безопасность и стек соединений (Connection Stack & Security)
1. **TCP Sockets Breakdown** (Time series):
   - Запросы: `node_sockstat_TCP_alloc`, `node_sockstat_TCP_inuse`, `node_sockstat_TCP_tw`.
2. **Conntrack Table Saturation %** (Gauge):
   - Запрос: `(node_nf_conntrack_entries{instance=~"$instance"} / node_nf_conntrack_entries_limit) * 100`.
   - Порог тревоги: > 80%.

### Строка 5: Логирование Loki в реальном времени (Correlated Logs Stream)
1. **Logs Volume Histogram** (Bar chart):
   - Запрос: `sum by (detected_level) (count_over_time({job="systemd-journal", instance=~"$instance"}[$__interval]))`
2. **Live Logs Stream** (Logs panel):
   - Запрос LogQL: `{job="systemd-journal", instance=~"$instance"} |~ "(?i)$log_search"`
   - Настройки: перенос строк, показ меток уровня (`detected_level`), временная шкала.

---

## 4. Правила алертинга (PrometheusRule)

Манифест `vps-alerts.yaml` разворачивается в namespace `monitoring` с меткой `role: alert-rules`:

1. **`VpsNodeDown`** (Critical):
   - `up{job="prometheus.scrape.node_exporter"} == 0` (for: 2m)
   - Summary: `VPS инстанс {{ $labels.instance }} недоступен`
   - Description: `Узел {{ $labels.instance }} не отвечает более 2 минут.`
2. **`VpsXuiServiceDown`** (Critical):
   - `node_systemd_unit_state{job="prometheus.scrape.node_exporter", name="x-ui.service", state="active"} == 0` (for: 1m)
   - Summary: `Служба 3x-ui на {{ $labels.instance }} остановлена или упала`
   - Description: `Служба x-ui.service не активна. VPN недоступен.`
3. **`VpsDiskSpaceWarning` / `VpsDiskSpaceCritical`** (Warning / Critical):
   - `(node_filesystem_avail_bytes{job="prometheus.scrape.node_exporter", mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 < 15` (Warning, for: 5m)
   - `... < 5` (Critical, for: 5m)
   - Summary: `Мало свободного места на диске {{ $labels.instance }}`
4. **`VpsHighCpuUsage`** (Warning):
   - `100 - (avg by (instance) (rate(node_cpu_seconds_total{job="prometheus.scrape.node_exporter", mode="idle"}[5m])) * 100) > 90` (for: 10m)
   - Summary: `Высокая нагрузка CPU на {{ $labels.instance }} (> 90%)`
5. **`VpsHighMemoryUsage`** (Warning):
   - `((node_memory_MemTotal_bytes{job="prometheus.scrape.node_exporter"} - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes) * 100 > 90` (for: 5m)
   - Summary: `Высокое потребление памяти на {{ $labels.instance }} (> 90%)`
6. **`VpsConntrackTableAlmostFull`** (Critical):
   - `(node_nf_conntrack_entries{job="prometheus.scrape.node_exporter"} / node_nf_conntrack_entries_limit) * 100 > 85` (for: 5m)
   - Summary: `Таблица conntrack на {{ $labels.instance }} заполнена более чем на 85%`
   - Description: `Риск отбрасывания новых VPN-соединений ядром Linux.`
7. **`VpsNetworkPacketDrops`** (Warning):
   - `(rate(node_network_receive_drop_total{job="prometheus.scrape.node_exporter", device=~"eth.*|ens.*"}[5m]) + rate(node_network_transmit_drop_total[5m])) > 50` (for: 5m)
   - Summary: `Потери пакетов на интерфейсе {{ $labels.device }} ({{ $labels.instance }})`

---

## 5. Файлы и план реализации в GitOps

### Создаваемые и изменяемые файлы:
1. `clusters/my-cluster/releases/apps/vps-nodes-dashboard.yaml` — ConfigMap с JSON дашборда (метка `grafana_dashboard: "1"`, аннотация `kustomize.toolkit.fluxcd.io/substitute: disabled`).
2. `clusters/my-cluster/releases/apps/vps-alerts.yaml` — `PrometheusRule` с группой правил `vps.rules`.
3. `clusters/my-cluster/releases/apps/kustomization.yaml` — регистрация 2 новых манифестов в `resources:`.

---

## 6. Верификация

1. **Синтаксическая проверка**:
   - `kustomize build clusters/my-cluster/releases/apps > /dev/null`
   - Валидация сгенерированного JSON скриптом python.
2. **GitOps применение**:
   - `flux reconcile kustomization releases --with-source`
3. **Проверка в рантайме**:
   - Проверка создания ConfigMap и PrometheusRule в кластере:
     `kubectl get cm,prometheusrule -n monitoring -l grafana_dashboard=1`
   - Проверка правил в Prometheus:
     проверка группы `vps.rules` на `http://localhost:19090/api/v1/rules`.
   - Проверка появления дашборда в Grafana на `https://grafana.xinfra.ru`.
