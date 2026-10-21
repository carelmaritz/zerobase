# Deploying Zerobase on Proxmox

A runbook for putting Zerobase on a Proxmox VE cluster. It is written so a person or an automated agent can follow it top to bottom.

> **Read this first.** The Docker image and Compose stack have been validated for syntax and the application itself has been tested against PostgreSQL, but the container build has **not** yet been run on a real Docker host. Treat the first deployment as the real test, and fix anything small you find (then send the fix back as a pull request).

## 1. Decide these first

Defaults are in **bold**. Everything below works with the defaults; the other sections cover the alternatives.

| Decision | Options | Notes |
|---|---|---|
| Guest type | **VM** / LXC | A VM is the lowest-friction way to run Docker. LXC notes are in [section 9](#9-running-in-an-lxc-instead). |
| Guest OS | **Debian 12 or Ubuntu 24.04** / Rocky Linux 9 | Rocky needs a few extra steps (Docker's repo, SELinux). Both are covered. |
| HTTPS | **Bundled Caddy proxy** / your own reverse proxy / none (trusted LAN only) | See [section 5](#5-choose-how-people-reach-it). |
| Name | **`budget.<your-domain>`** or a LAN name | Needed for HTTPS. Create the DNS record (or local DNS entry) before you start. |
| Sizing | **2 vCPU, 2 GB RAM, 20 GB disk** | More than enough for a household. The image build is the only heavy moment. |
| Backups | **Proxmox backup job + nightly `pg_dump`** | See [section 7](#7-back-it-up). |

Things to collect before starting: the Proxmox node name, the storage to put the disk on, the network bridge (and VLAN tag, if you use one), a fixed IP or DHCP reservation for the guest, and the hostname people will type.

## 2. Create the VM

In the Proxmox web UI: **Create VM**, then:

| Tab | Setting |
|---|---|
| General | Name `zerobase`. Tick **Start at boot**. |
| OS | Your Debian/Ubuntu/Rocky ISO (or use a cloud-init template if you already have one). |
| System | Machine `q35`. Tick **Qemu Agent**. |
| Disks | 20 GB, bus SCSI, controller VirtIO SCSI single. Enable *Discard* if the storage is thin-provisioned. |
| CPU | 2 cores. Type `host` is fine. |
| Memory | 2048 MB. |
| Network | Model VirtIO, your bridge, VLAN tag if needed. |

Install the OS with a normal non-root user that has `sudo`, give it a fixed IP (or a DHCP reservation), then install the guest agent so Proxmox can see its IP and freeze its filesystem for snapshot backups:

```sh
# Debian / Ubuntu
sudo apt update && sudo apt install -y qemu-guest-agent git curl openssl
sudo systemctl enable --now qemu-guest-agent

# Rocky Linux 9
sudo dnf install -y qemu-guest-agent git curl openssl
sudo systemctl enable --now qemu-guest-agent
```

## 3. Install Docker

Install Docker Engine with the Compose plugin from Docker's own repository. The distribution packages are older and Podman's Compose support is not reliable enough for this stack.

**Debian / Ubuntu:** follow <https://docs.docker.com/engine/install/debian/> or <https://docs.docker.com/engine/install/ubuntu/>.

**Rocky Linux 9** (uses Docker's CentOS repository; check <https://docs.docker.com/engine/install/centos/> if the commands have changed):

```sh
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

Either way, then:

```sh
sudo usermod -aG docker "$USER"   # log out and back in for this to apply
docker --version && docker compose version
```

SELinux can stay enforcing on Rocky; the Compose file already labels its bind mount (`:z`).

## 4. Get the code and configure it

```sh
sudo mkdir -p /opt/zerobase && sudo chown "$USER": /opt/zerobase
git clone https://github.com/carelmaritz/zerobase.git /opt/zerobase
cd /opt/zerobase
cp .env.example .env
chmod 600 .env
```

Generate the two required secrets and put them in `.env`:

```sh
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env
sed -i "s|^ZEROBASE_SECRET_KEY=.*|ZEROBASE_SECRET_KEY=$(openssl rand -hex 32)|" .env
```

Use `openssl rand -hex` as shown. The database password is placed inside a connection URL, so a password with characters like `@`, `/` or `#` would break it. Never commit `.env`; it is already gitignored.

Other settings (full table in the README): `ZEROBASE_CURRENCY_SYMBOL` (default `£`) and `ZEROBASE_ALLOW_REGISTRATION` (default `false`; the first account can always be created, further sign-ups need it on).

**Do not change `POSTGRES_PASSWORD` after the first start.** PostgreSQL only reads it when it first creates the data volume, so changing it later makes the app fail to log in to the database. See [troubleshooting](#10-troubleshooting).

## 5. Choose how people reach it

By default the app only listens on `127.0.0.1:8000` inside the VM. Pick **one** of these.

### Option A: bundled Caddy proxy with HTTPS (recommended)

Set the hostname and mark session cookies as secure:

```sh
echo 'ZEROBASE_DOMAIN=budget.example.com' >> .env
echo 'ZEROBASE_HTTPS_ONLY=true'           >> .env
echo 'COMPOSE_PROFILES=proxy'             >> .env   # makes every docker compose command include Caddy
docker compose up -d --build
```

How the certificate is obtained depends on the name:

- **A public DNS name that points at this VM, with ports 80 and 443 reachable from the internet:** Caddy gets a Let's Encrypt certificate automatically.
- **A LAN-only name, or `localhost`:** Caddy issues certificates from its own private CA. Browsers will warn until each client trusts Caddy's root certificate. Export it with:

  ```sh
  docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt > zerobase-root.crt
  ```

  Then import that file into the OS or browser trust store on each device.
- **A certificate from your own CA:** edit the [`Caddyfile`](Caddyfile) to add a `tls /path/to/cert.pem /path/to/key.pem` line and mount the files into the container.

Caddy publishes ports 80 and 443 on the VM, so point DNS at the VM's IP.

> **`ZEROBASE_HTTPS_ONLY=true` only works over HTTPS.** Browsers refuse to store the secure session cookie on a plain-HTTP page, so sign-in appears to succeed and then bounces you back to the login page. Leave it `false` until HTTPS works.

### Option B: your existing reverse proxy

Use this if Nginx Proxy Manager, Traefik, HAProxy or similar already fronts your services.

1. Let that proxy reach the app: change the existing `ZEROBASE_BIND=` line in `.env` to an address it can reach (the VM's LAN IP, or `0.0.0.0`), for example `sed -i 's|^ZEROBASE_BIND=.*|ZEROBASE_BIND=0.0.0.0|' .env`. Then restrict port 8000 to the proxy's IP with the Proxmox firewall on the VM's network interface.
2. Point the proxy at `http://<vm-ip>:8000`, and **pass the original `Host` header through unchanged**. Zerobase rejects form posts whose `Origin` does not match the `Host` it receives, so a proxy that rewrites `Host` to an internal name causes every save to fail with "Cross-site request blocked". Nginx Proxy Manager and Traefik pass it by default; with plain nginx add `proxy_set_header Host $host;`.
3. Set `ZEROBASE_HTTPS_ONLY=true` once the proxy serves HTTPS.
4. Start without the Caddy profile: `docker compose up -d --build`.

### Option C: plain HTTP on a trusted LAN

Change the existing `ZEROBASE_BIND=` line in `.env` to `0.0.0.0` (`sed -i 's|^ZEROBASE_BIND=.*|ZEROBASE_BIND=0.0.0.0|' .env`) and run `docker compose up -d --build`. Passwords and session cookies travel unencrypted, so only do this on a network you trust.

> **About firewalls:** Docker publishes container ports with its own firewall rules, which bypass `ufw` and `firewalld`. A published port is reachable no matter what those tools say. That is why the default bind is `127.0.0.1`: keep it there unless you deliberately need something else to reach port 8000. For anything beyond that, use the Proxmox firewall on the VM's network interface.

## 6. Verify it works

Run these in order and stop at the first failure.

```sh
cd /opt/zerobase
docker compose ps                         # db and app show "healthy"; caddy "running" if you use it
curl -fsS http://127.0.0.1:8000/healthz   # {"status":"ok"}
docker compose logs --tail=50 app         # no tracebacks
```

Then from another machine:

1. Open the URL people will actually use. For Option A, check the padlock.
2. Create the first account (the sign-up link only appears while no account exists).
3. Add an account with an opening balance, assign money to a category, and add a transaction. The Ready to Assign banner should update as you type.
4. Prove it survives a restart: `docker compose restart`, then reload the page and confirm your data and login are still there. Then reboot the VM and check it comes back on its own (all services use `restart: unless-stopped`; Docker starts at boot).
5. Prove the backup works: run `./scripts/backup.sh` and confirm a non-empty file appears in `backups/`.

## 7. Back it up

There are two layers, and you want both.

**Proxmox backup of the whole VM.** In *Datacenter > Backup*, add a job for the `zerobase` VM: mode **Snapshot**, a nightly schedule, your backup storage (Proxmox Backup Server if you have one), and a retention you are happy with. With the guest agent installed, snapshots are filesystem-consistent.

**Logical database dump.** This is the one you can restore anywhere, even to a different machine. Schedule `scripts/backup.sh` and keep a copy off the VM:

```sh
# crontab -e   (as the user that runs docker)
15 3 * * *  cd /opt/zerobase && mkdir -p backups && ./scripts/backup.sh >> backups/backup.log 2>&1
45 3 * * *  find /opt/zerobase/backups -name 'zerobase-*.sql.gz' -mtime +30 -delete
```

Copy `backups/` to another machine regularly (rsync, a NAS share, object storage). A backup on the same disk is not a backup.

**Restore** (this replaces the current data, so rehearse it on a scratch VM first):

```sh
cd /opt/zerobase
docker compose stop app
gunzip -c backups/zerobase-YYYYmmdd-HHMMSS.sql.gz | docker compose exec -T db psql -U zerobase zerobase
docker compose start app
```

## 8. Operating it

```sh
docker compose logs -f app          # follow logs
docker compose ps                   # health
docker compose restart app          # restart just the app
```

**Update to a new version.** The app upgrades its database automatically when it starts (the log shows `Database schema at revision ...`). Always back up first: a database upgrade cannot be undone except by restoring that backup.

```sh
cd /opt/zerobase
./scripts/backup.sh
git pull
docker compose up -d --build
curl -fsS http://127.0.0.1:8000/healthz
```

**Roll back:** `git checkout <previous-commit-or-tag> && docker compose up -d --build`. If the release changed the database, restore the dump you took before updating. Run `git checkout main` before the next `git pull`.

**Let another person sign up:** set `ZEROBASE_ALLOW_REGISTRATION=true` in `.env`, run `docker compose up -d`, have them register, then set it back to `false` and run `docker compose up -d` again. Each person's budget is private to them.

**Forgotten password.** There is no reset flow yet. Generate a new hash and write it to the database:

```sh
cd /opt/zerobase
NEWHASH=$(docker compose exec -T app python -c "from zerobase.security import hash_password; print(hash_password('choose-a-new-password'))")
docker compose exec -T db psql -U zerobase zerobase <<SQL
UPDATE users SET password_hash = '$NEWHASH' WHERE email = 'you@example.com';
SQL
```

The shell expands `$NEWHASH` once, so the dollar signs inside the hash itself are left alone. The password you type appears in your shell history; clear that line afterwards, and change the password again once you are signed in if that matters to you.

## 9. Running in an LXC instead

It works, but a VM is less fiddly. If you want an LXC anyway:

- Use an **unprivileged** container with the options **Nesting** and **keyctl** enabled (*Options > Features*), a Debian or Ubuntu template, and the same sizing as above.
- Install Docker as in [section 3](#3-install-docker) and carry on from section 4.
- If the container's storage is ZFS, Docker may fall back to a slower storage driver. That is fine at this scale but worth knowing if image builds feel slow.
- Back it up with the same Proxmox backup job and the same `pg_dump` cron.

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `docker compose` stops with *Set POSTGRES_PASSWORD in .env* or *Set ZEROBASE_SECRET_KEY in .env* | Those two values are required. Fill them in (section 4). |
| `app` exits at start with *ZEROBASE_SECRET_KEY must be set to a random value of at least 32 characters* | The key is empty or too short. Use `openssl rand -hex 32`. |
| `app` logs *password authentication failed for user "zerobase"* | `POSTGRES_PASSWORD` was changed after the database was first created. Either set it back, or change it inside PostgreSQL: `docker compose exec db psql -U zerobase -c "ALTER USER zerobase PASSWORD 'new-value';"`. If there is no data yet, `docker compose down -v` wipes the volume so the new password is used. |
| Sign-in "works" but you land back on the login page | `ZEROBASE_HTTPS_ONLY=true` while browsing over plain HTTP. Use the HTTPS address, or set it to `false`. |
| Every save fails with *Cross-site request blocked.* | The proxy is changing the `Host` header, or you are using a different hostname than the proxy forwards. Pass `Host` through unchanged (section 5, option B). |
| Browser shows a certificate warning | Expected with Caddy's private CA. Trust its root certificate (section 5, option A) or use a public name. |
| Caddy cannot get a Let's Encrypt certificate | Ports 80 and 443 must reach the VM from the internet and the DNS record must point at it. Check `docker compose logs caddy`. |
| Caddy cannot read the Caddyfile (*permission denied*) on Rocky | SELinux. The Compose file labels the mount with `:z`; make sure you are on the current version. |
| `Too many attempts. Try again in a few minutes.` on the login page | The sign-in rate limiter. It clears itself after 15 minutes or when the app restarts. |
| `app` stays `unhealthy` | `docker compose logs app`. Most often the database is not ready or the URL is wrong; confirm `db` is `healthy`. |
| `permission denied` running `docker` | You are not in the `docker` group yet. Log out and back in. |

## Appendix: prompt for an automated agent

Paste this into a Claude Code session that has access to your Proxmox cluster. Fill in the bracketed values first.

```text
Deploy Zerobase, a self-hosted budgeting web app, onto my Proxmox cluster by
following DEPLOYMENT.md in https://github.com/carelmaritz/zerobase (branch main).
Read DEPLOYMENT.md and the README fully before changing anything.

Choices:
- Guest: [new VM / new LXC] on node [NODE], storage [STORAGE], bridge [vmbr0], VLAN [none/ID]
- OS: [Debian 12 / Ubuntu 24.04 / Rocky Linux 9]
- Address: [static IP or DHCP reservation], hostname [budget.example.com]
- HTTPS: [bundled Caddy with a public name / bundled Caddy with its private CA /
  my existing reverse proxy at ... / none, trusted LAN only]
- Backups: Proxmox backup job to [STORAGE] nightly, plus the pg_dump cron from section 7

Rules:
- Only create and change the NEW guest for Zerobase. Do not modify, stop, restart or
  migrate any existing VM, container, storage or network configuration.
- Never print, log or commit secrets. Generate them on the guest, keep .env at mode 600,
  and do not paste its contents back to me.
- Do not expose the app to the internet unless I chose a public hostname above.
- The Docker build has not been tested before. If it fails, diagnose and fix the smallest
  thing that works, then tell me exactly what you changed so it can go back into the repo.

Finish only when every check in section 6 passes. Then report: the URL, the guest ID
and IP, what you changed from the runbook and why, where backups are written, and
anything you could not verify. Do not create my user account; I will do that myself.
```
