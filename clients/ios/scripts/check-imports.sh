#!/bin/bash

script_dir="$(dirname $0)"
source_dir="${script_dir}/../Source"
tmp_dir=$(mktemp -d /tmp/check-imports.XXXXXX)
trap "rm -fr ${TMPDIR}" 0

for file in "$@"; do
  original="${tmp_dir}/$(basename file).original"
  sorted="${tmp_dir}/$(basename file).sorted"
  egrep '#(import|include) "' ${file} > ${original}
  sort -f -k 2 ${original} > ${sorted}

  if ! cmp -s "${original}" "${sorted}"; then
    echo "$file";
    diff -u "${original}" "${sorted}" | egrep -v '^(---|\+\+\+|@@)' | sed 's/^/    /g'
    # TODO(peter): With a little more work we could probably make this script
    # actually fix the imports.
  fi
done
