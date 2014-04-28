// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "RowView.h"

@class CheckmarkBadge;

@interface TitleRowView : RowView {
 @private
  CheckmarkBadge* badge_;
}

@property (nonatomic, readonly) float badgeLeftMargin;
@property (nonatomic, readonly) float badgeTopMargin;
@property (nonatomic, readonly) float textEditModeOffset;
@property (nonatomic, readonly) UIImage* selectedImage;
@property (nonatomic, readonly) UIImage* unselectedImage;

@end  // TitleRowView

// local variables:
// mode: objc
// end:
