#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/file.nzb"
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "Missing .env in $(pwd)"
  exit 1
fi

while IFS= read -r line; do
  case "$line" in
    ""|\#*) continue ;;
  esac
  if [[ "$line" != *"="* ]]; then
    continue
  fi
  key="${line%%=*}"
  value="${line#*=}"
  key="${key//[[:space:]]/}"
  value="${value%%#*}"
  value="${value%"${value##*[![:space:]]}"}"
  value="${value#"${value%%[![:space:]]*}"}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    export "${key}=${value}"
  fi
done < ./.env

: "${NNTP_HOST:?NNTP_HOST is required}"
: "${NNTP_USER:?NNTP_USER is required}"
: "${NNTP_PASS:?NNTP_PASS is required}"

masked_pass="***"
if [[ ${#NNTP_PASS} -ge 4 ]]; then
  masked_pass="${NNTP_PASS:0:2}***${NNTP_PASS: -2}"
fi

echo "NNTP_HOST=${NNTP_HOST}"
echo "NNTP_PORT=${NNTP_PORT:-119}"
echo "NNTP_SSL=${NNTP_SSL:-false}"
echo "NNTP_USER=${NNTP_USER}"
echo "NNTP_PASS=${masked_pass}"

NNTP_PORT="${NNTP_PORT:-119}"
NNTP_SSL="${NNTP_SSL:-false}"

if [[ "${NNTP_SSL,,}" == "true" || "${NNTP_SSL,,}" == "1" || "${NNTP_SSL,,}" == "yes" ]]; then
  ENCRYPTION="yes"
  if [[ "${NNTP_PORT}" == "119" ]]; then
    NNTP_PORT="563"
  fi
else
  ENCRYPTION="no"
fi

NZB_FILE="$1"
BASE_DIR="${PWD}/nzb_downloads"
TEMPLATE_DIR="${BASE_DIR}/templates"

mkdir -p "${BASE_DIR}/complete" "${BASE_DIR}/incomplete" "${TEMPLATE_DIR}"

TMP_CONF="$(mktemp)"
trap 'rm -f "$TMP_CONF"' EXIT

cat <<EOF > "$TMP_CONF"
MainDir=${BASE_DIR}
DestDir=${BASE_DIR}/complete
InterDir=${BASE_DIR}/incomplete
ConfigTemplate=${TEMPLATE_DIR}

Server1.Name=TriceraPost
Server1.Host=${NNTP_HOST}
Server1.Port=${NNTP_PORT}
Server1.Username=${NNTP_USER}
Server1.Password=${NNTP_PASS}
Server1.Encryption=${ENCRYPTION}
Server1.Connections=4
EOF

nix run nixpkgs#nzbget -- \
  -n \
  -c "$TMP_CONF" \
  "${NZB_FILE}"
