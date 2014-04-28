// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AuthService.h"

@implementation AuthService

@dynamic sessionChanged;

- (id)init {
  if (self = [super init]) {
    load_needed_ = true;
  }
  return self;
}

- (NSString*)serviceName {
  return @"Unknown";
}

- (NSString*)primaryId {
  return NULL;
}

- (NSString*)accessToken {
  return NULL;
}

- (NSString*)refreshToken {
  return NULL;
}

- (NSDate*)expirationDate {
  return NULL;
}

- (CallbackSet*)sessionChanged {
  return &session_changed_;
}

- (bool)valid {
  return false;
}

- (void)load {
}

- (void)loadIfNecessary {
  if (!load_needed_) {
    return;
  }
  dispatch_main(^{
      if (load_needed_) {
        load_needed_ = false;
        [self load];
      }
    });
}

- (void)login:(UINavigationController*)navigation {
}

- (void)logout {
}

- (BOOL)handleOpenURL:(NSURL*)url {
  return NO;
}

@end  // AuthService
