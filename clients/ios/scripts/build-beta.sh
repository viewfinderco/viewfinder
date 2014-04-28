#!/bin/bash

# Build beta and app-store IPAs (iPhone Application Archive). Need a different
# IPA for each distribution certificate. Need a different build configuration
# for each distribution certificate.

set -e

# hg doesn't have a good scriptable interface, so just read the output of these commands into a string.
if test -n "$(hg status -mar; hg qapplied)"; then
  echo "Pending hg changes exist; please revert or commit before continuing."
  exit 1
fi

PLIST_BUDDY=/usr/libexec/PlistBuddy
INFO_PLIST="Source/Viewfinder-Info.plist"

prev_vers=$(${PLIST_BUDDY} -c "Print :CFBundleShortVersionString" ${INFO_PLIST})
prev_build=$(${PLIST_BUDDY} -c "Print :CFBundleVersion" ${INFO_PLIST})

build="$2"
if test -z "${build}"; then
  build=$[prev_build + 1]
fi

while test "${prev_build}" -gt 0; do
  if test -n "$(hg tags | grep ${prev_vers}.${prev_build})"; then
    break
  fi
  prev_build=$[prev_build - 1]
done

vers="${prev_vers}"
if test -n "$1" -a "${vers}" != "$1"; then
  vers="$1"
fi

if test "$(basename $0)" = "build-beta.sh"; then
  scheme="Viewfinder-AdHoc"
elif test "$(basename $0)" = "build-enterprise.sh"; then
  scheme="Viewfinder-Enterprise"
else
  scheme="Viewfinder-AppStore"
fi

echo "Building ${scheme}: ${prev_vers}.${prev_build} -> ${vers}.${build}"
sleep 1

${PLIST_BUDDY} -c "Set :CFBundleShortVersionString ${vers}" ${INFO_PLIST}
${PLIST_BUDDY} -c "Set :CFBundleVersion ${build}" ${INFO_PLIST}

TMPDIR=$(mktemp -d /tmp/build-beta.XXXXXX)
trap "rm -fr ${TMPDIR}" 0

echo "Build ${vers}.${build} (${scheme})." > ${TMPDIR}/build.notes
echo >> ${TMPDIR}/build.notes
if test -e release-notes.txt; then
  cat release-notes.txt >> ${TMPDIR}/build.notes
  echo -e "\n------------------------------------------------------------" >> ${TMPDIR}/build.notes
fi
echo -e "\nChange log:\n" >> ${TMPDIR}/build.notes
hg log --style=../../mercurial/sample.hglogformat.nocolor -r "::.-::tag(${prev_vers}.${prev_build})" . >> ${TMPDIR}/build.notes
cat ${TMPDIR}/build.notes

# Build project
../../scripts/generate-projects.sh
xcodebuild -workspace ViewfinderWorkspace.xcworkspace -scheme "${scheme}" archive

if test "$(basename $0)" = "build-enterprise.sh"; then
  # Nothing left to do for enterprise builds.
  exit
fi

DATE=$(date +"%Y-%m-%d")
ARCHIVE=$(ls -td "${HOME}/Library/Developer/Xcode/Archives/${DATE}/${scheme}"*.xcarchive | head -1)
if test -z "${ARCHIVE}"; then
  echo "ERROR: unable to find app archive"
  exit 1
fi

APP="${ARCHIVE}/Products/Applications/Viewfinder.app"
DSYM="${ARCHIVE}/dSYMS/Viewfinder.app.dSYM"

if test "${scheme}" = "Viewfinder-AppStore"; then
  echo "Verifying ${APP}"

  PROVISIONING_PLIST="${TMPDIR}/provisioning.plist"
  security cms -D -i "${APP}/embedded.mobileprovision" > "${PROVISIONING_PLIST}"

  # Verify that the get-task-allow entitlement is false.
  GET_TASK_ALLOW=$(${PLIST_BUDDY} -c "Print :Entitlements:get-task-allow" "${PROVISIONING_PLIST}")
  if [ "${GET_TASK_ALLOW}" != "false" ]; then
    echo "ERROR: get-task-allow != false (${GET_TASK_ALLOW})"
    exit 1
  fi

  # Verify that the aps-environment entitlement is production.
  APS_ENVIRONMENT=$(${PLIST_BUDDY} -c "Print :Entitlements:aps-environment" "${PROVISIONING_PLIST}")
  if [ "${APS_ENVIRONMENT}" != "production" ]; then
    echo "ERROR: aps-environment != production (${APS_ENVIRONMENT})"
    exit 1
  fi

  # Verify that we cannot find the AmIBeingDebugged symbol.
  if [ "$(xcrun dwarfdump -f AmIBeingDebugged "${DSYM}" | grep "no matching")" = "" ]; then
    echo "ERROR: Found the AmIBeingDebugged symbol"
    exit 1
  fi
fi

IPA="${TMPDIR}/Viewfinder.ipa"
DSYM_ZIP="${TMPDIR}/Viewfinder.ipa.dSYM.zip"

SIGNING_IDENTITY="iPhone Distribution: Minetta LLC"
PROVISIONING_PROFILE=$(scripts/get_provisioning_profile.sh "Viewfinder Ad Hoc")

export CODESIGN_ALLOCATE="/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/usr/bin/codesign_allocate"

/usr/bin/xcrun -sdk iphoneos PackageApplication \
  -v "${APP}" \
  -o "${IPA}" \
  --sign "${SIGNING_IDENTITY}" \
  --embed "${HOME}/Library/MobileDevice/Provisioning Profiles/${PROVISIONING_PROFILE}.mobileprovision"
zip -r "${DSYM_ZIP}" "${DSYM}"

API_TOKEN="dea1a6657a0e17dd8a80ae1508c81850_MjA2NDA0MjAxMS0xMS0wNCAxMDo1NTowNS45MjgwMDg"
TEAM_TOKEN="c012aedef4478bc67d3d3e540d295793_Mzg5MDUyMDExLTExLTA0IDEwOjU4OjU2LjQ4OTIzOQ"
curl -o "${TMPDIR}/testflight.out" "http://testflightapp.com/api/builds.json" \
  -F file=@"${IPA}" \
  -F dsym=@"${DSYM_ZIP}" \
  -F api_token="${API_TOKEN}" \
  -F team_token="${TEAM_TOKEN}" \
  -F notes="<${TMPDIR}/build.notes" \
  -F distribution_lists='Internal' \
  -F notify='True'
cat "${TMPDIR}/testflight.out"

if test "${vers}" != "${prev_vers}" -o "${build}" != "${prev_build}"; then
  hg commit -m "Bump version number: ${vers}.${build}" ${INFO_PLIST}
  hg tag "${vers}.${build}"

  # If this fails, be sure to merge (not rebase/qimport) and push again.
  hg push
fi

# Output of this is index.html and manifest.plist
# scripts/generate-manifest.py \
#   -f "${APP_FILENAME}" \
#   -d "${ROOT_DEPLOYMENT_ADDRESS}/Viewfinder/manifest.plist"
