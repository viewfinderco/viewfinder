// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "ConversationNavbar.h"
#import "ConversationPickerView.h"
#import "DayTable.h"
#import "LayoutUtils.h"
#import "PhotoPickerView.h"
#import "PhotoSelection.h"
#import "RowView.h"
#import "ScopedNotification.h"
#import "ViewfinderTool.h"
#import "ViewpointTable.h"

class UIAppState;
@class SummaryToolbar;

@interface ConversationScrollView : TwoFingerSwipeScrollView {
 @private
  UIEdgeInsets visible_insets_;
  bool scrolling_animation_;
}

@property (nonatomic) UIEdgeInsets visibleInsets;
@property (nonatomic) bool scrollingAnimation;

@end  // ConversationScrollView

typedef std::unordered_map<int, EpisodeLayoutRow> RowCacheMap;

struct CachedConversation {
  DayTable::ViewpointSummaryHandle vsh;
  ViewpointHandle vh;
  RowCacheMap row_cache;
  UIView* content_view;
  ConversationScrollView* scroll_view;
  UIView* bottom_row;
  UIView* browsing_overlay;
  ViewfinderTool* viewfinder;
  EpisodeLayoutRow browsing_row;
  float drag_offset;

  CachedConversation()
      : drag_offset(0) {
  }
};

typedef std::unordered_map<int, CachedConversation> ConversationCacheMap;
typedef std::pair<int, int> ConversationRange;

@interface ConversationLayoutController
    : LayoutController<ConversationNavbarEnv,
                       ConversationPickerEnv,
                       PhotoPickerEnv,
                       RowViewEnv,
                       UIActionSheetDelegate,
                       UIGestureRecognizerDelegate,
                       UIScrollViewDelegate,
                       ViewfinderToolEnv> {
 @private
  bool need_rebuild_;     // waiting for UI to allow a rebuild
  bool rebuilding_;       // a rebuild is underway
  bool network_paused_;
  bool browsing_;
  bool edit_mode_;
  bool use_camera_;
  bool showing_alert_;
  bool pending_comment_;
  bool pending_add_photos_;
  int editing_row_index_;
  int visible_conversation_;
  NSTimer* browsing_timer_;
  ConversationCacheMap conversation_cache_;
  ConversationRange visible_conversations_;
  ConversationRange cache_conversations_;
  PhotoSelectionSet selection_;
  PhotoQueue photo_queue_;
  ScopedPtr<LayoutTransitionState> transition_;
  bool show_all_followers_;
  bool viewfinder_active_;
  int day_table_epoch_;
  DayTable::SnapshotHandle snapshot_;
  DBHandle commit_transaction_;
  UIScrollView* horizontal_scroll_;
  SummaryToolbar* toolbar_;
  ConversationNavbar* convo_navbar_;
  ConversationPickerView* convo_picker_;
  PhotoPickerView* add_photos_;
  UITapGestureRecognizer* single_tap_recognizer_;
  UILongPressGestureRecognizer* long_press_recognizer_;
  UISwipeGestureRecognizer* swipe_left_recognizer_;
  UISwipeGestureRecognizer* swipe_right_recognizer_;
  CGRect keyboard_frame_;
  ScopedNotification keyboard_will_show_;
  ScopedNotification keyboard_will_hide_;
  WallTimer viewfinder_timer_;
}

@property (nonatomic, readonly) UIView* currentConversationView;
@property (nonatomic) bool pendingComment;
@property (nonatomic) bool pendingAddPhotos;

- (id)initWithState:(UIAppState*)state;

@end  // ConversationLayoutController

ConversationLayoutController* NewConversationLayoutController(UIAppState* state);

// local variables:
// mode: objc
// end:
