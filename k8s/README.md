# Kubernetes manifests (k3s + flux)

This directory is the GitOps source for the application stack. Postgres and all
cluster plumbing live in the infra repo (`m-gora/cluster-config`); this repo owns
everything from the Gateway route down to the app container.

## Layout

```
k8s/app/                       # single flux Kustomization
  namespace.yaml               # dpp
  postgres-externalname.yaml   # stable alias -> postgres-rw.postgres.svc.cluster.local
  secret-dpp-db.yaml           # SOPS: DATABASE_URL (host "postgres" via the alias)
  secrets-sops.yaml            # SOPS: dpp-auth (Auth0), dpp-app (SESSION_SECRET, AI keys)
  configmap.yaml               # non-secret env (app + oauth2-proxy sidecar), via configMapGenerator
  gliederungen.yaml            # Gliederung config (arch-02), via configMapGenerator, mounted as file
  service.yaml                 # 8000 (dpp) + 4180 (oauth2-proxy)
  deployment.yaml              # migrations initContainer + dpp + oauth2-proxy sidecar
  middleware-forwardauth.yaml  # Traefik Middleware: forwardAuth + authResponseHeaders
  httproute.yaml               # Gateway API route -> cluster Gateway, dpp.cloud.marcodoes.tech
  httproute-healthz.yaml       # exact /healthz route, bypasses forward-auth
```

Migrations run as an **initContainer** (`alembic upgrade head`, idempotent)
inside the dpp pod, not as a standalone Job: k8s Jobs are immutable, so a
dependabot image bump re-applied by flux would fail on an existing Job. With
the initContainer there is exactly one Kustomization and no ordering problem.

Both `dpp-config` and `dpp-gliederungen` are produced by `configMapGenerator`;
kustomize hash-suffixes their names, so any config change (including the
Gliederung YAML) rolls the pod automatically on the next flux reconcile.

## Flux registration (one-time, imperative)

```bash
# One-time: generate the pull secret (keypair + GitHub host key)
flux create secret git dpp-git-auth --namespace flux-system \
  --url=ssh://git@github.com/m-gora/digitalpolitics
# Add the printed public key as a read-only deploy key in GitHub:
# https://github.com/m-gora/digitalpolitics/settings/keys

flux create source git dpp \
  --url=ssh://git@github.com/m-gora/digitalpolitics \
  --branch=main --interval=1m \
  --secret-ref=dpp-git-auth

flux create kustomization dpp \
  --source-ref=dpp --path=./k8s/app \
  --prune --interval=10m \
  --decryption-provider=sops --decryption-secret=sops-age
```

These objects live in etcd only (ArgoCD-style imperative app registration): a
cluster rebuild needs the two commands re-run. `flux export` them into
cluster-config later if you want GitOps DR. The `cluster-config` root
Kustomization does not touch them (its prune only covers its own inventory).

## Secrets (SOPS)

Secrets are encrypted in git; flux decrypts with the age key stored in
`flux-system/sops-age`. Only `data`/`stringData` are encrypted, so diffs and
reviews stay readable. `.sops.yaml` at the repo root holds the rules.

- Private key lives in the cluster (`flux-system/sops-age`) and in the
  operator's personal backup (`~/.config/sops/age/keys.txt`,
  `SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt` for local sops use).
  **Back it up** — a lost key means re-entering every secret by hand.
- View/edit a secret: `sops k8s/app/secrets-sops.yaml` (local decrypt/encrypt).
- Create a new one: write plaintext, then
  `sops --encrypt --in-place --encrypted-regex '^(data|stringData)$' file.yaml`.

Secret contents:

| Secret | Keys |
|---|---|
| `dpp-db` | `DATABASE_URL` (`postgresql+asyncpg://user:pass@postgres:5432/dpp`) |
| `dpp-auth` | `OAUTH2_PROXY_CLIENT_ID`, `OAUTH2_PROXY_CLIENT_SECRET`, `OAUTH2_PROXY_COOKIE_SECRET` |
| `dpp-app` | `SESSION_SECRET`, `GOOGLE_API_KEY` / `OPENAI_API_KEY`, `TYPESAFE_API_KEY` |

## Gliederung config (arch-02)

`k8s/app/gliederungen.yaml` is the deployed copy of the party unit hierarchy —
the same file the app bundles as `app/config/gliederungen.yaml` for local
development. **Keep the two copies in sync** (the k8s copy is what the
initContainer-less prod pods actually read via `DPP_GLIEDERUNGEN_FILE`);
a ConfigMap edit rolls the pods automatically. Slugs are stable identifiers:
add districts freely, never rename or remove one while campaigns/initiatives
reference it.

## Auth0 wiring (see docs/auth0-action.js)

- Issuer: `https://auth.marcodoes.tech/` (verified custom domain; tokens
  issued through the hosted login carry `iss=auth.marcodoes.tech`).
- App callback/logout URLs: `https://dpp.cloud.marcodoes.tech/*`.
- Groups claim: an Auth0 Action injects the user's Gliederung memberships
  (`app_metadata.gliederungen`) as the `https://dpp/groups` claim;
  `OAUTH2_PROXY_OIDC_GROUPS_CLAIM` makes oauth2-proxy emit it as
  `X-Auth-Request-Groups`, which Traefik relays (listed in
  `authResponseHeaders`) and `dpp.gliederungen` expands to district scopes
  (adr-03). There is no static roles/scopes injection anywhere.

## Contract with the infra repo

Postgres is reachable as `postgres-rw.postgres.svc.cluster.local` (namespace
`postgres`). The app's DB credentials live in this repo (SOPS) and must match a
role/password configured on that instance (`dpp-db` Secret in ns `postgres`
holds them for the postgres container). Postgres needs the `postgis` and
`vector` extensions created in the `dpp` database before
`alembic upgrade head` runs (a fresh DB needs
`CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS vector;`).

## Validation

```bash
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
rm -rf /tmp/k8s-app && mkdir -p /tmp/k8s-app
for f in k8s/app/*.yaml; do
  sops -d "$f" > "/tmp/k8s-app/$(basename "$f")" 2>/dev/null || cp "$f" "/tmp/k8s-app/$(basename "$f")"
done
kubectl kustomize /tmp/k8s-app | kubectl apply --dry-run=client -f -
```

(Plain `kubectl kustomize` does not decrypt SOPS secrets; flux does that
during reconcile.)

## Image tags

`deployment.yaml` pins the image once and uses it for both the migrate
initContainer and the app container — they can never diverge. Dependabot bumps
the tag (docker ecosystem, `.github/dependabot.yml`).

## Cutover checklist

1. Fill real values into the SOPS secrets (`sops k8s/app/secret-dpp-db.yaml`,
   `sops k8s/app/secrets-sops.yaml`), commit.
2. Register flux (commands above); watch `flux get kustomizations -A`.
3. Create the Auth0 Action (docs/auth0-action.js), set the Auth0 app's
   callback/logout URLs to `https://dpp.cloud.marcodoes.tech`.
4. Reseed the DB (drop + re-create or truncate; the schema migrates itself on
   pod start), then run `uv run python -m dpp.seed`.
5. Tear down the legacy Compose stack; external-dns creates the
   `dpp.cloud.marcodoes.tech` record once the HTTPRoute reconciles.
