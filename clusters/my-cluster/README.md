# Flux Cluster — my-cluster

GitOps-репозиторий для Kubernetes-кластера `my-cluster` на `xinfra.ru`.
Управляется через FluxCD v2 с SOPS-шифрованием секретов (age).

## Структура

```
clusters/my-cluster/
├── flux-system/                        # Bootstrap Flux (не редактировать)
├── infrastructure/                     # Статические ресурсы кластера (namespaces, middlewares, storageclasses, traefik, flux-operator)
│   ├── namespaces/                     # Определение namespaces и middlewares
│   ├── cert-manager/                   # ClusterIssuer + Certificate (Let's Encrypt)
│   ├── storage/                        # StorageClasses (local-path, longhorn-low)
│   ├── traefik/                        # Traefik HelmRelease и TLSOption
│   └── flux-operator.yaml              # Flux Operator (Source, HelmRelease, Ingress)
├── sources/                            # Source CRDs (helm-repositories.yaml, git-repositories, image-automation)
├── releases/                           # Базовые инфраструктурные HelmReleases (cert-manager, reflector)
│   └── apps/                           # HelmRelease приложений, IngressRoutes и единый pvcs.yaml
├── kustomizations/                     # Flux Kustomization CRD (stages.yaml)
└── secrets/                            # SOPS-encrypted secrets (*.enc.yaml)
```

## Порядок применения (depends_on)

1. `infrastructure` — namespaces, middlewares, storageclasses, traefik, flux-operator
2. `sources` — каталог helm-repositories, git-repositories, image-automation
3. `releases` — cert-manager, reflector (depends_on: infrastructure, sources)
4. `secrets` — SOPS-зашифрованные секреты (depends_on: infrastructure)
5. `cert-manager-configs` — ClusterIssuer и wildcard certificate (depends_on: releases, secrets)
6. `apps` — HelmRelease приложений и pvcs (depends_on: cert-manager-configs)

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
