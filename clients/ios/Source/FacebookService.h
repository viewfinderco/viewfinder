// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AuthService.h"
#import "Facebook.h"

@interface FacebookService
    : AuthService <FBRequestDelegate,
                   FBSessionDelegate> {
 @private
  Facebook* facebook_;
  NSString* primary_id_;
}

- (id)initWithAppId:(NSString*)app_id;
- (BOOL)handleOpenURL:(NSURL*)url;

@end  // FacebookService

// local variables:
// mode: objc
// end:
