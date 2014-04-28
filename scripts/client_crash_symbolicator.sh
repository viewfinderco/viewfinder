#!/bin/bash
# Launcher for the client crash log symbolicator. This job looks for new (unsymbolicated) crash logs
# in S3, symbolicates them, saves them to S3, and emails a summary.
# This is meant to be run from a cronjob. Preferably soon after the nightly prod cronjob that
# aggregates unsymbolicated crash files which runs at noon UTC (see viewfinder/scripts/crontab.staging)
#
# Requirements:
# - must be run on OSX
# - must have the unencrypted passphrase stored in ~/.ssh/vf-passphrase (make sure you chmod it)
#
# $ crontab -l
# MAILTO=""
# 0 12 * * * ~/viewfinder/scripts/client_crash_symbolicator.sh

export VF_HOME=${HOME}/viewfinder
source ${VF_HOME}/scripts/viewfinder.bash
cd ${VF_HOME}

PASSPHRASE_FILE="~/.ssh/vf-passphrase"
ARGS="--devbox --dry_run=False --passphrase_file=${PASSPHRASE_FILE}"
python -m viewfinder.backend.logs.symbolicate_user_crashes ${ARGS}
