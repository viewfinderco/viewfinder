// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault

#ifndef VIEWFINDER_JNI_NATIVE_APP_STATE_H
#define VIEWFINDER_JNI_NATIVE_APP_STATE_H

#include "AppState.h"
#include "JNIUtils.h"

class NativeAppState : public AppState {
 public:
  NativeAppState(const string& base_dir, int server_port, JNIEnv* env, jobject app_state);
  virtual ~NativeAppState();

  virtual InitAction GetInitAction();
  virtual bool Init(InitAction init_action);
  virtual void RunMaintenance(InitAction init_action);

  virtual void SetupViewpointTransition(int64_t viewpoint_id, const DBHandle& updates);
  virtual bool CloudStorageEnabled();
  virtual void DeleteAsset(const string& key);
  virtual void ProcessPhotoDuplicateQueue();
  virtual void LoadViewfinderImages(int64_t photo_id, const DBHandle& db,
                                    Callback<void (bool)> completion);
  virtual int TimeZoneOffset(WallTime t) const;

  virtual SubscriptionManager* subscription_manager() const { return NULL; }

  virtual string timezone() const;

  JNIEnv* jni_env() const {
    return GetJNIEnv(jvm_);
  }

  ScopedLocalRef<jobject> app_state(JNIEnv* env) const {
    return ScopedLocalRef<jobject>(env, env->NewLocalRef(weak_app_state_));
  }

  ScopedLocalRef<jobject> app_state() const {
    JNIEnv* env = jni_env();
    return ScopedLocalRef<jobject>(env, env->NewLocalRef(weak_app_state_));
  }

 protected:
  virtual DayTableEnv* NewDayTableEnv();
  virtual bool MaybeMigrate(ProgressUpdateBlock progress_update);

 private:
  JavaVM* const jvm_;
  jweak weak_app_state_;
};

#endif // VIEWFINDER_JNI_NATIVE_APP_STATE_H
