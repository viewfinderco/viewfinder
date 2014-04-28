// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault

#ifndef VIEWFINDER_JNI_PLAYGROUND_H
#define VIEWFINDER_JNI_PLAYGROUND_H

#include <jni.h>

void JNICALL DumpValues(JNIEnv* env, jobject obj);
void JNICALL SetValue(JNIEnv* env, jobject obj, jstring j_strKey, jstring j_strValue);
jstring JNICALL GetValue(JNIEnv* env, jobject obj, jstring j_strKey);
void JNICALL Put(JNIEnv* env, jobject obj, jstring j_strKey, jbyteArray j_byteValue);
jbyteArray JNICALL Get(JNIEnv* env, jobject obj, jstring j_strKey);
void JNICALL PassSerializedProto(JNIEnv* env, jobject obj, jbyteArray j_byteValue);
void JNICALL TestMD5Sum(JNIEnv* env, jobject obj, jbyteArray j_byteValue);
jint JNICALL TestJavaCallback(JNIEnv* env, jobject obj, jstring j_str);

#endif // VIEWFINDER_JNI_PLAYGROUND_H
