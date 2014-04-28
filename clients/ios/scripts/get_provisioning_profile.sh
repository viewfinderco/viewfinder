#!/bin/sh
# Prints the UUID of the named provisioning profile.
# The argument should be either "Viewfinder Ad Hoc" or "Viewfinder Distribution".
profile="$1"
full_path=$(grep -l "$profile" "${HOME}/Library/MobileDevice/Provisioning Profiles/"*.mobileprovision)
basename -s .mobileprovision "$full_path"
