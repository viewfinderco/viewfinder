// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "ScopedPtr.h"
#import "ScopedRef.h"

class ProdUIAppState;

@interface AppDelegate :
    NSObject <UIApplicationDelegate,
              UITabBarControllerDelegate> {
 @private
  ScopedPtr<ProdUIAppState> state_;
  UIWindow* window_;
  bool becoming_active_;
  bool maintenance_done_;
  bool active_;
}

// Attempts to register the device to receive push notifications. This
// will prompt the user with an iOS dialog asking for push
// notification permission and should ideally be done after some
// explanation to user regarding the purpose of push notifications.
+ (void)registerForPushNotifications;

// Sets the app icon badge number.
+ (void)setApplicationIconBadgeNumber:(int)number;

// Return the unique identifier for this device.
// Only available to dev and adhoc builds, others always return NULL.
+ (NSString*)uniqueIdentifier;

@end  // AppDelegate

// local variables:
// mode: objc
// end:
