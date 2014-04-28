// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <unordered_map>
#import <AssetsLibrary/AssetsLibrary.h>
#import "AppState.h"
#import "ScopedHandle.h"
#import "ScopedRef.h"

class AddressBookManager;
class PhotoDuplicateQueue;
class PhotoLoader;
class PhotoManager;
class SubscriptionManagerIOS;

@class AssetsManager;
@class AuthService;
@class LocationTracker;
@class PhotoView;
@class RootViewController;
@class UIViewController;

// A structure to hold the various bits of data discovered about a single asset
// during a scan.
struct AssetScanData {
  AssetScanData(ALAsset* a, const string& k, int i, CGImageRef st)
      : asset(a),
        asset_key(k),
        asset_index(i) {
    square_thumbnail.reset(st);
  }
  ALAsset* const asset;
  const string asset_key;
  const int asset_index;
  ScopedRef<CGImageRef> square_thumbnail;
};

typedef CallbackSet1<const StringSet*> AssetScanEnd;
typedef CallbackSet1<const AssetScanData&> AssetScanProgress;
typedef CallbackSet1<NSURL*> OpenURL;
typedef CallbackSet1<NSData*> APNDeviceTokenCallback;
typedef std::unordered_map<int64_t, vector<PhotoView*> > PhotoViewMap;

enum ViewState {
  STATE_NOT_REGISTERED,
  STATE_RESET_DEVICE_ID,
  STATE_ACCOUNT_SETUP,
  STATE_PHOTO_NOT_AUTHORIZED,
  STATE_OK,
};

class UIAppState : public AppState {
 public:
  UIAppState(const string& dir, const string& server_host,
             int server_port, bool production);
  virtual ~UIAppState();

  virtual InitAction GetInitAction();
  virtual bool Init(InitAction init_action);
  virtual void RunMaintenance(InitAction init_action);

  virtual void ProcessPhotoDuplicateQueue();
  virtual void LoadViewfinderImages(int64_t photo_id, const DBHandle& db,
                                    Callback<void (bool)> completion);
  virtual int TimeZoneOffset(WallTime t) const;

  // Notify the UIAppState that the app crashed.
  void ReportAppCrashed();

  void Vibrate(int count = 1);

  static void ShowNotRegisteredAlert();
  static void ShowNetworkDownAlert();
  static void ShowInvalidEmailAlert(const string& address, const string& error);

  void SendFeedback(UIViewController* parent);

  virtual void SetupViewpointTransition(int64_t viewpoint_id, const DBHandle& updates);
  virtual bool CloudStorageEnabled();

  virtual void UnlinkDevice() = 0;

  virtual void AssetForKey(const string& key,
                           ALAssetsLibraryAssetForURLResultBlock result,
                           ALAssetsLibraryAccessFailureBlock failure) = 0;
  virtual void AddAsset(NSData* data, NSDictionary* metadata,
                        void (^done)(string asset_url, string asset_key)) = 0;

  // Returns the desired frame for the view controller.
  CGRect ControllerFrame(UIViewController* vc);

  // Simulate logging out, showing the signup/login screen on the dashboard.
  void FakeLogout();
  // Simulate logging in.
  void FakeLogin();
  // Simulate maintenance.
  void FakeMaintenance();
  // Simulate assets authorization not determined.
  void FakeAssetsAuthorizationDetermined();
  // Simulate assets not authorized.
  void FakeAssetsNotAuthorized();
  // Simulate fake zero state.
  void FakeZeroState();
  // Fake a 401 status code on the next request.
  void Fake401();

  virtual AssetsManager* assets_manager() const = 0;
  virtual LocationTracker* location_tracker() const = 0;
  virtual RootViewController* root_view_controller() const = 0;
  virtual bool app_active() const = 0;
  virtual bool network_up() const = 0;

  AddressBookManager* address_book_manager() { return address_book_manager_.get(); }
  AuthService* facebook() const { return facebook_; }
  AuthService* google() const { return google_; }
  PhotoDuplicateQueue* photo_duplicate_queue() const { return photo_duplicate_queue_.get(); }
  PhotoLoader* photo_loader() const { return photo_loader_.get(); }
  PhotoManager* photo_manager() const { return photo_manager_.get(); }
  PhotoViewMap* photo_view_map() const { return photo_view_map_.get(); }
  virtual SubscriptionManager* subscription_manager() const {
    // It really is a SubscriptionManager, but we haven't included the headers
    // which indicate that.
    return reinterpret_cast<SubscriptionManager*>(subscription_manager_ios_.get());
  }
  SubscriptionManagerIOS* subscription_manager_ios() const { return subscription_manager_ios_.get(); }

  float screen_width() const { return screen_width_; }
  float screen_height() const { return screen_height_; }
  float status_bar_height() const { return status_bar_height_; }

  virtual string timezone() const {
    return ToString(system_tz_.name);
  }

  ViewState view_state();

  virtual bool assets_authorized() const;
  bool assets_authorization_determined() const;
  bool assets_full_scan() const;
  bool assets_initial_scan() const;
  virtual bool assets_scanning() const;

  bool battery_charging() const;
  float battery_level() const;
  bool ui_application_active() const;
  bool ui_application_background() const;
  string ui_application_state() const;
  int remote_notification_types() const;

  bool show_update_notification(const string& version) const;
  void set_show_update_notification(bool v);

  WallTime compose_last_used() const;
  void set_compose_last_used(WallTime timestamp);

  APNDeviceTokenCallback* apn_device_token() { return &apn_device_token_; }
  CallbackSet* assets_changed() { return &assets_changed_; }
  AssetScanEnd* assets_scan_end() { return &assets_scan_end_; }
  CallbackSet* assets_scan_group() { return &assets_scan_group_; }
  AssetScanProgress* assets_scan_progress() { return &assets_scan_progress_; }
  CallbackSet* assets_scan_start() { return &assets_scan_start_; }
  OpenURL* open_url() { return &open_url_; }

  bool fake_logout() const { return fake_logout_; }
  bool fake_zero_state() const { return fake_zero_state_; }

 protected:
  virtual void InitVars();
  virtual DayTableEnv* NewDayTableEnv();
  virtual void Clean(const string& dir);
  virtual bool MaybeMigrate(ProgressUpdateBlock progress_update);

 protected:
  const string crashed_path_;
  string update_notification_;
  APNDeviceTokenCallback apn_device_token_;
  CallbackSet assets_changed_;
  AssetScanEnd assets_scan_end_;
  CallbackSet assets_scan_group_;
  AssetScanProgress assets_scan_progress_;
  CallbackSet assets_scan_start_;
  OpenURL open_url_;
  ScopedPtr<AddressBookManager> address_book_manager_;
  ScopedPtr<PhotoDuplicateQueue> photo_duplicate_queue_;
  ScopedPtr<PhotoLoader> photo_loader_;
  ScopedPtr<PhotoManager> photo_manager_;
  ScopedPtr<PhotoViewMap> photo_view_map_;
  ScopedPtr<SubscriptionManagerIOS> subscription_manager_ios_;
  AuthService* facebook_;
  AuthService* google_;
  NSTimeZone* system_tz_;
  float screen_width_;
  float screen_height_;
  float status_bar_height_;
  int log_fatal_callback_id_;
  WallTime compose_last_used_;
  bool fake_zero_state_;
  bool fake_assets_authorization_determined_;
  bool fake_assets_not_authorized_;
};

class ProdUIAppState : public UIAppState {
 public:
  ProdUIAppState();
  ~ProdUIAppState();

  virtual bool Init(InitAction init_action);
  virtual void UnlinkDevice();

  virtual void AssetForKey(const string& key,
                           ALAssetsLibraryAssetForURLResultBlock result,
                           ALAssetsLibraryAccessFailureBlock failure);
  virtual void AddAsset(NSData* data, NSDictionary* metadata,
                        void(^done)(string asset_url, string asset_key));
  virtual void DeleteAsset(const string& key);

  AssetsManager* assets_manager() const { return assets_manager_; }
  LocationTracker* location_tracker() const { return location_tracker_; }
  RootViewController* root_view_controller() const { return root_view_controller_; }
  bool app_active() const;
  bool network_up() const;
  bool network_wifi() const;

 protected:
  void InitServices();
  void InitDeviceUUID();

 private:
  AssetsManager* assets_manager_;
  LocationTracker* location_tracker_;
  RootViewController* root_view_controller_;
  int log_rotate_callback_id_;
};

// local variables:
// mode: c++-mode
// end:
