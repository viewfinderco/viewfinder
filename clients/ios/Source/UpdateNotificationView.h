// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

class UIAppState;

@interface UpdateNotificationView : UIView {
 @private
}

+ (void)maybeShow:(UIAppState*)state
           inView:(UIView*)parent;
+ (void)disable:(UIAppState*)state;

@end  // UpdateNotificationView

// local variables:
// mode: objc
// end:
