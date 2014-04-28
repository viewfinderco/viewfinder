// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import <UIKit/UIKit.h>
#import "PhotoOptions.h"

class UIAppState;
@class PhotoView;

@protocol SinglePhotoViewEnv
- (void)singlePhotoViewToggle:(PhotoView*)p;
- (void)singlePhotoViewWillClose;
@end  // SinglePhotoViewEnv

@interface SinglePhotoView
    : UIScrollView<PhotoOptionsEnv,
                   UIScrollViewDelegate> {
 @private
  __weak id<SinglePhotoViewEnv> env_;
  UIAppState* state_;
  PhotoView* photo_;
  PhotoOptions* options_;
  UIView* orig_view_;
  CGRect orig_frame_;
  int orig_index_;
  UIScrollView* scroll_view_;
  UITapGestureRecognizer* single_tap_recognizer_;
  UITapGestureRecognizer* double_tap_recognizer_;
}

@property (nonatomic, weak) id<SinglePhotoViewEnv> env;

- (id)initWithState:(UIAppState*)state
          withPhoto:(PhotoView*)photo;
- (void)show;
- (void)hide;

@end  // SinglePhotoView

// local variables:
// mode: objc
// end:
