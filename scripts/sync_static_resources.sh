#!/bin/bash

# We keep a copy of our static and template directories synced to a dropbox shared folder
# so our designers (dwight@divisionof.com) can work on them.  This script applies
# made there to the main source repo.  After running this script code review and commit normally.
# (to go in the other direction, just cp -R the static and template directories into dropbox
# and make copies with the -original suffix.

for DIR in static template; do
  (cd ~/Dropbox/viewfinder-static && diff -u -r -N -a $DIR{-original,}) | (cd $VF_HOME/backend/resources/$DIR && patch -p1)
done
