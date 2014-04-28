#!/bin/bash
# Launcher for the pdf analytics report generator.
# This is meant to be run from a cronjob. Preferably soon after the nightly prod cronjob that
# computes metrics at noon UTC (see viewfinder/scripts/crontab.staging)
#
# Requirements:
# - must have the unencrypted passphrase stored in ~/.ssh/vf-passphrase (make sure you chmod it)
#
# $ crontab -l
# MAILTO=""
# 0 12 * * * ~/viewfinder/scripts/generate_pdf_report.sh

export VF_HOME=${HOME}/viewfinder
source ${VF_HOME}/scripts/viewfinder.bash
cd ${VF_HOME}

PASSPHRASE_FILE="~/.ssh/vf-passphrase"
ARGS="--devbox --passphrase_file=${PASSPHRASE_FILE}"
python -m viewfinder.backend.logs.generate_pdf_report ${ARGS}
