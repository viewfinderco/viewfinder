#!/bin/bash
cd "$(dirname $0)/../"

# The android gyp backend is pretty strict about paths, so generate third-party separately.
CUR_PATH=$(pwd)
SHARED_TP="${CUR_PATH}/third_party/shared"
ANDROID_HOME="${CUR_PATH}/clients/android"
ANDROID_JNI="${CUR_PATH}/clients/android/jni"
SHARED_CLIENTS="${CUR_PATH}/clients/shared"

#export ANDROID_BUILD_TOP=${ANDROID_HOME}
export ANDROID_BUILD_TOP="${CUR_PATH}/"
#echo "Set ANDROID_BUILD_TOP=${ANDROID_BUILD_TOP}"
GENERATOR="android"

#cd ${ANDROID_JNI}
cd ${ANDROID_BUILD_TOP}
gyp --depth=. -DOS=android -f ${GENERATOR} -I${ANDROID_JNI}/globals.gypi ${ANDROID_JNI}/Android.gyp
exit 0

cd ${SHARED_TP}
gyp --depth=. -DOS=android -f ${GENERATOR} -I${ANDROID_HOME}/jni/globals.gypi \
  protobuf.gyp leveldb.gyp re2.gyp icu.gyp snappy.gyp jsoncpp.gyp
cd ${SHARED_CLIENTS}
gyp --depth=. -DOS=android -f ${GENERATOR} -I${ANDROID_HOME}/jni/globals.gypi shared.android.gyp
