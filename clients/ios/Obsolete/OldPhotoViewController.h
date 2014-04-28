// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

class AppState;
class PhotoLayout;
class PhotoLayoutEnv;

@interface OldPhotoViewController
    : UIViewController <UIActionSheetDelegate,
                        UIAlertViewDelegate,
                        UIGestureRecognizerDelegate,
                        UIScrollViewDelegate> {
 @private
  ScopedPtr<PhotoLayoutEnv> env_;
  ScopedPtr<PhotoLayout> layout_;
  int64_t target_photo_;
  bool reload_delayed_;
  bool reload_needed_;
  bool detailed_mode_;
  bool individual_mode_;
  bool deleting_;
}

- (id)initWithState:(AppState*)state;

@end  // OldPhotoViewController

// local variables:
// mode: objc
// end:
