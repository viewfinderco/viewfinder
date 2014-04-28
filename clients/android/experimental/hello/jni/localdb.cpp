/*  Copyright 2013 Viewfinder Inc. All Rights Reserved.

localdb.cpp

*/

#include <jni.h>
#include <string>

#include <com_hello_LocalDB.h>

#include <android/log.h>
#include <leveldb/db.h>

using namespace std;

#define TAG "LevelDB"
static leveldb::DB* gs_pleveldb = NULL;

/*
 * Class:     com_hello_LocalDB
 * Method:    Load
 * Signature: (Ljava/lang/String;)V
 */
JNIEXPORT void JNICALL Java_com_hello_LocalDB_Load(JNIEnv *env, jobject obj, jstring jstr_path) {
  const char *path_str = env->GetStringUTFChars(jstr_path, 0);
  string str(path_str);

  leveldb::DB* pleveldb = NULL;
  leveldb::Options options;
  options.create_if_missing = true;
  leveldb::Status status = leveldb::DB::Open(options, path_str, &pleveldb);
  if (status.ok())
  {
    gs_pleveldb = pleveldb;
  }
  env->ReleaseStringUTFChars(jstr_path, path_str);
}

/*
 * Class:     com_hello_LocalDB
 * Method:    IsLoaded
 * Signature: ()Z
 */
JNIEXPORT jboolean JNICALL Java_com_hello_LocalDB_IsLoaded(JNIEnv *env, jobject obj)
{
  return gs_pleveldb != NULL;
}

/*
 * Class:     com_hello_LocalDB
 * Method:    Unload
 * Signature: ()V
 */
JNIEXPORT void JNICALL Java_com_hello_LocalDB_Unload(JNIEnv *env, jobject obj) {
  if (gs_pleveldb != NULL) {
    leveldb::DB* pleveldb = gs_pleveldb;
    gs_pleveldb = NULL;
    delete pleveldb;
  }
}

/*
 * Class:     com_hello_LocalDB
 * Method:    DumpValues
 * Signature: ()V
 */
JNIEXPORT void JNICALL Java_com_hello_LocalDB_DumpValues(JNIEnv* env, jobject obj) {

  leveldb::Iterator* it = gs_pleveldb->NewIterator(leveldb::ReadOptions());
  for (it->SeekToFirst(); it->Valid(); it->Next()) {
    string strKey(it->key().ToString());
    string strValue(it->value().ToString());
    __android_log_print(ANDROID_LOG_INFO, TAG, " *** LevelDB Dump: %s: %s", strKey.c_str(), strValue.c_str());
  }
  delete it;
}

/*
 * Class:     com_hello_LocalDB
 * Method:    SetValue
 * Signature: (Ljava/lang/String;Ljava/lang/String;)V
 */
JNIEXPORT void JNICALL Java_com_hello_LocalDB_SetValue(JNIEnv* env,
                                                       jobject obj,
                                                       jstring j_strKey,
                                                       jstring j_strValue) {
  const char * key_str = env->GetStringUTFChars(j_strKey, NULL);
  const char * value_str = env->GetStringUTFChars(j_strValue, NULL);
  string strKey(key_str);
  string strValue(value_str);

  gs_pleveldb->Put(leveldb::WriteOptions(), strKey, strValue);

  env->ReleaseStringUTFChars(j_strKey, key_str);
  env->ReleaseStringUTFChars(j_strValue, value_str);
}

/*
 * Class:     com_hello_LocalDB
 * Method:    GetValue
 * Signature: (Ljava/lang/String;)Ljava/lang/String;
 */
JNIEXPORT jstring JNICALL Java_com_hello_LocalDB_GetValue(JNIEnv* env, jobject obj, jstring j_strKey) {
  const char * key_str = env->GetStringUTFChars(j_strKey, NULL);
  string strKey(key_str);
  string strValue;

  leveldb::Status status = gs_pleveldb->Get(leveldb::ReadOptions(), strKey, &strValue);

  env->ReleaseStringUTFChars(j_strKey, key_str);

  if (status.ok())
  {
    return env->NewStringUTF(strValue.c_str());
  }

  return NULL;
}
