// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import "Defines.h"
#import "RootViewController.h"
#import "SearchFieldView.h"
#import "SearchableSummaryView.h"
#import "SummaryLayoutController.h"
#import "UIView+geometry.h"

@implementation SearchableSummaryView

- (id)initWithState:(UIAppState*)state withType:(SummaryType)type {
  if (self = [super initWithState:state withType:type]) {
    search_field_ = [[SearchFieldView alloc] initWithState:state withSearchParent:self];
    search_field_.searchPlaceholder = self.searchPlaceholder;
    __weak SearchableSummaryView* weak_self = self;
    search_field_.env = weak_self;
    [scroll_view_ insertSubview:search_field_ belowSubview:viewfinder_];
  }
  return self;
}

- (void)layoutSubviews {
  search_field_.frameWidth = self.frameWidth;
  [super layoutSubviews];
}

- (CallbackSet*)searchCallback {
  return &search_callback_;
}

- (NSString*)searchPlaceholder {
  return @"";
}

- (int)numRows {
  if (self.searching) {
    return search_results_.size();
  } else {
    return self.unfilteredNumRows;
  }
}

- (float)totalHeight {
  if (self.searching) {
    if (search_results_.size() == 0) {
      return 0;
    } else {
      return search_results_.back().position() + search_results_.back().height();
    }
  } else {
    return self.unfilteredTotalHeight;
  }
}

- (bool)getSummaryRow:(int)row_index
              rowSink:(SummaryRow*)row
         withSnapshot:(const DayTable::SnapshotHandle&)snapshot {
  if (self.searching) {
    if (row_index >= search_results_.size()) {
      return false;
    }
    row->CopyFrom(search_results_[row_index]);
    return true;
  } else {
    return [self getUnfilteredSummaryRow:row_index rowSink:row withSnapshot:snapshot];
  }
}

- (int)getRowIndexForId:(int64_t)row_id {
  const int row_index = [self getUnfilteredRowIndexForId:row_id];
  if (self.searching) {
    return row_map_[row_index];
  } else {
    return row_index;
  }
}

- (bool)isModal {
  return super.isModal || search_field_.editing;
}

- (bool)zeroState {
  return super.zeroState && !search_field_.searching;
}

- (bool)searching {
  return search_field_.searching;
}

- (bool)resetSnapshot:(bool)force {
  if (![super resetSnapshot:force]) {
    return false;
  }
  if (self.searching) {
    search_results_.clear();
    [self populateSearchResults:&search_results_ forQuery:search_field_.searchQuery];
  }
  self.searchCallback->Run();
  return true;
}

- (void)searchFieldViewWillBeginSearching:(SearchFieldView*)field {
  [self hideToolbar];
}

- (void)searchFieldViewDidBeginSearching:(SearchFieldView*)field {
  self.modalCallback->Run(true);
}

- (void)searchFieldViewDidChange:(SearchFieldView*)field {
  if (self.contentInsetTop != last_inset_top_) {
    // The text field has changed size, so update contentInset.  If we read the contentInset
    // property in the future it will be adjusted based on the scroll view's bounds and
    // contentOffset, so remember the last content inset we used instead of reading it back from the
    // scroll view.
    [self updateScrollView];
    last_inset_top_ = self.contentInsetTop;
  }
}

- (void)searchFieldViewWillEndSearching:(SearchFieldView*)field {
  // Run the modal callback first to change toolbar items while offscreen.
  self.modalCallback->Run(false);
  [self showToolbar];
}

- (void)searchFieldViewDidEndSearching:(SearchFieldView*)field {
  scroll_view_.contentOffset = CGPointMake(0, scroll_view_.contentOffsetMinY);
}

- (void)searchFieldViewDidSearch:(SearchFieldView*)field {
  if (self.isRowExpanded) {
    [self clearExpandedRow];
  }
  [self rebuild:true];
  [self scrollToTop];
}

- (void)searchFieldViewPopulateAutocomplete:(SearchFieldView*)field
                                    results:(SummaryAutocompleteResults*)results
                                   forQuery:(const Slice&)query {
  [self populateAutocomplete:results forQuery:query];
}

- (void)populateSearchResults:(vector<SummaryRow>*)results forQuery:(const Slice&)query {
  DIE("abstract method");
}

- (void)populateAutocomplete:(SummaryAutocompleteResults*)results forQuery:(const Slice&)query {
  DIE("abstract method");
}

- (int)unfilteredNumRows {
  DIE("abstract method");
  return 0;
}

- (float)unfilteredTotalHeight {
  DIE("abstract method");
  return 0;
}

- (bool)getUnfilteredSummaryRow:(int)row_index
                        rowSink:(SummaryRow*)row
                   withSnapshot:(const DayTable::SnapshotHandle&)snapshot {
  DIE("abstract method");
  return false;
}

- (int)getUnfilteredRowIndexForId:(int64_t)row_id {
  DIE("abstract method");
  return 0;
}

- (float)contentInsetTop {
  return self.toolbarBottom + search_field_.frameHeight;
}

- (NSString*)searchTitle {
  DCHECK(self.searching);
  return Format("%d result%s", search_results_.size(), Pluralize(search_results_.size()));
}

@end  // SearchableSummaryView
