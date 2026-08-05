# Deployment

Four supported targets. They differ in operational cost, not in the application
— the same two images, or the same two build artefacts, run in all of them.

| Target | Best for | Throughput | Effort |
|---|---|---|---|
| **Docker Compose** | A single box, or a staging environment | High | Lowest |
| **Azure App Service** | Managed, scaled, CI-deployed | High | Medium |
| **Linux VPS** | Full control, lowest running cost | High | Medium |
| **cPanel** | Shared hosting, when it is the only option | Low — see the caveat | Highest |

---

## The short version

```bash
python3 deploy.py
```

`deploy.py` at the repository root automates everything below that *can* be
automated. It runs the test suites first, refuses to continue on a red build,
and asks before touching any machine other than this one.

| | Automated by `deploy.py` |
|---|---|
| Docker Compose | **Fully** — build, start, migrate, seed, health-check, roll back |
| Linux VPS | **Yes, over SSH** — after the one-time host setup below |
| Azure | **Yes** — after `az login` and the registry/resource group exist |
| cPanel | **No** — builds the bundle and prints the checklist |

Useful flags: `--check` (preflight only), `--dry-run` (print commands, change
nothing), `--skip-tests`, `--yes`, `--keep-on-failure`.

The rest of this document is what `deploy.py` is doing, and what to do when it
cannot do it for you.

---

## Before any deployment

### Generate a secret key

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

This signs access tokens. Changing it signs every existing session out, so
treat it as permanent and store it wherever that environment keeps secrets.

### Understand the production guard

Setting `ENVIRONMENT=production` turns on a start-up check that **refuses to
boot** on any of the following:

- `SECRET_KEY` unset or shorter than 32 characters
- `DEBUG` true
- `REFRESH_COOKIE_SECURE` false
- `HSTS_ENABLED` false
- `RATE_LIMIT_ENABLED` false
- `CORS_ORIGINS` containing `localhost`, `127.0.0.1`, or `*`
- `DATABASE_URL` pointing at SQLite
- `EMAIL_BACKEND=console` — mail would go to the log
- `FRONTEND_URL` not `https`

Every one of these is something that *works* while being wrong, which is why
the process would rather not start than run with it. All problems are reported
in a single message, so one failed boot tells you the whole list.

### Run the tests against PostgreSQL

SQLite ignores `VARCHAR` length limits; PostgreSQL enforces them. That
difference has already hidden one production bug (see `PART10.md`), so run the
suite against the dialect you deploy on:

```bash
docker run -d --rm --name pg -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=nlp_ci -p 55432:5432 postgres:17-alpine
cd backend
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/nlp_ci" pytest -q
```

CI does this on every pull request.

---

## 1. Docker Compose

The fastest route to a working deployment, and what `docker-compose.yml`
describes: PostgreSQL, the API, and nginx serving the bundle.

```bash
cp backend/.env.example .env      # then edit
docker compose up --build -d
docker compose exec api python -m app.seeds
```

Serves on `http://localhost:8080`. For anything public, put a TLS terminator in
front (Caddy, Traefik, or nginx with certbot) and set the production
environment variables on the `api` service.

**Migrations** run on container start (`alembic upgrade head` in the compose
command). That is fine for one instance. With more than one, move migrations
into a separate one-shot step — two containers booting together will race.

---

## 2. Azure App Service

`infra/azure/main.bicep` provisions everything: two Linux App Services on one
plan, a Flexible Server for PostgreSQL, and a Key Vault the API reads through
its **managed identity**, so no connection string is ever stored in an app
setting.

```bash
az group create --name nlp-prod --location uksouth

az keyvault secret set --vault-name nlp-prod-kv \
  --name jwt-secret-key --value "$(python -c 'import secrets;print(secrets.token_urlsafe(64))')"

az deployment group create \
  --resource-group nlp-prod \
  --template-file infra/azure/main.bicep \
  --parameters @infra/azure/main.parameters.json \
  --parameters imageTag="$(git rev-parse HEAD)" dbAdminPassword='...'
```

`.github/workflows/deploy-azure.yml` does this on a `v*` tag, authenticating
with OIDC federated credentials — there is no long-lived Azure secret in
GitHub. Required repository secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID`, `ACR_NAME`, `AZURE_RESOURCE_GROUP`,
`DB_ADMIN_PASSWORD`.

**Images are tagged with the commit SHA, never `latest`.** A mutable tag makes
"which build is running?" unanswerable during an incident, and turns a rollback
into a rebuild.

Rolling back is redeploying the previous SHA:

```bash
az webapp config container set --name nlp-prod-api --resource-group nlp-prod \
  --docker-custom-image-name "nlpregistry.azurecr.io/nlp-api:<previous-sha>"
```

Two things the Bicep leaves deliberately simple, to be tightened when the
deployment justifies it: the PostgreSQL firewall uses the "allow Azure
services" rule rather than VNet integration with a private endpoint, and both
sites share one App Service plan.

---

## 3. Linux VPS

Full control, and the cheapest way to run this properly. Everything is in
`infra/vps/`.

### One-time setup

```bash
sudo adduser --system --group --home /opt/nlp nlp
sudo apt install -y python3.12-venv postgresql nginx certbot python3-certbot-nginx
sudo -u postgres createuser nlp --pwprompt
sudo -u postgres createdb network_learning --owner nlp

sudo mkdir -p /etc/nlp /var/log/nlp
sudo install -m 0640 -o root -g nlp infra/vps/api.env.example /etc/nlp/api.env
sudo -e /etc/nlp/api.env          # fill in every CHANGE_ME

sudo cp infra/vps/nlp-api.service /etc/systemd/system/
sudo cp infra/vps/nlp-security-headers.conf /etc/nginx/snippets/
sudo cp infra/vps/nginx-site.conf /etc/nginx/sites-available/nlp
sudo ln -s /etc/nginx/sites-available/nlp /etc/nginx/sites-enabled/nlp
sudo certbot --nginx -d learn.example.com
sudo systemctl daemon-reload && sudo systemctl enable --now nlp-api
```

### Deploying

```bash
sudo ./infra/vps/deploy.sh /path/to/checkout
```

Builds into a timestamped release directory, migrates, swaps three symlinks,
restarts, and **rolls back automatically if the health check does not pass**
within a minute. Keeps the last five releases.

The systemd unit is sandboxed: `ProtectSystem=strict`, no new privileges, a
system-call filter, and one writable path. A compromised worker has very little
reachable surface.

---

## 4. cPanel

**Read this before choosing cPanel.** cPanel runs Python under Passenger, which
speaks WSGI. This application is ASGI, so it runs through a bridge
(`a2wsgi`) — every request occupies a worker for its whole duration and the
async database driver's concurrency advantage is lost. It works correctly and
is fully supported here, but expect several times less throughput than the
other three targets on the same hardware. Choose it when shared hosting is the
constraint, not by preference.

1. **cPanel → Setup Python App**: Python 3.12, application root `nlp`,
   application URL `/api`, startup file `passenger_wsgi.py`.
2. Upload `backend/` into the application root, and
   `infra/cpanel/passenger_wsgi.py` beside it.
3. In the virtualenv cPanel prints:
   ```bash
   pip install -e ./backend
   pip install a2wsgi
   ```
4. Add every variable from `infra/vps/api.env.example` in the app's
   **Environment Variables** panel.
5. From the cPanel terminal: `alembic upgrade head`, then
   `python -m app.seeds`.
6. Build the frontend locally (`npm run build`) and upload `dist/` into
   `public_html`, with `infra/cpanel/.htaccess` beside it.
7. Restart the app from the cPanel panel.

The `.htaccess` handles HTTPS redirection, SPA routing, immutable caching for
hashed assets, and the same security headers as the other targets.

---

## Post-deployment checklist

```bash
# Health, and the database behind it
curl -fsS https://learn.example.com/api/v1/health
curl -fsS https://learn.example.com/api/v1/health/ready

# Security headers are actually being sent
curl -sI https://learn.example.com | grep -iE 'strict-transport|content-security|x-frame'

# Interactive docs are closed in production
curl -s -o /dev/null -w '%{http_code}\n' https://learn.example.com/api/v1/docs   # expect 404
```

Then, in the application:

- [ ] Register the administrator account **first**, before announcing the URL —
      `BOOTSTRAP_FIRST_USER_AS_ADMIN` promotes whoever registers first.
- [ ] Set `BOOTSTRAP_FIRST_USER_AS_ADMIN=false` and restart.
- [ ] Confirm a verification email actually arrives.
- [ ] Run through one lab end to end.
- [ ] Take a database backup and **restore it somewhere** — an untested backup
      is a hypothesis.

See [OPERATIONS.md](OPERATIONS.md) for what to do once it is running.
