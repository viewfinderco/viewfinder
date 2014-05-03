// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis

#ifndef VIEWFINDER_JNI_JNI_UTILS_H
#define VIEWFINDER_JNI_JNI_UTILS_H

#include <initializer_list>
#include <jni.h>
#include <google/protobuf/message_lite.h>
#include "Callback.h"
#include "Logging.h"
#include "Utils.h"

// Returns the JNIEnv associated with the specified JavaVM.
inline JNIEnv* GetJNIEnv(JavaVM* vm) {
  JNIEnv* env;
  CHECK_EQ(JNI_OK, vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6));
  return env;
}

// Returns the JavaVM associated with the specified JNIEnv.
inline JavaVM* GetJavaVM(JNIEnv* env) {
  JavaVM* vm;
  CHECK_EQ(JNI_OK, env->GetJavaVM(&vm));
  return vm;
}

// Wrapper around a java local reference that automatically releases the
// reference when destroyed.
template <typename T>
class ScopedLocalRef {
 public:
  ScopedLocalRef(const ScopedLocalRef& r)
      : env_(r.env_),
        obj_(NULL) {
    reset(r.obj_);
  }
  ScopedLocalRef(ScopedLocalRef&& r)
      : env_(r.env_),
        obj_(r.obj_) {
    r.obj_ = NULL;
  }
  ScopedLocalRef(JNIEnv* env, T obj = NULL)
      : env_(env),
        obj_(obj) {
  }
  ~ScopedLocalRef() {
    env_->DeleteLocalRef(obj_);
  }

  void reset(T new_obj) {
    if (obj_ != new_obj) {
      if (obj_) {
        env_->DeleteLocalRef(obj_);
      }
      if (new_obj) {
        obj_ = reinterpret_cast<T>(env_->NewLocalRef(new_obj));
      } else {
        obj_ = NULL;
      }
    }
  }

  ScopedLocalRef<T>& operator=(const ScopedLocalRef<T>& other) {
    reset(other.obj_);
    return *this;
  }

  T get() const { return obj_; }
  operator T() const { return get(); }

 private:
  JNIEnv* const env_;
  T obj_;
};

// Wrapper around a java global reference that automatically releases the
// reference when destroyed. We need the JVM since we may be be destroyed in a
// different thread, so we need a different env.
template <typename T>
class ScopedGlobalRef {
 public:
  ScopedGlobalRef(const ScopedGlobalRef& r)
      : jvm_(r.jvm_),
        obj_(NULL) {
    reset(r.obj_);
  }
  ScopedGlobalRef(ScopedGlobalRef&& r)
      : jvm_(r.jvm_),
        obj_(r.obj_) {
    r.obj_ = NULL;
  }
  ScopedGlobalRef(JavaVM* j, T obj = NULL)
      : jvm_(j),
        obj_(obj) {
  }
  ScopedGlobalRef(JNIEnv* env, T obj = NULL)
      : jvm_(GetJavaVM(env)),
        obj_(obj) {
  }
  ~ScopedGlobalRef() {
    JNIEnv* env = GetJNIEnv(jvm_);
    env->DeleteGlobalRef(obj_);
  }

  void reset(T new_obj) {
    if (obj_ != new_obj) {
      JNIEnv* env = GetJNIEnv(jvm_);
      if (obj_) {
        env->DeleteGlobalRef(obj_);
      }
      if (new_obj) {
        obj_ = reinterpret_cast<T>(env->NewGlobalRef(new_obj));
      } else {
        obj_ = NULL;
      }
    }
  }

  ScopedGlobalRef<T>& operator=(const ScopedGlobalRef<T>& other) {
    reset(other.obj_);
    return *this;
  }

  T get() const { return obj_; }
  operator T() const { return get(); }

 private:
  JavaVM* const jvm_;
  T obj_;
};

// Cloning a weak reference is problematic on old versions of Android. The only
// valid operations on a weak reference are NewLocalRef, NewGlobalRef or
// DeleteWeakGlobalRef. In particular, calling NewWeakGlobalRef on a weak
// reference will result in crashes.
inline jweak JavaCloneWeakRef(JNIEnv* env, jweak weak_obj) {
  ScopedLocalRef<jobject> obj(env, env->NewLocalRef(weak_obj));
  return env->NewWeakGlobalRef(obj);
}

// Find the specified class, returning a ScopedLocalRef.
inline ScopedLocalRef<jclass> JavaFindClass(JNIEnv* env, const char* class_name) {
  return ScopedLocalRef<jclass>(env, env->FindClass(class_name));
}

// Find the class for the specified object, returning a ScopedLocalRef.
inline ScopedLocalRef<jclass> JavaGetObjectClass(JNIEnv* env, jobject obj) {
  return ScopedLocalRef<jclass>(env, env->GetObjectClass(obj));
}

// Convert a Java to C++ string.
inline string JavaToCppString(JNIEnv* env, jobject obj) {
  jstring jstr = reinterpret_cast<jstring>(obj);
  const char* utf_chars = env->GetStringUTFChars(jstr, NULL);
  const string str(utf_chars);
  env->ReleaseStringUTFChars(jstr, utf_chars);
  return str;
}

// Convert a Java byte array to a C++ string.
inline string JavaByteArrayToCppString(JNIEnv* env, jbyteArray obj) {
  jbyte* bytes = env->GetByteArrayElements(obj, NULL);
  const string s = string((char*)bytes, env->GetArrayLength(obj));
  env->ReleaseByteArrayElements(obj, bytes, 0);
  return s;
}

// Convert a C++ vector<jlong> to a Java long array.
inline vector<jlong> JavaLongArrayToCppVector(JNIEnv* env, jlongArray obj) {
  jlong* vals = env->GetLongArrayElements(obj, NULL);
  const vector<jlong> v(vals, vals + env->GetArrayLength(obj));
  env->ReleaseLongArrayElements(obj, vals, 0);
  return v;
}

// Convert a Java pointer (a long) to a C++ pointer.
template <typename T>
inline T* JavaToCppPointer(JNIEnv* env, jlong j_ptr) {
  T* ptr;
  memcpy(&ptr, &j_ptr, sizeof(T*));
  return ptr;
}

// Convert a java proto (a byte array) to a C++ proto.
inline bool JavaToCppProto(
    JNIEnv* env, jbyteArray obj, google::protobuf::MessageLite* message) {
  jbyte* bytes = env->GetByteArrayElements(obj, NULL);
  return message->ParseFromArray(bytes, env->GetArrayLength(obj));
}

// Convert a C++ string to a Java string.
inline jstring CppToJavaString(JNIEnv* env, const string& str) {
  return env->NewStringUTF(str.c_str());
}

// Convert a C++ string to a Java byte array.
inline jbyteArray CppStringToJavaByteArray(JNIEnv* env, const string& s) {
  jbyteArray result = env->NewByteArray(s.size());
  env->SetByteArrayRegion(result, 0, s.size(), (jbyte*)s.data());
  return result;
}

// Convert a C++ vector<jlong> to a Java long array.
inline jlongArray CppVectorToJavaLongArray(JNIEnv* env, const vector<jlong>& v) {
  jlongArray result = env->NewLongArray(v.size());
  env->SetLongArrayRegion(result, 0, v.size(), (jlong*)v.data());
  return result;
}

// Convert a C++ pointer to a Java pointer (a long).
template <typename T>
inline jlong CppToJavaPointer(JNIEnv* env, T* ptr) {
  jlong j_ptr = 0;
  memcpy(&j_ptr, &ptr, sizeof(T*));
  return j_ptr;
}

// Convert a C++ proto to a java proto (a byte array).
inline jbyteArray CppToJavaProto(
    JNIEnv* env, const google::protobuf::MessageLite& message) {
  return CppStringToJavaByteArray(env, message.SerializeAsString());
}

// Helper class for determining the Java type signature for T and preparing a
// "jvalue" in order to invoke a Java method that takes type T as a parameter.
template <typename T>
struct JavaArg;

template <>
struct JavaArg<void> {
  static string Type() {
    return "V";
  }
};

template <>
struct JavaArg<jboolean> {
  static string Type() {
    return "Z";
  }
};

template <>
struct JavaArg<bool> : public JavaArg<jboolean> {
  static bool Prepare(JNIEnv* env, jvalue* value, bool v) {
    value->z = v;
    return false;
  }
};

template <>
struct JavaArg<jbooleanArray> {
  static string Type() {
    return "[Z";
  }
};

template <>
struct JavaArg<vector<bool>> : public JavaArg<jbooleanArray> {
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jbyte> {
  static string Type() {
    return "B";
  }
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jbyteArray> {
  static string Type() {
    return "[B";
  }
};

template <>
struct JavaArg<vector<jbyte>> : public JavaArg<jbyteArray> {
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jchar> {
  static string Type() {
    return "C";
  }
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jcharArray> {
  static string Type() {
    return "[C";
  }
};

template <>
struct JavaArg<vector<jchar>> : public JavaArg<jcharArray> {
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jshort> {
  static string Type() {
    return "S";
  }
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jshortArray> {
  static string Type() {
    return "[S";
  }
};

template <>
struct JavaArg<vector<short>> : public JavaArg<jshortArray> {
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jint> {
  static string Type() {
    return "I";
  }
  static bool Prepare(JNIEnv* env, jvalue* value, jint v) {
    value->i = v;
    return false;
  }
};

template <>
struct JavaArg<jintArray> {
  static string Type() {
    return "[I";
  }
};

template <>
struct JavaArg<vector<int>> : public JavaArg<jintArray> {
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jlong> {
  static string Type() {
    return "J";
  }
  static bool Prepare(JNIEnv* env, jvalue* value, jlong v) {
    value->j = v;
    return false;
  }
};

template <>
struct JavaArg<jlongArray> {
  static string Type() {
    return "[J";
  }
};

template <>
struct JavaArg<vector<long>> : public JavaArg<jlongArray> {
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jfloat> {
  static string Type() {
    return "F";
  }
  static bool Prepare(JNIEnv* env, jvalue* value, jfloat v) {
    value->f = v;
    return false;
  }
};

template <>
struct JavaArg<jfloatArray> {
  static string Type() {
    return "[F";
  }
};

template <>
struct JavaArg<vector<float>> : public JavaArg<jfloatArray> {
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jdouble> {
  static string Type() {
    return "D";
  }
  static bool Prepare(JNIEnv* env, jvalue* value, jdouble v) {
    value->d = v;
    return false;
  }
};

template <>
struct JavaArg<jdoubleArray> {
  static string Type() {
    return "[D";
  }
};

template <>
struct JavaArg<vector<double>> : public JavaArg<jdoubleArray> {
  // TODO(peter): Implement Prepare() when needed.
};

template <>
struct JavaArg<jstring> {
  static string Type() {
    return "Ljava/lang/String;";
  }
};

template <>
struct JavaArg<string> : public JavaArg<jstring> {
  static bool Prepare(JNIEnv* env, jvalue* value, const string& v) {
    value->l = CppToJavaString(env, v);
    return true;
  }
};

template <>
struct JavaArg<jobject> {
  static string Type() {
    return "Ljava/lang/Object;";
  }
  static bool Prepare(JNIEnv* env, jvalue* value, jobject v) {
    value->l = v;
    return false;
  }
};

template <>
struct JavaArg<jobjectArray> {
  static string Type() {
    return "[Ljava/lang/Object;";
  }
  // TODO(peter): Implement Prepare() when needed.
};

// Helper class which constructs the Java method argument signature from the
// specified C++ types. For example, JavaArgSignature<bool, int>::Get() will
// return "ZI".
template <typename... ArgTypes>
struct JavaArgSignature;

// The base case, no types is the empty signature.
template <>
struct JavaArgSignature<> {
  static string Get() {
    return "";
  }
};

// The recursive case, concatenate the type signature for T with the type
// signature for ArgTypes.
template <typename T, typename... ArgTypes>
struct JavaArgSignature<T, ArgTypes...> {
  static string Get() {
    return JavaArg<T>::Type() + JavaArgSignature<ArgTypes...>::Get();
  }
};

// Helper class which constructs the Java method signature from the specified
// C++ return values and arguments.
template <typename R>
struct JavaMethodSignature;

template <typename R, typename... ArgTypes>
struct JavaMethodSignature<R (ArgTypes...)> {
  static string Get() {
    return "(" + JavaArgSignature<ArgTypes...>::Get() + ")" + JavaArg<R>::Type();
  }
};

// Helper function which prepares an array of jvalues from C++ arguments. This
// is the base case where we've reached the end of the arguments.
inline void JavaPrepareArgs(JNIEnv* env, jvalue* values, bool* refs, int index) {
}

// The recursive case, prepare values[index] and recursively prepares the
// remaining arguments.
template <typename T, typename... ArgTypes>
void JavaPrepareArgs(
    JNIEnv* env, jvalue* values, bool* is_ref, int index, T value, ArgTypes...args) {
  is_ref[index] = JavaArg<T>::Prepare(env, &values[index], value);
  JavaPrepareArgs(env, values, is_ref, index + 1, args...);
}

// Helper class for preparing and holding an array of jvalues from C++
// arguments.
template <typename R>
struct JavaMethodArgs;

template <typename R, typename... ArgTypes>
struct JavaMethodArgs<R (ArgTypes...)> {
  JavaMethodArgs(JNIEnv* e, ArgTypes... a)
      : env(e) {
    JavaPrepareArgs(env, args, is_ref, 0, a...);
  }
  ~JavaMethodArgs() {
    for (int i = 0; i < sizeof...(ArgTypes); ++i) {
      if (is_ref[i]) {
        env->DeleteLocalRef(args[i].l);
      }
    }
  }
  JNIEnv* const env;
  jvalue args[sizeof...(ArgTypes)];
  bool is_ref[sizeof...(ArgTypes)];
};

// Helper class for invoking a java method with the specified return type R.
template <typename R>
struct JavaMethodResult;

template <>
struct JavaMethodResult<void> {
  static void Invoke(JNIEnv* env, jobject obj, jmethodID method_id, jvalue* args) {
    env->CallVoidMethodA(obj, method_id, args);
  }
  static void InvokeStatic(JNIEnv* env, jclass c, jmethodID method_id, jvalue* args) {
    env->CallStaticVoidMethodA(c, method_id, args);
  }
};

template <>
struct JavaMethodResult<jint> {
  static jint Invoke(JNIEnv* env, jobject obj, jmethodID method_id, jvalue* args) {
    return env->CallIntMethodA(obj, method_id, args);
  }
  static jint InvokeStatic(JNIEnv* env, jclass c, jmethodID method_id, jvalue* args) {
    return env->CallStaticIntMethodA(c, method_id, args);
  }
};

template <>
struct JavaMethodResult<jlong> {
  static jlong Invoke(JNIEnv* env, jobject obj, jmethodID method_id, jvalue* args) {
    return env->CallLongMethodA(obj, method_id, args);
  }
  static jlong InvokeStatic(JNIEnv* env, jclass c, jmethodID method_id, jvalue* args) {
    return env->CallStaticLongMethodA(c, method_id, args);
  }
};

template <>
struct JavaMethodResult<string> {
  static string Invoke(JNIEnv* env, jobject obj, jmethodID method_id, jvalue* args) {
    ScopedLocalRef<jobject> result(env, env->CallObjectMethodA(obj, method_id, args));
    return JavaToCppString(env, result);
  }
  static string InvokeStatic(JNIEnv* env, jclass c, jmethodID method_id, jvalue* args) {
    ScopedLocalRef<jobject> result(env, env->CallStaticObjectMethodA(c, method_id, args));
    return JavaToCppString(env, result);
  }
};

// Convenience class for invoking a Java method on an object. Automatically
// constructs the Java type signature from the specified C++ return type and
// argument types. Holds a weak global reference to the object.
template <typename R>
struct JavaMethod;

template <typename R, typename... ArgTypes>
struct JavaMethod<R (ArgTypes...)> {
  JavaMethod(const JavaMethod& m)
      : jvm(m.jvm),
        weak_obj(JavaCloneWeakRef(GetJNIEnv(jvm), m.weak_obj)),
        method_id(m.method_id),
        method_name(m.method_name) {
  }
  JavaMethod(JavaMethod&& m)
      : jvm(m.jvm),
        weak_obj(m.weak_obj),
        method_id(m.method_id),
        method_name(m.method_name) {
    m.weak_obj = NULL;
  }
  JavaMethod(JNIEnv* env, jobject obj, const char* method_name)
      : JavaMethod(
          GetJavaVM(env), env, obj,
          env->GetMethodID(
              JavaGetObjectClass(env, obj), method_name,
              JavaMethodSignature<R (ArgTypes...)>::Get().c_str()),
          method_name) {
  }
  JavaMethod(JavaVM* j, JNIEnv* env, jobject obj, jmethodID m, const char* n)
      : jvm(j),
        weak_obj(env->NewWeakGlobalRef(obj)),
        method_id(m),
        method_name(n) {
  }
  ~JavaMethod() {
    if (weak_obj) {
      JNIEnv* const env = GetJNIEnv(jvm);
      env->DeleteWeakGlobalRef(weak_obj);
    }
  }

  R Invoke(ArgTypes... args) const {
    JNIEnv* const env = GetJNIEnv(jvm);
    ScopedLocalRef<jobject> obj(env, env->NewLocalRef(weak_obj));
    if (!obj.get()) {
      return R();
    }
    return Invoke(GetJNIEnv(jvm), obj, args...);
  }

  R Invoke(JNIEnv* env, jobject obj, ArgTypes... args) const {
    JavaMethodArgs<R (ArgTypes...)> a(env, args...);
    return JavaMethodResult<R>::Invoke(env, obj, method_id, a.args);
  }

  static R Invoke(JNIEnv* env, jobject obj, const char* method_name, ArgTypes... args) {
    JavaMethod method(env, obj, method_name);
    return method.Invoke(env, obj, args...);
  }

  JavaVM* const jvm;
  jweak weak_obj;
  const jmethodID method_id;
  const char* method_name;
};

// Convenience class for invoking a Java static method. Automatically
// constructs the Java type signature from the specified C++ return type and
// argument types. Holds a global reference to the class.
template <typename R>
struct JavaStaticMethod;

template <typename R, typename... ArgTypes>
struct JavaStaticMethod<R (ArgTypes...)> {
  JavaStaticMethod(const JavaStaticMethod& m)
      : JavaStaticMethod(m.jvm, GetJNIEnv(m.jvm),
                         m.j_class, m.method_id, m.method_name) {
  }
  JavaStaticMethod(JavaStaticMethod&& m)
      : jvm(m.jvm),
        j_class(m.j_class),
        method_id(m.method_id),
        method_name(m.method_name) {
    m.j_class = NULL;
  }
  JavaStaticMethod(JNIEnv* env, const char* class_name, const char* method_name)
      : JavaStaticMethod(env, JavaFindClass(env, class_name), method_name) {
  }
  JavaStaticMethod(JNIEnv* env, jclass c, const char* method_name)
      : JavaStaticMethod(
          GetJavaVM(env), env, c,
          env->GetStaticMethodID(
              c, method_name,
              JavaMethodSignature<R (ArgTypes...)>::Get().c_str()),
          method_name) {
  }
  JavaStaticMethod(JavaVM* j, JNIEnv* env, jclass c, jmethodID m, const char* n)
      : jvm(j),
        j_class(reinterpret_cast<jclass>(env->NewGlobalRef(c))),
        method_id(m),
        method_name(n) {
  }
  ~JavaStaticMethod() {
    if (j_class) {
      JNIEnv* const env = GetJNIEnv(jvm);
      env->DeleteGlobalRef(j_class);
    }
  }

  R Invoke(ArgTypes... args) const {
    return Invoke(GetJNIEnv(jvm), args...);
  }

  R Invoke(JNIEnv* env, ArgTypes... args) const {
    JavaMethodArgs<R (ArgTypes...)> a(env, args...);
    return JavaMethodResult<R>::InvokeStatic(env, j_class, method_id, a.args);
  }

  static R Invoke(JNIEnv* env, const char* class_name, const char* method_name, ArgTypes... args) {
    JavaStaticMethod method(env, class_name, method_name);
    return method.Invoke(env, args...);
  }

  static R Invoke(JNIEnv* env, jclass c, const char* method_name, ArgTypes... args) {
    JavaStaticMethod method(env, c, method_name);
    return method.Invoke(env, args...);
  }

  JavaVM* const jvm;
  jclass j_class;
  const jmethodID method_id;
  const char* method_name;
};

// Adds a Java method to the specified "callbacks", inferring the Java type
// signature from the callback signature.
template <typename... ArgTypes>
void AddJavaCallback(
    JNIEnv* env, jobject obj, const char* method_name,
    CallbackSetBase<ArgTypes...>* callbacks) {
  JavaMethod<void (ArgTypes...)> method(env, obj, method_name);
  callbacks->Add([method](ArgTypes... args) {
      method.Invoke(args...);
    });
}

// Binds a Java method to the specified std::function object, inferring the
// Java type signature from the function signature.
template <typename R, typename... ArgTypes>
void BindJavaStaticMethod(
    JNIEnv* env, jclass c, const char* method_name,
    std::function<R (ArgTypes...)>* func) {
  JavaStaticMethod<R (ArgTypes...)> method(env, c, method_name);
  *func = [method](ArgTypes...args) {
    return method.Invoke(args...);
  };
}

// Utility class to ease the registration of native methods and binding java
// methods to std::function objects.
class JavaClass {
  // Helper class to infer the Java type signature of a native method. Notice
  // that we skip over the first 2 parameters (env and obj/class) when
  // computing the signature.
  struct NativeMethod {
    template <typename R, typename... ArgTypes>
    NativeMethod(const char* n,
                 R (*f)(JNIEnv* env, jobject obj, ArgTypes...))
        : name(n),
          signature(JavaMethodSignature<R (ArgTypes...)>::Get()),
          func((void*)f) {
    }
    template <typename R, typename... ArgTypes>
    NativeMethod(const char* n,
                 R (*f)(JNIEnv* env, jclass c, ArgTypes...))
        : name(n),
          signature(JavaMethodSignature<R (ArgTypes...)>::Get()),
          func((void*)f) {
    }


    operator JNINativeMethod() const {
      return { name, signature.c_str(), func };
    }

    const char* name;
    const string signature;
    void* func;
  };

 public:
  JavaClass(JNIEnv* env, const char* class_name)
      : env_(env),
        j_class_(JavaFindClass(env_, class_name)) {
  }
  JavaClass(JNIEnv* env, jclass c)
      : env_(env),
        j_class_(env, reinterpret_cast<jclass>(env->NewLocalRef(c))) {
  }

  const JavaClass& RegisterNatives(
      std::initializer_list<NativeMethod> methods) const {
    std::vector<JNINativeMethod> jni_methods(methods.begin(), methods.end());
    CHECK_EQ(JNI_OK, env_->RegisterNatives(
                 j_class_, &jni_methods[0], jni_methods.size()));
    return *this;
  }

  template <typename R, typename... ArgTypes>
  const JavaClass& BindStaticMethod(
      const char* method_name, std::function<R (ArgTypes...)>* func) const {
    JavaStaticMethod<R (ArgTypes...)> method(env_, j_class_, method_name);
    *func = [method](ArgTypes...args) {
      return method.Invoke(args...);
    };
    return *this;
  }

  template <typename T>
  jfieldID GetField(const char* field_name) const {
    return env_->GetFieldID(j_class_, field_name, JavaArg<T>::Type().c_str());
  }

 private:
  JNIEnv* const env_;
  ScopedLocalRef<jclass> j_class_;
};

#endif  // VIEWFINDER_JNI_JNI_UTILS_H
