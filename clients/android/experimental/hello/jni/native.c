#include <jni.h>
#include <string.h>
#include <android/log.h>
#define TAG "HelloActivity.Native"

void Java_com_hello_HelloActivity_nativeLog(JNIEnv * env, jobject this, jstring str) {
  jboolean isCopy;
  const char * log_str = (*env)->GetStringUTFChars(env, str, &isCopy);
  __android_log_print(ANDROID_LOG_INFO, TAG, "Native log: %s", log_str);
  (*env)->ReleaseStringUTFChars(env, str, log_str);
}
