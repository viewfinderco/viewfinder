// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <re2/re2.h>
#import <UIKit/UIView.h>
#import "ContactManager.h"
#import "TokenizedTextView.h"
#import "TutorialOverlayView.h"
#import "UIAppState.h"
#import "ViewpointTable.h"

class FollowerGroup;
@class FollowerFieldView;
@class FollowerLabel;

enum EditIconStyle {
  EDIT_ICON_PENCIL,
  EDIT_ICON_DROPDOWN,
};

@protocol FollowerFieldViewDelegate
- (void)followerFieldViewStopEditing:(FollowerFieldView*)field commit:(bool)commit;
- (void)followerFieldViewListFollowers:(FollowerFieldView*)field
                             followers:(ContactManager::ContactVec*)followers
                             removable:(std::unordered_set<int64_t>*)removable;
- (void)followerFieldViewDidBeginEditing:(FollowerFieldView*)field;
- (void)followerFieldViewDidEndEditing:(FollowerFieldView*)field;
- (void)followerFieldViewDidChange:(FollowerFieldView*)field;
- (bool)followerFieldViewEnableDone:(FollowerFieldView*)field;
- (bool)followerFieldViewDone:(FollowerFieldView*)field;
@end

@interface FollowerFieldView : UIView<UIGestureRecognizerDelegate,
                                      UITableViewDelegate,
                                      UITableViewDataSource,
                                      TokenizedTextViewDelegate> {
 @private
  UIAppState* state_;
  bool provisional_;
  float width_;
  __weak id<FollowerFieldViewDelegate> delegate_;
  FollowerLabel* label_;
  UIButton* dropdown_selected_;
  UIButton* dropdown_unselected_;
  UIGestureRecognizer* edit_recognizer_;
  bool editable_;
  bool can_edit_;
  bool editing_;
  bool enabled_;
  EditIconStyle edit_icon_style_;
  TokenizedTextView* tokenized_view_;
  UITableView* autocomplete_table_;
  TutorialOverlayView* tutorial_;
  ContactManager::ContactVec original_followers_;
  ContactManager::ContactVec contact_autocomplete_;
  ScopedPtr<RE2> autocomplete_filter_;
  ContactMetadata* dummy_autocomplete_;
  int contact_callback_id_;
  bool commit_;
  bool show_all_contacts_;
  bool show_dropdown_;
  vector<const FollowerGroup*> group_autocomplete_;
}

@property (nonatomic, readonly) float contentHeight;
@property (nonatomic, readonly) bool hasFocus;
@property (nonatomic) bool editable;
@property (nonatomic, readonly) bool editing;
@property (nonatomic) bool enabled;
@property (nonatomic) bool showAllFollowers;
@property (nonatomic) bool showEditIcon;
@property (nonatomic) EditIconStyle editIconStyle;
@property (nonatomic, readonly) bool empty;
@property (nonatomic, weak) id<FollowerFieldViewDelegate> delegate;
@property (nonatomic, readonly) ContactManager::ContactVec allContacts;
@property (nonatomic, readonly) ContactManager::ContactVec newContacts;
@property (nonatomic, readonly) vector<int64_t> removedIds;
@property (nonatomic, readonly) TokenizedTextView* tokenizedView;

- (id)initWithState:(UIAppState*)state
        provisional:(bool)provisional
              width:(float)width;
- (void)startEditing;
- (void)stopEditing;
- (void)clear;
- (bool)canEndEditing;
- (void)resetAutocomplete;

@end  // FollowerFieldView

// local variables:
// mode: objc
// end:
