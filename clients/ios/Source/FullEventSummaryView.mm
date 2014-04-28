// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import "FullEventSummaryView.h"
#import "InitialScanPlaceholderView.h"
#import "UIView+geometry.h"

namespace {

const float kFullEventTextLeftMargin = 52;
const float kFullEventTextRightMargin = 12;
const float kFullEventTextTopMargin = 20;

}  // namespace

@implementation FullEventSummaryView

@synthesize singlePhotoSelection = single_photo_selection_;

- (id)initWithState:(UIAppState*)state withType:(SummaryType)type {
  if (self = [super initWithState:state withType:type]) {
  }
  return self;
}

- (DayTable::Summary*)summaryWithSnapshot:(const DayTable::SnapshotHandle&)snapshot {
  return snapshot->full_events().get();
}

- (DayTable::Summary*)summary {
  return [self summaryWithSnapshot:snapshot_];
}

- (string)name {
  return "summary(full events)";
}

- (float)defaultScrollCacheBoundsPercentage {
  return 0.05;
}

- (float)contentInsetBottom {
  return 0;
}

- (NSString*)searchPlaceholder {
  return @"Search";
}

- (int)unfilteredNumRows {
  return self.summary->row_count();
}

- (float)unfilteredTotalHeight {
  return self.summary->total_height() + UIStyle::kGutterSpacing;
}

- (bool)rowSelectionEnabled:(int)row_index {
  return !single_photo_selection_;
}

- (bool)photoSelectionEnabled:(int)row_index {
  return !single_photo_selection_;
}

- (bool)singlePhotoSelectionEnabled {
  return single_photo_selection_;
}

- (void)navbarBack {
  if (single_photo_view_) {
    [single_photo_view_ hide];
    single_photo_view_ = NULL;
  }
}

- (void)navbarExit {
  [viewfinder_ close:true];
}

- (void)initLayoutRow:(SummaryLayoutRow*)row
          forRowIndex:(int)row_index {
  EventHandle evh = snapshot_->LoadEvent(
      row->summary_row.day_timestamp(), row->summary_row.identifier());
  InitFullEvent(state_, row, evh, single_photo_selection_,
                row->summary_row.weight(), self.rowWidth, snapshot_->db());

  // If this is the last row, extend frame to include trailing spacing.
  if (row_index == self.numRows - 1) {
    row->view.frameHeight += UIStyle::kGutterSpacing;
  }
  row->view.textLayer.maxWidth = self.rowWidth - kFullEventTextLeftMargin - kFullEventTextRightMargin;
}

- (bool)getUnfilteredSummaryRow:(int)row_index
                        rowSink:(SummaryRow*)row
                   withSnapshot:(const DayTable::SnapshotHandle&)snapshot {
  return [self summaryWithSnapshot:snapshot]->GetSummaryRow(row_index, row);
}

- (CGPoint)rowTextOffset:(int)row_index {
  return CGPointMake(kFullEventTextLeftMargin, kFullEventTextTopMargin);
}

- (CompositeTextLayer*)getTextLayer:(const SummaryRow&)summary_row {
  CompositeTextLayer* layer;
  EventHandle evh = snapshot_->LoadEvent(
      summary_row.day_timestamp(), summary_row.identifier());
  layer = [[EventTextLayer alloc] initWithEvent:*evh
                                     withWeight:summary_row.weight()
                                  locationFirst:true];

  layer.maxWidth = self.rowWidth - kFullEventTextLeftMargin - kFullEventTextRightMargin;
  return layer;
}

- (void)initPlaceholder {
  if (!self.zeroState) {
    [self clearPlaceholder];
    return;
  }

  if (self.type == SUMMARY_PHOTO_PICKER &&
      state_->assets_initial_scan()) {
    // We're still performing the initial scan, show the initial scan
    // placeholder.
    if (!initial_scan_placeholder_) {
      [self clearPlaceholder];
      initial_scan_placeholder_ = NewInitialScanPlaceholder();
      [self addSubview:initial_scan_placeholder_];
      [initial_scan_placeholder_ centerFrameWithinSuperview];
    }
    return;
  }

  [self clearPlaceholder];
}

- (void)clearPlaceholder {
  [initial_scan_placeholder_ removeFromSuperview];
  initial_scan_placeholder_ = NULL;
}

- (void)populateAutocomplete:(SummaryAutocompleteResults*)results forQuery:(const Slice&)query {
  PopulateEventAutocomplete(state_, results, query);
}

- (void)populateSearchResults:(vector<SummaryRow>*)results forQuery:(const Slice&)query {
  PopulateEventSearchResults(state_, snapshot_->full_events(), results, query, NULL);
}

@end  // FullEventSummaryView
