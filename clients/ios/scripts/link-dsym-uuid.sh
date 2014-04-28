#!/bin/bash

BASE_DIR="${HOME}/Dropbox/viewfinder"
DSYM_DIR=$"${BASE_DIR}/dSYMs"
UUID_DIR="${DSYM_DIR}.uuid"

rm -fr "${UUID_DIR}"
mkdir -p "${UUID_DIR}"

for dsym in $(ls "${DSYM_DIR}"); do
  ARCHIVE_DIR="${DSYM_DIR}/${dsym}"
  uuids=$(dwarfdump --uuid "${ARCHIVE_DIR}/Contents/Resources/DWARF/Viewfinder" | awk '{print $2}')
  for uuid in ${uuids}; do
    echo "${uuid} -> ${dsym}"
    echo $(basename "${ARCHIVE_DIR}") > "${UUID_DIR}/${uuid}"
  done
done
