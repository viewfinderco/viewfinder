// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

@interface CameraGridView : UIView {
 @private
  int grid_size_;
}

- (id)initWithGridSize:(int)grid_size;

@end  // CameraGridView

// local variables:
// mode: objc
// end:
