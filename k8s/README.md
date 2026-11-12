# Kubernetes manifests (k3s + flux)

This directory is the GitOps source for the application stack. Postgres and all
cluster plumbing live in the infra repo (`m-gora/cluster-config`); this repo owns
everything from the Gateway route down to the app container.

## Layout

```
k8s/
  migrations/        # flux Kustomization #1 (applied first)
    namespace.yaml               # dpp
    postgres-externalname.yaml   # stable alias -> postgres-rw.postgres.svc.cluster.local
    secret-dpp-db.yaml           # SOPS: DATABASE_URL (host "postgres" via the alias)
    migration-job.yaml           # alembic upgrade head
  app/               # flux Kustomization #2 (dependsOn #1)
    configmap.yaml               # non-secret env (app + oauth2-proxy sidecar)
    secrets-sops.yaml            # SOPS: dpp-auth (Auth0), dpp-app (SESSION_SECRET, AI keys)
    service.yaml                 # 8000 (dpp) + 4180 (oauth2-proxy)
    deployment.yaml              # dpp + oauth2-proxy sidecar, probes on /healthz and /ping
    middleware-forwardauth.yaml  # Traefik Middleware: forwardAuth + authResponseHeaders
    middleware-staticheaders.yaml# Traefik Middleware: static X-User-Roles / X-District-Scopes
    httproute.yaml               # Gateway API route -> cluster Gateway, dpp.cloud.marcodoes.tech
    httproute-healthz.yaml       # exact /healthz route, bypasses forward-auth
```

The two trees are separate because a single flux Kustomization would apply the
Job and Deployment simultaneously (app crash-loops until the migration is
done). `dpp-app` registers with `dependsOn: [dpp-migrations]` so the schema
exists before the app starts. Namespace, ExternalName, and the `dpp-db` secret
are applied by the migrations tree; the app tree only references them by name
(kustomize/flux cannot load resources above a Kustomization's directory).

## Flux registration (one-time, imperative)

```bash
flux create source git dpp \
  --url=ssh://git@github.com/m-gora/digital-politics-platform \
  --branch=main --interval=1m

flux create kustomization dpp-migrations \
  --source-ref=dpp --path=./k8s/migrations \
  --prune --interval=10m \
  --decryption-provider=sops --decryption-secret=sops-age

flux create kustomization dpp-app \
  --source-ref=dpp --path=./k8s/app \
  --prune --interval=10m \
  --depends-on=dpp-migrations \
  --decryption-provider=sops --decryption-secret=sops-age
```

These objects live in etcd only (ArgoCD-style imperative app registration): a
cluster rebuild needs the three commands re-run. `flux export` them into
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

Values come from the legacy server's `.env`; the Auth0 application stays the
same but its callback/logout URLs must be updated to
`https://dpp.cloud.marcodoes.tech` once at cutover.

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
for tree in migrations app; do
  rm -rf /tmp/k8s-$tree && mkdir -p /tmp/k8s-$tree
  for f in k8s/$tree/*.yaml; do
    sops -d "$f" > "/tmp/k8s-$tree/$(basename "$f")" 2>/dev/null || cp "$f" "/tmp/k8s-$tree/$(basename "$f")"
  done
  kubectl kustomize /tmp/k8s-$tree | kubectl apply --dry-run=client -f -
done
```

(Plain `kubectl kustomize` does not decrypt SOPS secrets; flux does that
during reconcile.)

## Image tags

Both `deployment.yaml` and `migration-job.yaml` pin the same image tag; keep
them in sync. Dependabot bumps the tag (docker ecosystem, grouped PR —
`.github/dependabot.yml`). If dependabot turns out not to read image entries
in these manifests, switch to renovate, which supports kustomize natively.

## Cutover checklist

1. Fill real values into the SOPS secrets (`sops k8s/migrations/secret-dpp-db.yaml`,
   `sops k8s/app/secrets-sops.yaml`), commit.
2. Register flux (commands above); watch `flux get kustomizations -A`.
3. Reseed the DB (`uv run python -m dpp.seed`), then replace the
   `REPLACE-ME` district scope in `middleware-staticheaders.yaml` with the
   seeded district UUID(s) and merge.
4. Update the Auth0 app's callback/logout URLs to
   `https://dpp.cloud.marcodoes.tech`; set `OAUTH2_PROXY_OIDC_ISSUER_URL` in
   `k8s/app/configmap.yaml` to the real tenant.
5. Tear down the legacy Compose stack; external-dns creates the
   `dpp.cloud.marcodoes.tech` record once the HTTPRoute reconciles.
