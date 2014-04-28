// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifdef TESTING

#import "IdentityManager.h"
#import "Testing.h"

TEST(IdentityManagerTest, IdentityForEmail) {
  EXPECT_EQ("Email:ben@emailscrubbed.com", IdentityManager::IdentityForEmail("ben@emailscrubbed.com"));
  EXPECT_EQ("Email:foo@bar.com", IdentityManager::IdentityForEmail("FOO@bar.Com"));
}


#endif  // TESTING
