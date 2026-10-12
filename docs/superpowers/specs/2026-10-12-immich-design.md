# Дизайн-документ: Развертывание Immich в кластере Kubernetes через Flux CD

## 1. Цели и Контекст
- **Цель**: Надежное селф-хостинг решение Immich для автоматического бэкапа фото и видео со смартфонов пользователя и семьи.
- **Инфраструктура**:
  - GitOps: Flux CD v2.
  - Ingress: Traefik + cert-manager (`wildcard-xinfra-ru-tls`), хост `immich.xinfra.ru`.
  - Storage: Longhorn CSI (storageClass `longhorn-low`).
  - База данных: Отдельный CNPG кластер с расширением векторов (pgvecto.rs).
  - Резервное копирование:
    - БД: Barman Object Store в S3 (`s3.twcstorage.ru`, бакет `a353ae34-e55f-4d81-b4fd-902fffed4427`).
    - Медиа: Longhorn PVC `immich-library` (100Gi стартово) с возможностью онлайн-расширения и бэкапов Longhorn.

---

## 2. Архитектура и Компоненты

### 2.1. База данных (CNPG PostgreSQL 16 + pgvecto.rs)
- **Имя кластера**: `immich-postgres` в namespace `database`.
- **Образ**: `ghcr.io/tensorchord/cloudnative-pgvecto.rs:16-v0.8.4` (официальный образ для CNPG с поддержкой pgvecto.rs).
- **Экземпляры**: 1 инстанс (для домашнего сетапа с Longhorn, storage: 15Gi под данные, 5Gi под WAL).
- **Параметры**:
  - `shared_preload_libraries: "vectors.so"`
  - `search_path: '"$user", public, vectors'`
- **Резервное копирование Barman S3**:
  - `endpointURL`: `https://s3.twcstorage.ru`
  - `destinationPath`: `s3://a353ae34-e55f-4d81-b4fd-902fffed4427/immich-cnpg`
  - `s3Credentials`: SOPS-зашифрованный Secret с Access Key и Secret Key.
  - `wal.compression`: `gzip`.
  - `ScheduledBackup`: Ежедневно в 03:00 UTC.

### 2.2. Хранилище (Longhorn PVCs)
- **Библиотека фото (`immich-library`)**:
  - Namespace: `apps`
  - Начальный объем: `100Gi` (с поддержкой расширения `allowVolumeExpansion: true`).
  - StorageClass: `longhorn-low`.
  - AccessMode: `ReadWriteOnce`.
- **Кэш моделей ML (`immich-ml-cache`)**:
  - Объем: `10Gi` (для кэширования моделей CLIP / распознавания лиц).

### 2.3. Immich Helm Release (`oci://ghcr.io/immich-app/immich-charts/immich`)
- **Namespace**: `apps`.
- **Зависимости Flux (`dependsOn`)**:
  - `cnpg` в `database` (оператор БД).
- **Компоненты**:
  - **Server**: Обработка API, мобильных клиентов и Web UI.
  - **Machine Learning**: Включен, с ограничениями ресурсов (CPU requests: `200m`, limits: `1500m`, memory requests: `512Mi`, limits: `2Gi`).
  - **Redis**: Встроенный redis subchart для очередей заданий Immich.
- **Traefik Ingress**:
  - Хост: `immich.xinfra.ru`.
  - TLS: `wildcard-xinfra-ru-tls`.
  - Traefik Middleware `immich-buffering`: отключает ограничение размера запроса (`buffering.maxRequestBodyBytes: 0`), предотвращая ошибку `413 Request Entity Too Large` при заливке больших видеофайлов.

---

## 3. План реализации и структура файлов

1. **Секреты (`clusters/my-cluster/secrets/immich.enc.yaml`)**:
   - SOPS-зашифрованные креденшлы:
     - Ключи S3 (Access Key, Secret Key).
     - Пароль пользователя БД `immich`.
2. **База данных (`clusters/my-cluster/releases/apps/immich-postgres.yaml`)**:
   - Манифест `Cluster` (CNPG) с pgvecto.rs и секцией `backup.barmanObjectStore`.
   - Манифест `ScheduledBackup` для регулярного создания снапшотов БД.
3. **Приложение (`clusters/my-cluster/releases/apps/immich.yaml`)**:
   - `PersistentVolumeClaim` для `immich-library` (100Gi).
   - Traefik `Middleware` для больших загрузок.
   - `HelmRelease` Immich с настройками подключения к `immich-postgres` и внешнему Traefik Ingress.
4. **Связка Kustomize (`clusters/my-cluster/releases/apps/kustomization.yaml`)**:
   - Добавление `immich-postgres.yaml` и `immich.yaml`.
5. **Валидация**:
   - Проверка локальной сборки манифестов через `kustomize build`.
