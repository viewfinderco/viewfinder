// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import <UIKit/UIKit.h>
#import "ValueUtils.h"

@class Navbar;

typedef void (^TutorialActionBlock)();

enum TutorialOrientation {
  TUTORIAL_OVER,
  TUTORIAL_UNDER,
};

@interface TutorialOverlayView : UIView {
 @private
  TutorialActionBlock block_;
  UIButton* button_;
  UIImageView* nipple_;
  double max_display_time_;
}

@property (nonatomic) double maxDisplayTime;

- (id)initWithText:(const string&)text
     withNippleTip:(CGPoint)nipple_tip
   withOrientation:(TutorialOrientation)orientation
         withBlock:(TutorialActionBlock)block;

- (void)show;
- (void)hide;

+ (TutorialOverlayView*)createTutorialWithText:(const string&)text
                                        toRect:(CGRect)rect
                               withOrientation:(TutorialOrientation)orientation
                                     withBlock:(TutorialActionBlock)block;

@end  // TutorialOverlayView

// local variables:
// mode: objc
// end:
