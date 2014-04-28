// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <algorithm>
#import <memory>
#import <unordered_set>
#import <errno.h>
#import <fcntl.h>
#import <unistd.h>
#import "ActivityTable.h"
#import "Analytics.h"
#import "AppState.h"
#import "AsyncState.h"
#import "ContactManager.h"
#import "DB.h"
#import "Defines.h"
#import "DigestUtils.h"
#import "FileUtils.h"
#import "IdentityManager.h"
#import "Logging.h"
#import "NetworkManager.h"
#import "NetworkQueue.h"
#import "NotificationManager.h"
#import "PathUtils.h"
#import "Server.pb.h"
#import "ServerId.h"
#import "ServerUtils.h"
#import "StringUtils.h"
#import "SubscriptionManager.h"
#import "Timer.h"

const WallTime NetworkManager::kMinBackoffDelay = 1;

namespace {

// Disable NETLOG statements in APPSTORE builds as they contain Personally
// Identifiable Information.
#ifdef APPSTORE
#define NETLOG  if (0) VLOG
#else
#define NETLOG  VLOG
#endif

const string kAccessCodeKey = DBFormat::metadata_key("access_code/");
const string kPushDeviceTokenKey = DBFormat::metadata_key("apn_device_token");
const string kQueryFollowedDoneKey =
    DBFormat::metadata_key("query_followed_done_key");
const string kQueryFollowedLastKey =
    DBFormat::metadata_key("query_followed_last_key");

const WallTime kMaxBackoffDelay = 60 * 10;
const WallTime kLogUploadInterval = 10;
const int kQueryContactsLimit = 1000;
const int kQueryUsersLimit = 500;
const int kQueryObjectsLimit = 200;
const int kQueryEpisodesLimit = 100;
const int kQueryFollowedLimit = 100;
const int kQueryNotificationsLimit = 100;
const int kQueryViewpointsLimit = 100;
const WallTime kPingPeriodDefault = 12 * 60 * 60;
const WallTime kPingPeriodFast = 10 * 60;
const WallTime kProspectiveUserCreationDelay = 2;
// For maximum compatibility with uncooperative proxies (e.g. hotel wifi), this should be under a minute.
const WallTime kQueryNotificationsMaxLongPoll = 58;
const WallTime kQueryNotificationsMaxRetryAfter = 3600;

#if defined(APPSTORE) && !defined(ENTERPRISE)
const int kUploadLogOptOutGracePeriod = 600;
#else
const int kUploadLogOptOutGracePeriod = 0;
#endif

const string kJsonContentType = "application/json";
const string kJpegContentType = "image/jpeg";
const string kOctetStreamContentType = "application/octet-stream";

const string kDefaultNetworkErrorMessage =
    "The network is unavailable. Please try again later.";

const string kDefaultLoginErrorMessage =
    "Your Viewfinder login failed. Please try again later.";

const string kDefaultVerifyErrorMessage =
    "Couldn't verify your identity…";

const string kDefaultChangePasswordErrorMessage =
    "Couldn't change your password…";

const string kDownloadBenchmarkURLPrefix = "https://public-ro-viewfinder-co.s3.amazonaws.com/";
const string kDownloadBenchmarkFiles[] = {
  "10KB.test",
  "50KB.test",
  "100KB.test",
  "200KB.test",
  "500KB.test",
  "1MB.test",
  "2MB.test",
};

string FormatUrl(AppState* state, const string& path) {
  return Format("%s://%s:%s%s",
                state->server_protocol(),
                state->server_host(),
                state->server_port(),
                path);
}

string FormatRequest(const JsonDict& dict, int min_required_version = 0,
                     bool synchronous = false) {
  JsonDict headers_dict = JsonDict("version", AppState::protocol_version());
  if (min_required_version > 0) {
    headers_dict.insert("min_required_version", min_required_version);
  }
  if (synchronous) {
    headers_dict.insert("synchronous", synchronous);
  }

  JsonDict req_dict = dict;
  req_dict.insert("headers", headers_dict);
  return req_dict.Format();
}

string FormatRequest(const JsonDict& dict, const OpHeaders& op_headers,
                     AppState* state, int min_required_version = 0) {
  JsonDict headers_dict = JsonDict("version", AppState::protocol_version());
  if (min_required_version > 0) {
    headers_dict.insert("min_required_version", min_required_version);
  }
  if (op_headers.has_op_id()) {
    headers_dict.insert(
        "op_id", EncodeOperationId(state->device_id(), op_headers.op_id()));
  }
  if (op_headers.has_op_timestamp()) {
    headers_dict.insert("op_timestamp", op_headers.op_timestamp());
  }
  JsonDict req_dict = dict;
  req_dict.insert("headers", headers_dict);
  return req_dict.Format();
}

JsonDict FormatDeviceDict(AppState* state) {
  JsonDict device({
      { "os", state->device_os() },
      { "platform", state->device_model() },
      { "version", AppVersion() }
    });
  if (!state->device_name().empty()) {
    device.insert("name", state->device_name());
  }
  if (state->device_id() != 0) {
    device.insert("device_id", state->device_id());
  }

  string push_token;
  if (state->db()->Get(kPushDeviceTokenKey, &push_token)) {
    device.insert("push_token", push_token);
  }

  device.insert("device_uuid", state->device_uuid());
  device.insert("language", state->locale_language());
  device.insert("country", state->locale_country());
  if (!state->test_udid().empty()) {
    device.insert("test_udid", state->test_udid());
  }

  return device;
}

// Create an activity dictionary suitable for passing to the server with ops
// that must create an activity.
const JsonDict FormatActivityDict(const ActivityHandle& ah) {
  return JsonDict({
      { "activity_id", ah->activity_id().server_id() },
      { "timestamp", ah->timestamp() }
    });
}

// Creates a new activity server id using the specified local id and timestamp.
const JsonDict FormatActivityDict(
    AppState* state, int64_t local_id, WallTime timestamp) {
  const string activity_id = EncodeActivityId(
      state->device_id(), local_id, timestamp);
  return JsonDict({
      { "activity_id", activity_id },
      { "timestamp", timestamp }
    });
}

JsonDict FormatAccountSettingsDict(AppState* state) {
  // TODO: add 'email_alerts' field when settable on the client.
  JsonDict account_settings;

  vector<string> storage_options;
  // We use the raw "cloud storage" toggle since we care about user-specified
  // settings, not additional logic.
  if (state->cloud_storage()) {
    storage_options.push_back("use_cloud");
  }
  if (state->store_originals()) {
    storage_options.push_back("store_originals");
  }
  // We need to specify 'storage_options' even if all are off,
  // otherwise the backend would never know.
  account_settings.insert("storage_options",
                          JsonArray(storage_options.size(), [&](int i) {
                              return storage_options[i];
                            }));

  return account_settings;
}

const char* PhotoURLSuffix(NetworkQueue::PhotoType type) {
  switch (type) {
    case NetworkQueue::THUMBNAIL:
      return ".t";
    case NetworkQueue::MEDIUM:
      return ".m";
    case NetworkQueue::FULL:
      return ".f";
    case NetworkQueue::ORIGINAL:
      return ".o";
  }
  return "";
}

const char* PhotoTypeName(NetworkQueue::PhotoType type) {
  switch (type) {
    case NetworkQueue::THUMBNAIL:
      return "thumbnail";
    case NetworkQueue::MEDIUM:
      return "medium";
    case NetworkQueue::FULL:
      return "full";
    case NetworkQueue::ORIGINAL:
      return "original";
  }
  return "";
}

}  // namespace

class AddFollowersRequest : public NetworkRequest {
 public:
  AddFollowersRequest(NetworkManager* net, const NetworkQueue::UploadActivity* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        upload_(u),
        needs_invalidate_(false) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UploadActivity* u = upload_;

    JsonDict d({
        { "viewpoint_id", u->viewpoint->id().server_id() },
        { "activity", FormatActivityDict(u->activity) },
        { "contacts", JsonArray(u->contacts.size(), [&](int i) {
              JsonDict d;
              const ContactMetadata& c = u->contacts[i];
              if (c.has_primary_identity()) {
                d.insert("identity", c.primary_identity());
              }
              if (c.has_user_id()) {
                d.insert("user_id", c.user_id());
              } else {
                // If we upload followers without user ids (prospective users), they will have user ids
                // assigned by this operation.  The DayTable does not display followers that do not yet
                // have user ids, so we need to fetch notifications once this is done.
                needs_invalidate_ = true;
              }
              if (c.has_name()) {
                d.insert("name", c.name());
              }
              return d;
            }) }
      });

    const string json = FormatRequest(d, u->headers, state());
    NETLOG("network: add followers: %s", json);
    SendPost(FormatUrl(state(), "/service/add_followers"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: add_followers error: %s", e);
    state()->analytics()->NetworkAddFollowers(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkAddFollowers(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: add_followers error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    }
    if (upload_ == state()->net_queue()->queued_upload_activity()) {
      if (status_code == 200) {
        const NetworkQueue::UploadActivity* u = upload_;
        LOG("network: added %d contact%s: %.03f",
            u->contacts.size(), Pluralize(u->contacts.size()),
            timer_.Milliseconds());
      }
      state()->net_queue()->CommitQueuedUploadActivity(status_code != 200);

      if (needs_invalidate_) {
        AppState* const s = state();
        dispatch_after_main(kProspectiveUserCreationDelay, [s] {
            DBHandle updates = s->NewDBTransaction();
            s->notification_manager()->Invalidate(updates);
            updates->Commit();
          });
      }
    }
    return true;
  }

 private:
  const NetworkQueue::UploadActivity* const upload_;
  bool needs_invalidate_;
};

class AuthRequest : public NetworkRequest {
 public:
  AuthRequest(NetworkManager* net)
      : NetworkRequest(net, NETWORK_QUEUE_REFRESH) {
  }

 protected:
  void SendAuth(const string& url, const JsonDict& auth,
                bool include_device_info = true) {
    JsonDict augmented_auth = auth;
    if (include_device_info) {
      augmented_auth.insert("device", FormatDeviceDict(state()));
    }

    const string json = FormatRequest(augmented_auth);
    NETLOG("network: auth: %s\n%s", url, json);
    SendPost(url, json, kJsonContentType);
  }

  void SendAuth(const string& url) {
    SendAuth(url, JsonDict());
  }

  void HandleError(const string& e) {
    LOG("network: auth error: %s", e);
  }

  bool HandleDone(int status_code) {
    AuthResponse a;
    if (!ParseAuthResponse(&a, data_)) {
      LOG("network: unable to parse auth response: %s", data_);
      return false;
    }
    return HandleDone(a);
  }

  bool HandleDone(const AuthResponse& a) {
    // LOG("network: auth: %s", a);
    const int64_t user_id = a.has_user_id() ? a.user_id() : state()->user_id();
    const int64_t device_id = a.has_device_id() ? a.device_id() : state()->device_id();
    state()->SetUserAndDeviceId(user_id, device_id);
    if (state()->is_registered()) {
      net_->AuthDone();
    }
    return true;
  }
};

class AuthViewfinderRequest : public AuthRequest {
 public:
  AuthViewfinderRequest(
      NetworkManager* net, const string& endpoint, const string& identity,
      const string& password, const string& first, const string& last,
      const string& name, bool error_if_linked,
      const NetworkManager::AuthCallback& done)
      : AuthRequest(net),
        endpoint_(endpoint),
        identity_(identity),
        password_(password),
        first_(first),
        last_(last),
        name_(name),
        error_if_linked_(error_if_linked),
        done_(done) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict auth;
    bool include_device_info = true;
    if (endpoint_ == AppState::kMergeTokenEndpoint) {
      LOG("network: %s viewfinder, identity=\"%s\"", endpoint_, identity_);
      auth.insert("identity", identity_);
      auth.insert("error_if_linked", error_if_linked_);
      include_device_info = false;
    } else {
      JsonDict auth_info("identity", identity_);
      if (endpoint_ == AppState::kRegisterEndpoint) {
        LOG("network: %s viewfinder, identity=\"%s\", first=\"%s\", "
            "last=\"%s\", name=\"%s\"",
            endpoint_, identity_, first_, last_, name_);
        if (!name_.empty()) {
          auth_info.insert("name", name_);
        }
        if (!first_.empty()) {
          auth_info.insert("given_name", first_);
        }
        if (!last_.empty()) {
          auth_info.insert("family_name", last_);
        }
      } else {
        LOG("network: %s viewfinder, identity=\"%s\"", endpoint_, identity_);
      }
      if (endpoint_ == AppState::kRegisterEndpoint ||
          endpoint_ == AppState::kLoginEndpoint) {
        if (!password_.empty()) {
          auth_info.insert("password", password_);
        }
      }
      auth.insert("auth_info", auth_info);
    }
    SendAuth(FormatUrl(state(), Format("/%s/viewfinder", endpoint_)),
             auth, include_device_info);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    state()->analytics()->NetworkAuthViewfinder(0, timer_.Get());
    AuthRequest::HandleError(e);
    done_(-1, ErrorResponse::UNKNOWN, e);
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkAuthViewfinder(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: auth viewfinder error: %d status: %s\n%s",
          status_code, url(), data_);
      // Note, unlike most other network requests, we do not retry on 5xx
      // errors and instead pass back the error to the caller so an error can
      // be displayed to the user.
      ErrorResponse err;
      if (!ParseErrorResponse(&err, data_)) {
        done_(status_code, ErrorResponse::UNKNOWN, kDefaultLoginErrorMessage);
      } else {
        done_(status_code, err.error().error_id(), err.error().text());
      }
      return true;
    }

    AuthResponse a;
    if (!ParseAuthResponse(&a, data_)) {
      LOG("network: unable to parse auth response: %s", data_);
      // We just fumble ahead if we're unable to parse the AuthResponse.
    }
    LOG("network: authenticated viewfinder identity");

    // TODO(peter): Passing AuthResponse::token_digits() in the error_id field
    // is a hack. Yo! Clean this shit up.
    done_(status_code, a.token_digits(), "");
    return AuthRequest::HandleDone(a);
  }

 private:
  const string endpoint_;
  const string identity_;
  const string password_;
  const string first_;
  const string last_;
  const string name_;
  const bool error_if_linked_;
  const NetworkManager::AuthCallback done_;
};

class VerifyViewfinderRequest : public AuthRequest {
 public:
  VerifyViewfinderRequest(NetworkManager* net, const string& identity,
                          const string& access_token, bool manual_entry,
                          const NetworkManager::AuthCallback& done)
      : AuthRequest(net),
        identity_(identity),
        access_token_(access_token),
        manual_entry_(manual_entry),
        done_(done) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    LOG("network: verify viewfinder, identity=\"%s\", access_token=\"%s\"",
        identity_, access_token_);
    JsonDict auth({
        { "identity", identity_ },
        { "access_token", access_token_ } });
    const string json = FormatRequest(auth, 0, true);
    const string url = FormatUrl(
        state(), Format("/%s/viewfinder", AppState::kVerifyEndpoint));
    NETLOG("network: verify_id: %s\n%s", url, json);
    SendPost(url, json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    state()->analytics()->NetworkVerifyViewfinder(0, timer_.Get(), manual_entry_);
    AuthRequest::HandleError(e);
    done_(-1, ErrorResponse::UNKNOWN, e);
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkVerifyViewfinder(status_code, timer_.Get(), manual_entry_);

    if (status_code != 200) {
      LOG("network: verify viewfinder error: %d status: %s\n%s",
          status_code, url(), data_);
      // Note, unlike most other network requests, we do not retry on 5xx
      // errors and instead pass back the error to the caller so an error can
      // be displayed to the user.
      ErrorResponse err;
      if (!ParseErrorResponse(&err, data_)) {
        done_(status_code, ErrorResponse::UNKNOWN, kDefaultVerifyErrorMessage);
      } else {
        done_(status_code, err.error().error_id(), err.error().text());
      }
      return true;
    }

    AuthResponse a;
    if (!ParseAuthResponse(&a, data_)) {
      LOG("network: unable to parse auth response: %s", data_);
      return false;
    }

    done_(status_code, ErrorResponse::OK, a.cookie());
    if (state()->registration_version() < AppState::REGISTRATION_EMAIL) {
      state()->set_registration_version(AppState::current_registration_version());
    }
    return AuthRequest::HandleDone(a);
  }

 private:
  const string identity_;
  const string access_token_;
  const bool manual_entry_;
  const NetworkManager::AuthCallback done_;
};

class BenchmarkDownloadRequest : public NetworkRequest {
 public:
  BenchmarkDownloadRequest(NetworkManager* net, const string& url)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        url_(url),
        total_bytes_(0) {
  }

  ~BenchmarkDownloadRequest() {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    NETLOG("network: starting benchmark download: up=%d wifi=%d: %s",
           net_->network_up(), net_->network_wifi(), url_);
    SendGet(url_);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleData(const Slice& d) {
    total_bytes_ += d.size();
    LOG("network: benchmark received %d bytes, %d bytes total: %s, %.03f ms",
        d.size(), total_bytes_, url_, timer_.Milliseconds());
  }

  void HandleError(const string& e) {
    LOG("network: benchmark download error: %s", e);
    state()->analytics()->NetworkBenchmarkDownload(0, net_->network_up(), net_->network_wifi(),
                                                   url_, -1, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkBenchmarkDownload(status_code, net_->network_up(), net_->network_wifi(),
                                                   url_, total_bytes_, timer_.Get());

    LOG("network: benchmark download finished with %d: %d bytes: %s: %.03f ms",
        status_code, total_bytes_, url_, timer_.Milliseconds());
    return true;
  }

 private:
  string url_;
  int64_t total_bytes_;
};

class DownloadPhotoRequest : public NetworkRequest {
 public:
  DownloadPhotoRequest(NetworkManager* net, const NetworkQueue::DownloadPhoto* d)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        download_(d),
        path_(d->path),
        url_(d->url),
        delete_file_(true),
        fd_(FileCreate(path_)) {
    MD5_Init(&md5_ctx_);
    CHECK_GE(fd_, 0) << "file descriptor is invalid";
  }
  ~DownloadPhotoRequest() {
    if (fd_ != -1) {
      close(fd_);
      fd_ = -1;
    }
    if (delete_file_) {
      FileRemove(path_);
    }
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::DownloadPhoto* d = download_;
    if (url_.empty()) {
      url_ = FormatUrl(
          state(), Format("/episodes/%s/photos/%s%s",
                          d->episode->id().server_id(),
                          d->photo->id().server_id(),
                          PhotoURLSuffix(d->type)));
    }
    NETLOG("network: downloading photo: %s: %s", d->photo->id(), url_);
    SendGet(url_);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleData(const Slice& d) {
    MD5_Update(&md5_ctx_, d.data(), d.size());

    // TODO(pmattis): Gracefully handle out-of-space errors.
    const char* p = d.data();
    int n = d.size();
    while (n > 0) {
      ssize_t res = write(fd_, p, n);
      if (res < 0) {
        LOG("write failed: %s: %d (%s)", path_, errno, strerror(errno));
        break;
      }
      p += res;
      n -= res;
    }
  }

  void HandleError(const string& e) {
    LOG("network: photo download error: %s", e);
    state()->analytics()->NetworkDownloadPhoto(0, -1, PhotoTypeName(download_->type), timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkDownloadPhoto(status_code, status_code == 200 ? FileSize(path_) : -1,
                                               PhotoTypeName(download_->type), timer_.Get());

    if (fd_ != -1) {
      close(fd_);
      fd_ = -1;
    }

    if (download_ == state()->net_queue()->queued_download_photo()) {
      const NetworkQueue::DownloadPhoto* d = download_;
      if (status_code == 403 && url_ == d->url) {
        // Our download was forbidden and we were talking directly to s3. Tell
        // the photo manager to retry.
        LOG("network: photo download error: %d status (retrying): %s: %s",
            status_code, d->photo->id(), url_);
        state()->net_queue()->CommitQueuedDownloadPhoto(string(), true);
      } else if (status_code != 200) {
        // The photo doesn't exist. Mark it with an error.
        LOG("network: photo download error: %d status (not-retrying): %s: %s",
            status_code, d->photo->id(), url_);
        state()->net_queue()->CommitQueuedDownloadPhoto(string(), false);
      } else {
        const string md5 = GetMD5();
        LOG("network: downloaded photo: %s: %d bytes: %s: %.03f ms",
            d->photo->id(), FileSize(path_), url_, timer_.Milliseconds());
        state()->net_queue()->CommitQueuedDownloadPhoto(md5, false);
        delete_file_ = false;
      }
    }
    return true;
  }

  string GetMD5() {
    uint8_t digest[MD5_DIGEST_LENGTH];
    MD5_Final(&md5_ctx_, digest);
    return BinaryToHex(Slice((const char*)digest, ARRAYSIZE(digest)));
  }

 private:
  const NetworkQueue::DownloadPhoto* const download_;
  MD5_CTX md5_ctx_;
  const string path_;
  string url_;
  bool delete_file_;
  int fd_;
};

class FetchContactsRequest : public NetworkRequest {
 public:
  FetchContactsRequest(NetworkManager* net,
                       const NetworkManager::FetchContactsCallback& done)
      : NetworkRequest(net, NETWORK_QUEUE_REFRESH),
        done_(done) {
  }

 protected:
  void SendFetch(const string& url) {
    JsonDict auth("device", FormatDeviceDict(state()));
    const string json = FormatRequest(auth);
    NETLOG("network: fetch contacts: %s\n%s", url, json);
    SendPost(url, json, kJsonContentType);
  }

  void HandleError(const string& e) {
    LOG("network: fetch contacts error: %s", e);
    done_("");
  }

  bool HandleDone(int status_code) {
    AuthResponse a;
    if (!ParseAuthResponse(&a, data_)) {
      LOG("network: unable to parse auth response: %s", data_);
      return false;
    }
    LOG("network: initiated fetch contacts: %s", a.headers().op_id());
    done_(a.headers().op_id());
    return true;
  }

 private:
  const NetworkManager::FetchContactsCallback done_;
};

class FetchFacebookContactsRequest : public FetchContactsRequest {
 public:
  FetchFacebookContactsRequest(NetworkManager* net,
                               const NetworkManager::FetchContactsCallback& done,
                               const string& access_token)
      : FetchContactsRequest(net, done),
        access_token_(access_token) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    LOG("network: fetch facebook contacts");
    SendFetch(FormatUrl(state(),
                        Format("/%s/facebook?access_token=%s",
                               state()->kLinkEndpoint,
                               access_token_)));
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    state()->analytics()->NetworkFetchFacebookContacts(0, timer_.Get());
    FetchContactsRequest::HandleError(e);
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkFetchFacebookContacts(status_code, timer_.Get());
    return FetchContactsRequest::HandleDone(status_code);
  }

 private:
  const string access_token_;
};

class FetchGoogleContactsRequest : public FetchContactsRequest {
 public:
  FetchGoogleContactsRequest(NetworkManager* net,
                             const NetworkManager::FetchContactsCallback& done,
                             const string& refresh_token)
      : FetchContactsRequest(net, done),
        refresh_token_(refresh_token) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    LOG("network: fetch google contacts");
    SendFetch(FormatUrl(state(),
                        Format("/%s/google?refresh_token=%s",
                               state()->kLinkEndpoint,
                               refresh_token_)));
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    state()->analytics()->NetworkFetchGoogleContacts(0, timer_.Get());
    FetchContactsRequest::HandleError(e);
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkFetchGoogleContacts(status_code, timer_.Get());
    return FetchContactsRequest::HandleDone(status_code);
  }

 private:
  const string refresh_token_;
};

class MergeAccountsRequest : public NetworkRequest {
 public:
  MergeAccountsRequest(NetworkManager* net,
                       const string& identity,
                       const string& access_token,
                       const string& completion_db_key,
                       const NetworkManager::AuthCallback& done)
      : NetworkRequest(net, NETWORK_QUEUE_REFRESH),
        identity_(identity),
        access_token_(access_token),
        completion_db_key_(completion_db_key),
        op_id_(state()->NewLocalOperationId()),
        done_(done) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    OpHeaders headers;
    headers.set_op_id(op_id_);
    headers.set_op_timestamp(WallTime_Now());
    JsonDict dict({
        { "source_identity",
              JsonDict({
                  { "identity", identity_ },
                  { "access_token", access_token_ } }) },
        { "activity", FormatActivityDict(
              state(), headers.op_id(), headers.op_timestamp()) } });

    const string json = FormatRequest(dict, headers, state());
    NETLOG("network: merge accounts: %s", json);
    SendPost(FormatUrl(state(), "/service/merge_accounts"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: merge accounts error: %s", e);
    state()->analytics()->NetworkMergeAccounts(0, timer_.Get());
    if (done_) {
      done_(-1, ErrorResponse::UNKNOWN, e);
    }
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkMergeAccounts(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: merge account error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
      ErrorResponse err;
      if (!ParseErrorResponse(&err, data_)) {
        done_(status_code, ErrorResponse::UNKNOWN, kDefaultChangePasswordErrorMessage);
      } else {
        done_(status_code, err.error().error_id(), err.error().text());
      }
      return true;
    }

    DBHandle updates = state()->NewDBTransaction();
    const string encoded_op_id = EncodeOperationId(state()->device_id(), op_id_);
    state()->contact_manager()->ProcessMergeAccounts(
        encoded_op_id, completion_db_key_, updates);
    updates->Commit();

    LOG("network: merge accounts: %s", encoded_op_id);
    done_(status_code, ErrorResponse::OK, "");
    return true;
  }

 private:
  const string identity_;
  const string access_token_;
  const string completion_db_key_;
  const int64_t op_id_;
  const NetworkManager::AuthCallback done_;
};

class PingRequest : public NetworkRequest {
 public:
  PingRequest(NetworkManager* net)
      : NetworkRequest(net, NETWORK_QUEUE_PING) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict ping("device", FormatDeviceDict(state()));

    const string json = FormatRequest(ping);
    NETLOG("network: ping:\n%s", json);
    SendPost(FormatUrl(state(), "/ping"), json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: ping error: %s", e);
    state()->analytics()->NetworkPing(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkPing(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: ping error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
      return true;
    }

    PingResponse p;
    if (!ParsePingResponse(&p, data_)) {
      // Don't retry, we could be a really old version that can't handle the response.
      // Reset the system message on bad responses. This ensures that we won't remain stuck
      // in the DISABLE_NETWORK state.
      LOG("network: unable to parse ping reponse");
      state()->clear_system_message();
      net_->SetNetworkDisallowed(false);
      return true;
    }

    if (!p.has_message()) {
      state()->clear_system_message();
      VLOG("Got empty ping response");
      net_->SetNetworkDisallowed(false);
      return true;
    }

    // Set disallowed variable from here, no need to register a callback.
    net_->SetNetworkDisallowed(p.message().severity() == SystemMessage::DISABLE_NETWORK);

    VLOG("Got ping response: %s", p);
    state()->set_system_message(p.message());

    return true;
  }
};

class PostCommentRequest : public NetworkRequest {
 public:
  PostCommentRequest(NetworkManager* net, const NetworkQueue::UploadActivity* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        upload_(u) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UploadActivity* u = upload_;

    JsonDict d({
        { "viewpoint_id", u->viewpoint->id().server_id() },
        { "comment_id", u->comment->comment_id().server_id() },
        { "activity", FormatActivityDict(u->activity) } });
    if (!u->comment->asset_id().empty()) {
      d.insert("asset_id", u->comment->asset_id());
    }
    if (u->comment->has_timestamp()) {
      d.insert("timestamp", u->comment->timestamp());
    }
    if (!u->comment->message().empty()) {
      d.insert("message", u->comment->message());
    }

    const string json = FormatRequest(d, u->headers, state());
    NETLOG("network: post comment %s", u->activity->activity_id());
    SendPost(FormatUrl(state(), "/service/post_comment"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: post_comment error: %s", e);
    state()->analytics()->NetworkPostComment(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkPostComment(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: post_comment error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    }
    if (upload_ == state()->net_queue()->queued_upload_activity()) {
      if (status_code == 200) {
        LOG("network: posted comment: %.03f", timer_.Milliseconds());
      }
      state()->net_queue()->CommitQueuedUploadActivity(status_code != 200);
    }
    return true;
  }

 private:
  const NetworkQueue::UploadActivity* const upload_;
};

class QueryContactsRequest : public NetworkRequest {
 public:
  QueryContactsRequest(NetworkManager* net,
                       const ContactSelection& contacts)
      : NetworkRequest(net, NETWORK_QUEUE_REFRESH),
        contacts_(contacts) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict d("limit", kQueryContactsLimit);
    if (!contacts_.start_key().empty()) {
      d.insert("start_key", contacts_.start_key());
    }
    const string json = FormatRequest(d);
    NETLOG("network: query contacts:\n%s", json);
    SendPost(FormatUrl(state(), "/service/query_contacts"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: query contacts error: %s", e);
    state()->analytics()->NetworkQueryContacts(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkQueryContacts(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: query contacts error: %d status: %s\n%s",
          status_code, url(), data_);
      return false;
    }

    QueryContactsResponse p;
    if (!ParseQueryContactsResponse(&p, &contacts_, kQueryContactsLimit, data_)) {
      LOG("network: unable to parse query_contacts response");
      return false;
    }

    LOG("network: queried %d contact%s: %s: %d bytes, %.03f ms",
        p.contacts_size(), Pluralize(p.contacts_size()),
        p.last_key(), data_.size(), timer_.Milliseconds());

    DBHandle updates = state()->NewDBTransaction();
    state()->contact_manager()->ProcessQueryContacts(p, contacts_, updates);
    updates->Commit();
    return true;
  }

 private:
  ContactSelection contacts_;
};

class QueryEpisodesRequest : public NetworkRequest {
 public:
  QueryEpisodesRequest(NetworkManager* net,
                       const vector<EpisodeSelection>& episodes)
      : NetworkRequest(net, NETWORK_QUEUE_REFRESH),
        episodes_(episodes),
        limit_(std::max<int>(1, kQueryObjectsLimit / episodes_.size())) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict d({
        { "photo_limit", limit_ },
        { "episodes",
              JsonArray(episodes_.size(), [&](int i) {
                  const EpisodeSelection& s = episodes_[i];
                  JsonDict d({
                      { "episode_id", s.episode_id() },
                      { "get_attributes", s.get_attributes() },
                      { "get_photos", s.get_photos() }
                    });
                  if (s.has_get_photos() && !s.photo_start_key().empty()) {
                    d.insert("photo_start_key", s.photo_start_key());
                  }
                  return d;
                }) }
      });
    const string json = FormatRequest(d);
    NETLOG("network: query episodes:\n%s", json);
    SendPost(FormatUrl(state(), "/service/query_episodes"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: query episodes error: %s", e);
    state()->analytics()->NetworkQueryEpisodes(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkQueryEpisodes(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: query episodes error: %d status: %s\n%s",
          status_code, url(), data_);
      return false;
    }

    QueryEpisodesResponse p;
    if (!ParseQueryEpisodesResponse(
            &p, &episodes_, limit_, data_)) {
      LOG("network: unable to parse query_episodes response");
      return false;
    }

    int num_photos = 0;
    for (int i = 0; i < p.episodes_size(); ++i) {
      num_photos += p.episodes(i).photos_size();
    }

    LOG("network: queried %d episode%s, %d photo%s: %d bytes, %.03f ms",
        p.episodes_size(), Pluralize(p.episodes_size()),
        num_photos, Pluralize(num_photos),
        data_.size(), timer_.Milliseconds());

    DBHandle updates = state()->NewDBTransaction();
    state()->net_queue()->ProcessQueryEpisodes(p, episodes_, updates);
    updates->Commit();
    return true;
  }

 private:
  vector<EpisodeSelection> episodes_;
  const int limit_;
};

class QueryFollowedRequest : public NetworkRequest {
 public:
  QueryFollowedRequest(NetworkManager* net)
      : NetworkRequest(net, NETWORK_QUEUE_REFRESH) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict d("limit", kQueryFollowedLimit);
    const string last_key = net_->query_followed_last_key_;
    if (!last_key.empty()) {
      d.insert("start_key", last_key);
    }
    const string json = FormatRequest(d);
    NETLOG("network: query followed:\n%s", json);
    SendPost(FormatUrl(state(), "/service/query_followed"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: query followed error: %s", e);
    state()->analytics()->NetworkQueryFollowed(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkQueryFollowed(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: query followed error: %d status: %s\n%s",
          status_code, url(), data_);
      return false;
    }

    QueryFollowedResponse p;
    if (!ParseQueryFollowedResponse(&p, data_)) {
      LOG("network: unable to parse query_followed response");
      return false;
    }

    LOG("network: query followed: %d viewpoint%s: %s: %.03f ms",
        p.viewpoints_size(), Pluralize(p.viewpoints_size()),
        p.last_key(), timer_.Milliseconds());

    DBHandle updates = state()->NewDBTransaction();
    {
      MutexLock l(&net_->mu_);
      net_->need_query_followed_ = (p.viewpoints_size() >= kQueryFollowedLimit);
      if (!net_->need_query_followed_) {
        updates->Put(kQueryFollowedDoneKey, true);
        // Force a query notification after we're done with the query_followed
        // traversal.
        state()->notification_manager()->Invalidate(updates);
      }
      if (p.has_last_key()) {
        net_->query_followed_last_key_ = p.last_key();
        updates->Put(kQueryFollowedLastKey, net_->query_followed_last_key_);
      }
    }
    state()->net_queue()->ProcessQueryFollowed(p, updates);
    updates->Commit();
    return true;
  }
};

class QueryNotificationsRequest : public NetworkRequest {
 public:
  QueryNotificationsRequest(NetworkManager* net,
                            const NotificationSelection& notifications,
                            bool long_poll)
      : NetworkRequest(net, long_poll ? NETWORK_QUEUE_NOTIFICATION : NETWORK_QUEUE_REFRESH),
        notifications_(notifications),
        long_poll_(long_poll) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict d;
    if (net_->need_query_followed_) {
      // We're performing a complete rebuild of our state, just retrieve the
      // latest notification so that we have our notification high water mark.
      d.insert("limit", 1);
      d.insert("scan_forward", false);
      notifications_.clear_last_key();
    } else {
      d.insert("limit", kQueryNotificationsLimit);
    }
    if (!notifications_.last_key().empty()) {
      d.insert("start_key", notifications_.last_key());
    }
    if (long_poll_) {
      d.insert("max_long_poll", kQueryNotificationsMaxLongPoll);
    }
    const string json = FormatRequest(d);
    NETLOG("network: query notifications: %s", json);
    SendPost(FormatUrl(state(), "/service/query_notifications"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: query notifications error: %s", e);
    state()->analytics()->NetworkQueryNotifications(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkQueryNotifications(status_code, timer_.Get());

    // Reset the application badge number to 0 to match server
    // behavior--but only if application is active.
    // TODO(spencer): Once the server supports a "clear_badge" flag,
    //   supply the value of clear_badge_ || app-active from here;
    //   server will always send ALL devices the badge=0 APNs alert.
    if (net_->ShouldClearApplicationBadge()) {
      NETLOG("network: clearing badge icon");
      net_->ClearApplicationBadge();
    } else {
      NETLOG("network: not clearing badge icon");
    }

    if (status_code != 200) {
      LOG("network: query notifications error: %d status: %s\n%s",
          status_code, url(), data_);
      return false;
    }
    QueryNotificationsResponse p;
    if (!ParseQueryNotificationsResponse(&p, &notifications_,
                                         kQueryNotificationsLimit, data_)) {
      LOG("network: unable to parse query_notifications response");
      return false;
    }

    LOG("network: queried %d notification%s (long poll: %d): %d bytes",
        p.notifications_size(), Pluralize(p.notifications_size()),
        long_poll_, data_.size());

    // If the query returned non-empty results, reset background manager backoff.
    if (p.notifications_size() > 0) {
      net_->ResetQueryNotificationsBackoff();
    }

    DBHandle updates = state()->NewDBTransaction();
    // If we're querying all of our state, we're just trying to find
    // the notification high-water mark and not actually processing
    // any notifications. Pass in !need_query_followed_ to indicate to
    // notification manager that it shouldn't call process callbacks.
    state()->notification_manager()->ProcessQueryNotifications(
        p, notifications_, !net_->need_query_followed_, updates);
    if (net_->need_query_followed_) {
      // If we're performing a query followed traversal we're not processing
      // notifications. So clear any fetch contact operation that could be
      // completed by a notification that we're skipping.
      state()->contact_manager()->ClearFetchContacts();
    }
    updates->Commit();

    if (long_poll_ && p.retry_after() > 0) {
      // If the server tells us to go away forever, don't listen.
      const WallTime retry_after = std::min(p.retry_after(), kQueryNotificationsMaxRetryAfter);
      LOG("network: pausing long polling for %s seconds", retry_after);
      // 'this' will be deleted by the time the timeout fires, so copy member variables we need.
      NetworkManager *const net = net_;
      const NetworkManagerQueueType queue_type = queue_type_;
      MutexLock lock(&net->mu_);
      net->PauseLocked(queue_type);
      dispatch_after_main(retry_after, [net, queue_type] {
          MutexLock lock(&net->mu_);
          net->ResumeLocked(queue_type);
        });
    }

    return true;
  }

 private:
  NotificationSelection notifications_;
  const bool long_poll_;
};

class QueryUsersRequest : public NetworkRequest {
 public:
  QueryUsersRequest(NetworkManager* net, const vector<int64_t>& user_ids)
      : NetworkRequest(net, NETWORK_QUEUE_REFRESH),
        user_ids_(user_ids) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict d("user_ids",
               JsonArray(user_ids_.size(), [&](int i) {
                   return JsonValue(user_ids_[i]);
                 }));
    const string json = FormatRequest(d);
    NETLOG("network: query users:\n%s", json);
    SendPost(FormatUrl(state(), "/service/query_users"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: query users error: %s", e);
    state()->analytics()->NetworkQueryUsers(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkQueryUsers(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: query users error: %d status: %s\n%s",
          status_code, url(), data_);
      return false;
    }

    QueryUsersResponse p;
    if (!ParseQueryUsersResponse(&p, data_)) {
      LOG("network: unable to parse query_users response");
      return false;
    }

    LOG("network: queried %d user%s: %d bytes, %.03f ms",
        p.user_size(), Pluralize(p.user_size()),
        data_.size(), timer_.Milliseconds());

    DBHandle updates = state()->NewDBTransaction();
    state()->contact_manager()->ProcessQueryUsers(p, user_ids_, updates);

    // TODO(marc): The network manager is not a great place for this. Use the
    // ContactManager::process_users() hook to place this elsewhere.
    for (int i = 0; i < p.user_size(); ++i) {
      const QueryUsersResponse::User& u = p.user(i);
      if (u.contact().user_id() != state()->user_id()) {
        continue;
      }

      // User identities are processed by ContactManager.ProcessQueryUsers.

      // Handle account settings.
      if (u.has_account_settings()) {
        const AccountSettingsMetadata& a = u.account_settings();

        // TODO: support email_alerts setting.
        bool cloud_storage = false;
        bool store_originals = false;
        for (int j = 0; j < a.storage_options_size(); ++j) {
          const string& option = a.storage_options(j);
          if (option == "use_cloud") {
            cloud_storage = true;
          } else if (option == "store_originals") {
            store_originals = true;
          }
        }

        LOG("Downloaded setting: cloud_storage=%d, store_originals=%d",
            cloud_storage, store_originals);
        state()->set_cloud_storage(cloud_storage);
        state()->set_store_originals(store_originals);

        AppState* const s = state();
        s->async()->dispatch_main_async([s] {
            // Note that "this" has been deleted at this point, so don't
            // dereference it.
            s->settings_changed()->Run(true);
          });
      }

      // Handle no-password field. False if not present.
      state()->set_no_password(u.no_password());
      break;
    }

    updates->Commit();
    return true;
  }

 private:
  const vector<int64_t> user_ids_;
};

class QueryViewpointsRequest : public NetworkRequest {
 public:
  QueryViewpointsRequest(NetworkManager* net,
                         const vector<ViewpointSelection>& viewpoints)
      : NetworkRequest(net, NETWORK_QUEUE_REFRESH),
        viewpoints_(viewpoints),
        limit_(std::max<int>(1, kQueryObjectsLimit / viewpoints_.size())) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict d({
        { "limit", limit_ },
        { "viewpoints",
              JsonArray(viewpoints_.size(), [&](int i) {
                  const ViewpointSelection& s = viewpoints_[i];
                  JsonDict d("viewpoint_id", s.viewpoint_id());
                  d.insert("get_activities", s.get_activities());
                  d.insert("get_attributes", s.get_attributes());
                  d.insert("get_episodes", s.get_episodes());
                  d.insert("get_followers", s.get_followers());
                  d.insert("get_comments", s.get_comments());
                  if (s.has_get_activities() && !s.activity_start_key().empty()) {
                    d.insert("activity_start_key", s.activity_start_key());
                  }
                  if (s.has_get_episodes() && !s.episode_start_key().empty()) {
                    d.insert("episode_start_key", s.episode_start_key());
                  }
                  if (s.has_get_followers() && !s.follower_start_key().empty()) {
                    d.insert("follower_start_key", s.follower_start_key());
                  }
                  if (s.has_get_comments() && !s.comment_start_key().empty()) {
                    d.insert("comment_start_key", s.comment_start_key());
                  }
                  return d;
                }) } });
    const string json = FormatRequest(d);
    NETLOG("network: query viewpoints:\n%s", json);
    SendPost(FormatUrl(state(), "/service/query_viewpoints"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: query viewpoints error: %s", e);
    state()->analytics()->NetworkQueryViewpoints(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkQueryViewpoints(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: query viewpoints error: %d status: %s\n%s",
          status_code, url(), data_);
      return false;
    }

    QueryViewpointsResponse p;
    if (!ParseQueryViewpointsResponse(
            &p, &viewpoints_, limit_, data_)) {
      LOG("network: unable to parse query_viewpoints response");
      return false;
    }

    int num_episodes = 0;
    for (int i = 0; i < p.viewpoints_size(); ++i) {
      num_episodes += p.viewpoints(i).episodes_size();
    }

    LOG("network: queried %d viewpoint%s, %d episode%s: %d bytes, %.03f ms",
        p.viewpoints_size(), Pluralize(p.viewpoints_size()),
        num_episodes, Pluralize(num_episodes),
        data_.size(), timer_.Milliseconds());

    DBHandle updates = state()->NewDBTransaction();
    state()->net_queue()->ProcessQueryViewpoints(p, viewpoints_, updates);
    updates->Commit();
    return true;
  }

 private:
  vector<ViewpointSelection> viewpoints_;
  const int limit_;
};

class RecordSubscriptionRequest : public NetworkRequest {
 public:
  RecordSubscriptionRequest(NetworkManager* net,
                            const SubscriptionManager::RecordSubscription* r)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        record_(r) {
  }

  void Start() {
    net_->mu_.AssertHeld();
    JsonDict d("receipt_data", Base64Encode(record_->receipt_data));
    const string json = FormatRequest(d, record_->headers, state());
    SendPost(FormatUrl(state(), "/service/record_subscription"),
             json, kJsonContentType);
  }

 protected:
  void HandleError(const string& e) {
    LOG("network: record subscription error %s", e);
    state()->analytics()->NetworkRecordSubscription(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkRecordSubscription(status_code, timer_.Get());
    ServerSubscriptionMetadata sub;
    if (status_code != 200) {
      LOG("network: record subscription error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    } else {
      const JsonValue d(ParseJSON(data_));
      if (!ParseServerSubscriptionMetadata(&sub, d["subscription"])) {
        LOG("network: record subscription error: invalid subscription metadata: %s", data_);
        return false;
      }
    }

    LOG("network: recorded subscription");
    DBHandle updates = state()->NewDBTransaction();
    // SubscriptionManager is currently iOS-specific, so
    // RecordSubscriptionRequest is too.
    state()->subscription_manager()->CommitQueuedRecordSubscription(
        sub, status_code == 200, updates);
    updates->Commit();
    return true;
  }

 private:
  const SubscriptionManager::RecordSubscription* record_;
};

class RemoveContactsRequest : public NetworkRequest {
 public:
  RemoveContactsRequest(NetworkManager* net, const ContactManager::RemoveContacts* remove)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        remove_(remove) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict d("contacts",
               JsonArray(remove_->server_contact_ids.size(), [&](int i) {
                   return JsonValue(remove_->server_contact_ids[i]);
                 }));

    const string json = FormatRequest(d, remove_->headers, state());
    NETLOG("network: remove contacts:\n%s", json);
    SendPost(FormatUrl(state(), "/service/remove_contacts"), json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: remove contacts error: %s", e);
    state()->analytics()->NetworkRemoveContacts(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkRemoveContacts(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: remove contacts error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    } else {
      LOG("network: removed contacts: %s: %.03f ms",
          remove_->server_contact_ids.size(), timer_.Milliseconds());
    }
    if (remove_ == state()->contact_manager()->queued_remove_contacts()) {
        state()->contact_manager()->CommitQueuedRemoveContacts(status_code == 200);
    }
    return status_code == 200;
  }

 private:
  const ContactManager::RemoveContacts* remove_;
};

class RemoveFollowersRequest : public NetworkRequest {
 public:
  RemoveFollowersRequest(NetworkManager* net, const NetworkQueue::UploadActivity* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        upload_(u) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UploadActivity* u = upload_;

    JsonDict d({
        { "viewpoint_id", u->viewpoint->id().server_id() },
        { "activity", FormatActivityDict(u->activity) },
        { "remove_ids",
              JsonArray(u->activity->remove_followers().user_ids_size(), [&](int i) {
                  return u->activity->remove_followers().user_ids(i);
                }) }
      });

    const string json = FormatRequest(d, u->headers, state());
    NETLOG("network: remove followers: %s", json);
    SendPost(FormatUrl(state(), "/service/remove_followers"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: remove_followers error: %s", e);
    state()->analytics()->NetworkRemoveFollowers(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkRemoveFollowers(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: remove_followers error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    }
    if (upload_ == state()->net_queue()->queued_upload_activity()) {
      if (status_code == 200) {
        const NetworkQueue::UploadActivity* u = upload_;
        LOG("network: removed %d follower%s: %.03f",
            u->activity->remove_followers().user_ids_size(),
            Pluralize(u->activity->remove_followers().user_ids_size()),
            timer_.Milliseconds());
      }
      state()->net_queue()->CommitQueuedUploadActivity(status_code != 200);
    }
    return true;
  }

 private:
  const NetworkQueue::UploadActivity* const upload_;
};

class RemovePhotosRequest : public NetworkRequest {
 public:
  RemovePhotosRequest(NetworkManager* net, const NetworkQueue::RemovePhotos* r)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        remove_(r) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::RemovePhotos* r = remove_;

    JsonDict d("episodes",
               JsonArray(r->episodes.size(), [&](int i) {
                   const NetworkQueue::Episode& e = r->episodes[i];
                   return JsonDict({
                       { "episode_id", e.episode->id().server_id() },
                       { "photo_ids",
                             JsonArray(e.photos.size(), [&](int j) {
                                 return e.photos[j]->id().server_id();
                               }) }
                     });
                 }));

    const string json = FormatRequest(d, r->headers, state());
    NETLOG("network: remove_photos:\n%s", json);
    SendPost(FormatUrl(state(), "/service/remove_photos"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    state()->analytics()->NetworkRemovePhotos(0, timer_.Get());
    LOG("network: remove photos error: %s", e);
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkRemovePhotos(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: remove photos error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    }
    if (remove_ == state()->net_queue()->queued_remove_photos()) {
      if (status_code == 200) {
        int num_photos = 0;
        for (int i = 0; i < remove_->episodes.size(); ++i) {
          num_photos += remove_->episodes[i].photos.size();
        }
        LOG("network: removed %d photo%s from %d episode%s",
            num_photos, Pluralize(num_photos),
            remove_->episodes.size(), Pluralize(remove_->episodes.size()));
      }
      state()->net_queue()->CommitQueuedRemovePhotos(status_code != 200);
    }
    return true;
  }

 private:
  const NetworkQueue::RemovePhotos* const remove_;
};

class SavePhotosRequest : public NetworkRequest {
 public:
  SavePhotosRequest(NetworkManager* net, const NetworkQueue::UploadActivity* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        episode_count_(0),
        photo_count_(0),
        upload_(u) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UploadActivity* u = upload_;

    JsonDict d("activity", FormatActivityDict(u->activity));
    if (!u->episodes.empty()) {
      d.insert("episodes",
               JsonArray(u->episodes.size(), [&](int i) {
                   const NetworkQueue::Episode& e = u->episodes[i];
                   ++episode_count_;
                   photo_count_ += e.photos.size();
                   return JsonDict({
                       { "existing_episode_id", e.parent->id().server_id() },
                       { "new_episode_id", e.episode->id().server_id() },
                       { "photo_ids",
                             JsonArray(e.photos.size(), [&](int j) {
                                 return e.photos[j]->id().server_id();
                               }) }
                     });
                 }));
    }
    // Viewpoint autosave photos.
    if (u->activity->save_photos().has_viewpoint_id()) {
      // TODO(spencer): enable this once support is on the server.
      /*
      d.insert("viewpoints", Array(1, [&](int i) {
            return u->activity->save_photos().viewpoint_id().server_id();
          }));
      */
    }

    const string json = FormatRequest(d, u->headers, state());
    NETLOG("network: save photos: %s", json);
    SendPost(FormatUrl(state(), "/service/save_photos"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: save_photos error: %s", e);
    state()->analytics()->NetworkSavePhotos(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkSavePhotos(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: save_photos error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    }
    if (upload_ == state()->net_queue()->queued_upload_activity()) {
      if (status_code == 200) {
        LOG("network: saved %d photo%s from %d episode%s: %.03f",
            photo_count_, Pluralize(photo_count_),
            episode_count_, Pluralize(episode_count_), timer_.Milliseconds());
      }
      state()->net_queue()->CommitQueuedUploadActivity(status_code != 200);
    }
    return true;
  }

 private:
  int episode_count_;
  int photo_count_;
  const NetworkQueue::UploadActivity* const upload_;
};

class ShareRequest : public NetworkRequest {
 public:
  ShareRequest(NetworkManager* net, const NetworkQueue::UploadActivity* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        upload_(u),
        needs_invalidate_(false) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UploadActivity* u = upload_;

    JsonDict d;
    if (u->activity->has_share_existing()) {
      d.insert("viewpoint_id", u->viewpoint->id().server_id());
    } else {
      JsonDict v({
          { "viewpoint_id", u->viewpoint->id().server_id() },
          { "type", "event" }
        });
      if (!u->viewpoint->title().empty()) {
        v.insert("title", u->viewpoint->title());
      }
      if (u->viewpoint->has_cover_photo()) {
        DCHECK(u->viewpoint->cover_photo().photo_id().has_server_id());
        DCHECK(u->viewpoint->cover_photo().episode_id().has_server_id());
        if (u->viewpoint->cover_photo().photo_id().has_server_id() &&
            u->viewpoint->cover_photo().episode_id().has_server_id()) {
          const string photo_id = u->viewpoint->cover_photo().photo_id().server_id();
          const string episode_id = u->viewpoint->cover_photo().episode_id().server_id();
          // Only add the cover_photo field if the specified photo exists in
          // the share request.
          bool found = false;
          for (int i = 0; !found && i < u->episodes.size(); ++i) {
            const NetworkQueue::Episode& e = u->episodes[i];
            if (e.episode->id().server_id() == episode_id) {
              for (int j = 0; !found && j < e.photos.size(); ++j) {
                const PhotoHandle& p = e.photos[j];
                if (p->id().server_id() == photo_id) {
                  found = true;
                  v.insert("cover_photo",
                           JsonDict({
                               { "photo_id", photo_id },
                               { "episode_id", episode_id}
                             }));
                  break;
                }
              }
            }
          }
        }
      }
      d.insert("viewpoint", v);
    }
    d.insert("activity", FormatActivityDict(u->activity));
    // The server requires "episodes" to be present for share_new even if it's empty.
    if (!u->episodes.empty() || u->activity->has_share_new()) {
      d.insert("episodes",
               JsonArray(u->episodes.size(), [&](int i) {
                   const NetworkQueue::Episode& e = u->episodes[i];
                   return JsonDict({
                       { "existing_episode_id", e.parent->id().server_id() },
                       { "new_episode_id", e.episode->id().server_id() },
                       { "photo_ids",
                             JsonArray(e.photos.size(), [&](int j) {
                                 return e.photos[j]->id().server_id();
                               }) }
                     });
                 }));
    }
    if (!u->contacts.empty()) {
      d.insert("contacts",
               JsonArray(u->contacts.size(), [&](int i) {
                   JsonDict d;
                   const ContactMetadata& c = u->contacts[i];
                   if (c.has_primary_identity()) {
                     d.insert("identity", c.primary_identity());
                   }
                   if (c.has_user_id()) {
                     d.insert("user_id", c.user_id());
                   } else {
                     // If we upload followers without user ids (prospective users), they will have user ids
                     // assigned by this operation.  The DayTable does not display followers that do not yet
                     // have user ids, so we need to fetch notifications once this is done.
                     needs_invalidate_ = true;
                   }
                   if (c.has_name()) {
                     d.insert("name", c.name());
                   }
                   return d;
                 }));
    }

    const string json = FormatRequest(d, u->headers, state());
    NETLOG("network: share_%s:\n%s",
           u->activity->has_share_existing() ? "existing" : "new", json);
    SendPost(FormatUrl(state(), Format("/service/share_%s",
                                       u->activity->has_share_existing() ?
                                       "existing" : "new")),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: share error: %s", e);
    state()->analytics()->NetworkShare(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkShare(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: share error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    }
    if (upload_ == state()->net_queue()->queued_upload_activity()) {
      if (status_code == 200) {
        const NetworkQueue::UploadActivity* u = upload_;
        int num_photos = 0;
        for (int i = 0; i < u->episodes.size(); ++i) {
          num_photos += u->episodes[i].photos.size();
        }
        LOG("network: shared %d episode%s, %d photo%s, %d contact%s",
            u->episodes.size(), Pluralize(u->episodes.size()),
            num_photos, Pluralize(num_photos),
            u->contacts.size(), Pluralize(u->contacts.size()));
      }
      state()->net_queue()->CommitQueuedUploadActivity(status_code != 200);

      if (needs_invalidate_) {
        AppState* const s = state();
        dispatch_after_main(kProspectiveUserCreationDelay, [s] {
            DBHandle updates = s->NewDBTransaction();
            s->notification_manager()->Invalidate(updates);
            updates->Commit();
          });
      }
    }
    return true;
  }

 private:
  const NetworkQueue::UploadActivity* const upload_;
  bool needs_invalidate_;
};

class ResolveContactsRequest : public NetworkRequest {
 public:
  ResolveContactsRequest(NetworkManager* net, const std::string& identity)
      : NetworkRequest(net, NETWORK_QUEUE_REFRESH),
        identity_(identity) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    net_->mu_.AssertHeld();
    const string json = FormatRequest(JsonDict("identities", JsonArray({ identity_ })));
    SendPost(FormatUrl(state(), "/service/resolve_contacts"),
             json, kJsonContentType);
  }

 protected:
  void HandleError(const string& e) {
    LOG("network: resolve contacts error: %s", e);
    state()->analytics()->NetworkResolveContacts(0, timer_.Get());
    state()->contact_manager()->ProcessResolveContact(identity_, NULL);
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkResolveContacts(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: resolve contacts error: %d status: %s\n%s",
          status_code, url(), data_);
      state()->contact_manager()->ProcessResolveContact(identity_, NULL);
      return false;
    }

    ResolveContactsResponse resp;
    if (!ParseResolveContactsResponse(&resp, data_)) {
      LOG("network: unable to parse resolve_contacts response");
      state()->contact_manager()->ProcessResolveContact(identity_, NULL);
      return false;
    }

    if (resp.contacts_size() != 1 ||
        resp.contacts(0).primary_identity() != identity_) {
      LOG("network: invalid resolve_contacts response");
      state()->contact_manager()->ProcessResolveContact(identity_, NULL);
      return false;
    }

    state()->contact_manager()->ProcessResolveContact(identity_, &resp.contacts(0));
    return true;
  }

 private:
  std::string identity_;
};

class UpdateFriendRequest : public NetworkRequest {
 public:
  UpdateFriendRequest(NetworkManager* net, int64_t user_id)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        user_id_(user_id) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    OpHeaders headers;
    headers.set_op_id(state()->NewLocalOperationId());
    headers.set_op_timestamp(WallTime_Now());

    ContactMetadata c;
    CHECK(state()->contact_manager()->LookupUser(user_id_, &c));
    JsonDict friend_dict("user_id", user_id_);
    if (c.nickname().empty()) {
      friend_dict.insert("nickname", Json::Value::null);
    } else {
      friend_dict.insert("nickname", c.nickname());
    }
    const JsonDict dict("friend", friend_dict);

    const string json = FormatRequest(dict, headers, state());
    NETLOG("network: update friend: %s", json);
    SendPost(FormatUrl(state(), "/service/update_friend"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: update friend error: %s", e);
    state()->analytics()->NetworkUpdateFriend(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkUpdateFriend(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: update friend error: %d status: %s\n%s",
          status_code, url(), data_);
      return false;
    }

    LOG("network: updated friend metadata");
    state()->contact_manager()->CommitQueuedUpdateFriend();

    return true;
  }

 private:
  const int64_t user_id_;
};

class UpdateUserRequest : public NetworkRequest {
 public:
  UpdateUserRequest(NetworkManager* net, const string& old_password,
                    const string& new_password,
                    const NetworkManager::AuthCallback& done)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        old_password_(old_password),
        new_password_(new_password),
        done_(done) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    OpHeaders headers;
    headers.set_op_id(state()->NewLocalOperationId());
    headers.set_op_timestamp(WallTime_Now());

    JsonDict dict("account_settings", FormatAccountSettingsDict(state()));

    ContactMetadata c;
    if (state()->contact_manager()->LookupUser(state()->user_id(), &c)) {
      // Note that we may not have a contact when the user initially logs in.
      if (!c.name().empty()) {
        dict.insert("name", c.name());
      }
      if (!c.first_name().empty()) {
        dict.insert("given_name", c.first_name());
      }
      if (!c.last_name().empty()) {
        dict.insert("family_name", c.last_name());
      }
    }

    if (!old_password_.empty()) {
      dict.insert("old_password", old_password_);
    }
    if (!new_password_.empty()) {
      dict.insert("password", new_password_);
    }

    const string json = FormatRequest(dict, headers, state());
    NETLOG("network: update user: %s", json);
    SendPost(FormatUrl(state(), "/service/update_user"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: update user error: %s", e);
    state()->analytics()->NetworkUpdateUser(0, timer_.Get());
    if (done_) {
      done_(-1, ErrorResponse::UNKNOWN, e);
    }
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkUpdateUser(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: update user error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
      if (done_) {
        ErrorResponse err;
        if (!ParseErrorResponse(&err, data_)) {
          done_(status_code, ErrorResponse::UNKNOWN, kDefaultChangePasswordErrorMessage);
        } else {
          done_(status_code, err.error().error_id(), err.error().text());
        }
      }
      return true;
    }

    LOG("network: updated user metadata");
    if (done_) {
      done_(status_code, ErrorResponse::OK, "");
    } else {
      state()->contact_manager()->CommitQueuedUpdateSelf();
    }
    return true;
  }

 private:
  const string old_password_;
  const string new_password_;
  const NetworkManager::AuthCallback done_;
};

class UpdateUserPhotoRequest : public NetworkRequest {
 public:
  UpdateUserPhotoRequest(NetworkManager* net, const NetworkQueue::UpdatePhoto* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        update_(u) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UpdatePhoto* u = update_;
    JsonDict d("photo_id", u->photo->id().server_id());
    const JsonArray asset_keys(u->photo->asset_fingerprints_size(), [&](int i) {
        return JsonValue(EncodeAssetKey("", u->photo->asset_fingerprints(i)));
    });
    if (!asset_keys.empty()) {
      d.insert("asset_keys", asset_keys);
    }

    const string json = FormatRequest(d, u->headers, state());
    NETLOG("network: update user photo:\n%s", json);
    SendPost(FormatUrl(state(), "/service/update_user_photo"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: update user photo error: %s", e);
    state()->analytics()->NetworkUpdateUserPhoto(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkUpdateUserPhoto(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: update user photo error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    }
    if (update_ == state()->net_queue()->queued_update_photo()) {
      if (status_code == 200) {
        LOG("network: updated user photo: %s: %.03f ms",
            update_->photo->id(), timer_.Milliseconds());
      }
      state()->net_queue()->CommitQueuedUpdatePhoto(status_code != 200);
    }
    return true;
  }

 private:
  const NetworkQueue::UpdatePhoto* const update_;
};

class UpdateViewpointRequest : public NetworkRequest {
 public:
  UpdateViewpointRequest(NetworkManager* net, const NetworkQueue::UpdateViewpoint* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        update_(u) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UpdateViewpoint* u = update_;
    JsonDict d;
    string service_endpoint;

    if (u->viewpoint->update_metadata()) {
      service_endpoint = "/service/update_viewpoint";
      update_type_ = NetworkQueue::UPDATE_VIEWPOINT_METADATA;
      d.insert("viewpoint_id", u->viewpoint->id().server_id());
      const string activity_id = EncodeActivityId(
          state()->device_id(), u->headers.op_id(), u->headers.op_timestamp());
      d.insert("activity",
               JsonDict({
                   { "activity_id", activity_id },
                   { "timestamp", u->headers.op_timestamp() }
                 }));
      if (!u->viewpoint->title().empty()) {
        d.insert("title", u->viewpoint->title());
      }
      if (u->viewpoint->has_cover_photo()) {
        d.insert("cover_photo",
                 JsonDict({
                     { "photo_id", u->viewpoint->cover_photo().photo_id().server_id() },
                     { "episode_id", u->viewpoint->cover_photo().episode_id().server_id() }
                   }));
      }
      if (!u->viewpoint->description().empty()) {
        d.insert("description", u->viewpoint->description());
      }
      if (!u->viewpoint->name().empty()) {
        d.insert("name", u->viewpoint->name());
      }
    } else if (u->viewpoint->update_remove()) {
      service_endpoint = "/service/remove_viewpoint";
      update_type_ = NetworkQueue::UPDATE_VIEWPOINT_REMOVE;
      d.insert("viewpoint_id", u->viewpoint->id().server_id());
      // Nothing else to set here. However, we must handle this case
      // before we set labels, as it will be illegal to change the
      // value of the "removed" label via a call to update follower
      // metadata.
    } else if (u->viewpoint->update_follower_metadata()) {
      service_endpoint = "/service/update_follower";
      update_type_ = NetworkQueue::UPDATE_VIEWPOINT_FOLLOWER_METADATA;
      vector<string> labels;
      if (u->viewpoint->label_admin()) {
        labels.push_back("admin");
      }
      if (u->viewpoint->label_autosave()) {
        labels.push_back("autosave");
      }
      if (u->viewpoint->label_contribute()) {
        labels.push_back("contribute");
      }
      if (u->viewpoint->label_hidden()) {
        labels.push_back("hidden");
      }
      if (u->viewpoint->label_muted()) {
        labels.push_back("muted");
      }
      if (u->viewpoint->label_removed()) {
        labels.push_back("removed");
      }
      // Only add labels if not empty; We should always have some
      // permission, the exception being when the viewpoint was
      // created locally and hasn't yet been uploaded.
      if (!labels.empty()) {
        JsonDict f("viewpoint_id", u->viewpoint->id().server_id());
        f.insert("labels", JsonArray(labels.size(), [&](int i) {
              return labels[i];
            }));
        d.insert("follower", f);
      }
    } else if (u->viewpoint->update_viewed_seq()) {
      service_endpoint = "/service/update_follower";
      update_type_ = NetworkQueue::UPDATE_VIEWPOINT_VIEWED_SEQ;
      JsonDict f("viewpoint_id", u->viewpoint->id().server_id());
      f.insert("viewed_seq", u->viewpoint->viewed_seq());
      d.insert("follower", f);
    }

    const string json = FormatRequest(d, u->headers, state());
    NETLOG("network: update viewpoint (type=%d):\n%s", update_type_, json);
    SendPost(FormatUrl(state(), service_endpoint), json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: update viewpoint error: %s", e);
    state()->analytics()->NetworkUpdateViewpoint(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkUpdateViewpoint(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: update viewpoint error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    }
    if (update_ == state()->net_queue()->queued_update_viewpoint()) {
      if (status_code == 200) {
        LOG("network: updated viewpoint (type=%d): %s: %.03f ms",
            update_type_, update_->viewpoint->id(), timer_.Milliseconds());
      }
      state()->net_queue()->CommitQueuedUpdateViewpoint(
          update_type_, status_code != 200);
    }
    return true;
  }

 private:
  const NetworkQueue::UpdateViewpoint* const update_;
  NetworkQueue::UpdateViewpointType update_type_;
};

class UnshareRequest : public NetworkRequest {
 public:
  UnshareRequest(NetworkManager* net, const NetworkQueue::UploadActivity* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        upload_(u) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UploadActivity* u = upload_;

    JsonDict d({
        { "viewpoint_id", u->viewpoint->id().server_id() },
        { "activity", FormatActivityDict(u->activity) }
      });
    if (!u->episodes.empty()) {
      d.insert("episodes",
               JsonArray(u->episodes.size(), [&](int i) {
                   const NetworkQueue::Episode& e = u->episodes[i];
                   return JsonDict({
                       { "episode_id", e.episode->id().server_id() },
                       { "photo_ids",
                             JsonArray(e.photos.size(), [&](int j) {
                                 return e.photos[j]->id().server_id();
                               }) }
                     });
                 }));
    }

    const string json = FormatRequest(d, u->headers, state());
    NETLOG("network: unshare:\n%s", json);
    SendPost(FormatUrl(state(), "/service/unshare"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: unshare error: %s", e);
    state()->analytics()->NetworkUnshare(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkUnshare(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: unshare error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    }
    if (upload_ == state()->net_queue()->queued_upload_activity()) {
      if (status_code == 200) {
        const NetworkQueue::UploadActivity* u = upload_;
        int num_photos = 0;
        for (int i = 0; i < u->episodes.size(); ++i) {
          num_photos += u->episodes[i].photos.size();
        }
        LOG("network: unshared %d photo%s from %d episode%s",
            num_photos, Pluralize(num_photos),
            u->episodes.size(), Pluralize(u->episodes.size()));
      }
      state()->net_queue()->CommitQueuedUploadActivity(status_code != 200);
    }
    return true;
  }

 private:
  const NetworkQueue::UploadActivity* const upload_;
};

class UpdateDeviceRequest : public NetworkRequest {
 public:
  UpdateDeviceRequest(NetworkManager* net, bool* update_device)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        update_device_(update_device) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    OpHeaders headers;
    headers.set_op_id(state()->NewLocalOperationId());
    headers.set_op_timestamp(WallTime_Now());

    const string json = FormatRequest(
        JsonDict("device_dict", FormatDeviceDict(state())),
        headers, state());
    NETLOG("network: update device:\n%s", json);
    SendPost(FormatUrl(state(), "/service/update_device"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: update device error: %s", e);
    state()->analytics()->NetworkUpdateDevice(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkUpdateDevice(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: update device error: %d status: %s\n%s",
          status_code, url(), data_);
      return false;
    }

    LOG("network: updated device metadata");
    *update_device_ = false;

    return true;
  }

 private:
  bool* update_device_;
};

class UploadContactsRequest : public NetworkRequest {
 public:
  UploadContactsRequest(NetworkManager* net, const ContactManager::UploadContacts* upload)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        upload_(upload) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    JsonDict d("contacts",
               JsonArray(upload_->contacts.size(), [&](int i) {
                   const ContactMetadata& m = upload_->contacts[i];
                   JsonDict cd;
#define MAYBE_SET(proto_name, json_name) if (!m.proto_name().empty()) { cd.insert(json_name, m.proto_name()); }
                   MAYBE_SET(contact_source, "contact_source");
                   MAYBE_SET(name, "name");
                   MAYBE_SET(first_name, "given_name");
                   MAYBE_SET(last_name, "family_name");
#undef MAYBE_SET
                   if (m.has_rank()) {
                     cd.insert("rank", m.rank());
                   }
                   cd.insert("identities", JsonArray(m.identities_size(), [&](int i) {
                         JsonDict ident("identity", m.identities(i).identity());
                         if (m.identities(i).has_description()) {
                           ident.insert("description", m.identities(i).description());
                         }
                         return ident;
                       }));
                   return cd;
                 }));

    const string json = FormatRequest(d, upload_->headers, state());
    NETLOG("network: upload contacts:\n%s", json);
    SendPost(FormatUrl(state(), "/service/upload_contacts"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: upload contacts error: %s", e);
    state()->analytics()->NetworkUploadContacts(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkUploadContacts(status_code, timer_.Get());

    UploadContactsResponse resp;
    bool success = false;
    if (status_code != 200) {
      LOG("network: upload contacts error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx errors.
        return false;
      }
    } else {
      LOG("network: uploaded contacts: %s: %.03f ms",
          upload_->contacts.size(), timer_.Milliseconds());

        if (!ParseUploadContactsResponse(&resp, data_)) {
          LOG("network: unable to parse upload contacts response");
          return false;
        }

        success = true;
    }

    if (upload_ == state()->contact_manager()->queued_upload_contacts()) {
      state()->contact_manager()->CommitQueuedUploadContacts(resp, success);
    }

    // Uploading contacts will generate silent notifications when server_contact_ids are assigned.
    // Manually trigger another query_notifications to try and fetch them immediately.
    DBHandle updates = state()->NewDBTransaction();
    state()->notification_manager()->Invalidate(updates);
    updates->Commit();

    return success;
  }

 private:
  const ContactManager::UploadContacts* upload_;
};

class UploadEpisodeRequest : public NetworkRequest {
 public:
  UploadEpisodeRequest(NetworkManager* net, const NetworkQueue::UploadEpisode* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        upload_(u) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UploadEpisode* u = upload_;

    JsonDict dict({
        { "episode",
              JsonDict({
                  { "timestamp", u->episode->timestamp() },
                  { "episode_id", u->episode->id().server_id() }
                }) },
        { "photos",
              JsonArray(u->photos.size(), [&](int i) {
                  const PhotoMetadata& m = *u->photos[i];
                  JsonDict d({
                      { "timestamp", m.timestamp() },
                      { "aspect_ratio", m.aspect_ratio() },
                      { "content_type", ToString(kJpegContentType) },
                      { "photo_id", m.id().server_id() }
                    });
                  const JsonArray asset_keys(m.asset_fingerprints_size(), [&](int i) {
                      return JsonValue(EncodeAssetKey("", m.asset_fingerprints(i)));
                    });
                  if (!asset_keys.empty()) {
                    d.insert("asset_keys", asset_keys);
                  }
                  if (m.has_images()) {
                    const PhotoMetadata::Images& images = m.images();
                    if (images.has_tn()) {
                      d.insert("tn_size", images.tn().size());
                      d.insert("tn_md5", images.tn().md5());
                    }
                    if (images.has_med()) {
                      d.insert("med_size", images.med().size());
                      d.insert("med_md5", images.med().md5());
                    }
                    if (images.has_full()) {
                      d.insert("full_size", images.full().size());
                      d.insert("full_md5", images.full().md5());
                    }
                    if (images.has_orig()) {
                      d.insert("orig_size", images.orig().size());
                      d.insert("orig_md5", images.orig().md5());
                    }
                  }
                  if (m.has_location()) {
                    const Location& l = m.location();
                    d.insert("location",
                             JsonDict({
                                 { "latitude", l.latitude() },
                                 { "longitude", l.longitude() } ,
                                 { "accuracy", l.accuracy() }
                               }));
                    if (m.has_placemark()) {
                      const Placemark& p = m.placemark();
                      JsonDict t;
                      if (p.has_iso_country_code()) {
                        t.insert("iso_country_code", p.iso_country_code());
                      }
                      if (p.has_country()) {
                        t.insert("country", p.country());
                      }
                      if (p.has_state()) {
                        t.insert("state", p.state());
                      }
                      if (p.has_locality()) {
                        t.insert("locality", p.locality());
                      }
                      if (p.has_sublocality()) {
                        t.insert("sublocality", p.sublocality());
                      }
                      if (p.has_thoroughfare()) {
                        t.insert("thoroughfare", p.thoroughfare());
                      }
                      if (p.has_subthoroughfare()) {
                        t.insert("subthoroughfare", p.subthoroughfare());
                      }
                      d.insert("placemark", t);
                    }
                  }
                  return d;
                }) }
      });
    dict.insert("activity", FormatActivityDict(
                    state(), u->headers.op_id(), u->headers.op_timestamp()));

    const string json = FormatRequest(dict, u->headers, state());
    NETLOG("network: upload episode\n%s", json);
    SendPost(FormatUrl(state(), "/service/upload_episode"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: upload episode error: %s", e);
    state()->analytics()->NetworkUploadEpisode(0, timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkUploadEpisode(status_code, timer_.Get());

    if (status_code != 200) {
      LOG("network: upload episode error: %s status\n%s",
          status_code, data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx status.
        return false;
      }
    }
    if (upload_ == state()->net_queue()->queued_upload_episode()) {
      UploadEpisodeResponse m;
      if (status_code == 200) {
        if (!ParseUploadEpisodeResponse(&m, data_)) {
          LOG("network: unable to parse upload episode response");
          return false;
        }
        const NetworkQueue::UploadEpisode* u = upload_;
        LOG("network: upload episode: %s: %d photo%s: %.03f ms",
            u->episode->id(), u->photos.size(), Pluralize(u->photos.size()),
            timer_.Milliseconds());
      }
      state()->net_queue()->CommitQueuedUploadEpisode(m, status_code);
    }
    return true;
  }

 private:
  const NetworkQueue::UploadEpisode* const upload_;
};

class UploadLogToS3Request : public NetworkRequest {
 public:
  UploadLogToS3Request(NetworkManager* net, const string& url,
                       const string& path, const string& md5,
                       const std::shared_ptr<string>& body)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        url_(url),
        path_(path),
        md5_(md5),
        body_(body) {
  }

  void Start() {
    NETLOG("network: upload log to s3: %s: %s", url_, md5_);
    SendPut(url_, *body_, kOctetStreamContentType, md5_, "");
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
#ifdef PRODUCTION
    LOG("network: upload log to s3 error: %s: %s", url(), e);
#else  // !PRODUCTION
    // In some non-production environments we can't upload the log to the
    // server. Just delete.
    FileRemove(path_);
#endif // !PRODUCTION
  }

  bool HandleDone(int status_code) {
    if (status_code != 200) {
      LOG("network: upload log to s3 error: %d status: %s\n%s",
          status_code, url(), data_);
      if (((status_code / 100) == 5) ||
          IsS3RequestTimeout(status_code, data_)) {
        // Retry on 5xx status and S3 timeouts.
        return false;
      }
    } else {
      LOG("network: uploaded log to s3: %s: %d bytes, %.03f ms",
          path_, body_->size(), timer_.Milliseconds());
      FileRemove(path_);
    }
    return true;
  }

 private:
  const string url_;
  const string path_;
  const string md5_;
  std::shared_ptr<string> body_;
};

class UploadLogRequest : public NetworkRequest {
 public:
  UploadLogRequest(NetworkManager* net, const string& dir, const string& file)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        path_(JoinPath(dir, file)),
        file_(file),
        body_(new string) {
  }

  void Start() {
    // Extract the timestamp from the log filename.
    WallTime timestamp;
    string suffix;
    if (!ParseLogFilename(file_, &timestamp, &suffix)) {
      AsyncRemoveAndDelete();
      return;
    }

    *body_ = ReadFileToString(path_);
    if (body_->size() == 0) {
      // Don't bother uploading 0 length logs.
      AsyncRemoveAndDelete();
      return;
    }

    md5_ = MD5HexToBase64(MD5(*body_));

    const string client_log_id(
        Format("%s%s", WallTimeFormat("%H-%M-%S", timestamp, false), suffix));
    const JsonDict d({
        { "client_log_id", client_log_id },
        { "timestamp", timestamp },
        { "content_type", ToString(kOctetStreamContentType) },
        { "content_md5", md5_ },
        { "num_bytes", static_cast<uint64_t>(body_->size()) }
      });

    OpHeaders headers;
    headers.set_op_id(state()->NewLocalOperationId());
    headers.set_op_timestamp(WallTime_Now());
    const string json = FormatRequest(d, headers, state());

    NETLOG("network: upload log: %s: %s", file_, json);
    SendPost(FormatUrl(state(), "/service/new_client_log_url"),
             json, kJsonContentType);
  }

 protected:
  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: upload log error: %s", e);
  }

  bool HandleDone(int status_code) {
    if (status_code != 200) {
      LOG("network: upload log error: %d status: %s\n%s",
          status_code, url(), data_);
      if ((status_code / 100) == 5) {
        // Retry on 5xx status.
        return false;
      }
    } else {
      // The mutex must be held before invoking Start() on a new request.
      MutexLock l(&net_->mu_);
      const JsonValue d(ParseJSON(data_));
      const JsonRef url(d["client_log_put_url"]);
      UploadLogToS3Request* req = new UploadLogToS3Request(
          net_, url.string_value(), path_, md5_, body_);
      req->Start();
    }
    return true;
  }

 private:
  void AsyncRemoveAndDelete() {
    state()->async()->dispatch_after_main(0, [this] {
        FileRemove(path_);
        net_->Dispatch();
        delete this;
      });
  }

 private:
  const string path_;
  const string file_;
  string md5_;
  std::shared_ptr<string> body_;
};

class UploadPhotoRequest : public NetworkRequest {
 public:
  UploadPhotoRequest(NetworkManager* net, const NetworkQueue::UploadPhoto* u)
      : NetworkRequest(net, NETWORK_QUEUE_SYNC),
        upload_(u),
        photo_id_(u->photo->id().local_id()),
        path_(u->path),
        md5_(u->md5),
        md5_base64_(MD5HexToBase64(md5_)) {
  }

  // Start is called with NetworkManager::mu_ held.
  void Start() {
    const NetworkQueue::UploadPhoto* u = upload_;
    string url = u->url;
    string body;
    string if_none_match;

    if (url.empty()) {
      url = FormatUrl(
          state(), Format("/episodes/%s/photos/%s%s",
                          u->episode->id().server_id(),
                          u->photo->id().server_id(),
                          PhotoURLSuffix(u->type)));
      if_none_match = Format("\"%s\"", md5_);
    } else {
      body = ReadFileToString(path_);
    }

    NETLOG("network: upload photo: %s: %s: %s", u->photo->id(), url, md5_);
    SendPut(url, body, kJpegContentType, md5_base64_, if_none_match);
  }

 protected:
  void HandleRedirect(
      ScopedPtr<string>* new_body,
      StringSet* delete_headers, StringMap* add_headers) {
    // Add in the body now that we've been redirected to s3.
    new_body->reset(new string);
    **new_body = ReadFileToString(path_);
    // Strip out the If-None-Match header which will cause s3 to fail.
    delete_headers->insert("If-None-Match");
    (*add_headers)["Content-Type"] = kJpegContentType;
    (*add_headers)["Content-MD5"] = md5_base64_;
  }

  // The various Handle*() methods are called on the NetworkManager
  // thread.
  void HandleError(const string& e) {
    LOG("network: upload photo error: %s", e);
    state()->analytics()->NetworkUploadPhoto(0, -1, PhotoTypeName(upload_->type), timer_.Get());
  }

  bool HandleDone(int status_code) {
    state()->analytics()->NetworkUploadPhoto(
        status_code, status_code == 200 ? FileSize(path_) : -1,
        PhotoTypeName(upload_->type), timer_.Get());

    bool error = (status_code != 200 && status_code != 304);
    if (error) {
      LOG("network: upload photo error: %d status: %s\n%s",
          status_code, url(), data_);
      if (((status_code / 100) == 5) ||
          IsS3RequestTimeout(status_code, data_)) {
        // Retry on 5xx status and S3 timeouts.
        return false;
      }
    }
    if (upload_ == state()->net_queue()->queued_upload_photo()) {
      const NetworkQueue::UploadPhoto* u = upload_;
      LOG("network: upload photo (%d): %s: %d bytes: %s: %.03f ms",
          status_code, u->photo->id(), FileSize(path_),
          md5_, timer_.Milliseconds());
      // Use VLOG for the headers to minimize spamming the debug console.
      VLOG("network: upload photo: %s", u->photo->id());
      state()->net_queue()->CommitQueuedUploadPhoto(error);
    }
    return true;
  }

 private:
  const NetworkQueue::UploadPhoto* const upload_;
  const int64_t photo_id_;
  const string path_;
  const string md5_;
  const string md5_base64_;
};

NetworkRequest::NetworkRequest(NetworkManager* net, NetworkManagerQueueType queue)
    : net_(net),
      state_(net_->state()),
      queue_type_(queue) {
}

NetworkRequest::~NetworkRequest() {
}

void NetworkRequest::HandleRedirect(
    ScopedPtr<string>* new_body,
    StringSet* delete_headers, StringMap* add_headers) {
}

void NetworkRequest::HandleData(const Slice& d) {
  data_.append(d.data(), d.size());
}

void NetworkRequest::SendGet(const string& url) {
  Send(url, "GET", "", "", "", "");
}

void NetworkRequest::SendPost(
    const string& url, const Slice& body, const Slice& content_type) {
  Send(url, "POST", body, content_type, "", "");
}

void NetworkRequest::SendPut(
    const string& url, const Slice& body,
    const Slice& content_type, const Slice& content_md5,
    const Slice& if_none_match) {
  Send(url, "PUT", body, content_type, content_md5, if_none_match);
}

void NetworkRequest::Send(
    const string& url, const Slice& method, const Slice& body,
    const Slice& content_type, const Slice& content_md5,
    const Slice& if_none_match) {
  url_ = url;
  net_->SendRequest(this, method, body, content_type, content_md5, if_none_match);
}

NetworkManager::NetworkManager(AppState* state)
    : state_(state),
      pause_non_interactive_count_(0),
      epoch_(0),
      last_request_success_(true),
      refreshing_(false),
      network_reachable_(false),
      network_wifi_(false),
      need_query_followed_(false),
      update_device_(false),
      assets_scanned_(false),
      draining_(false),
      network_disallowed_(false),
      register_new_user_(false),
      last_ping_timestamp_(0),
      fake_401_(false) {
  if (state_->server_host().empty()) {
    // Networking is disabled.
    return;
  }

  query_followed_last_key_ =
      state_->db()->Get<string>(kQueryFollowedLastKey);

  state_->notification_manager()->nuclear_invalidations()->Add(
      [this](const DBHandle& updates) {
        NuclearInvalidation(updates);
      });
}

NetworkManager::~NetworkManager() {
  for (int i = 0; i < NUM_NETWORK_QUEUE_TYPES; i++) {
    CHECK_EQ(queue_state_[i].network_count, 0);
  }
}

void NetworkManager::Dispatch() {
  // NSURLConnection objects are unhappy unless they are created on the main
  // thread.
  if (!dispatch_is_main_thread()) {
    NETLOG("network dispatch: called on non-main thread");
    return;
  }
  MutexLock l(&mu_);
  if (draining_) {
    NETLOG("network dispatch: draining");
    return;
  }

  // If we're experiencing errors and don't know whether the network is up, don't do anything.
  // As long as we're not experiencing errors, go ahead and try even if the reachability
  // check hasn't told us the network is up yet.
  if (!network_up()) {
    if (refreshing_) {
      refreshing_ = false;
      refresh_end_.Run();
    }
    return;
  }

  int orig_network_count[NUM_NETWORK_QUEUE_TYPES];
  for (int i = 0; i < NUM_NETWORK_QUEUE_TYPES; i++) {
    orig_network_count[i] = queue_state_[i].network_count;
  }

  // Dispatch the subqueues and verify that they don't try to start any operations for the other queues.
  for (int i = 0; i < NUM_NETWORK_QUEUE_TYPES; i++) {
    if (queue_is_busy(static_cast<NetworkManagerQueueType>(i))) {
      continue;
    }
    if (i != NETWORK_QUEUE_PING) {
      if (network_disallowed_) {
        // Network is temporarily disallowed due to system message.
        // Only Ping can go through (only way to re-allow).
        NETLOG("network dispatch: network disallowed");
        break;
      }
      if (queue_state_[NETWORK_QUEUE_PING].network_count > 0) {
        // While a ping is in progress, block all the other queues.
        break;
      }
    }
    switch (i) {
      case NETWORK_QUEUE_PING:
        DispatchPingLocked();
        break;
      case NETWORK_QUEUE_REFRESH:
        DispatchRefreshLocked();
        break;
      case NETWORK_QUEUE_NOTIFICATION:
        DispatchNotificationLocked();
        break;
      case NETWORK_QUEUE_SYNC:
        DispatchSyncLocked();
        break;
      default:
        DIE("unknown queue type %s", i);
    }
    orig_network_count[i] = queue_state_[i].network_count;
    for (int j = 0; j < NUM_NETWORK_QUEUE_TYPES; j++) {
      DCHECK_EQ(orig_network_count[j], queue_state_[j].network_count);
    }
  }

  SetIdleTimer();
}

void NetworkManager::DispatchPingLocked() {
  mu_.AssertHeld();

  MaybePingServer();
}

void NetworkManager::DispatchRefreshLocked() {
  mu_.AssertHeld();

  // The rest of the requests require authentication.
  if (need_auth()) {
    if (refreshing_) {
      refreshing_ = false;
      refresh_end_.Run();
    }
    NETLOG("network dispatch: need auth");
    return;
  }

  if (pause_non_interactive()) {
    NETLOG("network dispatch: pause non-interactive: %d",
           pause_non_interactive_count_);
    return;
  }

  const QueueState& queue_state = queue_state_[NETWORK_QUEUE_REFRESH];

  // Query for notifications and revalidate invalidated data. Only
  // perform this revalidation work the first time through the loop as it
  // is unexpected for it to change on a subsequent pass.
  do {
    MaybeQueryNotifications(false);   if (queue_state.network_count) break;
    MaybeQueryUsers();                if (queue_state.network_count) break;
    if (assets_scanned_) {
      // Only query for photos/episodes/viewpoints after we've finished the
      // first asset scan as we want to ensure we can match up local photos
      // with those returned from the server so that we can avoid
      // downloading the photos from the server if we have the photo
      // locally.
      //
      // TODO(peter): We could lift this restriction if a photo found
      // during the asset scan could clear the "download_*" bits of the
      // PhotoMetadata.
      MaybeQueryEpisodes();            if (queue_state.network_count) break;
      MaybeQueryViewpoints();          if (queue_state.network_count) break;
      MaybeQueryFollowed();            if (queue_state.network_count) break;
    }
    MaybeQueryContacts();             if (queue_state.network_count) break;
  } while (0);

  if (queue_state.network_count) {
    if (!refreshing_) {
      refreshing_ = true;
      refresh_start_.Run();
    }
    return;
  }

  if (refreshing_) {
    refreshing_ = false;
    if (assets_scanned_) {
      // Only mark the refresh as completed if we were actually able to query for everything.
      state_->set_refresh_completed(true);
    }
    refresh_end_.Run();
  }
}

void NetworkManager::DispatchNotificationLocked() {
  mu_.AssertHeld();

  // Let any refreshes finish before going into a long poll. The reverse is not true;
  // a refresh may start a short request while a long poll is in progress.  This is slightly less
  // efficient and we may want to change it as we gain more confidence in our long-polling system,
  // but for now this ensures that the app doesn't become unresponsive if a long poll becomes stuck
  // in some way that is slow to report an error.
  if (need_auth() || refreshing_) {
    return;
  }

  MaybeQueryNotifications(true);
}

void NetworkManager::DispatchSyncLocked() {
  mu_.AssertHeld();

  if (need_auth()) {
    return;
  }

  const QueueState& queue_state = queue_state_[NETWORK_QUEUE_SYNC];

  // 1. Upload logs if the last request was not successful. Otherwise we'll
  // upload logs at the end of this queue as the lowest priority operation.
  if (!pause_non_interactive() && !last_request_success_) {
    MaybeUploadLog();                   if (queue_state.network_count) return;
  }

  // 2. Prioritize sending update device, update friend/user, link identity,
  // and subscription requests.
  if (!pause_non_interactive()) {
    MaybeUpdateDevice();                if (queue_state.network_count) return;
    MaybeUpdateFriend();                if (queue_state.network_count) return;
    MaybeUpdateUser();                  if (queue_state.network_count) return;
    MaybeRecordSubscription();          if (queue_state.network_count) return;
  }

  // Don't do anything photo-related until the initial asset scan has run (so we have asset
  // fingerprints to match against)
  if (!assets_scanned_) {
    return;
  }

  // 3. Indicate the network is ready so that photo downloads and other
  // operations will be queued.
  if (pause_non_interactive()) {
    // If non-interactive operations are paused, only queue thumbnail and
    // full photo downloads.
    state_->network_ready()->Run(PRIORITY_UI_FULL);
  } else {
    state_->network_ready()->Run(PRIORITY_UI_MAX);
  }

  // 4. Download photos before querying for notifications as the UI might have
  // queued up the download requests (e.g. because of a non-existent or corrupt
  // image).
  MaybeDownloadPhoto();               if (queue_state.network_count) return;

  // 5. Other photo operations.
  if (!pause_non_interactive()) {
    state_->network_ready()->Run(PRIORITY_MAX);
  }
  // Note that we let any already queued photo manager operations start and
  // complete even if pause_non_interactive is true so that we can queue new
  // download photo operations.
  NETLOG("network dispatch: running all priorities");
  MaybeDownloadPhoto();               if (queue_state.network_count) return;
  MaybeUploadPhoto();                 if (queue_state.network_count) return;
  MaybeRemovePhotos();                if (queue_state.network_count) return;
  MaybeUploadEpisode();               if (queue_state.network_count) return;
  MaybeUploadActivity();              if (queue_state.network_count) return;
  MaybeUpdatePhoto();                 if (queue_state.network_count) return;
  MaybeUpdateViewpoint();             if (queue_state.network_count) return;
  MaybeUploadContacts();              if (queue_state.network_count) return;
  MaybeRemoveContacts();              if (queue_state.network_count) return;

  if (!pause_non_interactive()) {
    // 6. Logs.
    MaybeUploadLog();                 if (queue_state.network_count) return;
  }

#ifdef DEVELOPMENT
  MaybeBenchmarkDownload();           if (queue_state.network_count) return;
#endif  // DEVELOPMENT
}

bool NetworkManager::Refresh() {
  // Force a query notification.
  DBHandle updates = state_->NewDBTransaction();
  state_->notification_manager()->Invalidate(updates);
  updates->Commit();

  if (!assets_scanned_) {
    return false;
  }

  refreshing_ = true;
  refresh_start_.Run();

  Dispatch();
  return true;
}

void NetworkManager::ResetBackoff() {
  MutexLock lock(&mu_);

  last_request_success_ = true;
  for (int i = 0; i < NUM_NETWORK_QUEUE_TYPES; i++) {
    QueueState* state = &queue_state_[i];
    state->backoff_delay = kMinBackoffDelay;
    if (state->backoff_count) {
      NETLOG("network: reset backoff %s: %d", i, state->backoff_count);
      ResumeFromBackoffLocked(static_cast<NetworkManagerQueueType>(i));
    }
  }
}

void NetworkManager::ResolveContact(const string& identity) {
  if (need_auth()) {
    state_->contact_manager()->ProcessResolveContact(identity, NULL);
    return;
  }

  MutexLock lock(&mu_);

  ResolveContactsRequest* req = new ResolveContactsRequest(this, identity);
  req->Start();
}

bool NetworkManager::FetchFacebookContacts(
    const string& access_token, const FetchContactsCallback& done) {
  CHECK(dispatch_is_main_thread());

  MutexLock l(&mu_);

  if (draining_ || need_auth()) {
    return false;
  }

  // Immediately kick off the fetch contacts request.
  FetchFacebookContactsRequest* req =
      new FetchFacebookContactsRequest(
          this, done, access_token);
  req->Start();
  return true;
}

bool NetworkManager::FetchGoogleContacts(
    const string& refresh_token, const FetchContactsCallback& done) {
  CHECK(dispatch_is_main_thread());

  MutexLock l(&mu_);

  if (draining_ || need_auth()) {
    return false;
  }

  // Immediately kick off the fetch contacts request.
  FetchGoogleContactsRequest* req =
      new FetchGoogleContactsRequest(
          this, done, refresh_token);
  req->Start();
  return true;
}

void NetworkManager::AuthViewfinder(
    const string& endpoint, const string& identity, const string& password,
    const string& first, const string& last, const string& name,
    bool error_if_linked, const AuthCallback& done) {
  CHECK(dispatch_is_main_thread());
  MutexLock l(&mu_);

  if (draining_ || xsrf_cookie().empty()) {
    ResetPing();
    dispatch_after_main(0, [done] {
        done(-1, ErrorResponse::NETWORK_UNAVAILABLE, kDefaultNetworkErrorMessage);
      });
    return;
  }

  // We need to keep track of whether we are registering a new user or doing
  // some other auth request (such as login or password reset). We'll use this
  // state when AuthDone() is called to determine whether we have to wait for
  // the initial asset scan to finish before querying server state or not.
  register_new_user_ = (endpoint == AppState::kRegisterEndpoint);

  // Immediately kick off the auth request.
  AuthViewfinderRequest* req = new AuthViewfinderRequest(
      this, endpoint, identity, password, first,
      last, name, error_if_linked, done);
  req->Start();
}

void NetworkManager::VerifyViewfinder(
    const string& identity, const string& access_token,
    bool manual_entry, const AuthCallback& done) {
  CHECK(dispatch_is_main_thread());
  MutexLock l(&mu_);

  if (draining_ || xsrf_cookie().empty()) {
    ResetPing();
    dispatch_after_main(0, [done] {
        done(-1, ErrorResponse::NETWORK_UNAVAILABLE, kDefaultNetworkErrorMessage);
      });
    return;
  }

  // Immediately kick off the auth request.
  VerifyViewfinderRequest* req = new VerifyViewfinderRequest(
      this, identity, access_token, manual_entry, done);
  req->Start();
}

void NetworkManager::ChangePassword(
    const string& old_password, const string& new_password,
    const AuthCallback& done) {
  // TODO(peter): Spencer notes there is a bunch of shared code between this
  // method, AuthViewfinder and VerifyViewfinder.
  CHECK(dispatch_is_main_thread());
  MutexLock l(&mu_);

  if (draining_ || xsrf_cookie().empty()) {
    ResetPing();
    dispatch_after_main(0, [done] {
        done(-1, ErrorResponse::NETWORK_UNAVAILABLE, kDefaultNetworkErrorMessage);
      });
    return;
  }

  // Immediately kick off the change password request.
  UpdateUserRequest* req = new UpdateUserRequest(
      this, old_password, new_password, done);
  req->Start();
}

void NetworkManager::MergeAccounts(
    const string& identity, const string& access_token,
    const string& completion_db_key,
    const AuthCallback& done) {
  // TODO(peter): Spencer notes there is a bunch of shared code between this
  // method, AuthViewfinder and VerifyViewfinder.
  CHECK(dispatch_is_main_thread());
  MutexLock l(&mu_);

  if (draining_ || xsrf_cookie().empty()) {
    ResetPing();
    dispatch_after_main(0, [done] {
        done(-1, ErrorResponse::NETWORK_UNAVAILABLE, kDefaultNetworkErrorMessage);
      });
    return;
  }

  // Immediately kick off the merge accounts request.
  MergeAccountsRequest* req = new MergeAccountsRequest(
      this, identity, access_token, completion_db_key, done);
  req->Start();
}

void NetworkManager::SetPushNotificationDeviceToken(const string& base64_token) {
  LOG("network: push notification device token: %s", base64_token);
  state_->db()->Put(kPushDeviceTokenKey, base64_token);

  update_device_ = true;
  Dispatch();
}

void NetworkManager::PauseNonInteractive() {
  MutexLock l(&mu_);
  ++pause_non_interactive_count_;
  NETLOG("network: pause non-interactive: %d", pause_non_interactive_count_);
}

void NetworkManager::ResumeNonInteractive() {
  MutexLock l(&mu_);
  --pause_non_interactive_count_;
  NETLOG("network: resume non-interactive: %d", pause_non_interactive_count_);

  // Note that we intentionally do not call dispatch_main() here as we want the
  // stack to unwind and locks to be released before Dispatch() is called.
  state_->async()->dispatch_main_async([this] {
      Dispatch();
    });
}

void NetworkManager::SetNetworkDisallowed(bool disallow) {
  if (disallow == network_disallowed_) {
    return;
  }
  // Full system message is logged by AppState, only log network status switch.
  LOG("Setting network_disallowed=%s", disallow ? "true" : "false");
  network_disallowed_ = disallow;
}

void NetworkManager::RunDownloadBenchmark() {
  MutexLock l(&mu_);
  // Don't clear the queue, we want to finish the previous benchmark, if any.
  for (int i = 0; i < ARRAYSIZE(kDownloadBenchmarkFiles); ++i) {
    benchmark_urls_.push_back(kDownloadBenchmarkURLPrefix + kDownloadBenchmarkFiles[i]);
  }

  // Trigger a Dispatch to start right away.
  state_->async()->dispatch_main_async([this] {
      Dispatch();
    });
}

void NetworkManager::Logout(bool clear_user_id) {
  MutexLock l(&mu_);
  state_->SetAuthCookies(string(), string());
  // Force the app back into the signup/login state.
  state_->SetUserAndDeviceId(clear_user_id ? 0 : state_->user_id(), 0);
}

void NetworkManager::UnlinkDevice() {
  MutexLock l(&mu_);
  ++epoch_;
  for (int i = 0; i < NUM_NETWORK_QUEUE_TYPES; i++) {
    queue_state_[i].backoff_delay = kMinBackoffDelay;
  }
  need_query_followed_ = true;
  query_followed_last_key_.clear();
  assets_scanned_ = false;
  refreshing_ = false;
  refresh_end_.Run();
}

void NetworkManager::Drain() {
  MutexLock l(&mu_);
  draining_ = true;
}

void NetworkManager::AssetScanEnd() {
  state_->async()->dispatch_main([this]{
      assets_scanned_ = true;
      need_query_followed_ = !state_->db()->Exists(kQueryFollowedDoneKey);
      if (need_query_followed_ &&
          !state_->db()->Exists(kQueryFollowedLastKey)) {
        LOG("network: initial state rebuild, synthesizing nuclear invalidate");
        // The query followed done key does not exist, synthesize a nuclear
        // invalidation.
        DBHandle updates = state_->NewDBTransaction();
        state_->notification_manager()->nuclear_invalidations()->Run(updates);
        updates->Commit();
      }
      Dispatch();
    });
}

void NetworkManager::MaybePingServer() {
  WallTime time_since_last_ping = WallTime_Now() - last_ping_timestamp_;
  if (time_since_last_ping > kPingPeriodDefault ||
      (network_disallowed_ && time_since_last_ping > kPingPeriodFast)) {
    last_ping_timestamp_ = WallTime_Now();
    PingRequest* req = new PingRequest(this);
    req->Start();
  }
}

void NetworkManager::MaybeBenchmarkDownload() {
  if (benchmark_urls_.empty()) {
    return;
  }

  BenchmarkDownloadRequest* req = new BenchmarkDownloadRequest(this, benchmark_urls_.front());
  benchmark_urls_.pop_front();
  req->Start();
}

void NetworkManager::MaybeDownloadPhoto() {
  const NetworkQueue::DownloadPhoto* d =
      state_->net_queue()->queued_download_photo();
  if (!d) {
    return;
  }
  DownloadPhotoRequest* req = new DownloadPhotoRequest(this, d);
  req->Start();
}

void NetworkManager::MaybeQueryContacts() {
  ContactSelection contacts;
  if (!state_->contact_manager()->GetInvalidation(&contacts)) {
    return;
  }
  QueryContactsRequest* req = new QueryContactsRequest(this, contacts);
  req->Start();
}

void NetworkManager::MaybeQueryEpisodes() {
  vector<EpisodeSelection> episodes;
  state_->episode_table()->ListInvalidations(
      &episodes, kQueryEpisodesLimit, state_->db());
  if (episodes.empty()) {
    return;
  }
  QueryEpisodesRequest* req = new QueryEpisodesRequest(this, episodes);
  req->Start();
}

void NetworkManager::MaybeQueryFollowed() {
  if (!need_query_followed_ || !assets_scanned_) {
    return;
  }
  QueryFollowedRequest* req = new QueryFollowedRequest(this);
  req->Start();
}

void NetworkManager::MaybeQueryNotifications(bool long_poll) {
  NotificationSelection notifications;
  if (!assets_scanned_) {
    return;
  }
  if (need_query_followed_ && !query_followed_last_key_.empty()) {
    // If we're rebuilding our list of viewpoints, let that finish before querying for more notifications.
    return;
  }
  const bool need_query = state_->notification_manager()->GetInvalidation(&notifications);
  if (!need_query && !long_poll) {
    // If we think we're up to date, don't query unless we're in long-poll mode.
    return;
  }
  QueryNotificationsRequest* req = new QueryNotificationsRequest(this, notifications, long_poll);
  req->Start();
}

void NetworkManager::MaybeQueryUsers() {
  vector<int64_t> user_ids;
  state_->contact_manager()->ListQueryUsers(&user_ids, kQueryUsersLimit);
  if (user_ids.empty()) {
    return;
  }
  QueryUsersRequest* req = new QueryUsersRequest(this, user_ids);
  req->Start();
}

void NetworkManager::MaybeQueryViewpoints() {
  vector<ViewpointSelection> viewpoints;
  state_->viewpoint_table()->ListInvalidations(
      &viewpoints, kQueryViewpointsLimit, state_->db());
  if (viewpoints.empty()) {
    return;
  }
  QueryViewpointsRequest* req = new QueryViewpointsRequest(this, viewpoints);
  req->Start();
}

void NetworkManager::MaybeRecordSubscription() {
  if (!state_->subscription_manager()) {
    return;
  }
  const SubscriptionManager::RecordSubscription* r =
      state_->subscription_manager()->GetQueuedRecordSubscription();
  if (!r) {
    return;
  }
  RecordSubscriptionRequest* req = new RecordSubscriptionRequest(this, r);
  req->Start();
}

void NetworkManager::MaybeRemovePhotos() {
  const NetworkQueue::RemovePhotos* r =
      state_->net_queue()->queued_remove_photos();
  if (!r) {
    return;
  }
  RemovePhotosRequest* req = new RemovePhotosRequest(this, r);
  req->Start();
}

void NetworkManager::MaybeUpdateDevice() {
  if (!update_device_) {
    return;
  }
  UpdateDeviceRequest* req = new UpdateDeviceRequest(this, &update_device_);
  req->Start();
}

void NetworkManager::MaybeUpdateFriend() {
  if (!state_->contact_manager()->queued_update_friend()) {
    return;
  }
  UpdateFriendRequest* req = new UpdateFriendRequest(
      this, state_->contact_manager()->queued_update_friend());
  req->Start();
}

void NetworkManager::MaybeUpdatePhoto() {
  const NetworkQueue::UpdatePhoto* u =
      state_->net_queue()->queued_update_photo();
  if (!u) {
    return;
  }
  UpdateUserPhotoRequest* req = new UpdateUserPhotoRequest(this, u);
  req->Start();
}

void NetworkManager::MaybeUpdateUser() {
  if (!state_->contact_manager()->queued_update_self()) {
    return;
  }
  UpdateUserRequest* req = new UpdateUserRequest(this, "", "", NULL);
  req->Start();
}

void NetworkManager::MaybeUpdateViewpoint() {
  const NetworkQueue::UpdateViewpoint* u =
      state_->net_queue()->queued_update_viewpoint();
  if (!u) {
    return;
  }
  UpdateViewpointRequest* req = new UpdateViewpointRequest(this, u);
  req->Start();
}

void NetworkManager::MaybeUploadContacts() {
  const ContactManager::UploadContacts* u = state_->contact_manager()->queued_upload_contacts();
  if (!u) {
    return;
  }
  UploadContactsRequest* req = new UploadContactsRequest(this, u);
  req->Start();
}

void NetworkManager::MaybeRemoveContacts() {
  const ContactManager::RemoveContacts* r = state_->contact_manager()->queued_remove_contacts();
  if (!r) {
    return;
  }
  RemoveContactsRequest* req = new RemoveContactsRequest(this, r);
  req->Start();
}

void NetworkManager::MaybeUploadActivity() {
  const NetworkQueue::UploadActivity* u =
      state_->net_queue()->queued_upload_activity();
  if (!u) {
    return;
  }
  if (u->activity->has_share_new() || u->activity->has_share_existing()) {
    ShareRequest* req = new ShareRequest(this, u);
    req->Start();
  } else if (u->activity->has_add_followers()) {
    AddFollowersRequest* req = new AddFollowersRequest(this, u);
    req->Start();
  } else if (u->activity->has_post_comment()) {
    PostCommentRequest* req = new PostCommentRequest(this, u);
    req->Start();
  } else if (u->activity->has_remove_followers()) {
    RemoveFollowersRequest* req = new RemoveFollowersRequest(this, u);
    req->Start();
  } else if (u->activity->has_save_photos()) {
    SavePhotosRequest* req = new SavePhotosRequest(this, u);
    req->Start();
  } else if (u->activity->has_unshare()) {
    UnshareRequest* req = new UnshareRequest(this, u);
    req->Start();
  }
}

void NetworkManager::MaybeUploadEpisode() {
  const NetworkQueue::UploadEpisode* u =
      state_->net_queue()->queued_upload_episode();
  if (!u) {
    return;
  }
  UploadEpisodeRequest* req = new UploadEpisodeRequest(this, u);
  req->Start();
}

void NetworkManager::MaybeUploadLog() {
#if (TARGET_IPHONE_SIMULATOR)
  // Don't upload logs from the simulator.
  return;
#endif // (TARGET_IPHONE_SIMULATOR)

  if (!network_wifi_) {
    // Only attempt log upload on wifi connections.
    return;
  }

  if (!state_->upload_logs()) {
    // User has disabled debug log uploads
    return;
  }

  if (WallTime_Now() - state_->last_login_timestamp() < kUploadLogOptOutGracePeriod) {
    // Uploading logs is on by default, but to ensure that users have an opportunity to
    // opt-out, we don't actually start uploading logs for at least 10 minutes after login.
    return;
  }

  const string queue_dir = LoggingQueueDir();
  vector<string> queued_logs;
  DirList(queue_dir, &queued_logs);
  if (queued_logs.empty()) {
    return;
  }

  // TODO(pmattis): Is the sort necessary?
  std::sort(queued_logs.begin(), queued_logs.end(), std::greater<string>());
  UploadLogRequest* req = new UploadLogRequest(this, queue_dir, queued_logs[0]);
  req->Start();
}

void NetworkManager::MaybeUploadPhoto() {
  const NetworkQueue::UploadPhoto* u =
      state_->net_queue()->queued_upload_photo();
  if (!u) {
    return;
  }
  if (u->md5.empty()) {
    // The upload photo failed to queue. Call CommitQueuedUploadPhoto() on the
    // network thread.
    PauseLocked(NETWORK_QUEUE_SYNC);
    state_->async()->dispatch_network(true, [this, u] {
        LOG("network: upload photo error: %s: queueing failed", u->photo->id());
        state_->net_queue()->CommitQueuedUploadPhoto(true);
        MutexLock l(&mu_);  // We no longer have the lock here.
        ResumeLocked(NETWORK_QUEUE_SYNC);
      });
  } else {
    UploadPhotoRequest* req = new UploadPhotoRequest(this, u);
    req->Start();
  }
}

void NetworkManager::StartRequestLocked(NetworkManagerQueueType queue) {
  PauseLocked(queue);
}

void NetworkManager::FinishRequest(bool success, int epoch, NetworkManagerQueueType queue) {
  MutexLock l(&mu_);
  if (epoch != epoch_) {
    // Network requests from a different epoch should be ignored.
    --queue_state_[queue].network_count;
    LOG("network: ignoring network request from unexpected epoch: %d != %d",
        epoch, epoch_);
    return;
  }

  CHECK_GT(queue_state_[queue].network_count, 0);
  last_request_success_ = success;
  if (success) {
    queue_state_[queue].backoff_delay = kMinBackoffDelay;
    ResumeLocked(queue);
  } else {
    BackoffLocked(queue);
  }
}

void NetworkManager::PauseLocked(NetworkManagerQueueType queue) {
  mu_.AssertHeld();
  CHECK(state_->async()->Enter());
  ++queue_state_[queue].network_count;
  //LOG("paused; network count: %d", network_count_);
}

void NetworkManager::ResumeLocked(NetworkManagerQueueType queue) {
  mu_.AssertHeld();
  --queue_state_[queue].network_count;
  //LOG("resumed; network count: %d", network_count_);
  if (!state_->async()->Exit()) {
    return;
  }
  // Note that we intentionally do not call dispatch_main() here as we want the
  // stack to unwind and locks to be released before Dispatch() is called.
  state_->async()->dispatch_main_async([this] {
      Dispatch();
    });
}

void NetworkManager::BackoffLocked(NetworkManagerQueueType queue) {
  mu_.AssertHeld();
  // During the backoff delay, decrement the async running-operation
  // count, so that a backed-off request does not delay destruction of
  // the AsyncState object.  This is especially important during
  // tests, when a background thread may be generating errors due to
  // unimplemented server methods and thus be in a perpetual backoff
  // state.
  QueueState* state = &queue_state_[queue];
  --state->network_count;
  ++state->backoff_count;
  NETLOG("network: backoff start: %d %.0f", state->backoff_count, state->backoff_delay);
  if (!state_->async()->Exit()) {
    return;
  }
  state_->async()->dispatch_after_main(state->backoff_delay, [this, queue, state] {
      // Check the backoff_count_ flag in case the backoff was reset while we were waiting.
      MutexLock lock(&mu_);
      if (state->backoff_count) {
        NETLOG("network: backoff done: %d", state->backoff_count);
        state->backoff_delay = std::min<double>(state->backoff_delay * 2, kMaxBackoffDelay);
        ResumeFromBackoffLocked(queue);
      }
    });
}

void NetworkManager::ResumeFromBackoffLocked(NetworkManagerQueueType queue) {
  mu_.AssertHeld();
  QueueState* state = &queue_state_[queue];
  CHECK_GT(state->backoff_count, 0);
  CHECK(state_->async()->Enter());
  ++state->network_count;
  --state->backoff_count;
  ResumeLocked(queue);
}

void NetworkManager::NuclearInvalidation(const DBHandle& updates) {
  MutexLock l(&mu_);

  updates->Delete(kQueryFollowedDoneKey);
  updates->Delete(kQueryFollowedLastKey);
  query_followed_last_key_.clear();
  need_query_followed_ = true;
}

bool NetworkManager::queue_is_busy(NetworkManagerQueueType queue) const {
  const QueueState& state = queue_state_[queue];
  if (state.network_count || state.backoff_count) {
    NETLOG("network dispatch: queue: %s count: %d, backoff: %d",
           queue, state.network_count, state.backoff_count);
    return true;
  }
  return false;
}

void NetworkManager::ResetPing() {
  last_ping_timestamp_ = 0;
  dispatch_after_main(0, [this] {
      Dispatch();
    });
}

bool NetworkManager::need_auth() const {
  return state_->auth().user_cookie().empty();
}

const string& NetworkManager::xsrf_cookie() const {
  return state_->auth().xsrf_cookie();
}

// local variables:
// mode: c++
// end:
