// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>

@class CheckmarkBadge;

enum PhotoSource {
  SOURCE_CAMERA,
  SOURCE_CONVERSATION,
  SOURCE_PROFILE,
  SOURCE_INBOX,
  SOURCE_UNKNOWN,
};

@protocol PhotoOptionsEnv
@optional
- (void)photoOptionsClose;
@end  // PhotoOptionsEnv

@interface PhotoOptions : UIView {
 @private
  __weak id<PhotoOptionsEnv> env_;
  UIButton* done_;
  CGPoint done_position_;
}

@property (nonatomic) CGPoint donePosition;
@property (nonatomic, readonly, weak) id<PhotoOptionsEnv> env;

- (id)initWithEnv:(id<PhotoOptionsEnv>)env;
- (void)show;
- (void)hide;

@end  // PhotoOptions

// local variables:
// mode: objc
// end:
