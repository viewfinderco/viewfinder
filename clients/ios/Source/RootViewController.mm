// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AlertNotificationView.h"
#import "Appearance.h"
#import "CameraViewController.h"
#import "Chevron.h"
#import "ComposeLayoutController.h"
#import "ContactsController.h"
#import "ConversationLayoutController.h"
#import "DayTable.h"
#import "DB.h"
#import "Defines.h"
#import "FileUtils.h"
#import "Logging.h"
#import "MathUtils.h"
#import "PathUtils.h"
#import "PhotoLayoutController.h"
#import "RootViewController.h"
#import "ScopedRef.h"
#import "SettingsViewController.h"
#import "StatusBar.h"
#import "SummaryLayoutController.h"
#import "UIAppState.h"
#import "UIView+geometry.h"
#import "UIViewController+viewfinder.h"
#import "ValueUtils.h"

namespace {

const int kMaxStartCount = 10;

LazyStaticHexColor kChevronColor = { "#bebfbf" };
LazyStaticHexColor kStartupBackgroundColor = { "#0d0d0dff" };
LazyStaticHexColor kTopChevronColor = { "#bebfbf" };

NSString* const kStartCountKey = @"co.viewfinder.Viewfinder.start_count";

CAShapeLayer* NewShapeLayer(CGPathRef path) {
  CAShapeLayer* l = [CAShapeLayer new];
  l.path = path;
  return l;
}

const float kDefaultAlertTimeout = 5.0;

TransitionType ReverseTransition(TransitionType type) {
  switch (type) {
    case TRANSITION_DEFAULT:
      return TRANSITION_DEFAULT;
    case TRANSITION_FADE_IN:
      return TRANSITION_FADE_IN;
    case TRANSITION_SHOW_FROM_RECT:
      return TRANSITION_SHOW_FROM_RECT;
    case TRANSITION_SLIDE_UP:
      return TRANSITION_SLIDE_DOWN;
    case TRANSITION_SLIDE_OVER_UP:
      return TRANSITION_SLIDE_OVER_DOWN;
    case TRANSITION_SLIDE_LEFT:
      return TRANSITION_SLIDE_RIGHT;
    case TRANSITION_SLIDE_OVER_LEFT:
      return TRANSITION_SLIDE_OVER_RIGHT;
    case TRANSITION_SLIDE_DOWN:
      return TRANSITION_SLIDE_UP;
    case TRANSITION_SLIDE_OVER_DOWN:
      return TRANSITION_SLIDE_OVER_UP;
    case TRANSITION_SLIDE_RIGHT:
      return TRANSITION_SLIDE_LEFT;
    case TRANSITION_SLIDE_OVER_RIGHT:
      return TRANSITION_SLIDE_OVER_LEFT;
  }
}

int GetStartCount() {
  NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
  const int start_count = [defaults integerForKey:kStartCountKey];
  if (start_count < kMaxStartCount) {
    [defaults setInteger:1 + start_count forKey:kStartCountKey];
    [defaults synchronize];
  }
  return start_count;
}

#if TARGET_IPHONE_SIMULATOR

UIImage* MakeImageFromView(
    UIView* view, UIColor* bg_color, CGSize size, float scale) {
  if (CGSizeEqualToSize(size, CGSizeZero)) {
    size = view.bounds.size;
  }
  UIGraphicsBeginImageContextWithOptions(size, view.opaque, scale);
  CGContextRef context = UIGraphicsGetCurrentContext();
  CGContextSetFillColorWithColor(context, bg_color.CGColor);
  CGContextFillRect(context, CGRectMake(0, 0, size.width, size.height));
  CGContextTranslateCTM(context,
                        (size.width - view.boundsWidth) / 2,
                        (size.height - view.boundsHeight) / 2);
  [view.layer renderInContext:context];
  UIImage* image = UIGraphicsGetImageFromCurrentImageContext();
  UIGraphicsEndImageContext();
  return image;
}

#endif  // TARGET_IPHONE_SIMULATOR

}  // namespace

@interface StartupView : UIView {
 @private
}

@end  // StartupView

@implementation StartupView

- (id)initWithFrame:(CGRect)f {
  if (self = [super initWithFrame:f]) {
    const int kStartCount = GetStartCount();
    const float kDuration = LinearInterp<float>(
        kStartCount, 0, kMaxStartCount, 1.5, 0.5);
    const float kScaleStartTime = LinearInterp<float>(
        kStartCount, 0, kMaxStartCount, 0.35, 0);
    const float kScaleEndValue = 4.0;

    // The size (58.75) was experimentally determined to match up with the size
    // of the chevrons in signup-logo.png.
    ScopedRef<CGPathRef> chevron(MakeChevronPath(58.75));
    ScopedRef<CGMutablePathRef> logo(CGPathCreateMutable());

    const float kRotations[] = { 0, kPi / 2, kPi, 3 * kPi / 2 };
    for (int i = 0; i < ARRAYSIZE(kRotations); ++i) {
      CGAffineTransform t = CGAffineTransformMakeRotation(kRotations[i]);
      CGPathAddPath(logo, &t, chevron);

      CAShapeLayer* l = NewShapeLayer(chevron);
      l.affineTransform = t;
      l.fillColor = (i == 0) ? kTopChevronColor : kChevronColor;
      // We give the chevrons a small stroke width in order to ensure that they
      // are slightly larger than the "logo" chevrons eliminating the
      // possiblity of gaps.
      l.lineWidth = 1;
      l.opacity = 0;
      l.strokeColor = l.fillColor;
      l.position = self.boundsCenter;
      [self.layer addSublayer:l];

      CAKeyframeAnimation* scale =
          [CAKeyframeAnimation animationWithKeyPath:@"transform.scale"];
      scale.keyTimes = Array(kScaleStartTime, 1.0);
      scale.values = Array(1.0, kScaleEndValue);

      CAKeyframeAnimation* opacity =
          [CAKeyframeAnimation animationWithKeyPath:@"opacity"];
      opacity.keyTimes = Array(0.0, kScaleStartTime);
      opacity.values = Array(1.0, 0.0);

      CAAnimationGroup* animation = [CAAnimationGroup animation];
      animation.animations = Array(scale, opacity);
      animation.duration = kDuration;
      animation.timingFunction =
          [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseIn];

      [l addAnimation:animation forKey:NULL];
    }

    CGPathAddRect(logo, NULL,
                  CGRectOffset(self.bounds,
                               -self.boundsWidth / 2,
                               -self.boundsHeight / 2));
    CAShapeLayer* l = NewShapeLayer(logo);
    l.fillColor = kStartupBackgroundColor;
    l.fillRule = kCAFillRuleEvenOdd;
    l.opacity = 0;
    l.position = self.boundsCenter;
    [self.layer addSublayer:l];

    CAKeyframeAnimation* scale =
        [CAKeyframeAnimation animationWithKeyPath:@"transform.scale"];
    scale.keyTimes = Array(kScaleStartTime, 1.0);
    scale.values = Array(1.0, kScaleEndValue);

    CAKeyframeAnimation* opacity =
        [CAKeyframeAnimation animationWithKeyPath:@"opacity"];
    opacity.keyTimes = Array(0.0, kScaleStartTime, 1.0);
    opacity.values = Array(1.0, 1.0, 0.0);

    CAAnimationGroup* animation = [CAAnimationGroup animation];
    animation.animations = Array(scale, opacity);
    animation.delegate = self;
    animation.duration = kDuration;
    animation.timingFunction =
        [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseIn];

    [l addAnimation:animation forKey:NULL];

    const CFTimeInterval paused_time =
        [self.layer convertTime:CACurrentMediaTime() fromLayer:NULL];
    self.layer.speed = 0;
    self.layer.timeOffset = paused_time;
  }
  return self;
}

- (void)animationDidStop:(CAAnimation*)animation
                finished:(BOOL)finished {
#if TARGET_IPHONE_SIMULATOR
  if (0) {
    for (CALayer* l in self.layer.sublayers) {
      if ([l isKindOfClass:[CAShapeLayer class]]) {
        l.opacity = 1;
      }
    }
    // Render our superview which contains the top-left and top-right corner
    // images.
    LOG("writing default images (Default.png, Default@2x.png, "
        "Default-568@2x.png to %s", TmpDir());
    WriteDataToFile(
        JoinPath(TmpDir(), "Default.png"),
        UIImagePNGRepresentation(
            MakeImageFromView(self, kStartupBackgroundColor, CGSizeMake(320, 480), 1)));
    WriteDataToFile(
        JoinPath(TmpDir(), "Default@2x.png"),
        UIImagePNGRepresentation(
            MakeImageFromView(self, kStartupBackgroundColor, CGSizeMake(320, 480), 2)));
    WriteDataToFile(
        JoinPath(TmpDir(), "Default-568h@2x.png"),
        UIImagePNGRepresentation(
            MakeImageFromView(self, kStartupBackgroundColor, CGSizeMake(320, 568), 2)));
  }
#endif  // TARGET_IPHONE_SIMULATOR

  [self removeFromSuperview];
}

- (void)startAnimation {
  if (self.layer.speed != 0) {
    return;
  }
  const CFTimeInterval paused_time = self.layer.timeOffset;
  self.layer.speed = 1.0;
  self.layer.timeOffset = 0.0;
  self.layer.beginTime = 0.0;
  self.layer.beginTime =
      [self.layer convertTime:CACurrentMediaTime() fromLayer:NULL] - paused_time;
}

@end  // StartupView

@implementation RootViewController

@synthesize cameraController = camera_view_controller_;
@synthesize composeLayoutController = compose_layout_controller_;
@synthesize conversationLayoutController = conversation_layout_controller_;
@synthesize currentViewController = current_view_controller_;
@synthesize photoLayoutController = photo_layout_controller_;
@synthesize prevViewController = prev_view_controller_;
@synthesize settingsViewController = settings_view_controller_;
@synthesize statusBar = status_bar_;
@synthesize summaryLayoutController = summary_layout_controller_;

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;

    // Watch for day table updates in order to set the unviewed
    // conversation alert notification.
    __weak RootViewController* weak_self = self;
    state_->day_table()->update()->Add(^{
        dispatch_after_main(0, ^{
            [weak_self processDayTableUpdate];
          });
      });

    camera_view_controller_ =
        [[CameraViewController alloc] initWithState:state_];
    compose_layout_controller_ =
        [[ComposeLayoutController alloc] initWithState:state_];
    contacts_controller_ =
        [[ContactsController alloc] initWithState:state];
    conversation_layout_controller_ =
        NewConversationLayoutController(state_);
    photo_layout_controller_ =
        NewPhotoLayoutController(state_);
    settings_view_controller_ =
        [[SettingsViewController alloc] initWithState:state_];
    summary_layout_controller_ =
        [[SummaryLayoutController alloc] initWithState:state_];

    controllers_.push_back(summary_layout_controller_);
    controllers_.push_back(conversation_layout_controller_);
    controllers_.push_back(photo_layout_controller_);
    controllers_.push_back(camera_view_controller_);
    controllers_.push_back(compose_layout_controller_);
    controllers_.push_back(settings_view_controller_);
    controllers_.push_back(contacts_controller_);

    // Push the summary layout controller on the top of the stack.
    view_controller_stack_.push_back(
        std::make_pair(summary_layout_controller_, ControllerTransition()));
    current_view_controller_ = summary_layout_controller_;
    prev_view_controller_ = NULL;
  }
  return self;
}

- (BOOL)shouldAutorotate {
  return NO;
}

- (NSUInteger)supportedInterfaceOrientations {
  return UIInterfaceOrientationMaskPortrait;
}

- (void)didReceiveMemoryWarning {
  [super didReceiveMemoryWarning];
  LOG("root: did receive memory warning");
}

- (void)loadView {
  self.view = [UIView new];
  self.view.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  self.view.autoresizesSubviews = YES;

  [self.view addSubview:current_view_controller_.view];

  StartupView* startup_view =
      [[StartupView alloc] initWithFrame:[UIScreen mainScreen].bounds];
  [self.view addSubview:startup_view];
  startup_view_ = startup_view;

  // iOS logs a warning message if we create the status bar window inline.
  dispatch_after_main(0, ^{
      status_bar_ = [StatusBar new];
    });
}

- (void)viewDidUnload {
  [super viewDidUnload];
}

- (void)viewWillAppear:(BOOL)animated {
  [self viewDidLayoutSubviews];

  if (self != current_view_controller_.parentViewController) {
    [self addChildViewController:current_view_controller_];
    [current_view_controller_ didMoveToParentViewController:self];
  }
  current_view_controller_.view.frame =
      state_->ControllerFrame(current_view_controller_);
  [super viewWillAppear:animated];
}

- (void)viewDidAppear:(BOOL)animated {
  [super viewDidAppear:animated];
}

- (void)viewWillDisappear:(BOOL)animated {
  [super viewWillDisappear:animated];
}

- (void)viewDidLayoutSubviews {
  [super viewDidLayoutSubviews];
  // The obvious way to make the RootViewController take up the full screen is
  // to set "self.wantsFullScreenLayout = YES". Unfortunately, this setting has
  // a bad interaction with transitionFromViewController and causes an
  // unexpected setFrame on the transitioned view controller's view. If that
  // view has a non-identity transform all sorts of UI badness can occur.
  //
  // This isn't necessary on iOS 7 because the default state is for the root view
  // controller to take up the whole screen, and setting the frame here causes problems
  // when the status bar changes size (during a phone call).
  if (kSDKVersion < "7" || kIOSVersion < "7") {
    self.view.frame = [UIScreen mainScreen].bounds;
  }
}

- (void)dismissViewControllerAnimated:(BOOL)flag
                           completion:(void (^)(void))completion
                            withState:(ControllerState)state {
  // Refuse to pop the stack past the summary layout controller.
  if (view_controller_stack_.size() == 1) {
    return;
  }

  ControllerTransition transition = view_controller_stack_.back().second;
  transition.state = state;
  transition.reverse = true;

  view_controller_stack_.pop_back();
  UIViewController* new_view_controller = view_controller_stack_.back().first;
  ControllerTransition orig_transition = view_controller_stack_.back().second;

  [self showViewController:new_view_controller
            withTransition:transition];

  // Restore original transition.
  view_controller_stack_.back().second = orig_transition;
}

- (void)dismissViewControllerAnimated:(BOOL)flag
                           completion:(void (^)(void))completion {
  // RootViewController manages its own stack of view controllers, separate from UIViewController's
  // presentViewController stack.  This method is used in both cases.
  // TODO(ben): do we need to overload this method or can we use a different method for our own stack?
  if (self.presentedViewController) {
    [super dismissViewControllerAnimated:flag completion:completion];
  } else {
    [self dismissViewControllerAnimated:flag
                             completion:completion
                              withState:ControllerState()];
  }
}

- (void)showAddContacts:(ControllerTransition)transition {
  contacts_controller_.requestedPage = ADD_CONTACTS;
  [self pushViewController:contacts_controller_
            withTransition:transition];
}

- (void)showCamera:(ControllerTransition)transition {
  [self pushViewController:camera_view_controller_
            withTransition:transition];
}

- (void)showCompose:(ControllerTransition)transition {
  [self pushViewController:compose_layout_controller_
            withTransition:transition];
}

- (void)showContacts:(ControllerTransition)transition {
  contacts_controller_.requestedPage = CONTACTS_LIST;
  [self pushViewController:contacts_controller_
            withTransition:transition];
}

- (void)showConversation:(ControllerTransition)transition {
  [self pushViewController:conversation_layout_controller_
            withTransition:transition];
}

- (void)showMyInfo:(ControllerTransition)transition {
  contacts_controller_.requestedPage = MY_INFO;
  [self pushViewController:contacts_controller_
            withTransition:transition];
}

- (void)showPhoto:(ControllerTransition)transition {
  [self pushViewController:photo_layout_controller_
            withTransition:transition];
}

- (void)showSettings:(ControllerTransition)transition {
  [self pushViewController:settings_view_controller_
            withTransition:transition];
}

- (void)showSummaryLayout:(ControllerTransition)transition {
  // Start the startup animation the first time the summary layout is shown.
  [startup_view_ startAnimation];

  if (current_view_controller_ != summary_layout_controller_) {
    [self pushViewController:summary_layout_controller_
              withTransition:transition];
  }
}

- (void)showDashboard:(ControllerTransition)transition {
  // Start the startup animation the first time the dashboard is shown.
  [startup_view_ startAnimation];

  if (current_view_controller_ == summary_layout_controller_) {
    [summary_layout_controller_ setCurrentView:PAGE_PROFILE animated:YES];
  } else {
    [summary_layout_controller_ setCurrentView:PAGE_PROFILE animated:NO];
    [self pushViewController:summary_layout_controller_
              withTransition:transition];
  }
}

- (void)showInbox:(ControllerTransition)transition {
  if (current_view_controller_ == summary_layout_controller_) {
    [summary_layout_controller_ setCurrentView:PAGE_INBOX animated:YES];
  } else {
    [summary_layout_controller_ setCurrentView:PAGE_INBOX animated:NO];
    [self pushViewController:summary_layout_controller_
              withTransition:transition];
  }
}

- (UIViewController*)popViewController {
  return view_controller_stack_.size() > 1 ?
      view_controller_stack_[view_controller_stack_.size() - 2].first :
      view_controller_stack_[0].first;
}

- (void)dismissViewController:(ControllerState)state {
  [self dismissViewControllerAnimated:YES completion:NULL withState:state];
}

- (ControllerState)popControllerState {
  if ([self.popViewController isKindOfClass:[LayoutController class]]) {
    return ((LayoutController*)self.popViewController).controllerState;
  }
  return ControllerState();
}

- (void)showAlertNotificationOfType:(AlertNotificationType)type
                    withAlertString:(const string&)alert_str
                       withCallback:(AlertNotificationBlock)block {
  [alert_notification_ remove];
  alert_notification_ =
      [[AlertNotificationView alloc]
                          initWithType:type
                       withAlertString:alert_str
                           withTimeout:kDefaultAlertTimeout
                          withCallback:block];
  alert_notification_.frame = CGRectMake(
      0, 0, self.currentViewController.view.frameWidth,
      alert_notification_.height);
  [self.currentViewController.view addSubview:alert_notification_];
  [alert_notification_ show];
}

- (bool)isActiveConversation:(int64_t)viewpoint_id {
  if (self.currentViewController != self.conversationLayoutController) {
    return false;
  }
  const int64_t current_viewpoint_id =
      self.conversationLayoutController.controllerState.current_viewpoint;
  return current_viewpoint_id == viewpoint_id;
}

- (void)processDayTableUpdate {
  // Don't process updates if state is not OK.
  if (state_->view_state() != STATE_OK) {
    return;
  }

  DayTable::SnapshotHandle snapshot = state_->day_table()->GetSnapshot(NULL);
  std::unordered_set<int64_t> old_unviewed_convos = unviewed_convos_;
  unviewed_convos_.clear();

  // Find the set (if any) of newly unviewed conversations.
  int newly_unviewed_count = 0;
  int64_t first_vp_id = 0;

  for (int i = 0; i < snapshot->unviewed_conversations()->row_count(); ++i) {
    SummaryRow row;
    if (!snapshot->unviewed_conversations()->GetSummaryRow(i, &row)) {
      continue;
    }
    const int64_t vp_id = row.identifier();
    if (!first_vp_id) {
      first_vp_id = vp_id;
    }
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
        vp_id, snapshot->db());
    if (!ContainsKey(old_unviewed_convos, vp_id) &&
        ![self isActiveConversation:vp_id] &&
        !vh->label_muted()) {
      ++newly_unviewed_count;
    }
    unviewed_convos_.insert(vp_id);
  }

  // Only bother with alerts if we're not already viewing the inbox
  // (but update unviewed_convos_ regardless).
  if (current_view_controller_ == summary_layout_controller_ &&
      summary_layout_controller_.summaryPage == PAGE_INBOX) {
    return;
  }

  // Find the set of newly viewed conversations.
  int newly_viewed_count = 0;
  for (auto iter = old_unviewed_convos.begin();
       iter != old_unviewed_convos.end();
       ++iter) {
    if (!ContainsKey(unviewed_convos_, *iter)) {
      ++newly_viewed_count;
    }
  }

  // Update alert if there are any newly unviewed convos or there are
  // newly viewed convos, but unviewed ones remain and alert is visible.
  const int unviewed_count =
      snapshot->unviewed_conversations()->row_count();
  if (newly_unviewed_count ||
      (unviewed_count && newly_viewed_count && alert_notification_.active)) {
    const string alert_str =
        Format("%d unread conversation%s", unviewed_count, Pluralize(unviewed_count));
    [self showAlertNotificationOfType:ALERT_NOTIFICATION_NEW
                      withAlertString:alert_str
                         withCallback:^{
        ControllerState state;
        state.current_viewpoint = first_vp_id;
        [self showInbox:state];
      }];
  } else if (!unviewed_count) {
    // Otherwise, if there are now no unviewed conversations,
    // immediately remove the alert.
    [alert_notification_ remove];
  }
}

- (void)pushViewController:(UIViewController*)new_view_controller
            withTransition:(ControllerTransition)transition {
  [self showViewController:new_view_controller
            withTransition:transition];
}

- (void)showViewController:(UIViewController*)new_view_controller
            withTransition:(ControllerTransition)transition {
  // If applicable, set layout controller state for the new view controller.
  if ([new_view_controller isKindOfClass:[LayoutController class]]) {
    ((LayoutController*)new_view_controller).controllerState = transition.state;
  }

  // If we're already showing the specified controller, or we're in
  // the process of animating the transition, ignore the request.
  if (new_view_controller == current_view_controller_ ||
      disable_user_interaction_count_ > 0) {
    return;
  }

  // Search from the bottom of the stack to the top and remove any
  // prior occurrence of new_view_controller. Then push
  // new_view_controller onto the stack. The end result is that
  // new_view_controller will appear on the stack exactly once at the
  // top.
  //
  // Also, remove any occurence of the compose layout controller--it
  // should never remain as history in the stack. The one excpetion
  // to this rule is pushing the camera controller.
  for (int i = 0; i < view_controller_stack_.size(); ++i) {
    if (view_controller_stack_[i].first == new_view_controller ||
        (new_view_controller != camera_view_controller_ &&
         view_controller_stack_[i].first == compose_layout_controller_)) {
      view_controller_stack_.erase(view_controller_stack_.begin() + i);
      --i;
    }
  }

  view_controller_stack_.push_back(std::make_pair(new_view_controller, transition));

  prev_view_controller_ = current_view_controller_;
  current_view_controller_ = new_view_controller;
  [self addChildViewController:new_view_controller];

  float delta_x = 0;
  float delta_y = 0;
  bool set_frame = true;
  bool over = false;

  UIView* sibling_view = NULL;
  TransitionType type = transition.reverse ?
                        ReverseTransition(transition.type) :
                        transition.type;

  // Set initial conditions based on transition type.
  switch (type) {
    case TRANSITION_DEFAULT: {
      const int current_index = [self controllerIndex:prev_view_controller_];
      const int new_index = [self controllerIndex:current_view_controller_];
      delta_x = (current_index > new_index) ? 1 : -1;
      break;
    }
    case TRANSITION_FADE_IN:
      if (!transition.reverse) {
        current_view_controller_.view.alpha = 0;
      } else {
        current_view_controller_.view.alpha = 1;
        sibling_view = prev_view_controller_.view;
      }
      break;
    case TRANSITION_SHOW_FROM_RECT:
      if (!transition.reverse) {
        // Set frame to start, then apply scale transform.
        current_view_controller_.view.frame =
            state_->ControllerFrame(current_view_controller_);
        set_frame = false;  // do not set the frame if we have non-identity transform
        const float scale = 1.0 / prev_view_controller_.view.boundsHeight;
        current_view_controller_.view.transform =
            CGAffineTransformMakeScale(scale, scale);
        current_view_controller_.view.center =
            CGPointMake(CGRectGetMidX(transition.rect), CGRectGetMidY(transition.rect));
        current_view_controller_.view.layer.shouldRasterize = YES;
        current_view_controller_.view.layer.rasterizationScale = [UIScreen mainScreen].scale;
      } else {
        sibling_view = prev_view_controller_.view;
        prev_view_controller_.view.layer.shouldRasterize = YES;
        prev_view_controller_.view.layer.rasterizationScale = [UIScreen mainScreen].scale;
      }
      break;
    case TRANSITION_SLIDE_OVER_UP:
      over = true;
      // Fall through.
    case TRANSITION_SLIDE_UP:
      delta_y = -1;
      break;
    case TRANSITION_SLIDE_OVER_LEFT:
      over = true;
      // Fall through.
    case TRANSITION_SLIDE_LEFT:
      delta_x = 1;
      break;
    case TRANSITION_SLIDE_OVER_DOWN:
      over = true;
      // Fall through.
    case TRANSITION_SLIDE_DOWN:
      delta_y = 1;
      break;
    case TRANSITION_SLIDE_OVER_RIGHT:
      over = true;
      // Fall through.
    case TRANSITION_SLIDE_RIGHT:
      delta_x = -1;
      break;
  }

  // Make sure we set sibling view if we're reversing a slide
  // "over" transition.
  if (transition.reverse && over) {
    sibling_view = prev_view_controller_.view;
  }

  const bool uinavigation_controller =
      [current_view_controller_ isKindOfClass:[UINavigationController class]];

  if (uinavigation_controller) {
    // NOTE(peter): In order for UINavigationController to correctly size its
    // navigation bar, [UINavigationController view] must be added to the view
    // hierarchy before its position and size are set.
    //
    // TODO(peter): This causes UIKit to emit the following warning:
    //
    //    Unbalanced calls to begin/end appearance transitions for <...>
    //
    // This appears to be harmless. I can't figure out how to get rid of it.
    if (sibling_view) {
      [self.view insertSubview:current_view_controller_.view
                  belowSubview:sibling_view];
    } else {
      [self.view addSubview:current_view_controller_.view];
    }
  }

  // We always offset the current view unless we're reversing a previous
  // slide "over", in which case the current view should be already
  // positioned and only slated to be revealed.
  if (set_frame) {
    if (transition.reverse && over) {
      current_view_controller_.view.frame =
          state_->ControllerFrame(current_view_controller_);
    } else {
      current_view_controller_.view.frame =
          CGRectOffset(state_->ControllerFrame(current_view_controller_),
                       -delta_x * current_view_controller_.view.boundsWidth,
                       -delta_y * current_view_controller_.view.boundsHeight);
    }
  }

  [self disableUserInteraction];
  [self transitionFromViewController:prev_view_controller_
                    toViewController:current_view_controller_
                            duration:0.3
                             options:0
                          animations:^{
      if (!uinavigation_controller) {
        if (sibling_view) {
          [self.view insertSubview:current_view_controller_.view
                      belowSubview:sibling_view];
        } else {
          [self.view addSubview:current_view_controller_.view];
        }
      }

      current_view_controller_.view.alpha = 1;
      if (![current_view_controller_ animateTransitionCommit]) {
        // Reverse conditions.
        if (type == TRANSITION_SHOW_FROM_RECT) {
          if (!transition.reverse) {
            current_view_controller_.view.transform = CGAffineTransformIdentity;
            current_view_controller_.view.frame =
                state_->ControllerFrame(current_view_controller_);
          } else {
            const float scale = 1.0 / prev_view_controller_.view.boundsHeight;
            prev_view_controller_.view.transform = CGAffineTransformMakeScale(scale, scale);
            prev_view_controller_.view.center =
                CGPointMake(CGRectGetMidX(transition.rect), CGRectGetMidY(transition.rect));
          }
        } else if (type == TRANSITION_FADE_IN) {
          if (transition.reverse) {
            prev_view_controller_.view.alpha = 0;
          }
        } else {
          current_view_controller_.view.frame =
              state_->ControllerFrame(current_view_controller_);
          // If this is a forward slide "over", we don't move the previous controller.
          if (!(!transition.reverse && over)) {
            prev_view_controller_.view.frame =
                CGRectOffset(state_->ControllerFrame(prev_view_controller_),
                             delta_x * prev_view_controller_.view.boundsWidth,
                             delta_y * prev_view_controller_.view.boundsHeight);
          }
        }
      }
      [prev_view_controller_ willMoveToParentViewController:NULL];
      [prev_view_controller_ removeFromParentViewController];

      if (prev_view_controller_.statusBarLightContent !=
          current_view_controller_.statusBarLightContent) {
        [status_bar_ setLightContent:current_view_controller_.statusBarLightContent
                            animated:true];
      }
      if (prev_view_controller_.statusBarHidden !=
          current_view_controller_.statusBarHidden) {
        [status_bar_ setHidden:current_view_controller_.statusBarHidden
                      animated:true];
      }
    }
                         completion:^(BOOL finished) {
      current_view_controller_.view.layer.shouldRasterize = NO;
      prev_view_controller_.view.layer.shouldRasterize = NO;
      prev_view_controller_.view.transform = CGAffineTransformIdentity;
      prev_view_controller_.view.alpha = 1;

      [self enableUserInteraction];
      [current_view_controller_ didMoveToParentViewController:self];
    }];
}

- (int)controllerIndex:(UIViewController*)view_controller {
  return std::distance(controllers_.begin(),
                       std::find(controllers_.begin(), controllers_.end(),
                                 view_controller));
}

- (void)disableUserInteraction {
  BeginIgnoringInteractionEvents();
  ++disable_user_interaction_count_;
}

- (void)enableUserInteraction {
  EndIgnoringInteractionEvents();
  --disable_user_interaction_count_;
  CHECK_GE(disable_user_interaction_count_, 0);
}

@end  // RootViewController
