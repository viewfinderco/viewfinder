// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Appearance.h"
#import "Logging.h"
#import "StatusBar.h"
#import "UIView+geometry.h"

namespace {

const float kShowDuration = 0.15;    // 150 ms
const float kHideDuration = 0.3;     // 300 ms
const float kMinHideDuration = 0.4;  // 400 ms

LazyStaticHexColor kIOS6TextColor = { "#bbbfbf" };
LazyStaticHexColor kIOS7DarkTextColor = { "#000000" };
LazyStaticHexColor kIOS7LightTextColor = { "#ffffff" };

const int kIOS6FontSize = 14;
const int kIOS7FontSize = 12;

}  // namespace

CGRect NormalStatusBarFrame() {
  // Note that the status bar height (as reported by "[UIApplication
  // sharedApplication].statusBarFrame") changes to 40 when the user is
  // actively in a call. If the app is started when a call is active, we do not
  // want our status_bar_height_ field to be initialized to 40.
  CGRect f = [UIApplication sharedApplication].statusBarFrame;
  f.size.height = 20;
  return f;
}

@implementation StatusBar

- (id)init {
  const CGRect f = NormalStatusBarFrame();
  if (self = [super initWithFrame:f]) {
    self.windowLevel = UIWindowLevelStatusBar + 1;
    self.hidden = NO;
    self.userInteractionEnabled = NO;

    message_ = [UIView new];
    message_.alpha = 0;
    if (kIOSVersion >= "7") {
      message_.backgroundColor = [UIColor clearColor];
    } else {
      message_.backgroundColor = [UIColor blackColor];
    }
    message_.frame = self.bounds;
    [self addSubview:message_];

    message_label_ = [UILabel new];
    message_label_.backgroundColor = [UIColor clearColor];
    message_label_.frame = CGRectInset(message_.bounds, 8, 0);
    message_label_.textAlignment = NSTextAlignmentCenter;
    // TODO(peter): Should we use our custom font. This is currently the same
    // as the iOS status bar font.
    if (kIOSVersion >= "7") {
      message_label_.font = [UIFont boldSystemFontOfSize:kIOS7FontSize];
      message_label_.textColor = kIOS7LightTextColor;
    } else {
      message_label_.font = [UIFont boldSystemFontOfSize:kIOS6FontSize];
      message_label_.textColor = kIOS6TextColor;
    }
    [message_ addSubview:message_label_];

    // TODO(peter): The iOS network activity indicator is smaller than
    // UIActivityIndicatorView. We really need a custom activity indicator here
    // as UIActivityIndicatorView refuses to scale down smaller than 20x20.
    activity_indicator_ =
        [[UIImageView alloc] initWithImage:
               [UIImage animatedImageNamed:@"spinner"
                                  duration:1]];
    // Experimentally determined value for the left edge of text in the iOS
    // status bar.
    activity_indicator_.frameLeft = 4;
    activity_indicator_.frameTop =
        (self.boundsHeight - activity_indicator_.frameHeight) / 2;
    activity_indicator_.hidden = YES;
    [message_ addSubview:activity_indicator_];
  }
  return self;
}

- (void)setLightContent:(bool)light_content
               animated:(bool)animated {
  UIColor* color;
  UIStatusBarStyle style;
  if (light_content) {
    color = kIOS7DarkTextColor;
    style = UIStatusBarStyleDefault;
  } else {
    color = kIOS7LightTextColor;
    style = UIStatusBarStyleLightContent;
  }
  if (animated) {
    [UIView animateWithDuration:kHideDuration
                     animations:^{
        message_label_.textColor = color;
      }];
    [[UIApplication sharedApplication]
          setStatusBarStyle:style
                   animated:YES];
  } else {
    message_label_.textColor = color;
    [UIApplication sharedApplication].statusBarStyle = style;
  }
}

- (void)setHidden:(bool)hidden
         animated:(bool)animated {
  // The iOS status bar should remain hidden if a message is currently being
  // displayed.
  const BOOL status_bar_hidden =
      (message_.alpha == 1) ? YES : hidden;
  if (animated) {
    [UIView animateWithDuration:kHideDuration
                     animations:^{
        self.alpha = hidden ? 0 : 1;
      }];
    [[UIApplication sharedApplication]
          setStatusBarHidden:status_bar_hidden
               withAnimation:UIStatusBarAnimationFade];
  } else {
    self.alpha = hidden ? 0 : 1;
    [UIApplication sharedApplication].statusBarHidden = status_bar_hidden;
  }
}

- (int)messageIndex {
  for (int i = 0; i < ARRAYSIZE(messages_); ++i) {
    if (!ToSlice(messages_[i].text).empty()) {
      return i;
    }
  }
  return -1;
}

- (bool)messageActivity {
  const int index = self.messageIndex;
  if (index == -1) {
    return false;
  }
  return messages_[index].activity;
}

- (NSString*)messageLabelText {
  const int index = self.messageIndex;
  if (index == -1) {
    return NULL;
  }
  return messages_[index].text;
}

- (void)updateActivity {
  if (self.messageActivity) {
    [activity_indicator_ startAnimating];
    activity_indicator_.hidden = NO;
  } else {
    [activity_indicator_ stopAnimating];
    activity_indicator_.hidden = YES;
  }
}

- (void)showMessageInternal {
  [show_timer_ invalidate];
  show_timer_ = NULL;

  [[UIApplication sharedApplication]
    setStatusBarHidden:YES
         withAnimation:UIStatusBarAnimationFade];
  [UIView animateWithDuration:kShowDuration
                        delay:0
                      options:UIViewAnimationOptionBeginFromCurrentState
                   animations:^{
      message_.alpha = 1;
    }
                   completion:NULL];
}

- (void)setMessage:(NSString*)str
          activity:(bool)activity
              type:(StatusMessageType)type {
  [messages_[type].hide_timer invalidate];
  messages_[type].hide_timer = NULL;
  messages_[type].display_timer.Restart();
  messages_[type].text = str;
  messages_[type].activity = activity;
  message_label_.text = self.messageLabelText;
  [self updateActivity];

  if (show_timer_) {
    return;
  }

  if (message_.alpha == 0) {
    const WallTime delay = std::max<WallTime>(
        0.01, hide_time_ + kMinHideDuration - WallTime_Now());
    show_timer_ =
        [NSTimer scheduledTimerWithTimeInterval:delay
                                         target:self
                                       selector:@selector(showMessageInternal)
                                       userInfo:NULL
                                        repeats:NO];
    [[NSRunLoop currentRunLoop] addTimer:show_timer_
                                 forMode:UITrackingRunLoopMode];
  }
}

- (void)setMessage:(NSString*)str
          activity:(bool)activity
              type:(StatusMessageType)type
   displayDuration:(float)display_duration {
  [self setMessage:str
          activity:activity
              type:type];
  [self hideMessageType:type
     minDisplayDuration:display_duration];
}

- (void)hideMessageInternal:(NSTimer*)timer {
  int i;
  for (i = 0; i < ARRAYSIZE(messages_); ++i) {
    if (messages_[i].hide_timer == timer) {
      break;
    }
  }
  if (i == ARRAYSIZE(messages_)) {
    // Our timer was cancelled already?
    return;
  }

  [show_timer_ invalidate];
  show_timer_ = NULL;
  [messages_[i].hide_timer invalidate];
  messages_[i].hide_timer = NULL;
  messages_[i].text = NULL;

  NSString* text = self.messageLabelText;
  [self updateActivity];

  if (text) {
    message_label_.text = text;
  } else {
    hide_time_ = WallTime_Now();
    if (self.alpha != 0) {
      [[UIApplication sharedApplication]
        setStatusBarHidden:NO
             withAnimation:UIStatusBarAnimationFade];
    }
    [UIView animateWithDuration:kHideDuration
                          delay:0
                        options:UIViewAnimationOptionBeginFromCurrentState
                     animations:^{
        message_.alpha = 0;
      }
                     completion:NULL];
  }
}

- (void)hideMessageType:(StatusMessageType)type
     minDisplayDuration:(float)min_display_duration {
  if (messages_[type].hide_timer) {
    return;
  }
  const WallTime elapsed = messages_[type].display_timer.Get();
  const WallTime delay = std::max<float>(0.01, min_display_duration - elapsed);
  messages_[type].hide_timer =
      [NSTimer scheduledTimerWithTimeInterval:delay
                                       target:self
                                     selector:@selector(hideMessageInternal:)
                                     userInfo:NULL
                                      repeats:NO];
}

- (void)clearMessages {
  [show_timer_ invalidate];
  show_timer_ = NULL;
  for (int i = 0; i < ARRAYSIZE(messages_); ++i) {
    if (messages_[i].hide_timer) {
      [messages_[i].hide_timer invalidate];
      messages_[i].hide_timer = NULL;
    }
    messages_[i].text = NULL;
  }
  message_.alpha = 0;
  if (self.alpha != 0) {
    [UIApplication sharedApplication].statusBarHidden = NO;
  }
}

@end  // StatusBar
