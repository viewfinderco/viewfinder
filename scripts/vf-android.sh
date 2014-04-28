#!/bin/bash
set -e
declare -a adb_flags
declare -a ant_flags

# TODO(marc): figure out whether this is standard.
APP_DB_PATH="/data/data/co.viewfinder/files/Library/Database"

function build() {
  ant debug "${ant_flags[@]}"
}

function clean() {
  ant clean "${ant_flags[@]}"
}

function install() {
  adb "${adb_flags[@]}" install -r bin/viewfinder-debug.apk
}

function start() {
  adb "${adb_flags[@]}" shell am start -n co.viewfinder/.StartupActivity
}

function stop() {
  adb "${adb_flags[@]}" shell am force-stop co.viewfinder
}

function logcat() {
  adb "${adb_flags[@]}" logcat -v time
}

function pushdb() {
  local_path="data/${1}"
  if [ -n "${1}" -a -e "${local_path}" -a -d "${local_path}" ]; then
    adb "${adb_flags[@]}" shell rm "${APP_DB_PATH}/*"
    # "adb push a b" pushes all files in a/ to b/ (it does not push directories)
    adb "${adb_flags[@]}" push ${local_path} ${APP_DB_PATH}
  else
    echo "ERROR: pushdb: could not find DB directory \"${1}\" in `pwd`/data"
    exit 1
  fi
}

function fetchlogs() {
  local_path="${1}"
  mkdir -p ${local_path}
  adb "${adb_flags[@]}" pull /data/data/co.viewfinder/files/Library/Logs/ ${local_path}
}

function help() {
  cat <<EOF
$(basename $0) [ant|adb options] <command0> <command1> ...
  Options: options starting with -D are ant properties, all others are adb options
     samples: -h              this message
              -e              adb run on simulator (default)
              -d              adb run on device
              -x86            build for an x86 emulator
              -Dproto.skip=1  ant skip java genprotos
              -Dndk.args=V=1  ant verbose ndk-build
  Commands:
     build              build using 'ant debug'
     clean              clean using 'ant clean'
     install            build and push package
     start              start viewfinder app
     stop               stop viewfinder app
     logcat             dump android log
     all                build, install, start, logcat
     pushdb=<name>      push leveldb files from data/<name>/ to device (simulator or rooted device only)
     fetchlogs[=path]   copy client logs from device to /path/ (default: /tmp/android-logs/)
EOF
}

if [ $# -eq 0 ]; then
  help
  exit 0
fi

for cmd in "$@"; do
  case "${cmd}" in
    -h)
      help
      exit 0
      ;;
    -x86)
      ant_flags[${#ant_flags[*]}]="-Dndk.args=APP_ABI=x86"
      ;;
    -D*)
      ant_flags[${#ant_flags[*]}]="${cmd}"
      ;;
    -*)
      adb_flags[${#adb_flags[*]}]="${cmd}"
      ;;
    *)
      ;;
  esac
done

if test "${#adb_flags[*]}" -eq 0; then
  adb_flags[${#adb_flags[*]}]="-e"
fi

cd "${VF_HOME}/clients/android/"

for cmd in "$@"; do
  case "${cmd}" in
    build)
      build
      ;;
    clean)
      clean
      ;;
    install)
      build
      install
      ;;
    start)
      start
      ;;
    stop)
      stop
      ;;
    logcat)
      logcat
      ;;
    all)
      build
      install
      start
      logcat
      ;;
    pushdb*)
      split=(${cmd//=/ })
      if [ ${#split[@]} -ne 2 ]; then
        echo "ERROR: pushdb takes the name of a database to push. eg: pushdb=simple"
        exit 1
      fi
      stop
      pushdb ${split[1]}
      ;;
    fetchlogs*)
      split=(${cmd//=/ })
      out_dir=""
      if [ ${#split[@]} -ne 2 ]; then
        echo "fetchlogs called without output directory, saving to /tmp/android-logs/"
        out_dir="/tmp/android-logs/"
      else
        out_dir=${split[1]}
      fi
      fetchlogs ${out_dir}
      ;;
    -*)
      ;;
    *)
      echo "unknown command: ${cmd}"
      exit 1
  esac
done
