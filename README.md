# Zerobase

A self-hosted, web-based budgeting app built on zero-based (envelope) budgeting: give every pound a job.
It is a small, open-source take on the YNAB method that you run yourself, on your own hardware, with your data in your own PostgreSQL database.

> **Status: early (v0.1).** The core budgeting loop works, but this is a fresh scaffold. See [What works today](#what-works-today) and the [roadmap](#roadmap) before you trust it with real money.

## How it works

1. **Add accounts.** A *budget* account's balance is money you can plan with. A *tracking* account (a mortgage, say) only records a balance.
2. **Record income** as an inflow with no category. It lands in **Ready to Assign**.
3. **Assign** that money to categories, month by month. Type straight into the *Assigned* column; the totals update without a page reload.
4. **Spend** by recording transactions against a category. *Available* = rolled-over balance + assigned + activity.
5. **Overspent?** A negative envelope doesn't roll forward. It resets to zero next month and reduces Ready to Assign instead, so overspending is always paid for with real money.

The arithmetic lives in [`src/zerobase/budget.py`](src/zerobase/budget.py) and is covered by tests. All money is stored as integer pence, never floats.

## What works today

- Sign-up and sign-in (first account is always allowed; more only if you enable registration)
- Budget and tracking accounts, with an optional opening balance
- Monthly budget view with category groups, inline assignment, rollover and overspending
- Transactions with payee, memo and category, plus changing a category after the fact
- Several users on one install, each with fully separate data

Not there yet: editing a transaction, transfers between accounts, credit cards, CSV import, renaming or deleting categories, reports. See the roadmap.

## Quick start (Docker)

You need Docker with the Compose plugin.

```sh
git clone https://github.com/carelmaritz/zerobase.git
cd zerobase
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD and ZEROBASE_SECRET_KEY (the file shows how to generate them)
docker compose up -d --build
```

Open <http://localhost:8000> and create your account.

### Reaching it from other machines

By default the app only listens on `127.0.0.1`. Pick one:

- **HTTPS with the bundled Caddy proxy (recommended).** Set `ZEROBASE_DOMAIN` and `ZEROBASE_HTTPS_ONLY=true` in `.env`, then `docker compose --profile proxy up -d --build`. See the comments in [`Caddyfile`](Caddyfile) for public versus LAN-only certificates.
- **Plain HTTP on your LAN.** Set `ZEROBASE_BIND=0.0.0.0`. Fine on a trusted network, but passwords and session cookies are not encrypted.
- **Your own reverse proxy** (Nginx Proxy Manager, Traefik, and so on) pointing at port 8000. Set `ZEROBASE_HTTPS_ONLY=true` once it serves HTTPS.

## Running it on Proxmox

A full step-by-step runbook (VM setup, Docker, HTTPS options, backups, updates, troubleshooting) is in **[DEPLOYMENT.md](DEPLOYMENT.md)**. In short:

A small **VM** (1 vCPU, 1-2 GB RAM, a few GB of disk) running Debian or Ubuntu with Docker is the lowest-friction option, and Proxmox backups of the whole VM cover your data. An **LXC** container also works if you enable `nesting=1` and `keyctl=1` in its options so Docker can run inside it.

Whatever you choose:

- Back up the database as well as the guest. `./scripts/backup.sh` writes a compressed `pg_dump` to `./backups/`; the restore command is in the script header.
- Keep it behind your usual access controls. Exposing a budget to the internet deserves a VPN or an authenticating proxy in front.

## Configuration

Everything is set with environment variables (the Compose file reads them from `.env`).

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | *(required)* | Password for the bundled PostgreSQL |
| `ZEROBASE_SECRET_KEY` | *(required, 32+ chars)* | Signs login sessions. The app refuses to start without it |
| `ZEROBASE_ALLOW_REGISTRATION` | `false` | Allow sign-ups after the first account |
| `ZEROBASE_CURRENCY_SYMBOL` | `£` | Symbol shown before amounts |
| `ZEROBASE_HTTPS_ONLY` | `false` | Mark session cookies `Secure`; enable when served over HTTPS |
| `ZEROBASE_PORT` / `ZEROBASE_BIND` | `8000` / `127.0.0.1` | Published port and interface |
| `ZEROBASE_DOMAIN` | `localhost` | Hostname for the Caddy proxy profile |
| `ZEROBASE_DATABASE_URL` | set by Compose | SQLAlchemy URL, if you run the app outside Compose |

## Development

Requires Python 3.11 or newer.

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

pytest                      # SQLite, no setup needed
ruff check . && ruff format --check .

# Run the app locally on SQLite
ZEROBASE_ENV=dev ZEROBASE_DATABASE_URL=sqlite:///./dev.db \
  uvicorn zerobase.main:create_app --factory --reload
```

To run the tests against PostgreSQL, point `ZEROBASE_TEST_DATABASE_URL` at a throwaway database, for example `postgresql+psycopg://user:pass@localhost:5432/zerobase_test`. CI runs the suite on both.

### Database migrations

The schema is managed with [Alembic](https://alembic.sqlalchemy.org/). The app upgrades its database to the latest revision every time it starts, so deployments need no extra step. Migration scripts live in `src/zerobase/migrations/versions/`.

To change the schema, edit `models.py`, then generate a revision from the project root against a database that is already at head:

```sh
export ZEROBASE_DATABASE_URL=sqlite:///./dev.db
alembic upgrade head
alembic revision --autogenerate -m "add closed flag to accounts"
```

Read the generated file and fix anything autogenerate got wrong (it cannot detect renames, for example, and new non-null columns need a default for existing rows). Write a working `downgrade()` as well. `tests/test_migrations.py` fails if the migrations and the models disagree, on SQLite and PostgreSQL.

### Stack

Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL, Jinja2 templates and [htmx](https://htmx.org) (vendored, no CDN, no build step). One container for the app, one for the database.

```
src/zerobase/
  budget.py       envelope maths (the core logic)
  money.py        parsing and formatting of amounts
  models.py       database tables
  migrations/     Alembic schema migrations, applied on start
  routers/        auth, budget, accounts, transactions
  templates/      server-rendered pages
tests/            unit tests for the maths, plus end-to-end tests of the web app
```

## Security notes

- Passwords are hashed with Argon2. Sessions are signed, `HttpOnly`, `SameSite=Lax` cookies.
- State-changing requests from a different origin are rejected, and a strict Content-Security-Policy is sent.
- Failed sign-ins are rate-limited in memory per client address and email. Behind a reverse proxy every client appears to share the proxy's address, so this is a safety net, not a substitute for network-level protection.
- Every database query is scoped to the signed-in user.
- Found a vulnerability? Please open a private security advisory on GitHub rather than a public issue.

## Roadmap

- [ ] Edit transactions
- [ ] Transfers between accounts
- [ ] Credit card accounts
- [ ] CSV import
- [ ] Rename, reorder and delete categories; close accounts
- [x] Database migrations (Alembic)
- [ ] Targets and goals
- [ ] Scheduled and recurring transactions
- [ ] Spending and net-worth reports
- [ ] Trusted-proxy support for client addresses

## Licence

[MIT](LICENSE). The bundled htmx library is distributed under the 0BSD licence ([`htmx-LICENSE.txt`](src/zerobase/static/vendor/htmx-LICENSE.txt)).
