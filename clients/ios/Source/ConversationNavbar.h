// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "Callback.h"
#import "ScopedNotification.h"
#import "TextView.h"
#import "ViewpointTable.h"

@class PhotoView;
@class TextView;

@protocol ConversationNavbarEnv
- (void)navbarBeginMessage;
- (void)navbarEndMessage;
- (void)navbarShowDrawer;
- (void)navbarHideDrawer;

- (void)navbarAddPeople:(UIView*)sender;
- (void)navbarAddPhotos:(UIView*)sender;
- (void)navbarExit:(UIView*)sender;
- (void)navbarExport:(UIView*)sender;
- (void)navbarMuteConvo:(UIView*)sender;
- (void)navbarRemoveConvo:(UIView*)sender;
- (void)navbarSend:(UIView*)sender;
- (void)navbarShare:(UIView*)sender;
- (void)navbarUnshare:(UIView*)sender;
- (void)navbarUseCamera:(UIView*)sender;
- (void)navbarUnmuteConvo:(UIView*)sender;
@end  // ConversationNavbarEnv

enum ConversationNavbarState {
  CONVO_NAVBAR_MESSAGE,
  CONVO_NAVBAR_MESSAGE_ACTIVE,
  CONVO_NAVBAR_ACTION,
  CONVO_NAVBAR_BOTTOM_DRAWER,
  CONVO_NAVBAR_TOP_DRAWER,
};

@interface ConversationNavbar : UIView<TextViewDelegate> {
 @private
  __weak id<ConversationNavbarEnv> env_;
  UIView* action_tray_;
  UIView* message_tray_;
  UIImageView* text_container_;
  TextView* text_view_;
  UIView* background_;
  UIView* top_drawer_;
  UIView* bottom_drawer_;
  UIButton* add_;
  UIButton* export_;
  UIButton* exit_;
  UIButton* send_;
  UIButton* share_;
  UIButton* unshare_;
  UIButton* use_camera_;
  UIButton* add_photos_;
  UIButton* add_people_;
  UIButton* remove_;
  UIButton* mute_;
  UIView* keyboard_;
  UIPanGestureRecognizer* pan_;
  UIView* reply_to_photo_;
  ScopedNotification keyboard_did_show_;
  ScopedNotification keyboard_did_hide_;
  ScopedNotification keyboard_will_show_;
  ScopedNotification keyboard_will_hide_;
  CGRect keyboard_frame_;
  CGRect keyboard_window_frame_;
  float text_spacing_;
  CallbackSet changed_;
  ConversationNavbarState navbar_state_;
  float pan_multiple_;
  float relative_pan_y_;
}

@property (nonatomic, readonly) bool actionTray;
@property (nonatomic, readonly) bool keyboardActive;
@property (nonatomic, readonly) CallbackSet* changed;
@property (nonatomic, readonly) float contentInset;
@property (nonatomic, readonly) bool topDrawerOpen;
@property (nonatomic) bool enabled;
@property (nonatomic) UIPanGestureRecognizer* pan;
@property (nonatomic) NSString* text;
@property (nonatomic) PhotoView* replyToPhoto;

- (id)initWithEnv:(id<ConversationNavbarEnv>)env;
- (void)show;
- (void)hide;

- (void)configureFromViewpoint:(const ViewpointHandle&)vh;

// Changes the background color of the input to orange and fades
// it back to black.
- (void)showNotificationGlow;

- (void)showActionTray;
- (void)showMessageTray;

// Manually configure the pan for the case where the conversation
// scroll view exceeds the max scroll offset. The offset specified
// here is the amount the scroll's gone past the max offset in order
// to correctly position the message drawer.
- (void)setPan:(UIPanGestureRecognizer*)p
    withOffset:(float)offset;

@end  // ConversationNavbar

// local variables:
// mode: objc
// end:
