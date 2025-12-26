#!/bin/sh
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PKG_NAME="tricerapost"
BUILD_DIR="${ROOT_DIR}/synology/build"
PKG_DIR="${BUILD_DIR}/${PKG_NAME}"
PAYLOAD_DIR="${BUILD_DIR}/payload"
SPK_FILE="${BUILD_DIR}/${PKG_NAME}.spk"

rm -rf "${PKG_DIR}" "${PAYLOAD_DIR}" "${SPK_FILE}"
mkdir -p "${PKG_DIR}" "${PAYLOAD_DIR}/app" "${PAYLOAD_DIR}/port_conf" "${PAYLOAD_DIR}/ui" "${PAYLOAD_DIR}/indexdb"

cp "${ROOT_DIR}/synology/INFO" "${PKG_DIR}/INFO"
cp "${ROOT_DIR}/synology/PACKAGE_ICON.PNG" "${PKG_DIR}/PACKAGE_ICON.PNG"
cp "${ROOT_DIR}/synology/PACKAGE_ICON_256.PNG" "${PKG_DIR}/PACKAGE_ICON_256.PNG"
mkdir -p "${PKG_DIR}/conf" "${PKG_DIR}/scripts"
cp -R "${ROOT_DIR}/synology/conf/." "${PKG_DIR}/conf"
cp -R "${ROOT_DIR}/synology/scripts/." "${PKG_DIR}/scripts"
cp -R "${ROOT_DIR}/synology/ui/." "${PAYLOAD_DIR}/ui"
cp -R "${ROOT_DIR}/synology/indexdb/." "${PAYLOAD_DIR}/indexdb"

cp "${ROOT_DIR}/synology/port_conf/tricerapost.sc" "${PAYLOAD_DIR}/port_conf/tricerapost.sc"

APP_EXCLUDES="--exclude=.git --exclude=__pycache__ --exclude=.env --exclude=.env.* \
--exclude=data --exclude=nzbs --exclude=nzb_downloads --exclude=downloads \
--exclude=venv --exclude=.venv --exclude=env --exclude=*.log --exclude=synology"

# Copy source tree into payload app directory.
# shellcheck disable=SC2086
 tar -C "${ROOT_DIR}" ${APP_EXCLUDES} -cf - . | tar -C "${PAYLOAD_DIR}/app" -xf -

rm -rf "${PAYLOAD_DIR}/app/synology/build"

# Ensure payload files are readable/executable for package runtime.
find "${PAYLOAD_DIR}/app" -type d -exec chmod 755 {} +
find "${PAYLOAD_DIR}/app" -type f -exec chmod 644 {} +
find "${PAYLOAD_DIR}/ui" -type d -exec chmod 755 {} +
find "${PAYLOAD_DIR}/ui" -type f -exec chmod 644 {} +
find "${PAYLOAD_DIR}/indexdb" -type d -exec chmod 755 {} +
find "${PAYLOAD_DIR}/indexdb" -type f -exec chmod 644 {} +

 tar --format=ustar -C "${PAYLOAD_DIR}" -czf "${PKG_DIR}/package.tgz" .
 tar --format=ustar -C "${PKG_DIR}" -cf "${SPK_FILE}" INFO PACKAGE_ICON.PNG PACKAGE_ICON_256.PNG conf scripts package.tgz

 echo "Built ${SPK_FILE}"
