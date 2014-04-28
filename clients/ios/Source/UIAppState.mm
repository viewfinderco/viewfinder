// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <AudioToolbox/AudioToolbox.h>
#import <ImageIO/CGImageSource.h>
#import <MessageUI/MessageUI.h>
#import <sys/sysctl.h>
#import "AddressBookManager.h"
#import "Analytics.h"
#import "AppDelegate.h"
#import "AssetsManager.h"
#import "AsyncState.h"
#import "ContactManager.h"
#import "CppDelegate.h"
#import "DayTableEnv.h"
#import "DB.h"
#import "DBMigrationIOS.h"
#import "DebugUtils.h"
#import "Defines.h"
#import "FacebookService.h"
#import "FileUtils.h"
#import "GeocodeManager.h"
#import "GoogleService.h"
#import "ImageIndex.h"
#import "KeychainUtils.h"
#import "LazyStaticPtr.h"
#import "LocationTracker.h"
#import "Logging.h"
#import "NetworkManagerIOS.h"
#import "NetworkQueue.h"
#import "NotificationManager.h"
#import "PathUtils.h"
#import "PeopleRank.h"
#import "PhotoDuplicateQueue.h"
#import "PhotoLoader.h"
#import "PhotoManager.h"
#import "PhotoStorage.h"
#import "PhotoView.h"
#import "PlacemarkHistogram.h"
#import "PlacemarkTable.h"
#import "RootViewController.h"
#import "StatusBar.h"
#import "SubscriptionManagerIOS.h"
#import "Timer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIViewController+viewfinder.h"
#import "ValueUtils.h"
#import "WallTime.h"

namespace {

#if defined(PRODUCTION)

#ifndef HOST
#define HOST "www.viewfinder.co"
#endif  // HOST

#ifndef PORT
#define PORT 443
#endif  // PORT

NSString* const kFacebookAppId =
    @"260133567413905";
NSString* const kGoogleClientId =
    @"245859189621-fk59e4ieqle47lh2lkjilcspe93fvnve.apps.googleusercontent.com";
NSString* const kGoogleClientSecret =
    @"7ozTfcFORIOnnXxEjadJBIyP";

#else  // !defined(PRODUCTION)

// Generating a certificate can be done via:
// http://www.akadia.com/services/ssh_test_certificate.html
#ifndef HOST
#define HOST "www.goviewfinder.com"
#endif  // HOST

#ifndef PORT
#define PORT 8443
#endif  // PORT

NSString* const kFacebookAppId =
    @"177219665705543";
NSString* const kGoogleClientId =
    @"541211715268.apps.googleusercontent.com";
NSString* const kGoogleClientSecret =
    @"GsA6ho0ZLPeHRV7vh0_4GBeo";

#endif  // !defined(PRODUCTION)

const string kHost = HOST;
const int kPort = PORT;

const string kInitMaintenanceKey = DBFormat::metadata_key("init_maintenance");
const string kUpdateNotificationKey = DBFormat::metadata_key("update_notification");
const string kComposeLastUsedKey = DBFormat::metadata_key("compose_last_used");

// Database commit trigger key.
const string kViewpointTransitionTriggerKey = "viewpoint_transition";

// UUID generated the first time the app is run. Not to be confused with the
// server-generated device id stored in kDeviceIdKey.
NSString* const kCrashCountKey = @"co.viewfinder.Viewfinder.crash_count";

#ifdef DEVELOPMENT
// Disable app resets for development builds.
const int kMaxCrashesBeforeFSCK = 2;
const int kMaxCrashesBeforeReset = 1000000;
#else  // !DEVELOPMENT
const int kMaxCrashesBeforeFSCK = 2;
const int kMaxCrashesBeforeReset = 5;
#endif // !DEVELOPMENT

void DeleteOld(const string& old_dir) {
  int files = 0;
  int dirs = 0;
  if (DirRemove(old_dir, true, &files, &dirs)) {
    LOG("%s: removed %d files, %d dirs", old_dir, files, dirs);
  }
}

void ClearCrashed() {
  // Remove the crash count key after the app has successfully run for 30
  // seconds.
  dispatch_after_main(30, ^{
      NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
      [defaults removeObjectForKey:kCrashCountKey];
      [defaults synchronize];
    });
}

string SendFeedbackResultString(MFMailComposeResult result) {
  switch (result) {
    case MFMailComposeResultCancelled: return "cancelled";
    case MFMailComposeResultSaved:     return "saved";
    case MFMailComposeResultSent:      return "sent";
    case MFMailComposeResultFailed:    return "failed";
  }
  return Format("unknown result: %d", result);
}

string SysctlByName(const string& name) {
  size_t size;
  sysctlbyname(name.c_str(), NULL, &size, NULL, 0);
  char* buf = new char[size];
  sysctlbyname(name.c_str(), buf, &size, NULL, 0);
  const string value(buf);
  delete[] buf;
  return value;
}

string DeviceModel() {
  const string machine_str(SysctlByName("hw.machine"));
  const Slice machine(machine_str);

  // The ever mysterious iFPGA
  if (machine == "iFPGA")              return "iFPGA";

  // iPhone
  if (machine == "iPhone1,1")          return "iPhone 1G";
  if (machine == "iPhone1,2")          return "iPhone 3G";
  if (machine.starts_with("iPhone2"))  return "iPhone 3GS";
  if (machine.starts_with("iPhone3"))  return "iPhone 4";
  if (machine.starts_with("iPhone4"))  return "iPhone 4s";
  if (machine.starts_with("iPhone5"))  return "iPhone 5";
  if (machine.starts_with("iPhone6"))  return "iPhone 5s";
  if (machine.starts_with("iPhone"))   return "Unknown iPhone";

  // iPod
  if (machine.starts_with("iPod1"))    return "iPod touch 1G";
  if (machine.starts_with("iPod2"))    return "iPod touch 2G";
  if (machine.starts_with("iPod3"))    return "iPod touch 3G";
  if (machine.starts_with("iPod4"))    return "iPod touch 4G";
  if (machine.starts_with("iPod5"))    return "iPod touch 5G";
  if (machine.starts_with("iPod"))     return "Unknown iPod";

  // iPad
  if (machine.starts_with("iPad1"))    return "iPad 1G";
  if (machine.starts_with("iPad2"))    return "iPad 2G";
  if (machine.starts_with("iPad3"))    return "iPad 3G";
  if (machine.starts_with("iPad4"))    return "iPad 4G";
  if (machine.starts_with("iPad"))     return "Unknown iPad";

  // Apple TV
  if (machine.starts_with("AppleTV2"))  return "Apple TV 2G";
  if (machine.starts_with("AppleTV3"))  return "Apple TV 3G";
  if (machine.starts_with("AppleTV"))   return "Unknown Apple TV";

  // Simulator thanks Jordan Breeding
  if (machine.ends_with("86") || machine == "x86_64") {
    if ([[UIScreen mainScreen] bounds].size.width < 768) {
      return "iPhone Simulator";
    }
    return "iPad Simulator";
  }

  return Format("Unknown iOS device: %s", machine);
}

string DeviceName() {
  return ToString([UIDevice currentDevice].name);
}

string DeviceOS() {
  UIDevice* d = [UIDevice currentDevice];
  return Format("%s %s", d.systemName, d.systemVersion);
}

void MarkPhotosForDownload(AppState* state) {
  state->async()->dispatch_background(^{
      WallTimer timer;
      DBHandle updates = state->NewDBTransaction();
      int marked = 0;
      for (DB::PrefixIterator iter(updates, DBFormat::photo_key());
           iter.Valid();
           iter.Next()) {
        const Slice value = iter.value();
        PhotoMetadata p;
        if (!p.ParseFromArray(value.data(), value.size())) {
          continue;
        }
        if (!p.has_images() || (p.asset_keys_size() > 0)) {
          // The photo has not been uploaded or is backed by an asset.
          continue;
        }
        const bool thumbnail_exists =
            (state->photo_storage()->Size(PhotoThumbnailFilename(p.id())) > 0);
        const bool full_exists =
            (state->photo_storage()->Size(PhotoFullFilename(p.id())) > 0);
        if ((thumbnail_exists || p.download_thumbnail()) &&
            (full_exists || p.download_full())) {
          continue;
        }

        PhotoHandle ph = state->photo_table()->LoadPhoto(p.id().local_id(), updates);
        ph->Lock();
        if (!thumbnail_exists) {
          ph->set_download_thumbnail(true);
        }
        if (!full_exists) {
          ph->set_download_full(true);
        }
        ph->SaveAndUnlock(updates);

        ++marked;
      }
      updates->Commit();
      LOG("marked %d photo%s for download: %.1f sec",
          marked, Pluralize(marked), timer.Get());
    });
}

// void DumpCurve(const string& filename) {
//   const string path = MainBundlePath(filename);
//   ScopedRef<CGImageSourceRef> cg_image_source(
//       CGImageSourceCreateWithURL(URLForPath(path), NULL));
//   if (!cg_image_source) {
//     LOG("unable to load texture: %s", filename);
//     return;
//   }
//   if (CGImageSourceGetCount(cg_image_source) < 1) {
//     LOG("%s: no images found", filename);
//     return;
//   }

//   ScopedRef<CGImageRef> cg_image(
//       CGImageSourceCreateImageAtIndex(cg_image_source, 0, NULL));
//   if (!cg_image) {
//     LOG("%s: unable to create CGImage", filename);
//     return;
//   }

//   CGColorSpaceModel colorspace =
//       CGColorSpaceGetModel(CGImageGetColorSpace(cg_image));
//   if (colorspace != kCGColorSpaceModelRGB) {
//     LOG("%s: unsupported color space: %d", colorspace);
//     return;
//   }
//   const size_t bpp = CGImageGetBitsPerPixel(cg_image);
//   if (bpp < 8 || bpp > 32) {
//     LOG("%s: unsupported bits-per-pixel: %d", bpp);
//     return;
//   }

//   // Get a pointer to the uncompressed image data.
//   ScopedRef<CFDataRef> data(
//       CGDataProviderCopyData(CGImageGetDataProvider(cg_image)));
//   if (!data) {
//     LOG("%s: unable to retrieve pixel data");
//     return;
//   }
//   const uint8_t* pixels = (const uint8_t*)CFDataGetBytePtr(data);
//   if (!pixels) {
//     LOG("%s: unable to retrieve pixel data");
//     return;
//   }

//   const int width = CGImageGetWidth(cg_image);
//   for (int channel = 0; channel < 3; ++channel) {
//     for (int x = 0; x < width; ++x) {
//       if (x != int(pixels[x * (bpp >> 3) + channel])) {
//         LOG("%s: %d: %3d != %3d", filename, channel,
//             x, int(pixels[x * (bpp >> 3) + channel]));
//       }
//     }
//   }
// }

}  // namespace

UIAppState::UIAppState(
    const string& base_dir, const string& server_host,
    int server_port, bool production)
    : AppState(base_dir, server_host, server_port, production),
      crashed_path_(JoinPath(library_dir_, "crashed")),
      log_fatal_callback_id_(0),
      fake_zero_state_(false),
      fake_assets_authorization_determined_(false),
      fake_assets_not_authorized_(false) {
  [NSTimeZone resetSystemTimeZone];
  system_tz_ = [NSTimeZone systemTimeZone];
  screen_width_ = [UIScreen mainScreen].bounds.size.width;
  screen_height_ = [UIScreen mainScreen].bounds.size.height;
  status_bar_height_ = NormalStatusBarFrame().size.height;

  device_model_ = DeviceModel();
  device_name_ = DeviceName();
  device_os_ = DeviceOS();

  NSLocale* locale = [NSLocale currentLocale];
  locale_language_ = ToString([locale objectForKey:NSLocaleLanguageCode]);
  locale_country_ = ToString([locale objectForKey:NSLocaleCountryCode]);

  NSString* test_udid = [AppDelegate uniqueIdentifier];
  if (test_udid) {
    test_udid_ = ToString(test_udid);
  }
}

UIAppState::~UIAppState() {
  if (log_fatal_callback_id_) {
    Logging::RemoveLogFatal(log_fatal_callback_id_);
  }
  // Delete the async state first. This will block until all of the running
  // async operations have completed.
  Kill();
}

AppState::InitAction UIAppState::GetInitAction() {
  // Check for the existence of the "crashed" file indicating that the previous
  // instance of the app crashed. We perform this check here so that the
  // PLCrashReporter processing in [AppDelegate initCrashReporter] can create
  // the "crashed" file if it found a crash.
  NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
  if (!FileExists(crashed_path_)) {
    // We did not crash on the previous run. Clear the crash count.
    [defaults removeObjectForKey:kCrashCountKey];
    [defaults synchronize];
#ifdef FORCE_FSCK
    return INIT_FSCK;
#endif  // FORCE_FSCK
    return INIT_NORMAL;
  }

  // We crashed on the previous run. Bump the crash count number.
  const int crash_count = 1 + [defaults integerForKey:kCrashCountKey];
  LOG("app: crash count: %d", crash_count);
  [defaults setInteger:crash_count forKey:kCrashCountKey];
  [defaults synchronize];
  FileRemove(crashed_path_);

  if (crash_count < kMaxCrashesBeforeFSCK) {
    return INIT_NORMAL;
  }

  if (crash_count < kMaxCrashesBeforeReset) {
    // Force an FSCK.
    return INIT_FSCK;
  }

  // We've crashed too many times in a row. Force a full reset.
  UIAlertView* a =
      [[UIAlertView alloc]
            initWithTitle:@"Son Of A…"
                  message:
          @"I've experienced a major malfunction and need to reset. "
          @"This may take some time. Don't worry, your photos will still "
          @"be here!"
                 delegate:NULL
        cancelButtonTitle:@"OK"
        otherButtonTitles:NULL];
  [a show];
  return INIT_RESET;
}

bool UIAppState::Init(InitAction init_action) {
  // Add a callback to create the "crashed" file whenever a DIE or CHECK is
  // encountered.
  log_fatal_callback_id_ = Logging::AddLogFatal([this] {
      ReportAppCrashed();
    });

  if (production_ && !DirExists(database_dir_)) {
    // The iOS keychain is not cleared when an app is deleted which allows the
    // google auth credentials to persist across app installations. This is
    // unexpected, so we explicitly clear the keychain when we discover a new
    // app install.
    // ListKeychain();
    ClearKeychain();
  } else {
#ifdef CLEAR_KEYCHAIN
    ClearKeychain();
#endif  // CLEAR_KEYCHAIN
  }

  if (!AppState::Init(init_action)) {
    return false;
  }

  WallTimer timer;
  address_book_manager_.reset(new AddressBookManager(this));
  VLOG("init: address book manager: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  net_manager_.reset(new NetworkManagerIOS(this));
  VLOG("init: network manager: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  photo_duplicate_queue_.reset(new PhotoDuplicateQueue(this));
  VLOG("init: photo duplicate queue: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  photo_loader_.reset(new PhotoLoader(this));
  VLOG("init: photo loader: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  photo_manager_.reset(new PhotoManager(this));
  VLOG("init: photo manager: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  photo_view_map_.reset(new PhotoViewMap);

  subscription_manager_ios_.reset(new SubscriptionManagerIOS(this));
  VLOG("init: subscription manager: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  // If we are registered, but need a device id reset, log user out.
  if (is_registered() && NeedDeviceIdReset()) {
    [[[UIAlertView alloc]
      initWithTitle:@"New Mobile Device"
            message:@"It looks like you've changed devices. Log in again for account security."
           delegate:NULL
       cancelButtonTitle:@"OK"
       otherButtonTitles:NULL] show];
    net_manager_->Logout(false /* don't clear user id */);
    MarkPhotosForDownload(this);
  }

  app_did_become_active()->Add(^{
      DBHandle updates = NewDBTransaction();
      notification_manager_->Invalidate(updates);
      updates->Commit();
      net_manager_->ResetBackoff();
      net_manager_->Dispatch();
    });

  return true;
}

void UIAppState::RunMaintenance(InitAction init_action) {
  AppState::RunMaintenance(init_action);

  WallTimer timer;
  ClearCrashed();
  VLOG("init: clear crashed: %0.3f ms", timer.Milliseconds());
}

void UIAppState::ProcessPhotoDuplicateQueue() {
  photo_duplicate_queue_->MaybeProcess();
}

void UIAppState::LoadViewfinderImages(
    int64_t photo_id, const DBHandle& db, Callback<void (bool)> completion) {
  photo_manager_->LoadViewfinderImages(
      photo_id, db, ^(bool success) { completion(success); });
}

int UIAppState::TimeZoneOffset(WallTime t) const {
  NSDate* date = [NSDate dateWithTimeIntervalSince1970:t];
  return [system_tz_ secondsFromGMTForDate:date];
}

void UIAppState::ReportAppCrashed() {
  // Create the "crashed" file.
  const int fd = open(crashed_path_.c_str(), O_CREAT|O_WRONLY, 0644);
  if (fd >= 0) {
    close(fd);
  }
}

void UIAppState::Vibrate(int count) {
  if (count <= 0) {
    return;
  }
  AudioServicesPlaySystemSound(kSystemSoundID_Vibrate);
  for (int i = 1; i < count; ++i) {
    dispatch_after_main(0.5 * count, ^{
        AudioServicesPlaySystemSound(kSystemSoundID_Vibrate);
      });
  }
}

void UIAppState::ShowNotRegisteredAlert() {
  // NOTE(peter): This shouldn't happen anymore since we force sign-up/login
  // before the sharing code paths are reached.
  DCHECK(false);
  [[[UIAlertView alloc]
     initWithTitle:@"Who Are You?"
           message:
       @"You need to sign-up or login before sharing."
          delegate:NULL
     cancelButtonTitle:@"OK"
     otherButtonTitles:NULL] show];
}

void UIAppState::ShowNetworkDownAlert() {
  [[[UIAlertView alloc]
     initWithTitle:@"Yikes."
           message:
       @"The network is currently unavailable. Check your iPhone's network "
     @"settings or move out of that cave you're hiding in."
          delegate:NULL
     cancelButtonTitle:@"OK"
     otherButtonTitles:NULL] show];
}

void UIAppState::ShowInvalidEmailAlert(const string& address, const string& error) {
  NSString* full_error;
  if (error.empty()) {
    full_error = Format("Come on…\"%s\"? Even five-year-olds know what "
                        "an email address looks like, and that isn't one.",
                        address);
  } else {
    full_error = Format("\"%s\" is not a valid email address. %s",
                        address, error);
  }
  [[[UIAlertView alloc]
    initWithTitle:@"That's Not A Valid Email"
          message:full_error
         delegate:NULL
     cancelButtonTitle:@"Let me fix that…"
     otherButtonTitles:NULL] show];
}

void UIAppState::SendFeedback(UIViewController* parent) {
  if (![MFMailComposeViewController canSendMail]) {
    [[[UIAlertView alloc]
           initWithTitle:@"Yikes."
                 message:
         @"This device is not configured to send email."
                delegate:NULL
       cancelButtonTitle:@"OK"
       otherButtonTitles:NULL] show];
    return;
  }

  CppDelegate* cpp_delegate = new CppDelegate;
  cpp_delegate->Add(
      @protocol(MFMailComposeViewControllerDelegate),
      @selector(mailComposeController:didFinishWithResult:error:),
      ^(MFMailComposeViewController* controller,
        MFMailComposeResult result,
        NSError* error) {
        controller.delegate = NULL;
        delete cpp_delegate;
        VLOG("send feedback: %s: %s", SendFeedbackResultString(result), error);
        analytics_->SendFeedback(result);
        [controller
            dismissViewControllerAnimated:YES
                               completion:NULL];
      });

  MFMailComposeViewController* composer = [MFMailComposeViewController new];
  composer.mailComposeDelegate = cpp_delegate->delegate();
  composer.subject = Format("Viewfinder %s (iOS %s)", AppVersion(), kIOSVersion);
  composer.toRecipients = Array("support@emailscrubbed.com");

  [parent presentViewController:composer
                       animated:YES
                     completion:NULL];
}

void UIAppState::SetupViewpointTransition(
    int64_t viewpoint_id, const DBHandle& updates) {
  updates->AddCommitTrigger(kViewpointTransitionTriggerKey, ^{
      __block int id = day_table()->update()->Add(^{
          // Look for viewpoint id in the conversations summary &
          // transition when found.
          int epoch;
          DayTable::SnapshotHandle snap = day_table()->GetSnapshot(&epoch);
          const int row_index = snap->conversations()->GetViewpointRowIndex(viewpoint_id);
          if (row_index != -1) {
            day_table()->update()->Remove(id);
            async()->dispatch_after_main(0, ^{
                ControllerState new_controller_state;
                new_controller_state.current_viewpoint = viewpoint_id;
                new_controller_state.pending_viewpoint = true;
                [root_view_controller() showConversation:new_controller_state];
              });
          }
        });
    });
}

void UIAppState::InitVars() {
  AppState::InitVars();

  if (is_registered()) {
    update_notification_ = db_->Get<string>(kUpdateNotificationKey);
  } else {
    set_show_update_notification(true);
  }
  compose_last_used_ =
      db_->Get<WallTime>(kComposeLastUsedKey, WallTime_Now());
}

DayTableEnv* UIAppState::NewDayTableEnv() {
  return NewDayTableIOSEnv(this);
}

void UIAppState::Clean(const string& dir) {
  AppState::Clean(dir);
  NetworkManagerIOS::Clean();
}

bool UIAppState::MaybeMigrate(ProgressUpdateBlock progress_update) {
  DBMigrationIOS migration(this, progress_update);
  return migration.MaybeMigrate();
}

CGRect UIAppState::ControllerFrame(UIViewController* vc) {
  const CGRect screen_bounds = [UIScreen mainScreen].bounds;
  CGRect f = vc.parentViewController ?
      vc.parentViewController.view.bounds :
      screen_bounds;
  // In iOS 6, the root view controller does not set wantsFullScreenLayout but we set
  // its frame to the screen bounds.  We need to add a status bar inset for any
  // non-full-screen child controllers.
  //
  // In iOS 7, the root view controller's bounds overlap with the bottom 20 points of
  // the status bar (i.e. with a normal-size status bar the root view covers the entire
  // screen, but with a double-size (40 point) status bar the root view is inset by 20 points
  // (so half of the status bar overlaps the content's coordinate system).
  // Since we do not modify the root view controller's frame on iOS 7, we can treat it as always
  // fullscreen (and applying this adjustment to the only the direct descendants of the root
  // appears to do the right thing).
  const bool parent_is_fullscreen = (kSDKVersion < "7" || kIOSVersion < "7") ?
                                    CGRectEqualToRect(f, screen_bounds) :
                                    (vc.parentViewController == root_view_controller());

  if (!vc.wantsFullScreenLayout && parent_is_fullscreen) {
    // The view controller does not want full screen layout and its parent view
    // controller bounds cover the full screen.
    f.origin.y += status_bar_height_;
    f.size.height -= status_bar_height_;
  }
  return f;
}

void UIAppState::FakeLogout() {
  dispatch_main(^{
      LOG("fake logout");
      fake_logout_ = true;
      settings_changed_.Run(true);

      dispatch_after_low_priority(0.5, ^{
          maintenance_done_.Run(false);
        });
    });
}

void UIAppState::FakeLogin() {
  dispatch_main(^{
      LOG("fake login");
      fake_logout_ = false;
      settings_changed_.Run(true);
    });
}

void UIAppState::FakeMaintenance() {
  dispatch_main(^{
      LOG("fake maintenance");
      fake_logout_ = true;
      settings_changed_.Run(true);

      dispatch_after_low_priority(0.5, ^{
          maintenance_progress_.Run("Fake Maintenance");
          sleep(3);
          fake_logout_ = false;
          dispatch_main(^{
              settings_changed_.Run(true);
            });
          maintenance_done_.Run(false);
        });
    });
}

void UIAppState::FakeAssetsAuthorizationDetermined() {
  fake_assets_authorization_determined_ = !fake_assets_authorization_determined_;
  [root_view_controller() showSummaryLayout:ControllerTransition()];
}

void UIAppState::FakeAssetsNotAuthorized() {
  fake_assets_not_authorized_ = !fake_assets_not_authorized_;
  [root_view_controller() showSummaryLayout:ControllerTransition()];
}

void UIAppState::FakeZeroState() {
  fake_zero_state_ = !fake_zero_state_;
}

void UIAppState::Fake401() {
  net_manager()->set_fake_401(true);
}

ViewState UIAppState::view_state() {
  if (!is_registered()) {
    return STATE_NOT_REGISTERED;
  } else if (NeedDeviceIdReset()) {
    return STATE_RESET_DEVICE_ID;
  } else if (assets_authorization_determined() && !assets_authorized()) {
    return STATE_PHOTO_NOT_AUTHORIZED;
  } else if (account_setup()) {
    return STATE_ACCOUNT_SETUP;
  }
  return STATE_OK;
}

bool UIAppState::assets_authorized() const {
  if (fake_assets_not_authorized_) {
    return false;
  }
  AssetsManager* a = assets_manager();
  if (!a) {
    return true;
  }
  return a.authorized;
}

bool UIAppState::assets_authorization_determined() const {
  if (fake_assets_not_authorized_) {
    return true;
  }
  if (fake_assets_authorization_determined_) {
    return false;
  }
  AssetsManager* a = assets_manager();
  if (!a) {
    return true;
  }
  return a.authorizationDetermined;
}

bool UIAppState::assets_full_scan() const {
  AssetsManager* a = assets_manager();
  return a.fullScan;
}

bool UIAppState::assets_initial_scan() const {
  AssetsManager* a = assets_manager();
  return a.initialScan;
}

bool UIAppState::assets_scanning() const {
  return assets_manager().scanning;
}

bool UIAppState::battery_charging() const {
  switch ([[UIDevice currentDevice] batteryState]) {
    case UIDeviceBatteryStateCharging:
    case UIDeviceBatteryStateFull:
      return true;
    default:
      break;
  }
  return false;
}

float UIAppState::battery_level() const {
#if (TARGET_IPHONE_SIMULATOR)
  return 1.0;
#else // !(TARGET_IPHONE_SIMULATOR)
  return [[UIDevice currentDevice] batteryLevel];
#endif // !(TARGET_IPHONE_SIMULATOR)
}

bool UIAppState::ui_application_active() const {
  UIApplication* a = [UIApplication sharedApplication];
  return a.applicationState == UIApplicationStateActive;
}

bool UIAppState::ui_application_background() const {
  UIApplication* a = [UIApplication sharedApplication];
  return a.applicationState == UIApplicationStateBackground;
}

string UIAppState::ui_application_state() const {
  UIApplication* a = [UIApplication sharedApplication];
  switch (a.applicationState) {
    case UIApplicationStateActive:
      return "active";
    case UIApplicationStateInactive:
      return "inactive";
    case UIApplicationStateBackground:
      return "background";
    default:
      return "unknown";
  }
}

int UIAppState::remote_notification_types() const {
#if TARGET_IPHONE_SIMULATOR
  return 0;
#else  // TARGET_IPHONE_SIMULATOR
  UIApplication* a = [UIApplication sharedApplication];
  return [a enabledRemoteNotificationTypes];
#endif  // TARGET_IPHONE_SIMULATOR
}

bool UIAppState::show_update_notification(const string& version) const {
  return update_notification_ < version;
}

void UIAppState::set_show_update_notification(bool v) {
  if (v) {
    update_notification_ = "";
    db_->Delete(kUpdateNotificationKey);
  } else {
    update_notification_ = AppVersion();
    db_->Put(kUpdateNotificationKey, update_notification_);
  }
}

WallTime UIAppState::compose_last_used() const {
  return compose_last_used_;
}

void UIAppState::set_compose_last_used(WallTime timestamp) {
  compose_last_used_ = timestamp;
  db_->Put<WallTime>(kComposeLastUsedKey, compose_last_used_);
}

bool UIAppState::CloudStorageEnabled() {
  return cloud_storage() && subscription_manager_ios()->HasCloudStorage();
}

ProdUIAppState::ProdUIAppState()
    : UIAppState(HomeDir(), kHost, kPort, true),
      assets_manager_(NULL),
      root_view_controller_(NULL),
      log_rotate_callback_id_(0) {
  LOG("%s", BuildInfo());
  LOG("build=%s  model=%s  os=%s",
      AppVersion(), device_model(), device_os());
}

ProdUIAppState::~ProdUIAppState() {
  if (log_rotate_callback_id_) {
    Logging::RemoveLogRotate(log_rotate_callback_id_);
  }

  [assets_manager_ stop];
  [location_tracker_ stop];
  Kill();
}

bool ProdUIAppState::Init(InitAction init_action) {
  WallTimer total_timer;
  WallTimer timer;

  InitDeviceUUID();

  InitServices();
  VLOG("init: auth services: %0.3f ms", timer.Milliseconds());

  if (!UIAppState::Init(init_action)) {
    return false;
  }

  log_rotate_callback_id_ = Logging::AddLogRotate([this]{
      async()->dispatch_after_main(0, ^{
          net_manager()->Dispatch();
        });
    });

  timer.Restart();

  assets_manager_ = [[AssetsManager alloc] initWithState:this];
  VLOG("init: assets manager: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  geocode_manager_.reset(NewGeocodeManager());
  VLOG("init: geocode manager: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  location_tracker_ = [[LocationTracker alloc] initWithState:this];
  // NOTE, don't mention location in the log files.
  // VLOG("init: location tracker: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  UIStyle::Init();

  root_view_controller_ = [[RootViewController alloc] initWithState:this];
  VLOG("init: root view controller: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  LOG("init: total: %0.3f ms", total_timer.Milliseconds());
  LOG("init: host: %s disk=%.01f GB", HostInfo(),
        double(TotalDiskSpace()) / (1 << 30));

  DebugStatsLoop();
  return true;
}

void ProdUIAppState::UnlinkDevice() {
  WallTimer timer;

  day_table_->PauseEventRefreshes();

  [facebook_ logout];
  [google_ logout];
  auth_.Clear();
  WriteAuthMetadata();
  net_manager()->UnlinkDevice();
  LOG("unlink: logout: %.03f", timer.Milliseconds());
  timer.Restart();

  // Loop over the database and delete all keys.
  for (DB::PrefixIterator iter(db_, "");
       iter.Valid();
       iter.Next()) {
    db_->Delete(iter.key());
  }
  LOG("unlink: clean db: %.03f", timer.Milliseconds());
  timer.Restart();

  // Delete the Photos and (in release builds) ServerPhotos directories.
  const string old_dir(JoinPath(library_dir_, "old"));
  DirCreate(old_dir);
  const string unique_dir(JoinPath(old_dir, NewUUID()));
  DirCreate(unique_dir);

  const string kSubdirs[] = {
    "Photos",
#ifdef APPSTORE
    "ServerPhotos",
#endif // APPSTORE
  };
  for (int i = 0; i < ARRAYSIZE(kSubdirs); ++i) {
    FileRename(JoinPath(library_dir_, kSubdirs[i]),
               JoinPath(unique_dir, kSubdirs[i]));
  }

  dispatch_background(^{ DeleteOld(old_dir); });

  // Recreate the Photos and ServerPhotos directories.
  InitDirs();
  LOG("unlink: clean dirs: %.03f", timer.Milliseconds());
  timer.Restart();

  // Invalidate cached day metadata snapshot.
  day_table()->InvalidateSnapshot();
  LOG("unlink: invalidate all: %.03f", timer.Milliseconds());
  timer.Restart();

  contact_manager()->Reset();
  episode_table()->Reset();
  photo_table()->Reset();

  InitDB();
  InitVars();
  settings_changed_.Run(true);

  [root_view_controller() showDashboard:ControllerTransition()];

  BackgroundTask::Dispatch(^{
      RunMaintenance(INIT_NORMAL);
    });
}

void ProdUIAppState::AssetForKey(
    const string& key,
    ALAssetsLibraryAssetForURLResultBlock result,
    ALAssetsLibraryAccessFailureBlock failure) {
  [assets_manager_ assetForKey:key resultBlock:result failureBlock:failure];
}

void ProdUIAppState::AddAsset(
    NSData* data, NSDictionary* metadata,
    void (^done)(string asset_url, string asset_key)) {
  [assets_manager_ addAsset:data metadata:metadata callback:done];
}

void ProdUIAppState::DeleteAsset(const string& key) {
  [assets_manager_ deleteAsset:key];
}

void ProdUIAppState::InitServices() {
  facebook_ = [[FacebookService alloc]
                initWithAppId:kFacebookAppId];
  google_ = [[GoogleService alloc]
              initWithClientId:kGoogleClientId
                  clientSecret:kGoogleClientSecret];
}

void ProdUIAppState::InitDeviceUUID() {
  {
    // Remove the old device_uuid user default which could remain unchanged
    // when the user switched devices. We now use [UIDevice
    // identifierForVendor].
    NSString* const kDeviceUUIDKey = @"co.viewfinder.Viewfinder.device_uuid";
    NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
    if ([defaults objectForKey:kDeviceUUIDKey]) {
      [defaults removeObjectForKey:kDeviceUUIDKey];
      [defaults synchronize];
    }
  }

  NSUUID* id = [[UIDevice currentDevice] identifierForVendor];
  if (!id) {
    // The Apple docs say: "If the value is nil, wait and get the value again
    // later. This happens, for example, after the device has been restarted
    // but before the user has unlocked the device."
    async()->dispatch_after_main(0.5, ^{
        InitDeviceUUID();
      });
    return;
  }

  device_uuid_ = ToString([id UUIDString]);
}

bool ProdUIAppState::app_active() const {
  return [UIApplication sharedApplication].applicationState ==
      UIApplicationStateActive;
}

bool ProdUIAppState::network_up() const {
  return net_manager()->network_up();
}

bool ProdUIAppState::network_wifi() const {
  return net_manager()->network_wifi();
}

// local variables:
// mode: c++
// end:
