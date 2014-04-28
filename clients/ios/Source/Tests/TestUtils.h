// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_TESTS_TEST_UTILS_H
#define VIEWFINDER_TESTS_TEST_UTILS_H

#ifdef TESTING

#import <unordered_map>
#import <mongoose.h>
#import "ActivityTable.h"
#import "CommentTable.h"
#import "DB.h"
#import "EpisodeTable.h"
#import "NetworkManager.h"
#import "NetworkQueue.h"
#import "PhotoTable.h"
#import "Testing.h"
#import "UIAppState.h"
#import "ViewpointTable.h"

class HttpServer {
 public:
  typedef void (^HttpCallback)(mg_connection *, const mg_request_info *);
  typedef std::unordered_map<string, HttpCallback> HttpCallbackMap;

  // Start an HTTP server which by default serves nothing. Leave default port
  // to have one selected automatically.
  HttpServer(int port=-1);

  virtual ~HttpServer();

  // Registers 'callback' as the handler for requests arriving with URI
  // 'path'.
  void SetHandler(const string& path, HttpCallback callback);

  int port() const { return port_; }

  // Returns the request body, decompressing it if it was gzipped.
  static string DecompressedBody(const mg_connection* conn, const mg_request_info* info);

 private:
  static void URICallback(mg_connection* conn, const mg_request_info* info, void* user_data);
  static void LogCallback(mg_connection* conn, const mg_request_info* info, void* user_data);

 private:
  TestTmpDir dir_;
  const int port_;
  const string web_dir_;
  mg_context* ctx_;
  HttpCallbackMap callback_map_;
};

DBHandle NewTestDB(const string& dir);

class TestUIAppState : public UIAppState {
 public:
  TestUIAppState(const string& dir, const string& host = "", int port = -1);
  ~TestUIAppState();

  virtual void UnlinkDevice();
  virtual WallTime WallTime_Now();
  virtual void AssetForKey(
      const string& key,
      ALAssetsLibraryAssetForURLResultBlock result,
      ALAssetsLibraryAccessFailureBlock failure);
  virtual void AddAsset(NSData* data, NSDictionary* metadata,
                        void (^done)(string asset_url, string asset_key));
  virtual void DeleteAsset(const string& key);

  virtual AssetsManager* assets_manager() const { return NULL; }
  virtual LocationTracker* location_tracker() const { return NULL; }
  virtual RootViewController* root_view_controller() const { return NULL; }
  virtual bool app_active() const { return true; }
  virtual bool network_up() const { return net_manager()->network_up(); }

  virtual bool network_wifi() const {
    if (network_wifi_.get()) {
      return *network_wifi_;
    }
    return net_manager()->network_wifi();
  }
  void set_network_wifi(bool v) {
    network_wifi_.reset(new bool(v));
  }
  void clear_network_wifi() {
    network_wifi_.reset(NULL);
  }

  void set_now(WallTime now) { now_ = now; }

  typedef CallbackSet1<const string&> DeleteAssetCallback;
  DeleteAssetCallback* delete_asset() { return &delete_asset_; }

 private:
  WallTime now_;
  ScopedPtr<bool> network_wifi_;
  DeleteAssetCallback delete_asset_;
};

class BaseContentTest : public Test {
 public:
  BaseContentTest();
  virtual ~BaseContentTest();

  void ClearLocation();
  void SetLocation(const Location& location);
  void SetLocation(const Location& location, const Placemark& placemark);
  void AddContact(const string& identity, int user_id,
                  const string& first_name, const string& name);

  ViewpointHandle NewViewpoint();
  ViewpointHandle LoadViewpoint(int64_t id);
  ViewpointHandle LoadViewpoint(const string& server_id);
  void SaveViewpoint(const ViewpointHandle& h);
  string ListFollowers(const ViewpointHandle& h);

  ViewpointHandle AddFollowers(
      int64_t device_id, int64_t user_id, WallTime t, int64_t viewpoint_id,
      const vector<string>& contact_identities);
  ViewpointHandle AddFollowersByIds(
      int64_t device_id, int64_t user_id, WallTime t, int64_t viewpoint_id,
      const vector<int64_t>& follower_ids);
  ViewpointHandle PostComment(
      int64_t device_id, int64_t user_id, WallTime t,
      int64_t viewpoint_id, const string& message);
  void SavePhotos(
      int64_t device_id, int64_t user_id, WallTime t,
      const PhotoSelectionVec& photo_ids);
  ViewpointHandle ShareExisting(
      int64_t device_id, int64_t user_id, WallTime t, int64_t viewpoint_id,
      const PhotoSelectionVec& photo_ids);
  ViewpointHandle ShareNew(
      int64_t device_id, int64_t user_id, WallTime t,
      const PhotoSelectionVec& photo_ids,
      const vector<int64_t>& contact_ids);
  ViewpointHandle Unshare(
      int64_t device_id, int64_t user_id, WallTime t, int64_t viewpoint_id,
      const PhotoSelectionVec& photo_ids);
  // "t" == 0 uses state_->WallTime_Now().
  EpisodeHandle NewEpisode(int num_photos, WallTime t = 0);
  EpisodeHandle LoadEpisode(int64_t episode_id);
  PhotoHandle LoadPhoto(int64_t photo_id);
  ActivityHandle LoadActivity(int64_t activity_id);
  CommentHandle LoadComment(int64_t comment_id);
  string ListPhotos(int64_t episode_id);
  string ListActivities(int64_t viewpoint_id);
  string ListNetworkQueue();
  void ClearNetworkQueue();
  void WriteLocalImage(const string& filename, const string& data);
  string ListLocalImages();

  DBHandle db() const { return state_.db(); }
  ActivityTable* activity_table() const { return state_.activity_table(); }
  CommentTable* comment_table() const { return state_.comment_table(); }
  EpisodeTable* episode_table() const { return state_.episode_table(); }
  NetworkQueue* net_queue() const { return state_.net_queue(); }
  PhotoManager* photo_manager() const { return state_.photo_manager(); }
  PhotoStorage* photo_storage() const { return state_.photo_storage(); }
  PhotoTable* photo_table() const { return state_.photo_table(); }
  ViewpointTable* viewpoint_table() const { return state_.viewpoint_table(); }

 protected:
  TestUIAppState state_;
  bool has_location_;
  bool has_placemark_;
  Location location_;
  Placemark placemark_;
};

#endif  // TESTING

#endif  // VIEWFINDER_TESTS_TEST_UTILS_H
