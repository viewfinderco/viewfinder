#include <jni.h>
#include <android/log.h>

#include <map>
#include <string>

#define TAG "HelloActivity.Native"

using namespace std;

extern "C" {
  JNIEXPORT void JNICALL Java_com_hello_HelloActivity_nativeCPPLog(JNIEnv * env, jobject obj, jstring j_str);
};

JNIEXPORT void JNICALL Java_com_hello_HelloActivity_nativeCPPLog(JNIEnv * env, jobject j_obj, jstring j_str) {
  jboolean isCopy;
  const char * log_str = env->GetStringUTFChars(j_str, &isCopy);
  string str(log_str);
  __android_log_print(ANDROID_LOG_INFO, TAG, "Native log: %s", log_str);
  env->ReleaseStringUTFChars(j_str, log_str);

  map<string, int> sample_map;
  sample_map.insert(make_pair(str, 1));
  __android_log_print(ANDROID_LOG_INFO, TAG, "Native log: map size: %ld", sample_map.size());
}
