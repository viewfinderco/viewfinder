// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
// Author: Spencer Kimball.

#import <QuartzCore/QuartzCore.h>
#import "Analytics.h"
#import "AppDelegate.h"
#import "Appearance.h"
#import "AssetsManager.h"
#import "AsyncState.h"
#import "BadgeView.h"
#import "CALayer+geometry.h"
#import "ConversationLayoutController.h"
#import "ConversationSummaryView.h"
#import "CppDelegate.h"
#import "Defines.h"
#import "Logging.h"
#import "NetworkManager.h"
#import "NetworkQueue.h"
#import "PhotoManager.h"
#import "PhotoView.h"
#import "RootViewController.h"
#import "ScopedRef.h"
#import "StatusBar.h"
#import "SummaryLayoutController.h"
#import "UIView+geometry.h"
#import "UpdateNotificationView.h"

namespace {

const WallTime kTransitionLoadImagesDelay = 0.5;
const double kInitialScanProgressInterval = 0.3;  // 300 ms

const float kPageControlOffset = 58;
const float kPageSpacing = 0;
const float kPhotoAccessMargin = 20;
const float kPhotoCounterMargin = 20;
const float kTransitionDuration = 0.300;

#ifdef DEVELOPMENT
const int kShowQueueLengthThreshold = 3;
#else
const int kShowQueueLengthThreshold = 1000;
#endif

const int kMaxSummaryPage = 2;

struct InitialScanState {
 public:
  InitialScanState(UIAppState* s)
      : state(s),
        start_id(-1),
        progress_id(-1),
        end_id(-1) {
  }
  ~InitialScanState() {
    if (start_id != -1) {
      state->assets_scan_start()->Remove(start_id);
    }
    if (progress_id != -1) {
      state->assets_scan_progress()->Remove(progress_id);
    }
    if (end_id != -1) {
      state->assets_scan_end()->Remove(end_id);
    }
  }

 public:
  UIAppState* const state;
  Mutex mu;
  WallTimer interval_timer;
  WallTimer scan_timer;
  int start_id;
  int progress_id;
  int end_id;
};

}  // namespace

@implementation SummaryLayoutController

@synthesize summaryPage = summary_page_;
@synthesize dashboard = dashboard_;
@synthesize inbox = inbox_;

- (id)initWithState:(UIAppState*)state {
  if (self = [super initWithState:state]) {
    self.wantsFullScreenLayout = YES;

    summary_page_ = PAGE_INBOX;
    refreshing_ = false;
    need_rebuild_ = false;
    view_state_ = -1;

    dashboard_ = [[Dashboard alloc] initWithState:state env:self];

    state_->app_did_become_active()->Add(^{
        // Another dispatch to main in order to allow AssetsManager to cache
        // authorization status.
        state_->async()->dispatch_after_main(0, ^{
            [self maybePromptUser];
            [self maybeRebuildSummary:0];
          });
      });

    state_->system_message_changed()->Add(^{
        dispatch_main(^{
            [self rebuildDashboard];
          });
      });
    state_->contact_manager()->new_user_callback()->Add(^{
        dispatch_main(^{
            [self rebuildDashboard];
          });
      });

    // Receive notifications for refreshes to day metadata.
    state_->day_table()->update()->Add(^{
        need_rebuild_ = true;
        // Wait for a fraction of a second before rebuiding in case the day
        // table update causes a viewpoint transition.
        [self maybeRebuildSummary:0.001];
      });
    state_->net_manager()->network_changed()->Add(^{
        dispatch_main(^{
            [self updateNetworkActivity];
          });
      });
    state_->network_ready()->Add(^(int priority) {
        dispatch_main(^{
            [self updateNetworkActivity];
          });
      });
    // Let the stack unwind so that we don't re-entrantly call the
    // NetworkManager.
    state_->net_manager()->refresh_start()->Add(^{
        dispatch_after_main(0, ^{
            [self networkLoadingStart];
          });
      });
    state_->net_manager()->refresh_end()->Add(^{
        dispatch_after_main(0, ^{
            [self networkLoadingStop];
          });
      });
  }
  return self;
}

- (ControllerState)controllerState {
  if (summary_page_ == PAGE_PROFILE ||
      view_state_ != STATE_OK) {
    return super.controllerState;
  }
  DCHECK(inbox_);
  return inbox_.controllerState;
}

- (void)setControllerState:(ControllerState)controller_state {
  super.controllerState = controller_state;
  if (inbox_) {
    inbox_.controllerState = controller_state;
  }
}

- (string)summaryName {
  if (inbox_) {
    return inbox_.name;
  }
  return "dashboard";
}

- (void)setCurrentView:(int)page
              animated:(BOOL)animated {
  // Refresh the state if needed.
  [self prepareViews];
  [self setSummaryPage:static_cast<SummaryPage>(page)];
}

// Rebuild the summary if there were changes and the user is not active.
- (void)maybeRebuildSummary:(double)delay {
  if (!state_->day_table()->initialized()) {
    return;
  }
  dispatch_after_main(delay, ^{
      bool rebuilt = false;
      if (self.visible) {
        rebuilt = [self rebuildSummary];
      }
      [self updateInboxBadge];
      if (!rebuilt) {
        // Always rebuild the dashboard in order to ensure the badge is
        // updated.
        [self rebuildDashboard];
      }
    });
}

- (bool)rebuildSummary {
  if (!need_rebuild_) {
    return false;
  }

  if ((inbox_ && (inbox_.isModal || inbox_.isScrolling)) ||
      !state_->app_active()) {
    return false;
  }

  // Store any photo views during rebuild so we don't needlessly recreate them.
  BuildPhotoViewMap(state_->photo_view_map(), self.view);

  // Note that the dashboard can properly animate changes when it is rebuilt.
  [self rebuildDashboard];

  {
    const ScopedDisableCAActions disable_ca_actions;
    [self rebuildInbox];
    need_rebuild_ = false;
    [self updateToolbar:false modal:false];
  }

  // Always clear the photo view map as the library and inbox have already
  // repopulated their photos.
  state_->photo_view_map()->clear();
  return true;
}

- (bool)rebuildInbox {
  if (!dashboard_.maintenanceDone) {
    return false;
  }
  return [inbox_ rebuild];
}

- (void)rebuildDashboard {
  [dashboard_ rebuild];
  [self updateProfileBadge];
}

- (void)updateInboxBadge {
  DayTable::SnapshotHandle snap = state_->day_table()->GetSnapshot(NULL);
  if (snap->conversations()->unviewed_inbox_count() > 0) {
    toolbar_.inboxBadge.text =
        Format("%d", snap->conversations()->unviewed_inbox_count());
  } else {
    toolbar_.inboxBadge.text = NULL;
  }
}

- (void)updateProfileBadge {
  if (dashboard_.noticeCount > 0) {
    toolbar_.profileBadge.text = Format("%d", dashboard_.noticeCount);
  } else {
    toolbar_.profileBadge.text = NULL;
  }
}

- (void)updateNetworkActivity {
  if (state_->network_up() && state_->view_state() == STATE_OK) {
    NSString* message = NULL;
    const int top_priority = state_->net_queue()->TopPriority();
    if (top_priority != -1) {
      if (state_->net_queue()->IsDownloadPriority(top_priority)) {
        const int count = state_->net_queue()->GetDownloadCount();
        message = Format("Receiving%s…",
                         (count > kShowQueueLengthThreshold ?
                          ToString(Format(" (%s)", LocalizedNumberFormat(count))) : ""));
      } else {
        const int count = state_->net_queue()->GetUploadCount();
        message = Format("%s…",
                         (count > kShowQueueLengthThreshold ?
                          ToString(Format("Sending (%s)", LocalizedNumberFormat(count))) : "Updating"));
      }
    } else if (refreshing_) {
      message = @"Refreshing…";
    }
    if (message) {
      [state_->root_view_controller().statusBar
          setMessage:message
          activity:true
          type:STATUS_MESSAGE_NETWORK];
      return;
    }
  }

  [state_->root_view_controller().statusBar
      hideMessageType:STATUS_MESSAGE_NETWORK
      minDisplayDuration:0.75];
}

- (void)networkLoadingStart {
  LOG("%s: network loading start", self.summaryName);
  refreshing_ = true;
  [self updateNetworkActivity];
}

- (void)networkLoadingStop {
  LOG("%s: network loading stop (%s)",
      self.summaryName, self.visible ? "visible" : "hidden");
  refreshing_ = false;
  [self updateNetworkActivity];
  [self maybePromptUser];
}

- (void)dashboardMaintenanceBegin {
  toolbar_.hidden = YES;
  [state_->root_view_controller() showDashboard:ControllerTransition()];
}

- (void)dashboardMaintenanceEnd {
  toolbar_.hidden = NO;
  [state_->root_view_controller() showInbox:ControllerTransition()];
}

- (void)addInboxView {
  if (!inbox_) {
    __weak SummaryLayoutController* weak_self = self;
    ActivatedCallback modal_callback = ^(bool active) {
      if (!active) {
        [weak_self maybeRebuildSummary:0];
      }
      [weak_self updateToolbar:true modal:active];
    };

    if (!inbox_) {
      inbox_ = [[ConversationSummaryView alloc]
                 initWithState:state_
                      withType:SUMMARY_CONVERSATIONS];
      inbox_.modalCallback->Add(modal_callback);
      inbox_.scrollToTopCallback->Add(^{
          [weak_self manualRefresh];
        });
      inbox_.toolbarCallback->Add(^(bool hidden) {
          if (hidden) {
            [weak_self hideToolbar];
          } else {
            [weak_self showToolbar];
          }
        });
    }
    [self.view insertSubview:inbox_ belowSubview:dashboard_];
  }
}

- (void)clearViews {
  [toolbar_ removeFromSuperview];
  toolbar_ = NULL;
  [dashboard_ removeFromSuperview];
  [inbox_ removeFromSuperview];
  inbox_ = NULL;
}

- (void)prepareViews {
  // LOG("%s: prepare views", self.summaryName);
  const int new_state = state_->view_state();
  if (view_state_ == new_state) {
    return;
  }
  LOG("Switching summary view state: %d -> %d", view_state_, new_state);

  view_state_ = new_state;
  // Always clear the views (this removes them from self.view).
  [self clearViews];
  // Toolbar defaults to not visible.
  bool show_toolbar = false;
  // Always show the dashboard.
  [self.view addSubview:dashboard_];

  if (view_state_ == STATE_NOT_REGISTERED) {
    summary_page_ = PAGE_PROFILE;
  } else if (view_state_ == STATE_RESET_DEVICE_ID) {
    summary_page_ = PAGE_PROFILE;
  } else if (view_state_ == STATE_ACCOUNT_SETUP) {
    summary_page_ = PAGE_PROFILE;
  } else if (view_state_ == STATE_PHOTO_NOT_AUTHORIZED) {
    summary_page_ = PAGE_PROFILE;
  } else if (view_state_ == STATE_OK) {
    summary_page_ = PAGE_INBOX;
    [self addInboxView];
    // Show toolbar only if state is OK.
    show_toolbar = true;

    [self maybePromptUser];

    // Maybe show update notification.
    [UpdateNotificationView maybeShow:state_ inView:self.view];
  }

  __weak SummaryLayoutController* weak_self = self;
  if (show_toolbar) {
    toolbar_ = [[SummaryToolbar alloc] initWithTarget:weak_self];
    inbox_.toolbar = toolbar_;
    [self.view addSubview:toolbar_];
    [self updateToolbar:false modal:false];
  }

  if (self.visible) {
    [self viewWillAppear:NO];
  }
}

- (bool)maybePromptUser {
  if (view_state_ == STATE_NOT_REGISTERED) {
    // Only prompt the user once they have registered.
    return false;
  }
  if ([self maybePromptForPhotos]) {
    return true;
  }
  // Note(peter): iOS appears to have a bug with failing to call
  // didFailToRegisterForRemoteNotificationsWithError if we are the first app
  // on the phone to ask for push notifications and the user declines. The
  // result is that we receive no indicate of whether registration succeeded or
  // failed. We work around this bug by making push notifications the final
  // prompt.
  if ([self maybePromptForPushNotifications]) {
    return true;
  }
  return false;
}

- (bool)maybePromptForPhotos {
  if (state_->assets_authorization_determined()) {
    return false;
  }
  // TODO(peter): Provide a developer setting that can display this alert.
  // [[[UIAlertView alloc]
  //    initWithTitle:@"\"Viewfinder\" Would Like to Access Your Photos"
  //          message:NULL
  //         delegate:NULL
  //    cancelButtonTitle:@"Don't Allow"
  //    otherButtonTitles:@"OK", NULL] show];
  [state_->assets_manager() authorize];
  return true;
}

- (bool)maybePromptForPushNotifications {
  if (registered_for_push_notifications_ ||
      state_->view_state() != STATE_OK) {
    return false;
  }

  registered_for_push_notifications_ = true;
  [AppDelegate registerForPushNotifications];
  return true;
}

- (void)toolbarCancel {
  [inbox_ cancelEditMode];
}

- (void)toolbarCompose {
  state_->analytics()->InboxShareButton();
  [state_->root_view_controller() showCompose:ControllerTransition()];
}

- (void)toolbarEdit {
  [inbox_ activateEditMode:EDIT_MODE_EDIT];
}

- (void)toolbarExit {
  [inbox_ exitModal];
}

- (void)toolbarInbox {
  inbox_.hidden = NO;
  [inbox_ setNeedsDisplay];
  [toolbar_ showInboxItems:true];
  [UIView animateWithDuration:kTransitionDuration
                   animations:^{
      if (summary_page_ == PAGE_PROFILE) {
        dashboard_.frameTop += dashboard_.frameHeight;
      }
    }
                   completion:^(BOOL finished) {
      [self setSummaryPage:PAGE_INBOX];
    }];
}

- (void)hideToolbar {
  toolbar_offscreen_ = true;
  [self viewDidLayoutSubviews];
}

- (void)showToolbar {
  toolbar_offscreen_ = false;
  [self viewDidLayoutSubviews];
}

- (void)toolbarProfile {
  dashboard_.frameTop = dashboard_.frameHeight;
  dashboard_.hidden = NO;
  [toolbar_ showProfileItems:true];
  [UIView animateWithDuration:kTransitionDuration
                   animations:^{
      dashboard_.frameTop = 0;
    }
                   completion:^(BOOL finished) {
      [self setSummaryPage:PAGE_PROFILE];
    }];
}

- (void)toolbarSettings {
  [state_->root_view_controller() showSettings:ControllerTransition(TRANSITION_SLIDE_OVER_UP)];
}

- (void)setSummaryPage:(SummaryPage)page {
  summary_page_ = page;
  if (page == PAGE_PROFILE) {
    dashboard_.hidden = NO;
    [dashboard_ setNeedsDisplay];
  } else {
    dashboard_.hidden = YES;
  }
  if (page == PAGE_INBOX) {
    inbox_.hidden = NO;
    [inbox_ setNeedsDisplay];
  } else {
    inbox_.hidden = YES;
  }

  [self updateToolbar:false modal:false];
  [self updateProfileBadge];
  [self viewDidLayoutSubviews];
}

- (void)updateToolbar:(bool)animated
                modal:(bool)modal {
  if (summary_page_ == PAGE_INBOX) {
    if (modal) {
      [toolbar_ showSearchInboxItems:animated];
      toolbar_.exitItem.customView.hidden =
          (inbox_.viewfinder.mode == VF_JUMP_SCROLLING);
    } else {
      [toolbar_ showInboxItems:animated];
    }
  } else if (summary_page_ == PAGE_PROFILE) {
    [toolbar_ showProfileItems:animated];
  }
}

- (bool)manualRefresh {
  if (view_state_ != STATE_OK || refreshing_) {
    return false;
  }
  // Initiate an asset scan if the assets manager is idle.
  [state_->assets_manager() scan];

  state_->net_manager()->ResetBackoff();
  return state_->net_manager()->Refresh();
}

- (void)loadView {
  //  LOG("%s: view load", self.summaryName);

  self.view = [UIView new];
  self.view.autoresizesSubviews = YES;
  self.view.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  self.view.backgroundColor = [UIColor blackColor];

  if (state_->assets_initial_scan()) {
    // Only provide feedback of the initial scan of the assets library.
    InitialScanState* scan = new InitialScanState(state_);
    scan->start_id = state_->assets_scan_start()->Add(^{
        if (!state_->assets_full_scan()) {
          return;
        }
        LOG("initial asset scan: begin");
        scan->interval_timer.Restart();
        scan->scan_timer.Restart();
      });
    scan->end_id = state_->assets_scan_end()->Add(^(const StringSet*) {
        if (!state_->assets_full_scan()) {
          return;
        }
        LOG("initial asset scan: end: %.1f sec", scan->scan_timer.Get());
        delete scan;

        state_->day_table()->ResumeEventRefreshes();
      });
  }

  [self prepareViews];
}

- (void)viewDidUnload {
  //  LOG("%s: view did unload", self.summaryName);
  toolbar_ = NULL;
  [inbox_ clear];
}

- (void)viewWillAppear:(BOOL)animated {
  LOG("%s: view will appear", self.summaryName);
  [super viewWillAppear:animated];

  [CATransaction begin];
  [CATransaction setDisableActions:YES];

  if (animated) {
    state_->photo_view_map()->clear(),
    BuildPhotoViewMap(
        state_->photo_view_map(),
        state_->root_view_controller().prevViewController.view);
  }

  // Build all views so transition is always fast.
  [self setSummaryPage:summary_page_];
  [self rebuildDashboard];
  [self rebuildInbox];
  [self updateToolbar:animated modal:false];

  if (animated && !self.visible) {
    // animateTransitionCommit must be called after animateTransitionPrepare.  RootViewController will do this,
    // but other transitions will not.  The only case where this currently happens is when the export dialog
    // is dismissed, which also happens to call view{Will,Did}Appear without view{WillDid}Disappear,
    // so we can detect this case with self.visible.
    [self animateTransitionPrepare];
  }

  state_->photo_view_map()->clear();
  [CATransaction commit];

  [self maybePromptUser];

  switch (summary_page_) {
    case PAGE_PROFILE:
      state_->analytics()->SummaryDashboard();
      break;
    case PAGE_INBOX:
      state_->analytics()->SummaryInbox();
      break;
    default:
      break;
  }
}

- (void)viewDidAppear:(BOOL)animated {
  // LOG("%s: view did appear", self.summaryName);
  [super viewDidAppear:animated];
  transition_.reset(NULL);
  [inbox_ viewDidAppear];

  [self updateNetworkActivity];
}

- (void)viewWillDisappear:(BOOL)animated {
  // LOG("%s: view will disappear", self.summaryName);
  [super viewWillDisappear:animated];
}

- (void)viewDidDisappear:(BOOL)animated {
  // LOG("%s: view did disappear", self.summaryName);
  [super viewDidDisappear:animated];
  [inbox_ viewDidDisappear];
}

- (void)viewDidLayoutSubviews {
  // LOG("%s: view did layout subviews", self.summaryName);
  [super viewDidLayoutSubviews];

  toolbar_.frame = CGRectMake(
      0, 0, self.view.frameWidth,
      toolbar_.intrinsicHeight + state_->status_bar_height());

  if (toolbar_offscreen_) {
    toolbar_.frameBottom = -1;
  } else {
    toolbar_.frameTop = 0;
  }

  dashboard_.frame = self.view.bounds;
  inbox_.frame = self.view.bounds;
  inbox_.toolbarBottom = std::max<float>(0, toolbar_.frameBottom);
}

- (void)animateTransitionPrepare {
  UIViewController* prev = state_->root_view_controller().prevViewController;
  if (![prev isKindOfClass:[LayoutController class]]) {
    // Only perform a transition animation if we're transitioning from a layout
    // controller.
    return;
  }

  transition_.reset(new LayoutTransitionState(state_, self));
  if (inbox_) {
    [inbox_ animateTransitionPrepare:transition_.get()];
  }
  transition_->PrepareFinish();
}

- (bool)animateTransitionCommit {
  // LOG("%s: animate from view controller", self.summaryName);
  if (!transition_.get()) {
    return false;
  }
  UIViewController* prev = state_->root_view_controller().prevViewController;
  if (prev == (UIViewController*)state_->root_view_controller().conversationLayoutController) {
    UIView* c = state_->root_view_controller().conversationLayoutController.currentConversationView;
    c.transform = CGAffineTransformMakeScale(0.9, 0.9);
  }
  transition_->Commit();
  return true;
}

@end  // SummaryLayoutController
