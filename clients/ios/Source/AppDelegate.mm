// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef ADHOC
#import <TestFlight/TestFlight.h>
#endif  // ADHOC
#import <unicode/putil.h>
#import "Analytics.h"
#import "AppDelegate.h"
#import "Appearance.h"
#import "BackgroundManager.h"
#import "CrashReporter.h"
#import "DebugUtils.h"
#import "Defines.h"
#import "FacebookService.h"
#import "FileUtils.h"
#import "LocationTracker.h"
#import "Logging.h"
#import "NetworkManager.h"
#import "NotificationManager.h"
#import "PathUtils.h"
#import "RootViewController.h"
#import "StatusBar.h"
#import "StringUtils.h"
#import "SummaryLayoutController.h"
#import "Testing.h"
#import "UIAppState.h"
#import "ValueUtils.h"

namespace {

bool CheckIOSVersion(bool alert) {
  if (kIOSVersion >= "8") {
    if (alert) {
      [[[UIAlertView alloc]
         initWithTitle:Format("iOS %s not supported", kIOSVersion)
               message:Format("Viewfinder does not support iOS %s yet", kIOSVersion)
              delegate:NULL
         cancelButtonTitle:@"OK"
         otherButtonTitles:NULL]
        show];
    }
    return false;
  }
  return true;
}

}  // namespace

@implementation AppDelegate

- (BOOL)application:(UIApplication*)application
didFinishLaunchingWithOptions:(NSDictionary*)launchOptions {
  if (!CheckIOSVersion(true)) {
    return NO;
  }
  // Initialize ICU.
  u_setDataDirectory(MainBundlePath("icudt51l.dat").c_str());

  Logging::SetFatalHook([](LogStream& os) {
      os << "\n" << MemStats(false)
         << "\n" << FileStats()
         << "\nBacktrace:\n" << Backtrace();
    });

  DebugInject();
  InitAppearanceConstants();

  window_ = [[UIWindow alloc] initWithFrame:[[UIScreen mainScreen] bounds]];
  window_.backgroundColor = [UIColor blackColor];
  [window_ makeKeyAndVisible];
  [window_ becomeFirstResponder];
  becoming_active_ = false;

  // HACK: iOS cannot handle nested pthread_once/dispatch_once
  // calls. LazyStaticCTFont is initialized via dispatch_once and calls
  // CTFontCreateWithName. The iOS font routines use pthread_once to
  // perform one time initialization. If this initialization does not occur
  // before the first LazyStaticCTFont initialization we'll get a
  // deadlock. The workound is to ensure that the font initialization is
  // performed here.
  [UIFont familyNames];

  Testing::RunTests(window_, ^{
      Logging::InitFileLogging();
      LOG("app: did finish launching with options: %@", launchOptions);

      state_.reset(new ProdUIAppState);

#ifdef ADHOC
      [TestFlight setDeviceIdentifier:[AppDelegate uniqueIdentifier]];
      [TestFlight takeOff:@"f2550c51-2dbe-4a6d-81eb-ae32d481fa4c"];
#else  // ADHOC
      [self initCrashReporter];
#endif // !ADHOC

      // Initialize the application state.
      const UIAppState::InitAction init_action = state_->GetInitAction();
      if (!state_->Init(init_action)) {
        DIE("app: unable to initialize state");
      }

      NSDictionary* n =
          [launchOptions objectForKey:
                           UIApplicationLaunchOptionsRemoteNotificationKey];
      state_->analytics()->Launch(n ? "remote_notification" : "normal");

      state_->maintenance_done()->Add(^(bool) {
          maintenance_done_ = true;
          if (active_) {
            // Run the callback we skipped in applicationDidBecomeActive.
            state_->app_did_become_active()->Run();
          }
        });

      // Run maintenance on a low priority thread. All interaction with the
      // view controllers is done via the main thread.
      BackgroundTask::Dispatch(^{
          state_->RunMaintenance(init_action);
          dispatch_main(^{
              if (n) {
                // Synthesize a call to didReceiveRemoteNotification so that we can
                // have a single code path that deals with remote notification
                // processing.
                [self application:application didReceiveRemoteNotification:n];
              }
            });
        });

      window_.rootViewController = state_->root_view_controller();

      NSUbiquitousKeyValueStore* store = [NSUbiquitousKeyValueStore defaultStore];
      [store synchronize];
      VLOG("app: icloud: %s", store.dictionaryRepresentation);
      // if (![store stringForKey:@"test"]) {
      //   [store setString:@"hello" forKey:@"test"];
      // }
    });
  return YES;
}

- (void)applicationWillTerminate:(UIApplication*)application {
  LOG("app: will terminate");
}

- (void)applicationDidBecomeActive:(UIApplication*)application {
  LOG("app: did become active");
  active_ = true;
  [[UIDevice currentDevice] beginGeneratingDeviceOrientationNotifications];
  [UIDevice currentDevice].batteryMonitoringEnabled = YES;
  // If TESTING is true, this callback is invoked before the UIAppState is
  // initialized.
  becoming_active_ = false;
  if (state_.get() && maintenance_done_) {
    state_->app_did_become_active()->Run();
  }
}

- (void)applicationWillResignActive:(UIApplication*)application {
  LOG("app: will resign active");
  active_ = false;
  [[UIDevice currentDevice] endGeneratingDeviceOrientationNotifications];
  [UIDevice currentDevice].batteryMonitoringEnabled = NO;
  if (state_.get()) {
    state_->app_will_resign_active()->Run();
  }
}

- (void)applicationDidEnterBackground:(UIApplication*)application {
  LOG("app: did enter background");
  if (state_.get()) {
    state_->analytics()->EnterBackground();
    [state_->root_view_controller().statusBar clearMessages];

    BackgroundTask::Dispatch(^{
        state_->db()->MinorCompaction();
      });
  }
}

- (void)applicationWillEnterForeground:(UIApplication*)application {
  LOG("app: will enter foreground");
  if (state_.get()) {
    state_->analytics()->EnterForeground();
  }
  becoming_active_ = true;
}

- (void)applicationDidReceiveMemoryWarning:(UIApplication*)application {
  LOG("app: memory warning: %s", TaskInfo());
}

- (void)application:(UIApplication*)application
didRegisterForRemoteNotificationsWithDeviceToken:(NSData*)token {
  if (state_.get()) {
    state_->apn_device_token()->Run(token);
  }
}

- (void)application:(UIApplication*)application
didFailToRegisterForRemoteNotificationsWithError:(NSError*)err {
  if (state_.get()) {
    LOG("app: remote notification registration error: %s", err);
    state_->apn_device_token()->Run(NULL);
  }
}

// Pre iOS 7 support: delegate to the new iOS 7 interface.
- (void)application:(UIApplication*)application
didReceiveRemoteNotification:(NSDictionary*)user_info {
  [self application:application
        didReceiveRemoteNotification:user_info
        fetchCompletionHandler:NULL];
}

// iOS 7 and later.
- (void)application:(UIApplication*)application
didReceiveRemoteNotification:(NSDictionary*)user_info
fetchCompletionHandler:(void (^)(UIBackgroundFetchResult))handler {
  if (!state_.get()) {
    return;
  }
  const Dict d(user_info);
  const Dict aps(d.find_dict("aps"));
  const Value viewpoint_id_value = d.find_value("v");
  const string viewpoint_id(viewpoint_id_value.get() ? ToString(viewpoint_id_value) : string());
  LOG("app: did receive remote notification (%s): v:%s",
      state_->ui_application_state(), viewpoint_id);
  if (handler) {
    state_->net_manager()->refresh_end()->AddSingleShot([handler]() {
        handler(UIBackgroundFetchResultNewData);
      });
  }
  state_->analytics()->RemoteNotification();
  state_->notification_manager()->RemoteNotification(
      ToString(aps.find_value("alert")));

  if (becoming_active_ && !viewpoint_id.empty()) {
    // If the application was not active, attempt to transition to the
    // viewpoint associated with the notification. If the viewpoint was
    // specified via APNs, see if it exists already; if so, show it
    // immediately. Otherwise, show the inbox summary view.
    int epoch;
    DayTable::SnapshotHandle snap = state_->day_table()->GetSnapshot(&epoch);
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(viewpoint_id, snap->db());
    if (vh.get()) {
      int64_t viewpoint_local_id = vh->id().local_id();
      LOG("app: transitioning to viewpoint %s", viewpoint_local_id);
      dispatch_after_main(0, ^{
          ControllerState ctls;
          ctls.current_viewpoint = viewpoint_local_id;
          ctls.pending_viewpoint = true;
          // Set the summary page to be the inbox so that navigating
          // 'back' from conversation reveals the inbox.
          state_->root_view_controller().summaryLayoutController.summaryPage = PAGE_INBOX;
          [state_->root_view_controller() showConversation:ctls];
        });
    } else {
      LOG("app: transitioning to summary inbox to await new viewpoint %s",
          viewpoint_id);
      dispatch_after_main(0, ^{
          [state_->root_view_controller() showInbox:ControllerState()];
        });
    }
  }
}

// Pre 4.2 support
- (BOOL)application:(UIApplication*)application
      handleOpenURL:(NSURL*)url {
  return [self application:application
                   openURL:url
               sourceApplication:NULL
                annotation:NULL];
}

// For 4.2+ support
- (BOOL)application:(UIApplication*)application
            openURL:(NSURL*)url
  sourceApplication:(NSString*)sourceApplication
         annotation:(id)annotation {
  if (!state_.get()) {
    return NO;
  }
  LOG("app: open url: %s", url);
  // We currently receive both the "viewfinder" scheme and the "fb" schemes
  // (the latter occurs during facebook authorization). The openURL mechanism
  // is used in iOS for inter-app communication. Extend this method as
  // necessary.
  if (ToSlice(url.scheme) == "viewfinder") {
    state_->open_url()->Run(url);
    return YES;
  }
  return [state_->facebook() handleOpenURL:url];
}

+ (void)registerForPushNotifications {
  // Only register for remote notifications on devices. The simulator
  // doesn't support them and just gives a warning.
#if !(TARGET_IPHONE_SIMULATOR)
  static const UIRemoteNotificationType kRemoteNotifications =
      static_cast<UIRemoteNotificationType>(
          UIRemoteNotificationTypeAlert |
          UIRemoteNotificationTypeBadge |
          UIRemoteNotificationTypeSound);

  UIApplication* application = [UIApplication sharedApplication];
  const UIRemoteNotificationType current_notifications =
      [application enabledRemoteNotificationTypes];
  LOG("current notifications (%d); requested notifications (%d)",
      current_notifications, kRemoteNotifications);
  [application registerForRemoteNotificationTypes:kRemoteNotifications];
#else  // (TARGET_IPHONE_SIMULATOR)
  dispatch_after_main(0, ^{
      UIApplication* application = [UIApplication sharedApplication];
      [application.delegate application:application
                  didFailToRegisterForRemoteNotificationsWithError:NULL];
    });
#endif // (TARGET_IPHONE_SIMULATOR)
}

+ (void)setApplicationIconBadgeNumber:(int)number {
  [UIApplication sharedApplication].applicationIconBadgeNumber = number;
}

+ (NSString*)uniqueIdentifier {
#if defined(ADHOC) || defined(DEVELOPMENT)
  UIDevice* d = [UIDevice currentDevice];
  if ([d respondsToSelector:@selector(uniqueIdentifier)]) {
    return [d performSelector:@selector(uniqueIdentifier)];
  }
#endif  // ADHOC or DEVELOPMENT
  return NULL;
}

- (void)initCrashReporter {
  PLCrashReporter* crash_reporter = [PLCrashReporter sharedReporter];
  if ([crash_reporter hasPendingCrashReport]) {
    NSError* error = NULL;
    NSData* crash_data =
        [crash_reporter loadPendingCrashReportDataAndReturnError:&error];
    if (!crash_data) {
      LOG("ERROR: unable to load crash data: %@", error);
    } else {
      state_->ReportAppCrashed();

      PLCrashReport* crash_report =
          [[PLCrashReport alloc] initWithData:crash_data error:&error];
      // Purge the crash report before converting it to text in case there is a
      // bug in the formatting routines. We don't want to get into a crash loop
      // because of crash logs!
      [crash_reporter purgePendingCrashReport];

      if (!crash_report) {
        LOG("ERROR: unable to decode crash report: %@", error);
      } else {
        NSString* text =
            [PLCrashReportTextFormatter
              stringValueForCrashReport:crash_report
                         withTextFormat:PLCrashReportTextFormatiOS];
        const string crash_log = NewLogFilename(".crash");
        WriteStringToFile(JoinPath(LoggingQueueDir(), crash_log), ToSlice(text));
        LOG("app: prepared crash report: %s", crash_log);
      }
    }
  }

  NSError* error = NULL;
  if (![crash_reporter enableCrashReporterAndReturnError:&error]) {
    LOG("ERROR: unable to enable crash reporter: %@", error);
  }
}

@end  // AppDelegate
