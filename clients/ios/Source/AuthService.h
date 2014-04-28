// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "Callback.h"

@interface AuthService : NSObject {
 @private
  CallbackSet session_changed_;
  bool load_needed_;
}

@property (weak, readonly, nonatomic) NSString* serviceName;
@property (weak, readonly, nonatomic) NSString* primaryId;
@property (weak, readonly, nonatomic) NSString* accessToken;
@property (weak, readonly, nonatomic) NSString* refreshToken;
@property (weak, readonly, nonatomic) NSDate* expirationDate;
@property (readonly, nonatomic) bool valid;
@property (readonly, nonatomic) CallbackSet* sessionChanged;

- (void)load;
- (void)loadIfNecessary;
- (void)login:(UINavigationController*)navigation;
- (void)logout;
- (BOOL)handleOpenURL:(NSURL*)url;

@end  // AuthService

// local variables:
// mode: objc
// end:
