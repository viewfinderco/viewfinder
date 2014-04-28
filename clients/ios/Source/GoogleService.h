// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AuthService.h"

@class GTMOAuth2Authentication;

@interface GoogleService : AuthService {
 @private
  NSString* client_id_;
  NSString* client_secret_;
  GTMOAuth2Authentication* auth_;
}

@property (weak, readonly, nonatomic) NSString* serviceName;
@property (weak, readonly, nonatomic) NSString* primaryId;
@property (weak, readonly, nonatomic) NSString* accessToken;
@property (weak, readonly, nonatomic) NSString* refreshToken;
@property (weak, readonly, nonatomic) NSDate* expirationDate;

- (id)initWithClientId:(NSString*)client_id clientSecret:(NSString*)secret;
- (UIViewController*)newAuthViewController;

@end  // GoogleService

// local variables:
// mode: objc
// end:
