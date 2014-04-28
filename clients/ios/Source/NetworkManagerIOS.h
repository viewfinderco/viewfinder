// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_NETWORK_MANAGER_IOS_H
#define VIEWFINDER_NETWORK_MANAGER_IOS_H

#import <SystemConfiguration/SCNetworkReachability.h>
#import "BackgroundManager.h"
#import "NetworkManager.h"
#import "ScopedRef.h"

class NetworkManagerIOS : public NetworkManager {
 public:
  NetworkManagerIOS(UIAppState* state);
  virtual ~NetworkManagerIOS();

  virtual void ResetQueryNotificationsBackoff();
  virtual bool ShouldClearApplicationBadge();
  virtual void ClearApplicationBadge();
  virtual void Logout(bool clear_user_id);
  virtual void UnlinkDevice();

  static void Clean(const string& server = string());

 private:
  static void ReachabilityChanged(SCNetworkReachabilityRef target,
                                  SCNetworkConnectionFlags flags,
                                  void *object);
  void ReachabilityChanged(SCNetworkReachabilityRef target,
                           SCNetworkConnectionFlags flags);

  void InitCookies();

  void AddAssetsScanWatcher();

  virtual void SetIdleTimer();
  bool ShouldDisableIdleTimer() const;

  virtual void AuthDone();
  virtual void SendRequest(
      NetworkRequest* req, const Slice& method, const Slice& body,
      const Slice& content_type, const Slice& content_md5,
      const Slice& if_none_match);

  virtual bool pause_non_interactive() const;

 private:
  bool request_in_flight() const;

  UIAppState* const state_;
  ScopedRef<SCNetworkReachabilityRef> reachability_;
  BackgroundManager* bg_mgr_;
};

#endif  // VIEWFINDER_NETWORK_MANAGER_IOS_H
