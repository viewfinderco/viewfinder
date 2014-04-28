// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_NETWORK_MANAGER_H
#define VIEWFINDER_NETWORK_MANAGER_H

#import <deque>
#import "Callback.h"
#import "DB.h"
#import "Mutex.h"
#import "ScopedPtr.h"
#import "ServerUtils.h"
#import "Timer.h"
#import "WallTime.h"

class AppState;
class NetworkManager;

// The network manager manages several logical queues.  Only one request per queue type
// can be in flight at a time.
enum NetworkManagerQueueType {
  // The ping request gets its own queue because we want to block all other queues until it has completed.
  NETWORK_QUEUE_PING,

  // The refresh queue performs high-priority low-bandwidth operations; mainly downloading metadata from the
  // server.  These operations are paused while scrolling and during similar interactions to prevent UI
  // hiccups, but they may be performed while the sync queue is in the middle of a long upload or download.
  // The refresh_start and refresh_end callbacks are related to operations in this queue.
  NETWORK_QUEUE_REFRESH,

  // Long-polling query_notifications requests happen in their own queue.  Note that an explicit refresh
  // does a non-long-poll query_notifications in the REFRESH queue (which must come before this one).
  NETWORK_QUEUE_NOTIFICATION,

  // The sync queue handles uploading our state to the server as well as downloads of photo data.
  // The NetworkQueue priority scheme and the network_ready callback relate to operations in this queue.
  // TODO(ben): Refactor PhotoManager's MaybeQueueNetwork so we can split PRIORITY_UI_* ops into a
  // separate queue.
  NETWORK_QUEUE_SYNC,

  NUM_NETWORK_QUEUE_TYPES,
};

class NetworkRequest {
  friend class NetworkRequestImpl;

 public:
  NetworkRequest(NetworkManager* net, NetworkManagerQueueType queue);
  virtual ~NetworkRequest();

  AppState* state() const { return state_; }
  const string& url() const { return url_; }

 protected:
  virtual void HandleRedirect(
      ScopedPtr<string>* new_body,
      StringSet* delete_headers, StringMap* add_headers);
  virtual void HandleData(const Slice& d);
  virtual void HandleError(const string& e) = 0;
  virtual bool HandleDone(int status_code) = 0;

  void SendGet(const string& url);
  void SendPost(const string& url, const Slice& body, const Slice& content_type);
  void SendPut(const string& url, const Slice& body,
               const Slice& content_type, const Slice& content_md5,
               const Slice& if_none_match);
  void Send(const string& url, const Slice& method, const Slice& body,
            const Slice& content_type, const Slice& content_md5,
            const Slice& if_none_match);

 protected:
  NetworkManager* const net_;
  AppState* const state_;
  const NetworkManagerQueueType queue_type_;
  const WallTimer timer_;
  string url_;
  string data_;
};

class NetworkManager {
  friend class AddFollowersRequest;
  friend class AuthRequest;
  friend class DownloadPhotoRequest;
  friend class MergeAccountsRequest;
  friend class NetworkRequest;
  friend class NetworkRequestImpl;
  friend class PingRequest;
  friend class PostCommentRequest;
  friend class QueryContactsRequest;
  friend class QueryEpisodesRequest;
  friend class QueryFollowedRequest;
  friend class QueryNotificationsRequest;
  friend class QueryUsersRequest;
  friend class QueryViewpointsRequest;
  friend class RecordSubscriptionRequest;
  friend class RemoveFollowersRequest;
  friend class RemovePhotosRequest;
  friend class ResolveContactsRequest;
  friend class SavePhotosRequest;
  friend class ShareRequest;
  friend class UnshareRequest;
  friend class UpdateDeviceRequest;
  friend class UpdateFriendRequest;
  friend class UpdateUserRequest;
  friend class UpdateUserPhotoRequest;
  friend class UpdateViewpointRequest;
  friend class UploadEpisodeRequest;
  friend class UploadLogRequest;
  friend class UploadPhotoRequest;
  friend class VerifyViewfinderRequest;

  static const WallTime kMinBackoffDelay;

 public:
  struct QueueState {
    QueueState()
        : network_count(0),
          backoff_count(0),
          backoff_delay(kMinBackoffDelay) {
    }
    int network_count;
    int backoff_count;
    WallTime backoff_delay;
  };

  typedef Callback<void (int, int, const string&)> AuthCallback;
  typedef Callback<void (const string&)> FetchContactsCallback;

 public:
  NetworkManager(AppState* state);
  virtual ~NetworkManager();

  void Dispatch();
  bool Refresh();

  // Clear any saved error status and allow network operations to resume.
  void ResetBackoff();

  // Reset the backoff used for background query notifications.
  virtual void ResetQueryNotificationsBackoff() = 0;

  // Should the application badge be cleared.
  virtual bool ShouldClearApplicationBadge() = 0;
  // Clear the application badge.
  virtual void ClearApplicationBadge() = 0;

  // Non-queued network operations.  The following methods can be
  // called to start a network operation without waiting for the
  // queue.

  // Attempts to resolve the given identity (which must begin with
  // "Email:") and add it to the ContactManager.  To see the results,
  // add a contact_resolved callback on the ContactManager.
  void ResolveContact(const string& identity);

  // Fetch the contacts for the specified auth service. Returns true if a fetch
  // contacts request was started.
  bool FetchFacebookContacts(const string& access_token, const FetchContactsCallback& done);
  bool FetchGoogleContacts(const string& refresh_token, const FetchContactsCallback& done);

  // Start an authorization for a Viewfinder authorized identity (e.g. Email:
  // or Phone:). In cases where the endpoint is "link" or "register", the name
  // field may be non-empty. The "done" callback is invoked upon completion
  // with the first parameter indicating the status code and the third a
  // user-facing message from the server detailing the result.
  void AuthViewfinder(
      const string& endpoint, const string& identity, const string& password,
      const string& first, const string& last, const string& name,
      bool error_if_linked, const AuthCallback& done);

  // Verifies the identity using the specified access token. Upon receiving a
  // verification link, the client clicks a link which redirects to the app or
  // manually enters an access token. The "done" callback is invoked upon
  // completion with the first parameter indicating the status code and the
  // third a user-facing message from the server detailing the result.
  void VerifyViewfinder(
      const string& identity, const string& access_token,
      bool manual_entry, const AuthCallback& done);

  // Submit a change password request. The "done" callback is invoked upon
  // completion with the first parameter indicating the status code and the
  // third a user-facing message from the server detailing the result.
  void ChangePassword(
      const string& old_password, const string& new_password,
      const AuthCallback& done);

  // Merge with the user account specified by source_identity (retrieved by
  // performing a /merge_token/viewfinder request). On completion of the merge
  // operation, completion_db_key will be deleted from the database. The "done"
  // callback is invoked upon completion with the first parameter indicating
  // the status code and the third a user-facing message from the server
  // detailing the result.
  void MergeAccounts(
      const string& identity, const string& access_token,
      const string& completion_db_key, const AuthCallback& done);

  void SetPushNotificationDeviceToken(const string& base64_token);
  // Pause/resume background operations such as querying
  // notifications/viewpoints/episodes/photos.
  void PauseNonInteractive();
  void ResumeNonInteractive();
  void SetNetworkDisallowed(bool disallowed);
  void RunDownloadBenchmark();

  virtual void Logout(bool clear_user_id = true);
  virtual void UnlinkDevice();

  // Prepares the NetworkManager for shutdown. Once Drain() returns no more
  // requests will be started.
  void Drain();

  CallbackSet* network_changed() { return &network_changed_; }
  CallbackSet* refresh_start() { return &refresh_start_; }
  CallbackSet* refresh_end() { return &refresh_end_; }
  bool network_up() const { return network_reachable_ || last_request_success_; }
  bool network_wifi() const { return network_wifi_; }

  AppState* state() const { return state_; }

  void set_fake_401(bool val) { fake_401_ = val; }
  bool fake_401() { return fake_401_; }

  bool need_auth() const;

 protected:
  virtual void SetIdleTimer() = 0;
  void AssetScanEnd();

 private:
  // Sub-dispatch functions for the four network queues.
  void DispatchPingLocked();
  void DispatchNotificationLocked();
  void DispatchRefreshLocked();
  void DispatchSyncLocked();

  void MaybePingServer();
  void MaybeBenchmarkDownload();
  void MaybeDownloadPhoto();
  void MaybeQueryContacts();
  void MaybeQueryEpisodes();
  void MaybeQueryFollowed();
  void MaybeQueryNotifications(bool long_poll);
  void MaybeQueryUsers();
  void MaybeQueryViewpoints();
  void MaybeRecordSubscription();
  void MaybeRemoveContacts();
  void MaybeRemovePhotos();
  void MaybeUpdateDevice();
  void MaybeUpdateFriend();
  void MaybeUpdatePhoto();
  void MaybeUpdateUser();
  void MaybeUpdateViewpoint();
  void MaybeUploadActivity();
  void MaybeUploadContacts();
  void MaybeUploadEpisode();
  void MaybeUploadLog();
  void MaybeUploadPhoto();
  void StartRequestLocked(NetworkManagerQueueType queue);
  void FinishRequest(bool success, int epoch, NetworkManagerQueueType queue);
  void PauseLocked(NetworkManagerQueueType queue);
  void ResumeLocked(NetworkManagerQueueType queue);
  void BackoffLocked(NetworkManagerQueueType queue);
  void ResumeFromBackoffLocked(NetworkManagerQueueType queue);

  virtual void AuthDone() = 0;
  virtual void SendRequest(
      NetworkRequest* req, const Slice& method, const Slice& body,
      const Slice& content_type, const Slice& content_md5,
      const Slice& if_none_match) = 0;

  // Clears keys for querying all followed viewpoints to rebuild all asset
  // hierarchies from scratch.
  void NuclearInvalidation(const DBHandle& updates);

  int epoch() {
    MutexLock l(&mu_);
    return epoch_;
  }

  virtual bool pause_non_interactive() const = 0;
  bool queue_is_busy(NetworkManagerQueueType queue) const;

  // Resets the last ping timestamp and attempts to send a new ping.
  void ResetPing();

  const string& xsrf_cookie() const;

 protected:
  AppState* state_;
  mutable Mutex mu_;
  CallbackSet network_changed_;
  CallbackSet refresh_start_;
  CallbackSet refresh_end_;
  QueueState queue_state_[NUM_NETWORK_QUEUE_TYPES];
  int pause_non_interactive_count_;
  int epoch_;
  bool last_request_success_;
  bool refreshing_;
  bool network_reachable_;
  bool network_wifi_;
  bool need_query_followed_;
  string query_followed_last_key_;
  bool update_device_;
  bool assets_scanned_;
  bool draining_;
  bool network_disallowed_;
  bool register_new_user_;
  WallTime last_ping_timestamp_;
  bool fake_401_;
  std::deque<string> benchmark_urls_;
};

#endif  // VIEWFINDER_NETWORK_MANAGER_H
