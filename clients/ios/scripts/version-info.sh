#!/bin/bash

PLIST="$1"
PLISTBUDDY=/usr/libexec/PlistBuddy

# Create empty plist if it doesn't exist, clear it if it does
${PLISTBUDDY} -x -c "Clear dict" "${PLIST}"

# Add all fields to plist
${PLISTBUDDY} -x -c "Add :BuildDate string \"$(date -u +'%F %T')\"" "${PLIST}"
${PLISTBUDDY} -x -c "Add :BuildRevision string \"$(hg identify -i)\"" "${PLIST}"
${PLISTBUDDY} -x -c "Add :BuildBranch string \"$(hg identify -b)\"" "${PLIST}"

