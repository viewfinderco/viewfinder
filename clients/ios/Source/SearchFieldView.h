// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.
// Author: Spencer Kimball

#import <UIKit/UIKit.h>
#import "SearchUtils.h"
#import "TokenizedTextView.h"

class UIAppState;
@class SearchFieldView;

@protocol SearchFieldViewEnv
- (void)searchFieldViewWillBeginSearching:(SearchFieldView*)field;
- (void)searchFieldViewDidBeginSearching:(SearchFieldView*)field;
- (void)searchFieldViewDidChange:(SearchFieldView*)field;
- (void)searchFieldViewWillEndSearching:(SearchFieldView*)field;
- (void)searchFieldViewDidEndSearching:(SearchFieldView*)field;
- (void)searchFieldViewDidSearch:(SearchFieldView*)field;
- (void)searchFieldViewPopulateAutocomplete:(SearchFieldView*)field
                                    results:(SummaryAutocompleteResults*)results
                                   forQuery:(const Slice&)query;
@end  // SearchFieldViewEnv

@interface SearchFieldView : UIView<TokenizedTextViewDelegate,
                                    UIGestureRecognizerDelegate,
                                    UITableViewDelegate,
                                    UITableViewDataSource> {
 @private
  __weak id<SearchFieldViewEnv> env_;
  UIAppState* state_;
  bool searching_;
  string search_query_;
  NSString* search_placeholder_;

  UIView* orig_parent_;
  int orig_index_;
  UIView* search_parent_;

  UIView* search_bar_;
  UIImageView* search_field_background_;
  UIButton* clear_button_;
  UIButton* cancel_button_;

  UIColor* pinned_bg_color_;
  UIColor* unpinned_bg_color_;
  UIColor* border_color_;

  UIView* search_bar_bottom_border_;
  UIView* search_field_container_;
  UIImageView* search_field_icon_;
  TokenizedTextView* search_field_;
  UIImageView* search_bar_shadow_;
  UITableView* autocomplete_table_;
  UIView* autocomplete_header_;
  UIView* autocomplete_footer_;
  // search_field_editing_ is true while the field has the keyboard focus.
  bool search_field_editing_;
  vector<pair<int, SummaryTokenInfo> > autocomplete_;
  ScopedPtr<RE2> autocomplete_filter_;
  // The number of tokens in the previous call to tokenizedTextViewChangedTokens.
  int prev_num_tokens_;

  ScopedNotification keyboard_will_show_;
  ScopedNotification keyboard_will_hide_;
  CGRect keyboard_frame_;
}

@property (nonatomic, weak) id<SearchFieldViewEnv> env;
@property (nonatomic, readonly) bool searching;
@property (nonatomic, readonly) bool searchPinned;
@property (nonatomic, readonly) bool editing;
@property (nonatomic, readonly) string searchQuery;
@property (nonatomic, readonly) float intrinsicHeight;
@property (nonatomic) UIColor* pinnedBGColor;
@property (nonatomic) UIColor* unpinnedBGColor;
@property (nonatomic) UIColor* borderColor;
@property (nonatomic) NSString* searchPlaceholder;

- (id)initWithState:(UIAppState*)state
   withSearchParent:(UIView*)search_parent;
- (void)searchBarCancel;

@end  // SearchFieldView

// local variables:
// mode: objc
// end:
