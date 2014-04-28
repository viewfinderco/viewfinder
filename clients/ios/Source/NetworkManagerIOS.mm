// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Analytics.h"
#import "AppDelegate.h"
#import "AssetsManager.h"
#import "AsyncState.h"
#import "Defines.h"
#import "NetworkManagerIOS.h"
#import "NetworkQueue.h"
#import "NotificationManager.h"
#import "UIAppState.h"

namespace {

const string kJsonContentType = "application/json";

const WallTime kRequestTimeout = 60;

string ReachabilityFlagsToString(SCNetworkConnectionFlags flags) {
  return Format(
      "%c%c%c%c%c%c%c%c%c",
      (flags & kSCNetworkReachabilityFlagsIsWWAN)               ? 'W' : '-',
      (flags & kSCNetworkReachabilityFlagsReachable)            ? 'R' : '-',
      (flags & kSCNetworkReachabilityFlagsTransientConnection)  ? 't' : '-',
      (flags & kSCNetworkReachabilityFlagsConnectionRequired)   ? 'c' : '-',
      (flags & kSCNetworkReachabilityFlagsConnectionOnTraffic)  ? 'C' : '-',
      (flags & kSCNetworkReachabilityFlagsInterventionRequired) ? 'i' : '-',
      (flags & kSCNetworkReachabilityFlagsConnectionOnDemand)   ? 'D' : '-',
      (flags & kSCNetworkReachabilityFlagsIsLocalAddress)       ? 'l' : '-',
      (flags & kSCNetworkReachabilityFlagsIsDirect)             ? 'd' : '-');
}

string EncodeToString(NSDictionary* d) {
  NSMutableData* data = [NSMutableData new];
  NSKeyedArchiver* archiver =
      [[NSKeyedArchiver alloc] initForWritingWithMutableData:data];
  [d encodeWithCoder:archiver];
  [archiver finishEncoding];
  return ToString(data);
}

NSDictionary* DecodeFromString(const string& s) {
  NSKeyedUnarchiver* unarchiver =
      [[NSKeyedUnarchiver alloc] initForReadingWithData:NewNSData(s)];
  return [[NSDictionary alloc] initWithCoder:unarchiver];
}

bool ShouldBackoffForStatusCode(int code) {
  // We back off for all 5xx errors, but only some 4xx errors because others are used for
  // signalling normal conditions (like logout).
  switch (code / 100) {
    case 5:  // 5xx errors.
      return true;
    case 4:  // 4xx errors.
      // Keep retrying on 401 (we'd like to know if the logout process fails) and 404
      // since these may occur from S3.
      return (code != 401 && code != 404);
    default:
      return false;
  }
}

NSHTTPCookie* DecodeCookie(const string& raw_cookie) {
  if (raw_cookie.empty()) {
    return NULL;
  }
  NSDictionary* properties = DecodeFromString(raw_cookie);
  if (!properties) {
    return NULL;
  }
  return [NSHTTPCookie cookieWithProperties:properties];
}

}  // namespace


@class NetworkCallbacks;

class NetworkRequestImpl {
 public:
  NetworkRequestImpl(NetworkManager* net, NetworkRequest* req);
  ~NetworkRequestImpl();

  void Send(const string& url, const Slice& method, const Slice& body,
            const Slice& content_type, const Slice& content_md5,
            const Slice& if_none_match);
  NSURLRequest* Redirect(NSURLRequest* req, NSHTTPURLResponse* resp);
  void Response(NSHTTPURLResponse* r);
  void Data(NSData* d);
  void Error(NSError* e);
  void Done();

  string url() const {
    return ToString([url_req_ URL]);
  }

 private:
  void MaybeInitAuth(NSHTTPURLResponse* r);

  AppState* state() const { return net_->state(); }

 private:
  const int epoch_;
  NetworkManager* const net_;
  NetworkRequest* const req_;
  NetworkCallbacks* callbacks_;
  NSMutableURLRequest* url_req_;
  NSHTTPURLResponse* url_resp_;
  NSURLConnection* url_conn_;
};


@interface NetworkCallbacks : NSObject<NSURLConnectionDelegate> {
 @private
  NetworkRequestImpl* req_;
  AppState* state_;
}

- (id)initWithRequest:(NetworkRequestImpl*)req
                state:(AppState*)state;

@end  // NetworkCallbacks

@implementation NetworkCallbacks

- (id)initWithRequest:(NetworkRequestImpl*)req
                state:(AppState*)state {
  if (self = [super init]) {
    req_ = req;
    state_ = state;
  }
  return self;
}

- (NSURLRequest*)connection:(NSURLConnection*)conn
            willSendRequest:(NSURLRequest*)req
           redirectResponse:(NSURLResponse*)resp {
  return req_->Redirect(req, (NSHTTPURLResponse*)resp);
}

- (void)connection:(NSURLConnection*)conn
didReceiveResponse:(NSURLResponse*)resp {
  if (![resp isKindOfClass:[NSHTTPURLResponse class]]) {
    return;
  }
  req_->Response((NSHTTPURLResponse*)resp);
}

- (void)connection:(NSURLConnection*)conn
    didReceiveData:(NSData*)data {
  req_->Data(data);
}

- (void)connection:(NSURLConnection*)conn
  didFailWithError:(NSError*)error {
  req_->Error(error);
}

- (void)connectionDidFinishLoading:(NSURLConnection*)conn {
  req_->Done();
}

- (BOOL)connection:(NSURLConnection*)conn
canAuthenticateAgainstProtectionSpace:(NSURLProtectionSpace*)space {
  // Indicate we want to process certificates in didReceiveAuthenticationChallenge
  // (and not basic auth or other authentication challenges).
  return [space.authenticationMethod
          isEqualToString:NSURLAuthenticationMethodServerTrust];
}

- (void)connection:(NSURLConnection*)conn
didReceiveAuthenticationChallenge:(NSURLAuthenticationChallenge*)challenge {
#ifdef DEVELOPMENT
  // In non-production builds configured to talk to a non-production server,
  // allow any certificate as long as the hostname matches.
  // If we're using the production server, require a valid cert even in
  // non-production (i.e. TestFlight) builds.
  // TODO(ben): Consider cert pinning or CA restrictions in production builds.
  // (google for SecTrustEvaluate for details on how to do that)
  if ([challenge.protectionSpace.authenticationMethod
       isEqualToString:NSURLAuthenticationMethodServerTrust]) {
    const string& server_host = state_->server_host();
    const bool prod_server = (server_host == "www.viewfinder.co" || server_host == "staging.viewfinder.co");
    if (!prod_server && server_host == ToString(challenge.protectionSpace.host)) {
      [challenge.sender useCredential:
       [NSURLCredential credentialForTrust:challenge.protectionSpace.serverTrust]
       forAuthenticationChallenge:challenge];
      return;
    }
  }
#endif  // DEVELOPMENT
  // Fall through to default behavior (which for ServerTrust includes validating
  // against the OS-provided root CAs)
  [challenge.sender continueWithoutCredentialForAuthenticationChallenge:challenge];
}

@end  // NetworkCallbacks


NetworkRequestImpl::NetworkRequestImpl(NetworkManager* net, NetworkRequest* req)
    : epoch_(net->epoch_),
      net_(net),
      req_(req),
      callbacks_([[NetworkCallbacks alloc] initWithRequest:this state:net_->state()]) {
}

NetworkRequestImpl::~NetworkRequestImpl() {
  delete req_;
}

void NetworkRequestImpl::Send(
    const string& url, const Slice& method, const Slice& body,
    const Slice& content_type, const Slice& content_md5,
    const Slice& if_none_match) {
  url_req_ = [[NSMutableURLRequest alloc]
               initWithURL:NewNSURL(url)
               cachePolicy:NSURLRequestReloadIgnoringLocalAndRemoteCacheData
               timeoutInterval:kRequestTimeout];
  [url_req_ setHTTPMethod:NewNSString(method)];

  // Distinguish requests to our own server from others (e.g. s3).
  const bool is_vf_server = (ToString(url_req_.URL.host) == net_->state()->server_host());

  if (!body.empty()) {
    bool body_set = false;
    if (is_vf_server && content_type == kJsonContentType) {
      // TODO(ben): Move gzip handling into the shared codebase.
      const string compressed_body = GzipEncode(body);
      // An empty compressed body means a gzip failure.  Small requests may get bigger when compressed
      // (due to the gzip header in the payload and the HTTP Content-Encoding header), so send them
      // uncompressed.  Note the use of two comparisons because string::size() is unsigned and so the
      // subtraction might wrap around.
      static const int header_size = strlen("Content-Encoding: gzip\r\n");
      if (!compressed_body.empty() &&
          body.size() > compressed_body.size() &&
          body.size() - compressed_body.size() > header_size) {
        //LOG("network: sending gzip'd body: %d -> %d", body.size(), compressed_body.size());
        [url_req_ setHTTPBody:NewNSData(compressed_body)];
        [url_req_ setValue:@"gzip" forHTTPHeaderField:@"Content-Encoding"];
        body_set = true;
      } else {
        //LOG("network: not gzipping body: %d -> %d", body.size(), compressed_body.size());
      }
    }

    if (!body_set) {
      [url_req_ setHTTPBody:NewNSData(body)];
    }
  }
  if (!content_type.empty()) {
    [url_req_ setValue:NewNSString(content_type) forHTTPHeaderField:@"Content-Type"];
  }
  if (!content_md5.empty()) {
    [url_req_ setValue:NewNSString(content_md5) forHTTPHeaderField:@"Content-MD5"];
  }
  if (!if_none_match.empty()) {
    [url_req_ setValue:NewNSString(if_none_match) forHTTPHeaderField:@"If-None-Match"];
  }
  if (is_vf_server && method != "GET") {
    if (![url_req_.URL.path isEqualToString:@"/ping"]) {
      DCHECK(!net_->xsrf_cookie().empty());
    }
    NSHTTPCookie* cookie = DecodeCookie(net_->xsrf_cookie());
    if (cookie) {
      [url_req_ setValue:NewNSString(ToString(cookie.value)) forHTTPHeaderField:@"X-Xsrftoken"];
    }
  }

  url_conn_ = [[NSURLConnection alloc]
                initWithRequest:url_req_
                       delegate:callbacks_
                startImmediately:NO];
  [url_conn_ scheduleInRunLoop:[NSRunLoop mainRunLoop]
                       forMode:NSRunLoopCommonModes];
  net_->StartRequestLocked(req_->queue_type_);
  [url_conn_ start];
}

NSURLRequest* NetworkRequestImpl::Redirect(
    NSURLRequest* req, NSHTTPURLResponse* resp) {
  if (!resp) {
    return req;
  }

  [[resp allHeaderFields] enumerateKeysAndObjectsUsingBlock:
   ^(NSString* key, NSString* value, BOOL* stop) {
      if (ToLowercase(ToSlice(key)) == "x-vf-staging-redirect") {
        LOG("net: staging redirect, setting server host to %@", value);
        net_->state()->set_server_host(ToSlice(value));
        *stop = YES;
      }
    }];
  NSMutableURLRequest* r = [req mutableCopy];
  [r setHTTPMethod:[url_req_ HTTPMethod]];
  if (url_req_.HTTPBody) {
    [r setHTTPBody:url_req_.HTTPBody];
  }

#define MAYBE_COPY(field)                                     \
  do {                                                        \
    NSString* v = [url_req_ valueForHTTPHeaderField:field];   \
    if (v) {                                                  \
      [r setValue:v forHTTPHeaderField:field];                \
    }                                                         \
  } while (0)

  MAYBE_COPY(@"Content-Type");
  MAYBE_COPY(@"Content-MD5");
  MAYBE_COPY(@"X-Xsrftoken");

#undef MAYBE_COPY

  // Allow the NetworkRequest to mutate the redirect.
  ScopedPtr<string> new_body;
  StringSet delete_headers;
  StringMap add_headers;
  req_->HandleRedirect(&new_body, &delete_headers, &add_headers);
  if (new_body.get()) {
    [r setHTTPBody:NewNSData(*new_body)];
  }
  for (auto it : delete_headers) {
    [r setValue:NULL forHTTPHeaderField:NewNSString(it)];
  }
  for (auto it : add_headers) {
    [r setValue:NewNSString(it.second) forHTTPHeaderField:NewNSString(it.first)];
  }
  return r;
}

void NetworkRequestImpl::Response(NSHTTPURLResponse* r) {
  url_resp_ = r;
  net_->state_->async()->dispatch_network(true, ^{
      if (net_->epoch() == epoch_) {
        MaybeInitAuth(r);
      }
    });
}

void NetworkRequestImpl::Data(NSData* d) {
  net_->state_->async()->dispatch_network(true, ^{
      req_->HandleData(ToSlice(d));
    });
}

void NetworkRequestImpl::Error(NSError* e) {
  net_->state_->async()->dispatch_network(true, ^{
      if (net_->epoch() == epoch_) {
        req_->HandleError(ToString(e.localizedDescription));
      }
      net_->FinishRequest(false, epoch_, req_->queue_type_);
      delete this;
    });
}

void NetworkRequestImpl::Done() {
  net_->state_->async()->dispatch_network(true, ^{
      // Handle an explicit authentication rejection by the server.
      if (url_resp_.statusCode == 401 || net_->fake_401()) {
        net_->set_fake_401(false);
        net_->Logout();
      }
      if (net_->epoch() == epoch_) {
        bool success = req_->HandleDone(url_resp_.statusCode);
        if (ShouldBackoffForStatusCode(url_resp_.statusCode)) {
          // Some of our request handlers return true even for failed requests.  This is OK for the
          // ones that can correctly quarantine the request, but the ones that can't will retry in a
          // tight loop.  Safeguard against this loop by always treating 5xx or 400 status codes as
          // failures to trigger backoff (and high-priority log uploads).  This will cause a
          // slowdown for clients that are triggering quarantines, but we don't expect that to happen
          // often.
          success = false;
        }
        net_->FinishRequest(success, epoch_, req_->queue_type_);
      } else {
        net_->FinishRequest(false, epoch_, req_->queue_type_);
      }
      delete this;
    });
}

void NetworkRequestImpl::MaybeInitAuth(NSHTTPURLResponse* r) {
  MutexLock l(&net_->mu_);
  NSArray* cookies =
      [NSHTTPCookie cookiesWithResponseHeaderFields:r.allHeaderFields
                                             forURL:r.URL];
  string new_user_cookie = state()->auth().user_cookie();
  string new_xsrf_cookie = state()->auth().xsrf_cookie();

  for (NSHTTPCookie* cookie in cookies) {
    const Slice name(ToSlice(cookie.name));
    if (name == "user") {
      if (net_->need_auth()) {
        LOG("network: new user cookie");
      }
      new_user_cookie = EncodeToString(cookie.properties);
    } else if (name == "_xsrf") {
      NSHTTPCookie* prev_xsrf_cookie = DecodeCookie(net_->xsrf_cookie());
      if (!prev_xsrf_cookie || prev_xsrf_cookie.value != cookie.value) {
        LOG("network: new xsrf cookie");
        new_xsrf_cookie = EncodeToString(cookie.properties);
      }
    }
  }

  state()->SetAuthCookies(new_user_cookie, new_xsrf_cookie);
}


NetworkManagerIOS::NetworkManagerIOS(UIAppState* state)
    : NetworkManager(state),
      state_(state) {
  if (state_->server_host().empty()) {
    // Networking is disabled.
    return;
  }

  // Initialize background manager.
  bg_mgr_ = [[BackgroundManager alloc] initWithState:state_ withBlock:^{
      // If the app is in the background and remote notifications are disabled,
      // force a periodic invalidation to check for new content.  (if notifications
      // are enabled we'll get an AppDelegate notification (iOS 7+), and if we're in the
      // foreground we have long polling).
      if (network_up() && assets_scanned_ &&
          state_->remote_notification_types() == 0 &&
           !state_->ui_application_active()) {
        LOG("network: background query notifications running...");
        DBHandle updates = state_->NewDBTransaction();
        state_->notification_manager()->Invalidate(updates);
        updates->Commit();
      }
      Dispatch();
    }];

  InitCookies();

  AddAssetsScanWatcher();

  reachability_.acquire(
      SCNetworkReachabilityCreateWithName(NULL, state_->server_host().c_str()));

  SCNetworkReachabilityContext context = {0, (void*)this, NULL, NULL, NULL};
  if (!SCNetworkReachabilitySetCallback(
          reachability_, &NetworkManagerIOS::ReachabilityChanged, &context)) {
    LOG("network: unable to set reachability callback");
  }
  if (!SCNetworkReachabilityScheduleWithRunLoop(
          reachability_, [[NSRunLoop mainRunLoop] getCFRunLoop],
          kCFRunLoopCommonModes)) {
    LOG("network: unable to schedule network reachability");
  }

  state_->apn_device_token()->Add(^(NSData* token) {
      if (!token) {
        // TODO(peter): An error occurred. Should we clear the device token?
        return;
      }

#ifdef DEVELOPMENT
      const char *kPrefix = "apns-dev";
#elif ENTERPRISE
      const char *kPrefix = "apns-ent";
#else   // !DEVELOPMENT && !ENTERPRISE
      const char *kPrefix = "apns-prod";
#endif  // !DEVELOPMENT && !ENTERPRISE

      const string base64_token =
          Format("%s:%s", kPrefix, Base64Encode(ToSlice(token)));
      SetPushNotificationDeviceToken(base64_token);
    });

  // Set a low limit on caching as we mostly perform our own.
  NSURLCache* cache = [NSURLCache sharedURLCache];
  cache.memoryCapacity = 0;
  cache.diskCapacity = 1 << 20;  // 1 MB
}

NetworkManagerIOS::~NetworkManagerIOS() {
  if (reachability_.get()) {
    if (!SCNetworkReachabilitySetCallback(reachability_, NULL, NULL)) {
      LOG("network: unable to set reachability callback");
    }
  }
}

void NetworkManagerIOS::ResetQueryNotificationsBackoff() {
  [bg_mgr_ resetBackoff];
}

bool NetworkManagerIOS::ShouldClearApplicationBadge() {
  return state_->ui_application_active();
}

void NetworkManagerIOS::ClearApplicationBadge() {
  state_->async()->dispatch_main(^{
      [AppDelegate setApplicationIconBadgeNumber:0];
    });
}

void NetworkManagerIOS::Logout(bool clear_user_id) {
  NetworkManager::Logout(clear_user_id);
  // Delete all cookies (user, xsrf, facebook)
  Clean();
}

void NetworkManagerIOS::UnlinkDevice() {
  NetworkManager::UnlinkDevice();
  // Delete all cookies (user, xsrf, facebook)
  Clean();
  AddAssetsScanWatcher();
}

void NetworkManagerIOS::Clean(const string& server) {
  // This method doubles as our cookie-initialization method; it's always called before we do
  // anything else with cookies.
  NSHTTPCookieStorage* storage = [NSHTTPCookieStorage sharedHTTPCookieStorage];
  // If the user blocks all cookies in Safari settings, that setting is inherited by
  // NSHTTPCookieStorage objects created by all other apps.  We must override it so that
  // our authentication and xsrf cookies can work.
  storage.cookieAcceptPolicy = NSHTTPCookieAcceptPolicyAlways;

  int n = 0;
  for (NSHTTPCookie* cookie in storage.cookies) {
    if (server.empty() || ToSlice(cookie.domain).ends_with(server)) {
      [storage deleteCookie:cookie];
      ++n;
    }
  }
  VLOG("network: deleted %d cookie%s", n, Pluralize(n));
}

void NetworkManagerIOS::ReachabilityChanged(
    SCNetworkReachabilityRef target,
    SCNetworkConnectionFlags flags,
    void* object) {
  NetworkManagerIOS* net_manager = (NetworkManagerIOS*)object;
  net_manager->ReachabilityChanged(target, flags);
}

void NetworkManagerIOS::ReachabilityChanged(
    SCNetworkReachabilityRef target,
    SCNetworkConnectionFlags flags) {
  bool reachable = (flags & kSCNetworkReachabilityFlagsReachable) != 0;
  bool wifi = false;
  if (reachable) {
    if ((flags & kSCNetworkReachabilityFlagsConnectionRequired) == 0) {
      // If target host is reachable and no connection is required then we'll
      // assume (for now) that we have a wifi connection.
      wifi = true;
    }
    if (((((flags & kSCNetworkReachabilityFlagsConnectionOnDemand) != 0) ||
          (flags & kSCNetworkReachabilityFlagsConnectionOnTraffic) != 0)) &&
        ((flags & kSCNetworkReachabilityFlagsInterventionRequired) == 0)) {
      // The connect is on-demand or on-traffic and no user intervention is
      // required.
      wifi = true;
    }
    if ((flags & kSCNetworkReachabilityFlagsIsWWAN) != 0) {
      // WWAN connections are definitely not wifi.
      wifi = false;
    }
  }

  LOG("network: %s (%s) (%s): %s", reachable ? "up" : "down",
      need_auth() ? "not-authenticated" : "authenticated",
      wifi ? "wifi" : "3g", ReachabilityFlagsToString(flags));

  if (network_reachable_ != reachable || network_wifi_ != wifi) {
    network_reachable_ = reachable;
    network_wifi_ = wifi;

    network_changed_.Run();
    state_->analytics()->Network(reachable, wifi);
  }

  SetIdleTimer();
  if (network_reachable_) {
    Dispatch();
  }
}

void NetworkManagerIOS::InitCookies() {
  // Clean out any existing cookie. This is necessary because
  // NSHTTPCookieStorage is idiotic about when it synchronizes and often
  // times deleted cookies resurrect themselves.
  Clean();

  enum {
    kUserCookie = 0,
    kXsrfCookie,
  };
  const string cookie_values[] = {
    state_->auth().user_cookie(),
    state_->auth().xsrf_cookie()
  };

  for (int i = 0; i < ARRAYSIZE(cookie_values); ++i) {
    const string& encoded_cookie = cookie_values[i];
    NSHTTPCookie* cookie = DecodeCookie(encoded_cookie);
    if (!cookie) {
      continue;
    }
    NSHTTPCookieStorage* storage =
        [NSHTTPCookieStorage sharedHTTPCookieStorage];
    [storage setCookie:cookie];
    if (i == kUserCookie) {
      LOG("network: found user cookie: expires %s", cookie.expiresDate);
    }
  }
}

void NetworkManagerIOS::AddAssetsScanWatcher() {
  // Wait for the first asset scan to complete before querying for
  // notifications and updates. This is necessary in case the app state has
  // been reset. We want to load all of the assets before retrieving network
  // updates so that we'll be able to successfully match up images on the
  // server with local images. This matching is only done when the server sends
  // updates, not when a photo is added from the asset library, so let's make
  // sure the assets are loaded.
  assets_scanned_ = false;
  state_->assets_scan_end()->AddSingleShot(^(const StringSet*) {
      AssetScanEnd();
    });
}

void NetworkManagerIOS::SetIdleTimer() {
  UIApplication* a = [UIApplication sharedApplication];

  // If registered, start background manager.
  if (state_->is_registered()) {
    const bool keep_alive = !state_->net_queue()->Empty() || request_in_flight();
#if !(TARGET_IPHONE_SIMULATOR)
    // Start the timer if push notifications are disabled and the app is active.
    if (state_->remote_notification_types() == 0 && state_->ui_application_active()) {
      [bg_mgr_ resetBackoff];
    }
#endif // !(TARGET_IPHONE_SIMULATOR)
    [bg_mgr_ startWithKeepAlive:keep_alive];
  }

  if (ShouldDisableIdleTimer()) {
    if (!a.idleTimerDisabled) {
      LOG("network: disabling idle timer: %.2f battery%s",
          state_->battery_level(),
          state_->battery_charging() ? " (charging)" : "");
      a.idleTimerDisabled = YES;
    }
  } else {
    if (a.idleTimerDisabled) {
      LOG("network: enabling idle timer");
      a.idleTimerDisabled = NO;
    }
  }
}

bool NetworkManagerIOS::ShouldDisableIdleTimer() const {
  if (!network_up() || !state_->is_registered()) {
    return false;
  }
  if (!state_->battery_charging() && state_->battery_level() < 0.5) {
    return false;
  }
  if (!state_->net_queue()->Empty()) {
    return true;
  }
  if (request_in_flight()) {
    return true;
  }
  if (state_->assets_initial_scan() && state_->assets_manager().scanning) {
    return true;
  }
  return false;
}

void NetworkManagerIOS::AuthDone() {
  MutexLock l(&mu_);
  if (!register_new_user_ || !state_->is_registered()) {
    return;
  }
  // If we were registering a new user and the user is now registered, pretend
  // that the initial asset scan finished since we don't have to worry about
  // duplicate photo issues because the server will not have any photos for the
  // user.
  AssetScanEnd();
}

void NetworkManagerIOS::SendRequest(
    NetworkRequest* req, const Slice& method, const Slice& body,
    const Slice& content_type, const Slice& content_md5,
    const Slice& if_none_match) {
  NetworkRequestImpl* impl = new NetworkRequestImpl(this, req);
  impl->Send(req->url(), method, body, content_type, content_md5, if_none_match);
}

bool NetworkManagerIOS::pause_non_interactive() const {
  // Only pause non-interactive network operations while the application is
  // active. If the application is in the background, the UI can't possibly
  // be doing anything interesting that requires non-interactive network
  // operations to be paused.
  return state_->ui_application_active() &&
      (pause_non_interactive_count_ > 0);
}

bool NetworkManagerIOS::request_in_flight() const {
  for (int i = 0; i < NUM_NETWORK_QUEUE_TYPES; i++) {
    if (i != NETWORK_QUEUE_NOTIFICATION /* ignore long-poll for notifications */ &&
        queue_state_[i].network_count > 0) {
      return true;
    }
  }
  return false;
}


// local variables:
// mode: c++
// end:
