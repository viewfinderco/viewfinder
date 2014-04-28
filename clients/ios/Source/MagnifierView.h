// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.
//
// Taken from:
//   http://stackoverflow.com/questions/13330975/how-to-add-a-magnifier-to-custom-control/13333807#13333807

#import <UIKit/UIKit.h>

@interface MagnifierView : UIView {
  UIView *view_to_magnify_;
  CGPoint touch_point_;
}

@property (nonatomic) UIView* viewToMagnify;
@property (nonatomic) CGPoint touchPoint;

@end  // MagnifierView

// local variables:
// mode: objc
// end:
