#!/bin/bash

PLIST="${INTERMEDIATE_DIR}/Viewfinder-Version.plist"
PLISTBUDDY=/usr/libexec/PlistBuddy

HG="${HOME}/envs/vf-dev/bin/hg"

# Create empty plist if it doesn't exist, clear it if it does
${PLISTBUDDY} -x -c "Clear dict" "${PLIST}"

# Add all fields to plist
${PLISTBUDDY} -x -c "Add :BuildDate string \"$(date -u +'%F %T')\"" "${PLIST}"
${PLISTBUDDY} -x -c "Add :BuildRevision string \"$(${HG} identify -i)\"" "${PLIST}"
${PLISTBUDDY} -x -c "Add :BuildBranch string \"$(${HG} identify -b)\"" "${PLIST}"
