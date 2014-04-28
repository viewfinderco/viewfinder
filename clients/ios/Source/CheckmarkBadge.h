// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

typedef void(^ButtonCallback)(void);

@interface CheckmarkBadge :
    UIView<UIGestureRecognizerDelegate> {
 @private
  UIImage* selected_image_;
  UIImage* unselected_image_;
  UIImageView* selected_;
  UIImageView* unselected_;
  bool act_as_button_;
  ButtonCallback button_callback_;
  UITapGestureRecognizer* single_tap_recognizer_;
}

@property (nonatomic) bool selected;
@property (nonatomic, readonly) CGSize naturalSize;
@property (nonatomic) UIImage* selectedImage;
@property (nonatomic) UIImage* unselectedImage;
// If actAsButton is set, the badge acts like a button,
// recognizing single taps to change appearance and invoke the
// buttonCallback, if set.
@property (nonatomic) bool actAsButton;

- (void)setButtonCallback:(ButtonCallback)button_callback;
- (void)remove;

@end  // CheckmarkBadge

// local variables:
// mode: objc
// end:
