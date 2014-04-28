#!/bin/bash

set -e

# Determine the version number we just built.
PLIST_BUDDY=/usr/libexec/PlistBuddy
INFO_PLIST="${ARCHIVE_PRODUCTS_PATH}/Applications/${INFOPLIST_PATH}"
VERS=$(${PLIST_BUDDY} -c "Print :CFBundleShortVersionString" "${INFO_PLIST}")
BUILD=$(${PLIST_BUDDY} -c "Print :CFBundleVersion" "${INFO_PLIST}")

# Archive the dsyms.
ARCHIVE_ROOT="${HOME}/Dropbox/viewfinder/dSYMs"
ARCHIVE_DATE=$(date +"%Y%m%d-%H%M%S")
ARCHIVE_DIR="${ARCHIVE_ROOT}/${PRODUCT_NAME}-${VERS}.${BUILD}-${CONFIGURATION}-${ARCHIVE_DATE}"
mkdir -p $(dirname "${ARCHIVE_DIR}")
DSYM="${ARCHIVE_DSYMS_PATH}/${PRODUCT_NAME}.app.dSYM"
echo "Copying ${DSYM} to ${ARCHIVE_DIR}" >> /tmp/archive_dsym.out
cp -Rp "${DSYM}" "${ARCHIVE_DIR}" >> /tmp/archive_dsym.out

# Provide links for the uuids inside of the dsyms so that we can more easily
# find the dsyms for a particular uuid.
UUID_DIR="${ARCHIVE_ROOT}.uuid"
mkdir -p "${UUID_DIR}"
uuids=$(dwarfdump --uuid "${ARCHIVE_DIR}/Contents/Resources/DWARF/Viewfinder" | awk '{print $2}')
for uuid in ${uuids}; do
  echo $(basename "${ARCHIVE_DIR}") > "${UUID_DIR}/${uuid}"
done
