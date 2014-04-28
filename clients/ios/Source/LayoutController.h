// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "Utils.h"

class UIAppState;

@class PhotoView;

// Photo layout controller is able to cycle through groups of photos.
// For a conversation, this is just the conversation itself. For events,
// you're able to cycle past the end of one event and into the next or
// previous event.
typedef vector<pair<int64_t, int64_t> > PhotoIdVec;
struct CurrentPhotos {
  // SetIndex may update "photo_ids" using the prev/next callbacks.
  bool SetIndex(int index);
  // Hook to recompute the current photos array and prev/next callbacks
  // as applicable in the face of photos being removed or other changes
  // made in situ while viewing photos in single-photo layout.
  void Refresh();

  void (^prev_callback)();
  void (^next_callback)();
  void (^refresh_callback)();
  PhotoIdVec photo_ids;

  CurrentPhotos()
      : prev_callback(NULL),
        next_callback(NULL),
        refresh_callback(NULL) {
  }
};

struct ControllerState {
  PhotoView* current_photo;
  int64_t current_episode;
  int64_t current_viewpoint;
  UIView* current_view;
  bool pending_viewpoint;
  CurrentPhotos current_photos;

  ControllerState()
      : current_photo(NULL),
        current_episode(0),
        current_viewpoint(0),
        current_view(NULL),
        pending_viewpoint(false) {
  }
};

@interface LayoutController : UIViewController {
 @protected
  UIAppState* state_;
  ControllerState controller_state_;
}

- (id)initWithState:(UIAppState*)state;
- (bool)visible;

// The nonatomic specifier is required here for ios5, which lacks
// _objc_copyCppObjectAtomic, required to do an atomic (default)
// copy of the CPP struct ControllerState.
@property (nonatomic) ControllerState controllerState;

@end  // LayoutController

@interface TwoFingerSwipeScrollView : UIScrollView<UIGestureRecognizerDelegate> {
 @protected
  UISwipeGestureRecognizer* swipe_up_recognizer_;
  UISwipeGestureRecognizer* swipe_down_recognizer_;
}

- (id)init;

@end  // TwoFingerSwipeScrollView

// local variables:
// mode: objc
// end:
