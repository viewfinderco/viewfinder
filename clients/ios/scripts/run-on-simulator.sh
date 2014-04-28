#!/bin/sh
# This script builds the app and runs it on the simulator.
# Prerequisite: Install homebrew and "brew install ios-sim"
#
# Additional arguments to this script will be passed to ios-sim.
# The most useful one is "--sdk 6.0" to select the iOS version.
# There is a --debug flag, but it is buggy.  (instead, you can start
# a debugger separately with "gdb --pid $(pgrep -n Viewfinder)"

set -e

cd $(dirname $0)/..

# xcodebuild is pretty noisy on stdout; note that this leaves stderr unchanged.
xcodebuild -scheme Viewfinder > /dev/null

ios-sim launch build/Debug-iphoneos/Viewfinder.app "$@"
