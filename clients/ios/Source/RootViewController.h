// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <unordered_set>
#import <UIKit/UIKit.h>
#import "LayoutController.h"

@class AlertNotificationView;
@class ContactsController;
@class ComposeLayoutController;
@class ConversationLayoutController;
@class InitController;
@class LoginController;
@class StartupView;
@class StatusBar;
@class SummaryLayoutController;

enum TransitionType {
  TRANSITION_DEFAULT,
  TRANSITION_FADE_IN,
  TRANSITION_SHOW_FROM_RECT,
  TRANSITION_SLIDE_UP,
  TRANSITION_SLIDE_OVER_UP,
  TRANSITION_SLIDE_LEFT,
  TRANSITION_SLIDE_OVER_LEFT,
  TRANSITION_SLIDE_DOWN,
  TRANSITION_SLIDE_OVER_DOWN,
  TRANSITION_SLIDE_RIGHT,
  TRANSITION_SLIDE_OVER_RIGHT,
};

struct ControllerTransition {
  TransitionType type;
  ControllerState state;
  CGRect rect;   // set if showing from rect

  bool reverse;  // private

  ControllerTransition()
      : type(TRANSITION_DEFAULT),
        rect(CGRectZero),
        reverse(false) {
  }
  ControllerTransition(TransitionType t)
      : type(t),
        rect(CGRectZero),
        reverse(false) {
  }
  ControllerTransition(ControllerState s)
      : type(TRANSITION_DEFAULT),
        state(s),
        rect(CGRectZero),
        reverse(false) {
  }
};

@interface RootViewController : UIViewController {
 @private
  UIAppState* state_;
  __weak StartupView* startup_view_;
  vector<std::pair<UIViewController*, ControllerTransition> > view_controller_stack_;
  UIViewController* current_view_controller_;
  UIViewController* prev_view_controller_;
  UIViewController* camera_view_controller_;
  ComposeLayoutController* compose_layout_controller_;
  ContactsController* contacts_controller_;
  ConversationLayoutController* conversation_layout_controller_;
  LayoutController* photo_layout_controller_;
  UIViewController* settings_view_controller_;
  SummaryLayoutController* summary_layout_controller_;
  AlertNotificationView* alert_notification_;
  std::vector<UIViewController*> controllers_;
  StatusBar* status_bar_;
  int disable_user_interaction_count_;
  std::unordered_set<int64_t> unviewed_convos_;
}

@property (nonatomic, readonly) UIViewController* cameraController;
@property (nonatomic, readonly) ComposeLayoutController* composeLayoutController;
@property (nonatomic, readonly) ConversationLayoutController* conversationLayoutController;
@property (nonatomic, readonly) UIViewController* currentViewController;
@property (nonatomic, readonly) LayoutController* photoLayoutController;
// View controller when current controller is dismissed.
@property (nonatomic, readonly) UIViewController* popViewController;
// View controller that immediately preceeded current becoming visible.
@property (nonatomic, readonly) UIViewController* prevViewController;
@property (nonatomic, readonly) UIViewController* settingsViewController;
@property (nonatomic, readonly) StatusBar* statusBar;
@property (nonatomic, readonly) SummaryLayoutController* summaryLayoutController;

- (id)initWithState:(UIAppState*)state;
- (void)showAddContacts:(ControllerTransition)transition;
- (void)showCamera:(ControllerTransition)transition;
- (void)showCompose:(ControllerTransition)transition;
- (void)showContacts:(ControllerTransition)transition;
- (void)showConversation:(ControllerTransition)transition;
- (void)showMyInfo:(ControllerTransition)transition;
- (void)showPhoto:(ControllerTransition)transition;
- (void)showSettings:(ControllerTransition)transition;
- (void)showSummaryLayout:(ControllerTransition)transition;
- (void)showDashboard:(ControllerTransition)transition;
- (void)showInbox:(ControllerTransition)transition;
- (void)dismissViewController:(ControllerState)state;
// Accessible if popped view controller was a LayoutController or
// returns an empty controller state.
- (ControllerState)popControllerState;

@end  // RootViewController

// local variables:
// mode: objc
// end:
