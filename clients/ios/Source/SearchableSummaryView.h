// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import <re2/re2.h>
#import "SearchUtils.h"
#import "SearchFieldView.h"
#import "SummaryView.h"

@interface SearchableSummaryView : SummaryView<SearchFieldViewEnv> {
 @protected
  vector<SummaryRow> search_results_;
  RowIndexMap row_map_;

 @private
  CallbackSet search_callback_;
  SearchFieldView* search_field_;
  float last_inset_top_;
};

@property (nonatomic, readonly) bool searching;
@property (nonatomic, readonly) NSString* searchTitle;
@property (nonatomic, readonly) CallbackSet* searchCallback;

- (id)initWithState:(UIAppState*)state withType:(SummaryType)type;

- (void)populateSearchResults:(vector<SummaryRow>*)results forQuery:(const Slice&)query;
- (void)populateAutocomplete:(SummaryAutocompleteResults*)results forQuery:(const Slice&)query;

// Subclasses should override these "unfiltered" methods instead of the corresponding SummaryView methods.
- (int)unfilteredNumRows;
- (float)unfilteredTotalHeight;
- (bool)getUnfilteredSummaryRow:(int)row_index
                        rowSink:(SummaryRow*)row
                   withSnapshot:(const DayTable::SnapshotHandle&)snapshot;
- (int)getUnfilteredRowIndexForId:(int64_t)row_id;

@end  // SearchableSummaryView

// local variables:
// mode: objc
// end:
