#!/bin/bash

set -e

OS_NAME=$(uname -s)
PROTOC=$(dirname $0)/../../../third_party/shared/bin/protoc.${OS_NAME}

# If the path to the .proto file is relative, protoc includes the directory
# component of the path in the output directory. We squash this behavior be
# prepending PWD.
proto_path="${PWD}/$2"

# protoc requires that we always include a -I for the directory containing
# the .proto being processed, hence the $(dirname ${proto_path}).
declare -a include_dirs
include_dirs=( $1 $(dirname ${proto_path}) )
proto_includes=${include_dirs[@]/#/-I}

out_dir="$3"

# echo ${PROTOC} --cpp_out="${out_dir}" ${proto_includes} "${proto_path}"  >> ${HOME}/protoc.out
${PROTOC} --cpp_out="${out_dir}" ${proto_includes} "${proto_path}"
