// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <unordered_map>
#import <UIKit/UIKit.h>
#import "ComposeToolbar.h"
#import "EventRowView.h"
#import "FollowerFieldView.h"
#import "LayoutController.h"
#import "LayoutUtils.h"
#import "Navbar.h"
#import "PhotoLoader.h"
#import "PhotoSelection.h"
#import "ScopedNotification.h"
#import "SearchFieldView.h"
#import "SearchUtils.h"
#import "SinglePhotoView.h"
#import "TextView.h"

class UIAppState;
@class CameraEvent;
@class ConversationScrollView;
@class SinglePhotoView;

struct ComposeEvent : LayoutRow {
  UIScrollView* scroll;
};

enum ComposeTutorialMode {
  COMPOSE_TUTORIAL_ADD_PEOPLE = 0,
  COMPOSE_TUTORIAL_ADD_TITLE,
  COMPOSE_TUTORIAL_PHOTOS,
  COMPOSE_TUTORIAL_SEARCH,
  COMPOSE_TUTORIAL_SUGGESTIONS,
  COMPOSE_TUTORIAL_DONE,
};

enum ComposeEditMode {
  EDIT_MODE_NONE = 0,
  EDIT_MODE_FOLLOWERS,
  EDIT_MODE_TITLE,
};

typedef std::unordered_map<int, ComposeEvent> ComposeEventMap;
typedef std::pair<int, int> EventRange;
typedef std::pair<float, int> WeightedIndex;
typedef std::vector<WeightedIndex> WeightedEventIndexes;

@interface ComposeLayoutController
    : LayoutController<FollowerFieldViewDelegate,
                       NavbarEnv,
                       SearchFieldViewEnv,
                       SinglePhotoViewEnv,
                       TextViewDelegate,
                       UIScrollViewDelegate> {
 @private
  bool need_rebuild_;
  bool initialized_;
  bool toolbar_offscreen_;
  bool autosuggestions_initialized_;
  ComposeEditMode edit_mode_;
  ComposeTutorialMode tutorial_mode_;
  PhotoSelectionSet selection_;
  EventRange visible_events_;
  EventRange cache_events_;
  WeightedEventIndexes weighted_indexes_;
  ContactManager::ContactVec all_contacts_;
  int64_t searching_episode_id_;
  int current_weighted_index_;
  int searching_weighted_index_;
  int day_table_epoch_;
  DayTable::SnapshotHandle snapshot_;
  vector<SummaryRow> search_results_;
  RowIndexMap row_index_map_;
  ConversationScrollView* content_;
  SearchFieldView* search_field_;
  UIScrollView* event_scroll_;
  CameraEvent* use_camera_;
  UIView* initial_scan_placeholder_;
  ComposeToolbar* toolbar_;
  FollowerFieldView* followers_;
  UIView* followers_divider_;
  UIView* tutorial_overlay_;
  UIButton* tutorial_button_;
  Navbar* navbar_;
  TextView* title_;
  NSString* orig_title_;
  UIView* title_container_;
  UIView* title_divider_;
  UIView* suggestion_overlay_;
  SinglePhotoView* single_photo_view_;
  UITapGestureRecognizer* single_tap_recognizer_;
  ComposeEventMap event_map_;
  PhotoQueue photo_queue_;
  ScopedNotification keyboard_will_show_;
  ScopedNotification keyboard_will_hide_;
}

@property (nonatomic) ContactManager::ContactVec allContacts;

- (id)initWithState:(UIAppState*)state;

@end  // ComposeLayoutController

// local variables:
// mode: objc
// end:
