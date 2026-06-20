# Flux Cluster — my-cluster

GitOps-репозиторий для Kubernetes-кластера `my-cluster` на `xinfra.ru`.
Управляется через FluxCD v2 с SOPS-шифрованием секретов (age).

## Структура

```
clusters/my-cluster/
├── flux-system/                        # Bootstrap Flux (не редактировать)
├── infrastructure/                     # Статические ресурсы кластера
│   ├── namespaces/                     # Namespace definitions
│   ├── cert-manager/                   # ClusterIssuer + Certificate (Let's Encrypt)
│   └── traefik/                        # RKE2 HelmChartConfig
├── sources/                            # Source CRDs (HelmRepository, GitRepository, OCIRepository)
├── releases/                           # HelmRelease CRDs
├── kustomizations/                     # Flux Kustomization CRD с ordering
└── secrets/                            # SOPS-encrypted secrets
```

## Порядок применения (depends_on)

1. `infrastructure` — namespaces, cert-manager CRDs, traefik
2. `sources` — HelmRepository, GitRepository, OCIRepository
3. `releases` — HelmRelease (cert-manager, reflector и др.)
   depends_on: infrastructure, sources

## Добавление нового HelmRelease

1. Добавить HelmRepository (если нет) в `sources/`
2. Создать HelmRelease в `releases/` или `releases/apps/`
3. Добавить секреты (если нужны) в `secrets/` с суффиксом `.enc.yaml`

## Управление секретами

Секреты шифруются SOPS с age-ключом:

```bash
sops --encrypt --in-place clusters/my-cluster/secrets/my-secret.yaml
```

Трекинг: только файлы с суффиксом `*.enc.yaml` (настроено в `.gitignore`).

## Разработка

```bash
devenv shell        # войти в dev-окружение
kustomize build clusters/my-cluster/infrastructure  # проверить сборку
flux diff kustomization infrastructure              # посмотреть diff
```
