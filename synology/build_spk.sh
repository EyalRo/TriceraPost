#!/bin/sh
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PKG_NAME="TriceraPost"
BUILD_DIR="${ROOT_DIR}/synology/build"
PKG_DIR="${BUILD_DIR}/${PKG_NAME}"
PAYLOAD_DIR="${BUILD_DIR}/payload"
SPK_FILE="${BUILD_DIR}/${PKG_NAME}.spk"

rm -rf "${PKG_DIR}" "${PAYLOAD_DIR}" "${SPK_FILE}"
mkdir -p "${PKG_DIR}" "${PAYLOAD_DIR}/app" "${PAYLOAD_DIR}/port_conf"

cp "${ROOT_DIR}/synology/INFO" "${PKG_DIR}/INFO"
mkdir -p "${PKG_DIR}/conf" "${PKG_DIR}/scripts"
cp -R "${ROOT_DIR}/synology/conf/." "${PKG_DIR}/conf"
cp -R "${ROOT_DIR}/synology/scripts/." "${PKG_DIR}/scripts"

cp "${ROOT_DIR}/synology/port_conf/TriceraPost.sc" "${PAYLOAD_DIR}/port_conf/TriceraPost.sc"

APP_EXCLUDES="--exclude=.git --exclude=__pycache__ --exclude=.env --exclude=.env.* \
--exclude=data --exclude=nzbs --exclude=nzb_downloads --exclude=downloads \
--exclude=venv --exclude=.venv --exclude=env --exclude=*.log --exclude=synology"

# Copy source tree into payload app directory.
# shellcheck disable=SC2086
 tar -C "${ROOT_DIR}" ${APP_EXCLUDES} -cf - . | tar -C "${PAYLOAD_DIR}/app" -xf -

rm -rf "${PAYLOAD_DIR}/app/synology/build"

 tar -C "${PAYLOAD_DIR}" -czf "${PKG_DIR}/package.tgz" .
 tar -C "${PKG_DIR}" -cf "${SPK_FILE}" .

 echo "Built ${SPK_FILE}"
