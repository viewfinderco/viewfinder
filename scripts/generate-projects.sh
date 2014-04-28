#!/bin/bash
#
# To run this automatically from hg, add the following to $VF_HOME/.hg/hgrc:
# [hooks]
# update.gyp = generate-projects.sh
# qpush.gyp = generate-projects.sh
# qpop.gyp = generate-projects.sh
# qgoto.gyp = generate-projects.sh

# Remove any team provisioning profiles. We don't want 'em.
#dir="${HOME}/Library/MobileDevice/Provisioning Profiles/"
#if test -d "${dir}"; then
#  pushd "${dir}" 2>&1 > /dev/null
#  rm -f $(grep -l "iOS Team Provisioning Profile" *.mobileprovision)
#  popd 2>&1 > /dev/null
#fi

cd $(dirname $0)/../clients/ios

gyp --depth=. -DOS=ios -Iglobals.gypi ViewfinderGyp.gyp

$(dirname $0)/generate-projects-android.sh
