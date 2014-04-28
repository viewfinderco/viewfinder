// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "NativeAppState.h"
#import "NetworkManagerAndroid.h"

NetworkManagerAndroid::NetworkManagerAndroid(NativeAppState* state)
    : NetworkManager(state),
      state_(state),
      send_request_(state->jni_env(), "co/viewfinder/NetworkManager", "sendRequest") {
  // Always assume that we have a working wifi network connection.
  // TODO(marc): properly set using an android NetworkReceiver.
  network_wifi_ = true;
  network_reachable_ = true;

  state_->app_did_become_active()->Add([this]{
    dispatch_main([this]{
      if (state_->is_registered()) {
        AssetScanEnd();
      } else {
        Dispatch();
      }
    });
  });
}

NetworkManagerAndroid::~NetworkManagerAndroid() {
}

NetworkRequestImpl::NetworkRequestImpl(NetworkManager* net, NetworkRequest* req)
    // We access epoch_ directly to avoid the NetworkManager mutex.
    : epoch_(net->epoch_),
      net_(net),
      req_(req) { }

NetworkRequestImpl::~NetworkRequestImpl() {
  delete req_;
}

// TODO: handle redirect.

void NetworkRequestImpl::StartRequest() {
  net_->StartRequestLocked(req_->queue_type_);
}

void NetworkRequestImpl::Error(const string& error) {
  dispatch_network([this, error] {
    if (net_->epoch() == epoch_) {
      req_->HandleError(error);
    }
    net_->FinishRequest(false, epoch_, req_->queue_type_);
    delete this;
  });
}

void NetworkRequestImpl::Done(const string& data, int status_code) {
  dispatch_network([this, data, status_code] {
    // TODO: handle logout on 401.
    if (!data.empty()) {
      req_->HandleData(data);
    }
    bool success = false;
    if (net_->epoch() == epoch_) {
      success = req_->HandleDone(status_code);
      // TODO: handle backoff.
    }
    net_->FinishRequest(success, epoch_, req_->queue_type_);
    delete this;
  });
}

void NetworkRequestImpl::Redirect(const string& redirect_host) {
  net_->state()->set_server_host(redirect_host);
  // TODO(marc): call request->HandleRedirect and let it modify headers.
}

void NetworkManagerAndroid::ResetQueryNotificationsBackoff() {
  // TODO(peter): unimplemented.
}

bool NetworkManagerAndroid::ShouldClearApplicationBadge() {
  // TODO(peter): unimplemented. Does this apply on Android?
  return false;
}

void NetworkManagerAndroid::ClearApplicationBadge() {
  // TODO(peter): unimplemented. Does this apply on Android?
}

void NetworkManagerAndroid::Logout(bool clear_user_id) {
  NetworkManager::Logout(clear_user_id);
  // TODO(peter): Any Android-specific cleanup needed?
}

void NetworkManagerAndroid::UnlinkDevice() {
  NetworkManager::UnlinkDevice();
  // TODO(peter): Any Android-specific cleanup needed?
}

void NetworkManagerAndroid::SetIdleTimer() {
  // TODO(peter): unimplemented.
}

void NetworkManagerAndroid::AuthDone() {
  // TODO(peter): We don't have any asset scanning on Android yet. Just pretend
  // that the initial scan finished so that we can perform network refresh
  // operations.
  AssetScanEnd();
}

void NetworkManagerAndroid::SendRequest(
    NetworkRequest* req, const Slice& method, const Slice& body,
    const Slice& content_type, const Slice& content_md5,
    const Slice& if_none_match) {
  NetworkRequestImpl* impl = new NetworkRequestImpl(this, req);
  jlong req_ptr = CppToJavaPointer<NetworkRequestImpl>(state_->jni_env(), impl);
  impl->StartRequest();
  send_request_.Invoke(req_ptr, req->url(), method.as_string(), body.as_string(),
                       content_type.as_string(), content_md5.as_string(), if_none_match.as_string());
}

bool NetworkManagerAndroid::pause_non_interactive() const {
  // TODO(peter): Check that the app is active.
  return pause_non_interactive_count_ > 0;
}
