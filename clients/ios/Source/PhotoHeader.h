// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>

@interface PhotoHeader : UIView {
 @private
  UIScrollView* title_view_;
}

@property (nonatomic, readonly) UIScrollView* titleView;

- (id)init;
- (void)show;
- (void)hide;

@end  // PhotoHeader

// local variables:
// mode: objc
// end:
