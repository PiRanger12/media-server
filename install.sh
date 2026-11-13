#!/usr/bin/env bash
# Instala y levanta el servidor multimedia en Ubuntu (22.04 / 24.04).
# Uso:  sudo ./install.sh
set -euo pipefail

cd "$(dirname "$0")"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
say() { echo -e "${GREEN}==>${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta con sudo: sudo ./install.sh"; exit 1
fi
REAL_USER="${SUDO_USER:-$USER}"

# 1. Docker ──────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  say "Instalando Docker…"
  apt-get update -y
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  usermod -aG docker "$REAL_USER"
  systemctl enable --now docker
else
  say "Docker ya está instalado ($(docker --version))"
fi

# 2. Archivo .env ────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  say "Creando .env…"
  cp .env.example .env
  sed -i "s/^PUID=.*/PUID=$(id -u "$REAL_USER")/" .env
  sed -i "s/^PGID=.*/PGID=$(id -g "$REAL_USER")/" .env
  sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
  read -rsp "Contraseña para el panel: " PW; echo
  # escapar caracteres especiales para sed
  PW_ESC=$(printf '%s' "$PW" | sed -e 's/[\/&|]/\\&/g')
  sed -i "s|^PANEL_PASSWORD=.*|PANEL_PASSWORD=${PW_ESC}|" .env
  chown "$REAL_USER": .env
  chmod 600 .env
else
  say ".env ya existe, no se modifica"
fi

set -a; source .env; set +a

# 3. Carpetas ────────────────────────────────────────────────────────────
say "Preparando carpetas en ${MEDIA_ROOT}…"
mkdir -p "${MEDIA_ROOT}/videos" "${MEDIA_ROOT}/music" data/jellyfin/config data/jellyfin/cache data/navidrome data/panel
chown -R "${PUID}:${PGID}" "${MEDIA_ROOT}" data

# 4. Firewall (solo red local) ──────────────────────────────────────────
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  SUBNET=$(ip -o -f inet addr show | awk '/scope global/ {print $4; exit}')
  if [[ -n "$SUBNET" ]]; then
    NET=$(python3 -c "import ipaddress,sys;print(ipaddress.ip_interface(sys.argv[1]).network)" "$SUBNET")
    say "Abriendo puertos 8080, 8096 y 4533 solo para la red local ${NET}"
    for p in 8080 8096 4533; do ufw allow from "$NET" to any port "$p" proto tcp >/dev/null; done
  fi
fi

# 5. Arranque ────────────────────────────────────────────────────────────
say "Construyendo y levantando contenedores…"
docker compose up -d --build

IP=$(hostname -I | awk '{print $1}')
echo
say "¡Listo! Desde cualquier dispositivo de tu red:"
echo "   Panel de administración  → http://${IP}:8080"
echo "   Jellyfin (videos)        → http://${IP}:8096"
echo "   Navidrome (música)       → http://${IP}:4533"
echo
warn "Falta un paso: conectar el panel con Jellyfin y Navidrome (sección 'Configuración inicial' del README)."
