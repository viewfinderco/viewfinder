// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "Callback.h"
#import "ScopedNotification.h"
#import "Timer.h"

// The status bar frame when a (phone) call is not active.
CGRect NormalStatusBarFrame();

// The StatusBar class maintains an array of messages, one per message
// type. Lower numbered message types take precedence over higher numbered
// messages types.
enum StatusMessageType {
  STATUS_MESSAGE_UI_HIGH,
  STATUS_MESSAGE_UI,
  STATUS_MESSAGE_NETWORK,
  STATUS_MESSAGE_COUNT,
};

@interface StatusBar : UIWindow {
 @private
  struct MessageData {
    NSString* text;
    bool activity;
    NSTimer* hide_timer;
    WallTimer display_timer;
  };

  UIView* message_;
  UILabel* message_label_;
  MessageData messages_[STATUS_MESSAGE_COUNT];
  UIImageView* activity_indicator_;
  WallTime hide_time_;
  NSTimer* show_timer_;
  ScopedNotification did_become_active_;
}

- (void)setLightContent:(bool)light_content
               animated:(bool)animated;
- (void)setHidden:(bool)hidden
         animated:(bool)animated;
- (void)setMessage:(NSString*)str
          activity:(bool)activity
              type:(StatusMessageType)type;
- (void)setMessage:(NSString*)str
          activity:(bool)activity
              type:(StatusMessageType)type
   displayDuration:(float)display_duration;
- (void)hideMessageType:(StatusMessageType)type
     minDisplayDuration:(float)min_display_duration;
- (void)clearMessages;

@end  // StatusBar

// local variables:
// mode: objc
// end:
