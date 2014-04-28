// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_SUMMARY_VIEW_H
#define VIEWFINDER_SUMMARY_VIEW_H

#import <unordered_map>
#import <CoreText/CoreText.h>
#import <QuartzCore/QuartzCore.h>
#import <UIKit/UIKit.h>
#import "Callback.h"
#import "DayTable.h"
#import "EventRowView.h"
#import "LayoutController.h"
#import "LayoutUtils.h"
#import "Navbar.h"
#import "PhotoLoader.h"
#import "PhotoSelection.h"
#import "SinglePhotoView.h"
#import "Timer.h"
#import "ViewfinderTool.h"
#import "WallTime.h"

@class SummaryToolbar;

// Summary view types.
enum SummaryType {
  SUMMARY_CONTACT_TRAPDOORS,
  SUMMARY_CONVERSATIONS,
  SUMMARY_CONVERSATION_PICKER,
  SUMMARY_EVENTS,
  SUMMARY_EVENT_TRAPDOORS,
  SUMMARY_PHOTO_PICKER,
  SUMMARY_PHOTO_TRAPDOORS,
};

extern const float kStatsHeight;

struct SummaryLayoutRow : public LayoutRow {
  SummaryRow summary_row;
};

struct DisabledPhoto {
  int64_t photo_id;
  bool selected;

  DisabledPhoto()
      : photo_id(0), selected(true) {}
  DisabledPhoto(int64_t p, bool s)
      : photo_id(p), selected(s) {}
};

enum EditMode {
  EDIT_MODE_INACTIVE,
  EDIT_MODE_EDIT,
  EDIT_MODE_SHARE,
};

extern const WallTime kScrollLoadImagesDelay;

typedef std::pair<int, int> RowRange;
typedef void (^ActivatedCallback)(bool);
typedef CallbackSet1<bool> ActivatedCallbackSet;
typedef CallbackSet2<int64_t, PhotoView*> ViewpointSelectedCallbackSet;

@interface SummaryView : UIView<NavbarEnv,
                                UIGestureRecognizerDelegate,
                                UIScrollViewDelegate,
                                SinglePhotoViewEnv,
                                ViewfinderToolEnv> {
 @protected
  UIAppState* state_;
  SummaryType type_;
  int day_table_epoch_;
  int64_t expanded_row_id_;
  ViewfinderTool* viewfinder_;
  __weak SummaryToolbar* toolbar_;
  DayTable::SnapshotHandle snapshot_;
  PhotoSelectionSet selection_;
  TwoFingerSwipeScrollView* scroll_view_;
  SinglePhotoView* single_photo_view_;
  ControllerState controller_state_;

 @private
  bool initialized_;
  bool network_paused_;
  bool animating_rows_;
  int expanded_row_index_;
  float expanded_row_height_;
  float toolbar_bottom_;
  NSMutableAttributedString* stats_attr_str_;
  vector<DisabledPhoto> disabled_photos_;
  std::unordered_map<int, SummaryLayoutRow> row_cache_;
  RowRange visible_rows_;
  RowRange cache_rows_;
  bool edit_mode_active_;
  CallbackSet selection_callback_;
  CallbackSet scroll_to_top_callback_;
  ActivatedCallbackSet modal_callback_;
  ActivatedCallbackSet toolbar_callback_;
  ViewpointSelectedCallbackSet viewpoint_callback_;
  UIView* stats_view_;
  TextLayer* stats_text_;
  UIView* login_entry_;
  UITapGestureRecognizer* single_tap_recognizer_;
  UISwipeGestureRecognizer* swipe_left_recognizer_;
  UISwipeGestureRecognizer* swipe_right_recognizer_;
  PhotoQueue photo_queue_;
  WallTime load_images_delay_;
  WallTime load_thumbnails_wait_time_;
  float cache_bounds_percentage_;
  WallTimer viewfinder_timer_;
  std::unordered_map<int, float> offset_map_;
}

@property (nonatomic) SummaryType type;
@property (nonatomic, weak) SummaryToolbar* toolbar;
@property (nonatomic, readonly) ViewfinderTool* viewfinder;
@property (nonatomic, readonly) EditMode editMode;
@property (nonatomic, readonly) bool editModeActive;
@property (nonatomic, readonly) bool isModal;
@property (nonatomic, readonly) bool isScrolling;
@property (nonatomic, readonly) bool zeroState;
@property (nonatomic, readonly) float rowWidth;
@property (nonatomic, readonly) CGRect visibleBounds;
@property (nonatomic) ControllerState controllerState;
@property (nonatomic, readonly) bool isRowExpanded;
@property (nonatomic, readonly) int numSelected;
@property (nonatomic) const PhotoSelectionSet& selection;
@property (nonatomic) const vector<DisabledPhoto>& disabledPhotos;
@property (nonatomic, readonly) CallbackSet* selectionCallback;
@property (nonatomic, readonly) CallbackSet* scrollToTopCallback;
@property (nonatomic, readonly) ActivatedCallbackSet* modalCallback;
@property (nonatomic, readonly) ActivatedCallbackSet* toolbarCallback;
@property (nonatomic, readonly) ViewpointSelectedCallbackSet* viewpointCallback;
@property (nonatomic) WallTime loadImagesDelay;
@property (nonatomic, readonly) float contentHeight;
@property (nonatomic, readonly) int expandedRowIndex;
@property (nonatomic, readonly) float expandedRowHeight;
@property (nonatomic) float toolbarBottom;

- (id)initWithState:(UIAppState*)state
           withType:(SummaryType)type;

- (void)clear;
- (bool)rebuild:(bool)force;
- (bool)rebuild;
- (void)animateTransitionPrepare:(LayoutTransitionState*)transition;
- (void)viewDidAppear;
- (void)viewDidDisappear;
- (void)pauseNetwork;
- (void)resumeNetwork;
- (void)scrollToRow:(int)row_index;
- (void)scrollToTop;
- (void)animateExpandRow:(int)row_index
              completion:(void (^)(void))completion;
- (void)clearExpandedRow;
- (void)setSelectionBadgesForAllRows;

// Methods and properties below this point are to be implemented in subclasses.

@property (nonatomic, readonly) string name;
@property (nonatomic, readonly) float defaultScrollCacheBoundsPercentage;
@property (nonatomic, readonly) float contentInsetBottom;
@property (nonatomic, readonly) float contentInsetTop;
@property (nonatomic, readonly) int numRows;
@property (nonatomic, readonly) float totalHeight;
@property (nonatomic, readonly) bool singlePhotoSelectionEnabled;
@property (nonatomic, readonly) bool singleViewpointSelectionEnabled;
@property (nonatomic, readonly) bool displayPositionIndicator;
@property (nonatomic, readonly) bool searching;
@property (nonatomic, readonly) NSString* searchTitle;

- (bool)rowSelectionEnabled:(int)row_index;
- (bool)photoSelectionEnabled:(int)row_index;
- (void)setModal:(bool)modal;
- (void)activateEditMode:(EditMode)edit_mode;
- (void)cancelEditMode;
- (void)exitModal;
- (void)hideToolbar;
- (void)showToolbar;
- (void)initLayoutRow:(SummaryLayoutRow*)row
          forRowIndex:(int)row_index;
- (void)updateLayoutRow:(SummaryLayoutRow*)row
            forRowIndex:(int)row_index;
// Called on rebuild to set the current position.
- (int)getCurrentRowIndex;
- (int64_t)getIdForRowIndex:(int)row_index;
// This pair of methods are used for row expansion, to map back and forth between a row index and a stable id.
// Subclasses that don't support expansion don't need to implement them.
- (int64_t)getIdForSummaryRow:(const SummaryRow&)row;
- (int)getRowIndexForId:(int64_t)row_id;
- (bool)getSummaryRow:(int)row_index
              rowSink:(SummaryRow*)row
         withSnapshot:(const DayTable::SnapshotHandle&)snapshot;
- (bool)displayStats;
- (NSMutableAttributedString*)getStatsAttrStrWithAttributes:(const Dict&)attrs
                                       withNumberAttributes:(const Dict&)num_attrs;
- (CGPoint)rowTextOffset:(int)row_index;
- (CompositeTextLayer*)getTextLayer:(const SummaryRow&)summary_row;
- (void)initPlaceholder;
- (void)clearPlaceholder;
- (void)showTutorial;
- (void)hideTutorial;
- (void)scrollToCurrentPhotoInRowView:(RowView*)row_view;

// Called when the user selects a photo (event summary only).
- (void)selectPhoto:(PhotoView*)photo_view inRow:(int)row_index;

// Updates the size of the scroll view insets.
- (void)updateScrollView;

// Updates the DayTable snapshot; returns true if it has changed.
// May be overridden by subclasses to update derived data when the snapshot changes.
- (bool)resetSnapshot:(bool)force;

@end  // SummaryView

#endif  // VIEWFINDER_SUMMARY_VIEW_H

// local variables:
// mode: objc
// end:
