# Test deployment on Proxmox (LXC)

Scripts that built the test deployment on Carel's Proxmox cluster. They are specific to that
network; for a normal install follow [DEPLOYMENT.md](../../DEPLOYMENT.md).

| CT | VMID | Node | IP | Runs |
|---|---|---|---|---|
| zerobase | 161 | prox01 | 192.168.1.50 (zerobase.port115.com) | Docker Compose stack in `/opt/zerobase` |

Unprivileged Rocky 9 container (2 cores, 2 GB, 20 GB on `local-zfs`), following the
Home_Web_Games LXC conventions. nftables inside the CT allows SSH and the app from
192.168.1.0/24 only; SSH is key-only (the lnx02 deploy key). Plain HTTP on port 80.

## Create or repair the container

Idempotent: safe to re-run, skips what exists. Optional argument: the branch to deploy.

```bash
scp deploy/lxc/provision-zerobase.sh root@prox01.port115.com:/tmp/
ssh root@prox01.port115.com 'bash /tmp/provision-zerobase.sh main'
```

Secrets (`POSTGRES_PASSWORD`, `ZEROBASE_SECRET_KEY`) are generated on the CT in
`/opt/zerobase/.env` (mode 600) on first run and never leave it.

## Deploy a branch

Back up first if the change includes a migration (the app upgrades the database on start):

```bash
ssh root@192.168.1.50 'cd /opt/zerobase && ./scripts/backup.sh && git fetch -q origin \
  && git checkout -q main && git reset -q --hard origin/main && docker compose up -d --build'
```

## Demo data

`seed_demo.py` registers a user and enters Aug–Oct 2026 data through the web forms
(accounts, assignments, 38 transactions, one deliberately uncategorised). Run it from the
dev machine against an empty account; registration must be open:

```bash
.venv/bin/python deploy/lxc/seed_demo.py http://192.168.1.50 demo@zerobase.local '<password>'
```

The demo user on CT 161 already exists, so don't run it again there unless the database
has been reset.
