
#include <android/log.h>
#include <leveldb/db.h>
#include <Server.pb.h>
#include <sha1.h>

#include "Analytics.h"
#include "Callback.h"
#include "DigestUtils.h"
#include "JsonUtils.h"
#include "Logging.h"
#include "PhoneUtils.h"
#include "StringUtils.h"

#include "NativeAppState.h"
#include "Playground.h"

#define TAG "viewfinder.jni.PLAYGROUND"

typedef Callback<int (const string&, const string&)> DBCallback;
void IterateTable(DBCallback f) {
  leveldb::Iterator* it = db()->NewIterator();
  for (it->SeekToFirst(); it->Valid(); it->Next()) {
    string strKey(it->key().ToString());
    string strValue(it->value().ToString());
    int ret = f(strKey, strValue);
    LOG(" *** Callback return value: %d", ret);
    LOG(" *** LevelDB Dump (plain): %s: %s", strKey.c_str(), strValue.c_str());
  }
  delete it;
}


int LogOneDBEntry(const string& key, const string& value) {
  LOG(" *** LevelDB Dump (function): %s: %s", key.c_str(), value.c_str());
  return -1;
}

void JNICALL DumpValues(JNIEnv* env, jobject obj) {
  int by_ref = 0;
  int by_val = 0;

  LOG(" *** Before lambda capture: by_ref=%d, by_val=%d", by_ref, by_val);

  // Lambda declaration: http://en.cppreference.com/w/cpp/language/lambda
  // [by_val, &by_ref]                            by_val is captured by value, by_ref by reference.
  // (const string& key, cnst string& value)      arguments.
  // mutable                                      allow mutation of elements (in this case: by_val)
  // -> int                                       return type (optional, is usually guessed from the return)
  DBCallback lambda([by_val,&by_ref](const string& key, const string& value) mutable -> int {
                        LOG(" *** LevelDB Dump (lambda): %s: %s", key.c_str(), value.c_str());
                        by_ref++;
                        by_val++;
                        LOG(" *** In lambda capture: by_ref=%d, by_val=%d", by_ref, by_val);
                        return by_val + by_ref;
                      });

  // We could just pass the whole block without "lambda", but this was getting ugly.
  IterateTable(lambda);
  IterateTable(&LogOneDBEntry);

  lambda("END", "nada");

  LOG(" *** After lambda capture: by_ref=%d, by_val=%d", by_ref, by_val);
}


void JNICALL SetValue(JNIEnv* env, jobject obj, jstring j_strKey, jstring j_strValue) {
  const char * key_str = env->GetStringUTFChars(j_strKey, NULL);
  const char * value_str = env->GetStringUTFChars(j_strValue, NULL);
  string strKey(key_str);
  string strValue(value_str);

  LOG(" *** LevelDB Put: %s: %s", strKey.c_str(), strValue.c_str());
  db()->Put(strKey, strValue);

  env->ReleaseStringUTFChars(j_strKey, key_str);
  env->ReleaseStringUTFChars(j_strValue, value_str);
}

jstring JNICALL GetValue(JNIEnv* env, jobject obj, jstring j_strKey) {
  const char * key_str = env->GetStringUTFChars(j_strKey, NULL);
  string strKey(key_str);
  string strValue;

  bool status = db()->Get(strKey, &strValue);
  LOG(" *** LevelDB Get: %s: %s", strKey.c_str(), strValue.c_str());

  env->ReleaseStringUTFChars(j_strKey, key_str);

  if (status)
  {
    return env->NewStringUTF(strValue.c_str());
  }

  return NULL;
}

void JNICALL Put(JNIEnv* env, jobject obj, jstring j_strKey, jbyteArray j_byteValue) {
  const char * key_str = env->GetStringUTFChars(j_strKey, NULL);
  jbyte* content_array = env->GetByteArrayElements(j_byteValue, NULL);
  string strKey(key_str);
  string strValue((char*) content_array, env->GetArrayLength(j_byteValue));

  LOG(" *** LevelDB Put: %s: %s", strKey.c_str(), strValue.c_str());
  db()->Put(strKey, strValue);

  env->ReleaseStringUTFChars(j_strKey, key_str);
  env->ReleaseByteArrayElements(j_byteValue, content_array, 0);
}

jbyteArray JNICALL Get(JNIEnv* env, jobject obj, jstring j_strKey) {
  const char * key_str = env->GetStringUTFChars(j_strKey, NULL);
  string strKey(key_str);
  string strValue;

  bool status = db()->Get(strKey, &strValue);
  LOG(" *** LevelDB Get: %s: %s", strKey.c_str(), strValue.c_str());

  env->ReleaseStringUTFChars(j_strKey, key_str);

  if (status)
  {
    jbyteArray result = env->NewByteArray(strValue.size());
    env->SetByteArrayRegion(result, 0, strValue.size(), (jbyte*) strValue.c_str());
    return result;
  }

  return NULL;
}

void JNICALL PassSerializedProto(JNIEnv* env, jobject obj, jbyteArray j_byteValue) {
  jbyte* content_array = env->GetByteArrayElements(j_byteValue, NULL);
  string strValue((char*) content_array, env->GetArrayLength(j_byteValue));

  AuthResponse resp;
  resp.ParseFromString(strValue);
  LOG("**** Proto after JNI barrier: %s", resp.DebugString().c_str());
  env->ReleaseByteArrayElements(j_byteValue, content_array, 0);

  // Build a json object out of it.
  JsonDict dict({ { "user_id", resp.user_id() },
                  { "device_id", resp.device_id() },
                  { "token_digits", resp.token_digits() } });
  LOG("**** Json version: %s", dict.FormatCompact().c_str());

  // Test analytics.
  Analytics an(true);
  an.NetworkAuthViewfinder(500, 0.2);

  // Test PhoneNumbers lib.
  LOG("**** Valid number (+1-917-123-4567): %d", IsValidPhoneNumber("+1-918-123-4567", "+1"));
}

// Use function from StringUtils when ported.
const char kHexChars[] = "0123456789abcdef";
string BinaryToHex(const string& b) {
  string h(b.size() * 2, '0');
  const uint8_t* p = (const uint8_t*)b.data();
  for (int i = 0; i < b.size(); ++i) {
    const int c = p[i];
    h[2 * i] = kHexChars[c >> 4];
    h[2 * i + 1] = kHexChars[c & 0xf];
  }
  return h;
}

void JNICALL TestMD5Sum(JNIEnv* env, jobject obj, jbyteArray j_byteValue) {
  // Check against output of: echo -n "<arg>" | md5sum
  jbyte* content_array = env->GetByteArrayElements(j_byteValue, NULL);
  string strValue((char*) content_array, env->GetArrayLength(j_byteValue));

  string hex_digest = MD5(strValue);
  string base64 = MD5HexToBase64(hex_digest);
  LOG("**** Arg: %s, sha1sum: %s, base64: %s", strValue.c_str(), hex_digest.c_str(), base64.c_str());

  env->ReleaseByteArrayElements(j_byteValue, content_array, 0);
}
