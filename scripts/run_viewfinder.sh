#!/bin/bash

CUR_PWD=$(dirname $0)
source ${CUR_PWD}/viewfinder-prod.bash

cd ~/
EC2_HOME=/home/ec2-user
LOG_DIR=${EC2_HOME}/local/logs/
LOG_PREFIX=$LOG_DIR/server_log
mkdir -p $LOG_DIR

# Prod-specific args:
ARGS="--log_file_prefix=$LOG_PREFIX --log_file_max_size=10485760 --log_file_num_backups=50 --blocking_log_threshold=1.0"

# - logging path and settings
# - port and SSL settings (when sitting behind haproxy)
PROXIED_ARGS="--ssl=False --port=7090"

VIEWFINDER=${VF_HOME}/scripts/viewfinder

cd ${VF_HOME}
# Do not daemonize, supervisord handles this. Instead, we replace the shell.
# TODO(marc): pass PROXIED_ARGS when running behind haproxy.
exec python ${VIEWFINDER} ${ARGS}
