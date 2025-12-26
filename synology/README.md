# Synology SPK Packaging

This folder contains a minimal DSM 7.3+ SPK layout for TriceraPost.

## Build

```
./synology/build_spk.sh
```

The resulting package will be written to `synology/build/TriceraPost.spk`.

## Install

- Open DSM Package Center and choose Manual Install.
- Select `synology/build/TriceraPost.spk`.

## Service

The package starts TriceraPost with:

- `TRICERAPOST_DB_IN_MEMORY=0`
- `TRICERAPOST_DB_DIR=/var/packages/TriceraPost/var/data`
- `TRICERAPOST_SETTINGS_PATH=/var/packages/TriceraPost/var/settings.json`

Visit `http://<nas-ip>:8080/settings` to set NNTP credentials after install.

## Notes

- This package expects DSM's `Python3` package to be installed.
- If you change the service port, update `synology/port_conf/tricerapost.sc`.
