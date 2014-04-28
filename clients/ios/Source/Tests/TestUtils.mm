// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#import "AuthService.h"
#import "ContactManager.h"
#import "FileUtils.h"
#import "Format.h"
#import "PathUtils.h"
#import "PhotoSelection.h"
#import "PhotoStorage.h"
#import "TestUtils.h"

namespace {

const int kStartPort = 10000;
int port = kStartPort;

// Returns a monotonically increasing sequence of port numbers, starting
// at kStartPort.
int PickUnusedPort() {
  return port++;
}

}  // namespace

@interface TestAuthService : AuthService {
 @private
  bool loaded_;
}
@end  // TestAuthService

@implementation TestAuthService

- (NSString*)serviceName {
  return @"Test";
}

- (NSString*)primaryId {
  return NULL;
}

- (NSString*)accessToken {
  return @"test-access-token";
}

- (NSString*)refreshToken {
  return @"test-refresh-token";
}

- (NSDate*)expirationDate {
  return NULL;
}

- (bool)valid {
  return true;
}

- (void)load {
}

- (void)loadIfNecessary {
  if (!loaded_) {
    loaded_ = true;
    self.sessionChanged->Run();
  }
}

- (void)login:(UINavigationController*)navigation {
}

- (void)logout {
}

@end  // TestAuthService

// Starts an HTTP server on a [presumably] unused port.
HttpServer::HttpServer(int port)
    : port_(port == -1 ? PickUnusedPort() : port),
      web_dir_(JoinPath(dir_.dir(), "HttpServer")),
      ctx_(mg_start()) {
  mg_set_option(ctx_, "root", web_dir_.c_str());  // Set document root
  mg_set_option(ctx_, "ports", string(Format("127.0.0.1:%d", port_)).c_str());    // Listen on port XXXX
  mg_set_log_callback(ctx_, &HttpServer::LogCallback);
}

HttpServer::~HttpServer() {
  mg_stop(ctx_);
}

void HttpServer::SetHandler(const string& path, HttpCallback callback) {
  callback = [callback copy];
  callback_map_[path] = callback;
  mg_set_uri_callback(ctx_, path.c_str(), &HttpServer::URICallback, (__bridge void*)callback);
}

string HttpServer::DecompressedBody(const mg_connection* conn, const mg_request_info* info) {
  const string body(info->post_data, info->post_data_len);
  const char* const content_encoding = mg_get_header(conn, "Content-Encoding");
  if (content_encoding && strcmp(content_encoding , "gzip") == 0) {
    return GzipDecode(body);
  }
  return body;
}

void HttpServer::URICallback(mg_connection* conn, const mg_request_info* info, void* user_data) {
  HttpCallback callback = (__bridge HttpCallback)user_data;
  callback(conn, info);
}

void HttpServer::LogCallback(mg_connection* conn, const mg_request_info* info, void* user_data) {
  LOG("mongoose log: %s", (const char*)user_data);
}

DBHandle NewTestDB(const string& dir) {
  DBHandle db = NewDB(dir);
  CHECK(db->Open(1024 * 1024));
  return db;
}

TestUIAppState::TestUIAppState(const string& dir, const string& host, int port)
    : UIAppState(dir, host, port, false),
      now_(1) {
  facebook_ = [TestAuthService new];
  google_ = [TestAuthService new];
  device_uuid_ = "test-device-uuid";
  const InitAction init_action = GetInitAction();
  CHECK(Init(init_action));
  RunMaintenance(init_action);
}

TestUIAppState::~TestUIAppState() {
  net_manager()->Drain();
  Kill();
}

void TestUIAppState::UnlinkDevice() {
}

WallTime TestUIAppState::WallTime_Now() {
  return now_;
}

void TestUIAppState::AssetForKey(
    const string& key,
    ALAssetsLibraryAssetForURLResultBlock result,
    ALAssetsLibraryAccessFailureBlock failure) {
  DIE("unimplemented");
}

void TestUIAppState::AddAsset(
    NSData* data, NSDictionary* metadata,
    void(^done)(string asset_url, string asset_key)) {
  DIE("unimplemented");
}

void TestUIAppState::DeleteAsset(const string& key) {
  delete_asset_.Run(key);
}


BaseContentTest::BaseContentTest()
    : state_(dir()),
      has_location_(false),
      has_placemark_(false) {
}

BaseContentTest::~BaseContentTest() {
}

ViewpointHandle BaseContentTest::NewViewpoint() {
  DBHandle updates = state_.NewDBTransaction();
  ViewpointHandle h = viewpoint_table()->NewContent(updates);
  updates->Commit();
  return h;
}

void BaseContentTest::ClearLocation() {
  has_location_ = false;
  has_placemark_ = false;
}

void BaseContentTest::SetLocation(const Location& location) {
  has_location_ = true;
  location_.CopyFrom(location);
  has_placemark_ = false;
}

void BaseContentTest::SetLocation(const Location& location, const Placemark& placemark) {
  has_location_ = true;
  location_.CopyFrom(location);
  has_placemark_ = true;
  placemark_.CopyFrom(placemark);
}

void BaseContentTest::AddContact(const string& identity, int user_id,
                                 const string& first_name, const string& name) {
  QueryContactsResponse r;
  ContactMetadata* m = r.add_contacts();
  if (!identity.empty()) {
    m->set_primary_identity(identity);
    m->add_identities()->set_identity(identity);
  }
  if (user_id >= 0) {
    m->set_user_id(user_id);
  }
  if (!first_name.empty()) {
    m->set_first_name(first_name);
  }
  if (!name.empty()) {
    m->set_name(name);
  }
  ContactSelection cs;
  DBHandle updates = state_.NewDBTransaction();
  state_.contact_manager()->ProcessQueryContacts(r, cs, updates);
  updates->Commit();
}

ViewpointHandle BaseContentTest::LoadViewpoint(int64_t id) {
  return viewpoint_table()->LoadContent(id, state_.db());
}

ViewpointHandle BaseContentTest::LoadViewpoint(const string& server_id) {
  return viewpoint_table()->LoadContent(server_id, state_.db());
}

void BaseContentTest::SaveViewpoint(const ViewpointHandle& h) {
  DBHandle updates = state_.NewDBTransaction();
  h->SaveAndUnlock(updates);
  updates->Commit();
}

string BaseContentTest::ListFollowers(const ViewpointHandle& h) {
  vector<int64_t> follower_ids;
  h->ListFollowers(&follower_ids);
  return ToString(follower_ids);
}

ViewpointHandle BaseContentTest::AddFollowers(
    int64_t device_id, int64_t user_id, WallTime t, int64_t viewpoint_id,
    const vector<string>& contact_identities) {
  vector<ContactMetadata> contacts(contact_identities.size());
  for (int i = 0; i < contact_identities.size(); ++i) {
    contacts[i].set_primary_identity(contact_identities[i]);
    contacts[i].add_identities()->set_identity(contact_identities[i]);
  }
  state_.SetDeviceId(device_id);
  state_.SetUserId(user_id);
  state_.set_now(t);
  return viewpoint_table()->AddFollowers(viewpoint_id, contacts);
}

ViewpointHandle BaseContentTest::AddFollowersByIds(
    int64_t device_id, int64_t user_id, WallTime t, int64_t viewpoint_id,
    const vector<int64_t>& follower_ids) {
  vector<ContactMetadata> contacts(follower_ids.size());
  for (int i = 0; i < follower_ids.size(); ++i) {
    contacts[i].set_user_id(follower_ids[i]);
  }
  state_.SetDeviceId(device_id);
  state_.SetUserId(user_id);
  state_.set_now(t);
  return viewpoint_table()->AddFollowers(viewpoint_id, contacts);
}

ViewpointHandle BaseContentTest::PostComment(
    int64_t device_id, int64_t user_id, WallTime t,
    int64_t viewpoint_id, const string& message) {
  state_.SetDeviceId(device_id);
  state_.SetUserId(user_id);
  state_.set_now(t);
  return viewpoint_table()->PostComment(viewpoint_id, message, 0);
}

void BaseContentTest::SavePhotos(
    int64_t device_id, int64_t user_id, WallTime t,
    const PhotoSelectionVec& photo_ids) {
  state_.SetDeviceId(device_id);
  state_.SetUserId(user_id);
  state_.set_now(t);
  return viewpoint_table()->SavePhotos(photo_ids, 0);
}

ViewpointHandle BaseContentTest::ShareExisting(
    int64_t device_id, int64_t user_id, WallTime t, int64_t viewpoint_id,
    const PhotoSelectionVec& photo_ids) {
  state_.SetDeviceId(device_id);
  state_.SetUserId(user_id);
  state_.set_now(t);
  return viewpoint_table()->ShareExisting(viewpoint_id, photo_ids, false);
}

ViewpointHandle BaseContentTest::Unshare(
    int64_t device_id, int64_t user_id, WallTime t, int64_t viewpoint_id,
    const PhotoSelectionVec& photo_ids) {
  state_.SetDeviceId(device_id);
  state_.SetUserId(user_id);
  state_.set_now(t);
  return viewpoint_table()->Unshare(viewpoint_id, photo_ids);
}

ViewpointHandle BaseContentTest::ShareNew(
    int64_t device_id, int64_t user_id, WallTime t,
    const PhotoSelectionVec& photo_ids,
    const vector<int64_t>& contact_ids) {
  vector<ContactMetadata> contacts(contact_ids.size());
  for (int i = 0; i < contact_ids.size(); ++i) {
    contacts[i].set_user_id(contact_ids[i]);
  }
  state_.SetDeviceId(device_id);
  state_.SetUserId(user_id);
  state_.set_now(t);
  return viewpoint_table()->ShareNew(photo_ids, contacts, string(), false);
}

EpisodeHandle BaseContentTest::NewEpisode(int num_photos, WallTime timestamp) {
  if (timestamp == 0) {
    timestamp = state_.WallTime_Now();
  }
  DBHandle updates = state_.NewDBTransaction();
  EpisodeHandle eh = episode_table()->NewContent(updates);
  eh->Lock();
  eh->set_timestamp(timestamp);
  eh->set_user_id(state_.user_id());
  for (int i = 0; i < num_photos; ++i) {
    PhotoHandle ph = photo_table()->NewContent(updates);
    ph->Lock();
    ph->set_timestamp(timestamp + i);
    if (has_location_) {
      ph->mutable_location()->CopyFrom(location_);
    }
    if (has_placemark_) {
      ph->mutable_placemark()->CopyFrom(placemark_);
    }
    ph->SaveAndUnlock(updates);
    eh->AddPhoto(ph->id().local_id());
  }
  eh->SaveAndUnlock(updates);
  updates->Commit();
  return eh;
}

EpisodeHandle BaseContentTest::LoadEpisode(int64_t episode_id) {
  return episode_table()->LoadEpisode(episode_id, state_.db());
}

PhotoHandle BaseContentTest::LoadPhoto(int64_t photo_id) {
  return photo_table()->LoadPhoto(photo_id, state_.db());
}

ActivityHandle BaseContentTest::LoadActivity(int64_t activity_id) {
  return activity_table()->LoadActivity(activity_id, state_.db());
}

CommentHandle BaseContentTest::LoadComment(int64_t comment_id) {
  return comment_table()->LoadComment(comment_id, state_.db());
}

string BaseContentTest::ListPhotos(int64_t episode_id) {
  EpisodeHandle h = episode_table()->LoadEpisode(episode_id, state_.db());
  if (!h.get()) {
    return string();
  }
  vector<int64_t> photo_ids;
  h->ListPhotos(&photo_ids);
  return ToString(photo_ids);
}

string BaseContentTest::ListActivities(int64_t viewpoint_id) {
  ScopedPtr<ActivityTable::ActivityIterator> iter(
      activity_table()->NewViewpointActivityIterator(
          viewpoint_id, 0, false, state_.db()));
  vector<int64_t> activities;
  for (; !iter->done(); iter->Next()) {
    ActivityHandle a = iter->GetActivity();
    activities.push_back(a->activity_id().local_id());
  }
  return ToString(activities);
}

string BaseContentTest::ListNetworkQueue() {
  ScopedPtr<NetworkQueue::Iterator> iter(net_queue()->NewIterator());
  vector<string> v;
  for (; !iter->done(); iter->Next()) {
    if (iter->op().has_upload_activity()) {
      ActivityHandle a = LoadActivity(iter->op().upload_activity());
      CHECK(a.get());
      CHECK(a->has_queue());
      v.push_back(ToString(iter->op().upload_activity()));
    }
    if (iter->op().has_remove_photos()) {
      vector<pair<int64_t, int64_t> > r;
      for (int i = 0; i < iter->op().remove_photos().episodes_size(); ++i) {
        const ActivityMetadata::Episode& e =
            iter->op().remove_photos().episodes(i);
        for (int j = 0; j < e.photo_ids_size(); ++j) {
          r.push_back(std::make_pair(e.episode_id().local_id(),
                                     e.photo_ids(j).local_id()));
        }
      }
      v.push_back(ToString(r));
    }
  }
  return ToString(v);
}

void BaseContentTest::ClearNetworkQueue() {
  DBHandle updates = state_.NewDBTransaction();
  for (ScopedPtr<NetworkQueue::Iterator> iter(net_queue()->NewIterator());
       !iter->done();
       iter->Next()) {
    net_queue()->Remove(iter->priority(), iter->sequence(), iter->op(), updates);
  }
  updates->Commit();
}

void BaseContentTest::WriteLocalImage(const string& filename, const string& data) {
  DBHandle updates = state_.NewDBTransaction();
  CHECK(photo_storage()->Write(filename, 0, data, updates));
  updates->Commit();
}

string BaseContentTest::ListLocalImages() {
  vector<string> files;
  DirList(state_.photo_dir(), &files);
  for (vector<string>::iterator iter(files.begin()); iter != files.end(); ) {
    if (*iter == "tmp") {
      iter = files.erase(iter);
    } else {
      ++iter;
    }
  }
  std::sort(files.begin(), files.end());
  return ToString(files);
}

#endif  // TESTING

// local variables:
// mode: c++
// end:
