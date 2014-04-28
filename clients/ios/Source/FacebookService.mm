// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "FacebookService.h"
#import "KeychainUtils.h"
#import "Logging.h"
#import "ValueUtils.h"

namespace {

typedef void (^SuccessBlock)(FBRequest* request, id result);
typedef void (^ErrorBlock)(FBRequest* request, NSError* error);

const string kFacebookService = "Viewfinder: Facebook";
NSString* kAccessTokenKey = @"FBAccessTokenKey";
NSString* kExpirationDateKey = @"FBExpirationDateKey";
NSString* kPrimaryIdKey = @"FBPrimaryIdKey";

bool SetSecureItem(NSDictionary* d) {
  if (!SetKeychainItem(kFacebookService, d)) {
    return false;
  }
  DCHECK([GetKeychainItem(kFacebookService) isEqualToDictionary:d]);
  return true;
}

NSDictionary* GetSecureItem() {
  NSDictionary* d = GetKeychainItem(kFacebookService);
  if (d) {
    return d;
  }
  // TODO(pmattis): This upgrade code can go away at some point.
  NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
  NSString* access_token = [defaults objectForKey:kAccessTokenKey];
  NSDate* expiration_date = [defaults objectForKey:kExpirationDateKey];
  if (!access_token || !expiration_date) {
    return NULL;
  }
  Dict t(kAccessTokenKey, access_token,
         kExpirationDateKey, expiration_date);
  NSString* primary_id = [defaults objectForKey:kPrimaryIdKey];
  if (primary_id) {
    t.insert(kPrimaryIdKey, primary_id);
  }
  if (SetSecureItem(t)) {
    [defaults removeObjectForKey:kAccessTokenKey];
    [defaults removeObjectForKey:kExpirationDateKey];
    [defaults removeObjectForKey:kPrimaryIdKey];
    [defaults synchronize];
  }
  return t;
}

void DeleteSecureItem() {
  DeleteKeychainItem(kFacebookService);
  DCHECK(!GetSecureItem());
}

}  // namespace

@interface FacebookList : NSObject <FBRequestDelegate> {
 @private
  SuccessBlock success_;
  ErrorBlock error_;
}

- (id)initWithSuccess:(SuccessBlock)success
                error:(ErrorBlock)error;

@end  // FacebookList

@implementation FacebookList

- (id)initWithSuccess:(SuccessBlock)success
                error:(ErrorBlock)error {
  if (self = [super init]) {
    success_ = [success copy];
    error_ = [error copy];
  }
  return self;
}

- (void)request:(FBRequest*)request
didReceiveResponse:(NSURLResponse*)response {
}

- (void)request:(FBRequest*)request
        didLoad:(id)result {
  success_(request, result);
}

- (void)request:(FBRequest*)request
didFailWithError:(NSError*)error {
  error_(request, error);
}

@end  // FacebookList

@interface FacebookService (internal)
- (void)fbSessionStart;
- (void)fbSessionStop;
@end  //  FacebookService (internal)

@implementation FacebookService

- (id)initWithAppId:(NSString*)app_id {
  if (self = [super init]) {
    facebook_ = [[Facebook alloc] initWithAppId:app_id andDelegate:self];
  }
  return self;
}

- (NSString*)serviceName {
  return @"Facebook";
}

- (NSString*)primaryId {
  return primary_id_;
}

- (NSString*)accessToken {
  return [facebook_ accessToken];
}

- (NSString*)refreshToken {
  return NULL;
}

- (NSDate*)expirationDate {
  return [facebook_ expirationDate];
}

- (bool)valid {
  return [facebook_ isSessionValid] && primary_id_ != NULL;
}

- (void)fbSessionStart {
  if (![facebook_ isSessionValid]) {
    return;
  }

  __block FacebookList* list =
      [[FacebookList alloc] initWithSuccess:^(FBRequest* request, id result) {
          NSDictionary* d = result;
          primary_id_ = [d objectForKey:@"name"];
          if (!primary_id_) {
            primary_id_ = [d objectForKey:@"email"];
          }
          Dict secure_item = GetSecureItem();
          secure_item = secure_item.clone();
          secure_item.insert(kPrimaryIdKey, primary_id_);
          SetSecureItem(secure_item);
          self.sessionChanged->Run();
          list = NULL;
        }
                                      error:^(FBRequest* request, NSError* error) {
          // TODO(pmattis): What to do here? Try again later?
          LOG("facebook: me error: %@", error);
          list = NULL;
        }];
  [facebook_ requestWithGraphPath:@"me" andDelegate:list];
}

- (void)fbSessionStop {
  primary_id_ = NULL;
  self.sessionChanged->Run();
}

- (void)fbDidLogin {
  // TODO(pmattis): Use a keychain instead of NSUserDefaults for storing this
  // sensitive information.
  Dict secure_item(kAccessTokenKey, [facebook_ accessToken],
                   kExpirationDateKey, [facebook_ expirationDate]);
  SetSecureItem(secure_item);
  primary_id_ = NULL;
  [self fbSessionStart];
}

- (void)fbDidNotLogin:(BOOL)cancelled {
  LOG("facebook: did not login: %d", int(cancelled));
  [self fbSessionStop];
}

- (void)fbDidLogout {
  LOG("facebook: did logout");
  DeleteSecureItem();
  [self fbSessionStop];
}

- (void)fbSessionInvalidated {
  LOG("facebook: session invalidated");
  [self fbSessionStop];
}

- (void)load {
  CHECK(dispatch_is_main_thread());
  const Dict secure_item = GetSecureItem();
  if (secure_item.find(kAccessTokenKey) &&
      secure_item.find(kExpirationDateKey)) {
    [facebook_ setAccessToken:secure_item.find(kAccessTokenKey)];
    [facebook_ setExpirationDate:secure_item.find(kExpirationDateKey)];
    primary_id_ = secure_item.find(kPrimaryIdKey);
  }

  if (!primary_id_) {
    [self fbSessionStart];
  } else {
    self.sessionChanged->Run();
  }
}

- (void)login:(UINavigationController*)navigation {
  CHECK(dispatch_is_main_thread());
  if (![facebook_ isSessionValid]) {
    LOG("facebook: logging in");
    [facebook_ authorize:Array("offline_access", "user_photos", "friends_photos")];
  }
}

- (void)logout {
  CHECK(dispatch_is_main_thread());
  if ([facebook_ isSessionValid]) {
    LOG("facebook: logging out");
    [facebook_ logout];
  }
}

- (BOOL)handleOpenURL:(NSURL*)url {
  CHECK(dispatch_is_main_thread());
  return [facebook_ handleOpenURL:url];
}

@end  // FacebookService
