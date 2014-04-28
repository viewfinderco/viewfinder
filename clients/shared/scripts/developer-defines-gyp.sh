#!/bin/bash

set -e

function init_defines() {
  local out="${1}"
  local base="$(basename ${out})"
  if test "${base}" = ".viewfinder.DeveloperDefines.h"; then
    cat > "${out}" <<EOF
#define PRODUCTION
// #define HOST             "localhost"
// #define PORT             6666
// #define RESET_STATE      false
// #define DB_FORMAT_VALUE  "52"
EOF
  elif test "${base}" = ".viewfinder.TestDefines.h"; then
    cat > "${out}" <<EOF
#define TEST_VERBOSE false
#define TEST_ONLY false
#define TEST_SELECTION ""
#define TEST_EXCLUSION "AssetsManagerTest"
EOF
  fi
}

function link_defines() {
  local outbase="${1}"
  local out="${SHARED_INTERMEDIATE_DIR}/$outbase"
  local inbase=.viewfinder.${outbase}
  local in="${HOME}/${inbase}"
  if ! test -e "${in}"; then
    init_defines "${in}"
  fi
  echo $out
  if ! cmp "${in}" "${out}" >/dev/null 2>&1; then
    mkdir -p $(dirname "${out}")
    ln -f "${in}" "${out}"
  fi
}

# Have to be careful about quoting these variables - gyp likes to use spaces
# in intermediate directory names.
for i in DeveloperDefines.h TestDefines.h; do
  link_defines "$i"
done
