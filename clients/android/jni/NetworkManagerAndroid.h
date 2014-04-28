// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_NETWORK_MANAGER_ANDROID_H
#define VIEWFINDER_NETWORK_MANAGER_ANDROID_H

#import "JNIUtils.h"
#import "NetworkManager.h"

class NativeAppState;

class NetworkRequestImpl {
 public:
  NetworkRequestImpl(NetworkManager* net, NetworkRequest* req);
  ~NetworkRequestImpl();

  void StartRequest();
  void Error(const string& error);
  void Done(const string& data, int status_code);
  void Redirect(const string& redirect_host);

 private:
  const int epoch_;
  NetworkManager* net_;
  NetworkRequest* req_;
};

class NetworkManagerAndroid : public NetworkManager {
 public:
  NetworkManagerAndroid(NativeAppState* state);
  virtual ~NetworkManagerAndroid();

  virtual void ResetQueryNotificationsBackoff();
  virtual bool ShouldClearApplicationBadge();
  virtual void ClearApplicationBadge();
  virtual void Logout(bool clear_user_id);
  virtual void UnlinkDevice();

 private:
  virtual void SetIdleTimer();
  virtual void AuthDone();
  virtual void SendRequest(
      NetworkRequest* req, const Slice& method, const Slice& body,
      const Slice& content_type, const Slice& content_md5,
      const Slice& if_none_match);
  virtual bool pause_non_interactive() const;

 private:
  NativeAppState* const state_;
  JavaStaticMethod<void (jlong, string, string, string, string, string, string)> send_request_;
};

#endif  // VIEWFINDER_NETWORK_MANAGER_IOS_H

// local variables:
// mode: c++
// end:
