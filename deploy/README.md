# Production deployment

`docker-compose.prod.yml` is the production variant of the server Compose stack. Keep the
existing development Compose file at `app/docker-compose.yml` for local database work.

## Server setup

1. Copy `.env.prod.example` to `.env`, fill in the values, and use lowercase GHCR image names.
   `DPP_TAG` must be a release tag. The receiver updates this value after a successful deploy so
   later Compose operations continue to use the deployed version.
2. Configure the GHCR package as public, or give the server a read-only `read:packages` token in
   `GHCR_TOKEN`. Set `GHCR_USERNAME` to its owner. The host's Docker client also needs to be logged
   in to GHCR to pull the app and updater packages when starting or recreating the stack.
3. Add a Caddy route for the receiver to the existing site block. Keep it outside the OAuth2
   Proxy authentication flow; the receiver itself requires the bearer token:

   ```caddyfile
   handle /_deploy {
       rewrite * /deploy
       reverse_proxy updater:8090
   }
   ```

   Put this route before/beside the existing OAuth2 Proxy handling so `/_deploy` is not sent
   through the interactive login flow. The webhook URL is `https://<DOMAIN>/_deploy`; do not
   expose the Docker socket.
4. Start the stack with `docker compose -f docker-compose.prod.yml up -d`. The host must have the
   application and updater packages available from GHCR. The included `migration` service performs
   the initial schema upgrade; deployments run the migration from the requested image before
   replacing `app`.

The updater runs as a static Go binary in `scratch`. It uses the Docker Engine API over
`/var/run/docker.sock`, finds the Compose `app` container by project/service labels, and clones its
configuration for the migration and replacement containers. It waits for the new app's
unauthenticated `/healthz` endpoint before committing the new `DPP_TAG`; on failure it restores
the old container. Docker socket access is effectively host-root access. Restrict the webhook
route and use a long random `DEPLOY_TOKEN`.

Database migrations are forward-only; keep schema changes compatible with the currently running
app until the new container passes its health check. A failed app replacement restores the old
container but does not reverse a migration that already completed.

## GitHub configuration

The release workflow uses semantic-release on pushes to `main`: `feat:` commits cause minor
releases, `fix:` commits cause patch releases, and `!` or `BREAKING CHANGE:` causes a major release.
It creates a `vX.Y.Z` tag and GitHub release directly, then publishes both images to GHCR in the
same workflow run—there is no release PR. Commits without a release-worthy Conventional Commit type
do not publish images. Add these repository secrets for **Actions → Deploy**:

- `DEPLOY_WEBHOOK_URL`: the public `/_deploy` URL above.
- `DEPLOY_WEBHOOK_TOKEN`: the same value as the server's `DEPLOY_TOKEN`.

The manual workflow accepts a `vX.Y.Z` tag. It posts `{"tag":"vX.Y.Z"}` and waits for the
receiver to finish. The receiver supports private GHCR pulls using `GHCR_USERNAME` and
`GHCR_TOKEN` from the server's `.env`.
