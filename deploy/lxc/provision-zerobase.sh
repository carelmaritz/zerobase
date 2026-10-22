#!/usr/bin/env bash
# Provision a test Zerobase LXC on prox01 (CT 161, 192.168.1.50).
# Run ON prox01 as root: bash provision-zerobase.sh [branch]   (default: main)
# Idempotent: skips what already exists. Secrets are generated on the CT, never stored here.
# Follows the Home_Web_Games LXC conventions (Rocky 9, unprivileged, nftables in the CT).
set -euo pipefail

VMID=161
NAME=zerobase
IP=192.168.1.50
TEMPLATE="local:vztmpl/rockylinux-9-default_20240912_amd64.tar.xz"
STORAGE="local-zfs"
BRIDGE="vmbr0"
GW="192.168.1.1"
DNS="192.168.1.1"
LAN="192.168.1.0/24"
REPO="https://github.com/carelmaritz/zerobase.git"
BRANCH="${1:-main}"
DEPLOY_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAID5jlvbML2Yct/UffiO2FLIst1h0/j9hpNDmc15YLoWJ carel@port115.com"

in_ct() { pct exec "$VMID" -- bash -c "$*"; }

if pct status "$VMID" &>/dev/null; then
    echo "== CT $VMID already exists, skipping create"
else
    echo "== Creating CT $VMID ($NAME) at $IP"
    pct create "$VMID" "$TEMPLATE" \
        --hostname "$NAME" --unprivileged 1 --onboot 1 \
        --cores 2 --memory 2048 --swap 512 \
        --rootfs "$STORAGE:20" \
        --net0 "name=eth0,bridge=$BRIDGE,ip=$IP/24,gw=$GW,firewall=0" \
        --nameserver "$DNS" --features nesting=1,keyctl=1 \
        --description "Zerobase budgeting app (test deployment). Docker Compose in /opt/zerobase."
fi
pct status "$VMID" | grep -q running || pct start "$VMID"
for _ in $(seq 1 30); do
    in_ct "ip -4 -br addr show eth0 2>/dev/null | grep -q '$IP'" && break
    sleep 1
done

echo "== Base packages and SSH"
in_ct "
    set -euo pipefail
    dnf -q -y install openssh-server git nftables dnf-plugins-core >/dev/null
    mkdir -p /root/.ssh && chmod 700 /root/.ssh
    grep -qF '$DEPLOY_PUBKEY' /root/.ssh/authorized_keys 2>/dev/null \
        || echo '$DEPLOY_PUBKEY' >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    mkdir -p /etc/ssh/sshd_config.d
    printf '%s\n' 'PasswordAuthentication no' 'KbdInteractiveAuthentication no' \
        'PermitRootLogin prohibit-password' > /etc/ssh/sshd_config.d/50-zerobase-hardening.conf
    systemctl enable --now sshd >/dev/null 2>&1
    systemctl try-reload-or-restart sshd
"

echo "== Firewall (LAN only)"
in_ct "
    set -euo pipefail
    cat > /etc/nftables/zerobase.nft <<'EOF'
# Zerobase test CT: SSH and the app from the LAN only.
table inet zerobase {
    chain input {
        type filter hook input priority filter; policy drop;
        iif lo accept
        ct state established,related accept
        ip protocol icmp accept
        ip saddr $LAN tcp dport 22 accept
    }
    # Docker publishes the app with DNAT, so it arrives via forward, not input.
    chain forward {
        type filter hook forward priority filter - 1; policy accept;
        ct state new ct status dnat tcp dport 8000 ip saddr != $LAN drop
    }
}
EOF
    grep -q 'zerobase.nft' /etc/sysconfig/nftables.conf \
        || echo 'include \"/etc/nftables/zerobase.nft\"' >> /etc/sysconfig/nftables.conf
    nft delete table inet zerobase 2>/dev/null || true
    nft -f /etc/nftables/zerobase.nft
    systemctl enable nftables >/dev/null 2>&1
"

echo "== Docker"
in_ct "
    set -euo pipefail
    if ! command -v docker >/dev/null; then
        dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo >/dev/null
        dnf -q -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
    fi
    systemctl enable --now docker >/dev/null 2>&1
    docker --version && docker compose version
"

echo "== Code and configuration"
in_ct "
    set -euo pipefail
    if [ ! -d /opt/zerobase/.git ]; then
        git clone -q '$REPO' /opt/zerobase
    fi
    cd /opt/zerobase
    git fetch -q origin
    git checkout -q '$BRANCH'
    git reset -q --hard 'origin/$BRANCH'
    if [ ! -f .env ]; then
        cp .env.example .env
        chmod 600 .env
        sed -i \"s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=\$(openssl rand -hex 24)|\" .env
        sed -i \"s|^ZEROBASE_SECRET_KEY=.*|ZEROBASE_SECRET_KEY=\$(openssl rand -hex 32)|\" .env
    fi
    set_env() { grep -q \"^\$1=\" .env && sed -i \"s|^\$1=.*|\$1=\$2|\" .env || echo \"\$1=\$2\" >> .env; }
    set_env ZEROBASE_BIND 0.0.0.0
    set_env ZEROBASE_PORT 80
    set_env ZEROBASE_ALLOW_REGISTRATION true
    git log --oneline -1
"

echo "== Start"
in_ct "
    set -euo pipefail
    cd /opt/zerobase
    docker compose up -d --build 2>&1 | tail -5
    for _ in \$(seq 1 60); do
        curl -fsS http://127.0.0.1:80/healthz && echo && break
        sleep 2
    done
    docker compose ps
    docker compose logs --tail=20 app
"
