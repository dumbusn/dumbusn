#!/bin/bash
# Déploie l’application derrière le proxy, sur Debian ou Ubuntu.
# Le service écoute sur MAHH_HOST (0.0.0.0). data/ n’est jamais effacé.
# L’adresse publique reste le nom de domaine.
set -euo pipefail

SITE="mhhc.nasad.gn"
SERVICE="mahh"
CADDYFILE="/etc/caddy/Caddyfile"

usage() {
  echo "Usage : sudo bash deploy/deploiement.sh" >&2
}

# Affiche le Caddyfile en remplaçant seulement le bloc du site.
ecrire_caddy() {
  python3 - "$SITE" "$1" <<'PY'
import pathlib
import sys

site = sys.argv[1]
chemin = pathlib.Path(sys.argv[2])
texte = chemin.read_text(encoding="utf-8") if chemin.is_file() else ""

def code(ligne):
    return ligne.split("#", 1)[0]

def hotes(ligne):
    brut = code(ligne).strip()
    if brut.endswith("{"):
        brut = brut[:-1].strip()
    if not brut or brut == "{":
        return []
    trouves = []
    for morceau in brut.split(","):
        morceau = morceau.strip()
        if not morceau:
            continue
        for prefixe in ("https://", "http://"):
            if morceau.startswith(prefixe):
                morceau = morceau[len(prefixe):]
                break
        morceau = morceau.split("/", 1)[0]
        if not morceau.startswith("["):
            morceau = morceau.split(":", 1)[0]
        trouves.append(morceau)
    return trouves

lignes = texte.splitlines(keepends=True)
sortie = []
index = 0
profondeur = 0
while index < len(lignes):
    ligne = lignes[index]
    if profondeur == 0 and site in hotes(ligne):
        if hotes(ligne) != [site]:
            raise SystemExit(
                f"Le site {site} partage un bloc Caddy avec un autre nom. "
                "Séparez-le avant de relancer le script."
            )
        niveau = code(ligne).count("{") - code(ligne).count("}")
        index += 1
        if "{" not in code(ligne):
            while index < len(lignes) and "{" not in code(lignes[index]):
                index += 1
            if index >= len(lignes):
                break
            niveau = code(lignes[index]).count("{") - code(lignes[index]).count("}")
            index += 1
        while index < len(lignes) and niveau > 0:
            niveau += code(lignes[index]).count("{") - code(lignes[index]).count("}")
            index += 1
        continue
    sortie.append(ligne)
    profondeur += code(ligne).count("{") - code(ligne).count("}")
    if profondeur < 0:
        profondeur = 0
    index += 1

corps = "".join(sortie).rstrip() + "\n\n"
bloc = f"{site} {{\n\treverse_proxy 127.0.0.1:8000\n}}\n"
sys.stdout.write(corps + bloc)
PY
}

if [[ "${1:-}" == "--essai-caddy" ]]; then
  ecrire_caddy "${2:-/dev/null}"
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  usage
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Ce script vise Debian ou Ubuntu." >&2
  exit 1
fi
# shellcheck disable=SC1091
source /etc/os-release
if ! printf '%s\n' "$ID" "${ID_LIKE:-}" | grep -Eq '(^|[[:space:]])(debian|ubuntu)([[:space:]]|$)'; then
  echo "Ce script vise Debian ou Ubuntu (détecté : ${ID:-inconnu})." >&2
  exit 1
fi

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
if [[ ! -f "$ROOT/mahh/__main__.py" ]]; then
  echo "Le dossier du dépôt est introuvable : $ROOT" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 ca-certificates curl gnupg

if ! command -v caddy >/dev/null 2>&1; then
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  install -d -m 755 /usr/share/keyrings /etc/apt/sources.list.d
  cle="$(mktemp)"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor >"$cle"
  install -m 644 "$cle" /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  rm -f "$cle"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

if ! getent group "$SERVICE" >/dev/null; then
  groupadd --system "$SERVICE"
fi
if ! id -u "$SERVICE" >/dev/null 2>&1; then
  useradd \
    --system \
    --gid "$SERVICE" \
    --home-dir "$ROOT" \
    --shell /usr/sbin/nologin \
    --comment "Application du ministère" \
    "$SERVICE"
fi

# Le code est lisible par le service. data/ n’est pas vidé, seulement rendu privé.
chmod a+rX "$ROOT" "$ROOT/mahh"
find "$ROOT/mahh" -exec chmod a+rX {} +
install -d -o "$SERVICE" -g "$SERVICE" -m 750 "$ROOT/data"
chown -R "$SERVICE:$SERVICE" "$ROOT/data"
chmod 750 "$ROOT/data"
find "$ROOT/data" -type d -exec chmod 750 {} +
find "$ROOT/data" -type f -exec chmod 640 {} +

PYTHON="$(command -v python3)"
install -d -m 755 /etc/systemd/system
cat >"/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=Application du ministère
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${SERVICE}
Group=${SERVICE}
WorkingDirectory=${ROOT}
Environment=MAHH_HOST=0.0.0.0
Environment=MAHH_PORT=8000
Environment=MAHH_DATA=${ROOT}/data
ExecStart=${PYTHON} -m mahh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

install -d -m 755 /etc/caddy
temporaire="$(mktemp)"
ecrire_caddy "$CADDYFILE" >"$temporaire"
caddy validate --config "$temporaire" --adapter caddyfile
install -m 644 "$temporaire" "$CADDYFILE"
rm -f "$temporaire"

systemctl enable caddy
if systemctl is-active --quiet caddy; then
  systemctl reload caddy
else
  systemctl start caddy
fi

echo "Service ${SERVICE} actif, écoute sur 0.0.0.0:8000 pour le proxy du réseau local."
echo "L’adresse publique reste https://${SITE}."
echo "Les fichiers de data/ sont conservés."
