#!/bin/bash

set -e
PROTOC=../../third_party/Darwin-11.0.0-x86_64-i386-64bit/bin/protoc

outdir="${DERIVED_FILES_DIR}/${CURRENT_ARCH}"
mkdir -p "${outdir}"

function replace_if_changed() {
  local src="${2}/${1}"
  local dest="${3}/${1}"
  if cmp "${src}" "${dest}" >/dev/null 2>&1; then
    return;
  fi
  echo "replacing: ${dest}"
  mv -f "${src}" "${dest}"
}

function build_proto() {
  local in=${1}
  local indir=$(dirname ${in})
  local inbase=$(basename ${in})
  local outbase=${inbase%.proto}
  rm -f "${outdir}/${outbase}".pb.{cc,h}
  ${PROTOC} --cpp_out="${outdir}" --proto_path="${indir}" "${in}"
  sed -i '' -e  's^<google/protobuf/^<third_party/protobuf/google/protobuf/^' "${outdir}"/"${outbase}".pb.{cc,h}

  replace_if_changed "${outbase}.pb.cc" "${outdir}" "${indir}"
  replace_if_changed "${outbase}.pb.h" "${outdir}" "${indir}"
}

for i in $(seq 0 $[SCRIPT_INPUT_FILE_COUNT - 1]); do
  build_proto $(eval "echo \$SCRIPT_INPUT_FILE_$i")
done
