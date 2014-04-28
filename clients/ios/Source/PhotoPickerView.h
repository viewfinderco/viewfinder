// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import "FullEventSummaryView.h"
#import "ModalView.h"

class UIAppState;
@class SummaryToolbar;

@protocol PhotoPickerEnv
@optional
- (void)photoPickerAddPhotos:(PhotoSelectionVec)photo_ids;
- (void)photoPickerExit;
@end  // PhotoPickerEnv

@interface PhotoPickerView :
    ModalView<UIGestureRecognizerDelegate> {
 @private
  __weak id<PhotoPickerEnv> env_;
  bool need_rebuild_;
  bool single_photo_selection_;
  float toolbar_top_;
  FullEventSummaryView* summary_;
  SummaryToolbar* toolbar_;
}

@property (nonatomic, weak) id<PhotoPickerEnv> env;
@property (nonatomic, readonly) FullEventSummaryView* summary;
@property (nonatomic, readonly) bool singlePhotoSelection;

- (id)initWithState:(UIAppState*)state
singlePhotoSelection:(bool)single_photo_selection;

@end  // PhotoPickerView

// local variables:
// mode: objc
// end:
