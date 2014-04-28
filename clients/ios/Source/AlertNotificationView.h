// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import <UIKit/UIKit.h>
#import "ValueUtils.h"

// Show an alert notification, visible to every controller in the app.
// which invokes a callback if tapped. The notification is dismissable
// and will disappear on its own if not tapped within a preset time
// interval.
enum AlertNotificationType {
  ALERT_NOTIFICATION_NEW,
};

typedef void (^AlertNotificationBlock)();

@interface AlertNotificationView : UIButton {
 @private
  AlertNotificationBlock block_;
  UIButton* dismiss_;
  float height_;
  bool active_;
}

@property (nonatomic, readonly) float height;
@property (nonatomic, readonly) bool active;

- (id)initWithType:(AlertNotificationType)type
   withAlertString:(const string&)alert_str
       withTimeout:(float)timeout
      withCallback:(AlertNotificationBlock)block;

- (void)show;
- (void)remove;

@end  // AlertNotificationView

// local variables:
// mode: objc
// end:
