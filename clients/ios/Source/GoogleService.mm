// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "GDataServiceGoogleContact.h"
#import "GoogleService.h"
#import "GTMOAuth2SignIn.h"
#import "GTMOAuth2ViewControllerTouch.h"
#import "Logging.h"
#import "StringUtils.h"
#import "ValueUtils.h"

namespace {

NSString* kKeychainName = @"Viewfinder: Google";

}  // namespace

@interface MyGTMOAuth2ViewControllerTouch : GTMOAuth2ViewControllerTouch {
}

@end  // MyGTMOAuth2ViewControllerTouch

@implementation MyGTMOAuth2ViewControllerTouch

- (void)viewDidLoad {
  [super viewDidLoad];
  self.navigationItem.rightBarButtonItem = NULL;
}

@end  // MyGTMOAuth2ViewControllerTouch

@implementation GoogleService

- (id)initWithClientId:(NSString*)client_id
          clientSecret:(NSString*)secret {
  if (self = [super init]) {
    client_id_ = client_id;
    client_secret_ = secret;
  }
  return self;
}

- (NSString*)serviceName {
  return @"Google";
}

- (NSString*)primaryId {
  return [auth_ userEmail];
}

- (NSString*)accessToken {
  return [auth_ accessToken];
}

- (NSString*)refreshToken {
  return [auth_ refreshToken];
}

- (NSDate*)expirationDate {
  return [auth_ expirationDate];
}

- (bool)valid {
  return auth_ != NULL;
}

- (void)load {
  CHECK(dispatch_is_main_thread());
  GTMOAuth2Authentication* auth =
      [GTMOAuth2ViewControllerTouch
           authForGoogleFromKeychainForName:kKeychainName
                                   clientID:client_id_
                               clientSecret:client_secret_];
  if (auth && auth.canAuthorize) {
    auth_ = auth;
    self.sessionChanged->Run();
  }
}

- (void)login:(UINavigationController*)navigation {
  CHECK(dispatch_is_main_thread());
  UIViewController* view_controller = [self newAuthViewController];
  [navigation pushViewController:view_controller animated:YES];
}

- (void)logout {
  CHECK(dispatch_is_main_thread());
  LOG("google: logging out");
  [GTMOAuth2ViewControllerTouch
      removeAuthFromKeychainForName:kKeychainName];
  [GTMOAuth2ViewControllerTouch
      revokeTokenForGoogleAuthentication:auth_];
  auth_ = NULL;
  self.sessionChanged->Run();
}

- (UIViewController*)newAuthViewController {
  CHECK(dispatch_is_main_thread());
  LOG("google: logging in");
  NSString* scope = Format(
      "%s %s",
      [GDataServiceGoogleContact authorizationScope],
      "http://www-opensocial.googleusercontent.com/api/people");
  GTMOAuth2ViewControllerTouch* view_controller =
      [[MyGTMOAuth2ViewControllerTouch alloc]
                        initWithScope:scope
                             clientID:client_id_
                         clientSecret:client_secret_
                     keychainItemName:kKeychainName
                    completionHandler:^(GTMOAuth2ViewControllerTouch* view_controller,
                                        GTMOAuth2Authentication* auth,
                                        NSError* error) {
          if (!error && auth) {
            auth_ = auth;
            self.sessionChanged->Run();
          } else {
            LOG("google: error: %@", error);
            LOG("google: auth: %@", auth);
          }
        }];

  view_controller.signIn.additionalAuthorizationParameters = Dict("hl", "en");
  view_controller.signIn.shouldFetchGoogleUserEmail = YES;
  view_controller.signIn.shouldFetchGoogleUserProfile = YES;
  view_controller.initialHTMLString = @"<html><body bgcolor=white></body></html>";
  return view_controller;
}

@end  // GoogleService
