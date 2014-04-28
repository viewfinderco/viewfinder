#!/bin/bash
#
# supervisord   Supervisord for haproxy and viewfinder backends.
#
# Author:       Marc Berhault (marc@emailscrubbed.com)
#
# chkconfig:	2345 98 02
#
# description   Process manager for haproxy and viewfinder backends.
# processname:  python
# pidfile: /var/run/supervisord.pid
#

### BEGIN INIT INFO
# Provides: supervisord
# Required-Start: $syslog $local_fs
# Required-Stop: $syslog $local_fs
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: Viewfinder web server
# Description: Process manager for haproxy and viewfinder backends.
### END INIT INFO

EC2_HOME=/home/ec2-user
ENV_DIR=${EC2_HOME}/env/viewfinder
VIEWFINDER_HOME=$EC2_HOME/viewfinder
CONF_FILE=${VIEWFINDER_HOME}/scripts/supervisord.conf

ARGS="-c ${CONF_FILE}"

# source function library
. /etc/rc.d/init.d/functions

RETVAL=0

start() {
	echo -n $"Starting supervisord: "
	daemon --user=ec2-user ${ENV_DIR}/bin/supervisord ${ARGS}
	RETVAL=$?
	echo
	[ $RETVAL -eq 0 ] && touch /var/lock/subsys/supervisord
}

stop() {
	echo -n $"Stopping supervisord: "
  killproc supervisord
	echo
	[ $RETVAL -eq 0 ] && rm -f /var/lock/subsys/supervisord
}

restart() {
	stop
	start
}

case "$1" in
  start)
	start
	;;
  stop)
	stop
	;;
  restart|force-reload|reload)
	restart
	;;
  condrestart|try-restart)
	[ -f /var/lock/subsys/supervisord ] && restart
	;;
  status)
	status supervisord
	RETVAL=$?
	;;
  *)
	echo $"Usage: $0 {start|stop|status|restart|reload|force-reload|condrestart}"
	exit 1
esac

exit $RETVAL
