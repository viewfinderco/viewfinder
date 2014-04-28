#!/bin/sh

security find-identity -v -p codesigning | grep "$1" | awk -F\" '/"/ {print $2}' | head -n1
