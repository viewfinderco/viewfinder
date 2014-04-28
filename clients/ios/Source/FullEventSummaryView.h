// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import "SearchableSummaryView.h"

@interface FullEventSummaryView : SearchableSummaryView {
 @private
  bool single_photo_selection_;
  UIView* initial_scan_placeholder_;
}

@property (nonatomic) bool singlePhotoSelection;

- (id)initWithState:(UIAppState*)state withType:(SummaryType)type;

@end  // FullEventSummaryView

// local variables:
// mode: objc
// end:
