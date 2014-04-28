// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import "ContactTrapdoorsView.h"
#import "InboxCardRowView.h"
#import "SummaryToolbar.h"
#import "UIView+geometry.h"

namespace {

const float kTrapdoorTextLeftMargin = 16;
const float kTrapdoorTextTopMargin = 45;
const float kTrapdoorTextWithCoverPhotoLeftMargin = 60;
const float kTrapdoorTextRightMargin = 83;

struct TrapdoorTimestampGreaterThan {
  bool operator()(const TrapdoorHandle& a, const TrapdoorHandle& b) const {
    if (a->latest_timestamp() != b->latest_timestamp()) {
      return a->latest_timestamp() > b->latest_timestamp();
    } else {
      return a->viewpoint_id() < b->viewpoint_id();
    }
  }
};

}  // namespace

@interface ContactTrapdoorsSummaryView : SummaryView {
 @private
  int64_t contact_id_;
  float total_height_;
  vector<SummaryRow> summary_rows_;
}

- (id)initWithState:(UIAppState*)state
      withContactId:(int64_t)contact_id;

@end  // ContactTrapdoorsSummaryView


@implementation ContactTrapdoorsSummaryView

- (id)initWithState:(UIAppState*)state
      withContactId:(int64_t)contact_id {
  if (self = [super initWithState:state withType:SUMMARY_CONTACT_TRAPDOORS]) {
    contact_id_ = contact_id;

    // Get a snapshot to initialize summary rows. We can't rely
    // on the base class having gotten the snapshot as it won't until
    // rebuild is invoked.
    snapshot_ = state_->day_table()->GetSnapshot(NULL);

    vector<int64_t> viewpoint_ids;
    state_->viewpoint_table()->ListViewpointsForUserId(
        contact_id, &viewpoint_ids, snapshot_->db());

    // Create array of summary rows.
    total_height_ = 0;
    vector<TrapdoorHandle> traps;
    for (int  i = 0; i < viewpoint_ids.size(); ++i) {
      const TrapdoorHandle trh = snapshot_->LoadTrapdoor(viewpoint_ids[i]);
      if (trh.get()) {
        traps.push_back(trh);
      }
    }
    std::sort(traps.begin(), traps.end(), TrapdoorTimestampGreaterThan());

    for (int  i = 0; i < traps.size(); ++i) {
      const TrapdoorHandle& trh = traps[i];
      const float height = InitInboxCard(
          state_, NULL, trh, ViewpointHandle(), false, 0, state_->screen_width());

      const int row_index =
          snapshot_->conversations()->GetViewpointRowIndex(trh->viewpoint_id());
      SummaryRow summary_row;
      if (!snapshot_->conversations()->GetSummaryRow(row_index, &summary_row)) {
        continue;
      }
      // Adjust the height and position.
      summary_row.set_type(SummaryRow::TRAPDOOR);
      summary_row.set_height(height);
      summary_row.set_position(total_height_);

      summary_rows_.push_back(summary_row);
      total_height_ += height;
    }
  }
  return self;
}

- (float)textLeftMargin:(int)row_index {
  SummaryRow row;
  if (![self getSummaryRow:row_index rowSink:&row withSnapshot:snapshot_]) {
    return kTrapdoorTextLeftMargin;
  }
  return row.photo_count() > 0 ? kTrapdoorTextWithCoverPhotoLeftMargin :  kTrapdoorTextLeftMargin;
}

- (string)name {
  return "contact trapdoors";
}

- (float)defaultScrollCacheBoundsPercentage {
  return 0.05;
}

- (float)contentInsetBottom {
  return 0;
}

- (int)numRows {
  return summary_rows_.size();
}

- (float)totalHeight {
  return total_height_;
}

- (bool)singleViewpointSelectionEnabled {
  return true;
}

- (bool)displayPositionIndicator {
  return false;
}

- (void)navbarExit {
  [viewfinder_ close:true];
}

- (void)initLayoutRow:(SummaryLayoutRow*)row
          forRowIndex:(int)row_index {
  DCHECK_GE(row_index, 0);
  DCHECK_LT(row_index, self.numRows);
  TrapdoorHandle trh = snapshot_->LoadTrapdoor(row->summary_row.identifier());
  ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
      trh->viewpoint_id(), snapshot_->db());
  InitInboxCard(state_, row, trh, vh, false, 0, self.rowWidth);
  row->view.frameTop = row->summary_row.position();

  CompositeTextLayer* tl = row->view.textLayer;
  tl.maxWidth = self.rowWidth - kTrapdoorTextLeftMargin - kTrapdoorTextRightMargin;
  tl.transition = 0;
  tl.frame = CGRectMake(kTrapdoorTextLeftMargin, kTrapdoorTextTopMargin,
                        tl.frame.size.width, tl.frame.size.height);
}

- (bool)getSummaryRow:(int)row_index
              rowSink:(SummaryRow*)row
         withSnapshot:(const DayTable::SnapshotHandle&)snapshot {
  if (row_index >= 0 && row_index < self.numRows) {
    row->CopyFrom(summary_rows_[row_index]);
    return true;
  }
  return false;
}

- (CGPoint)rowTextOffset:(int)row_index {
  return CGPointMake([self textLeftMargin:row_index], kTrapdoorTextTopMargin);
}

- (CompositeTextLayer*)getTextLayer:(const SummaryRow&)summary_row {
  TrapdoorHandle trh = snapshot_->LoadTrapdoor(summary_row.identifier());
  ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
      trh->viewpoint_id(), snapshot_->db());
  CompositeTextLayer* layer =
      [InboxCardRowView newTextLayerWithTrapdoor:*trh
                                   withViewpoint:vh
                                       withWidth:self.rowWidth
                                      withWeight:0];
  layer.maxWidth = self.rowWidth - kTrapdoorTextLeftMargin - kTrapdoorTextRightMargin;

  return layer;
}

@end  // ContactTrapdoorsSummaryView


@implementation ContactTrapdoorsView

@synthesize env = env_;

- (id)initWithState:(UIAppState*)state
        withContactId:(int64_t)contact_id {
  if (self = [super initWithState:state]) {
    need_rebuild_ = true;

    summary_ = [[ContactTrapdoorsSummaryView alloc]
                 initWithState:state_ withContactId:contact_id];
    [self addSubview:summary_];

    __weak ContactTrapdoorsView* weak_self = self;

    summary_.modalCallback->Add(^(bool modal) {
        [weak_self updateToolbar:modal];
      });
    summary_.toolbarCallback->Add(^(bool hidden) {
        if (hidden) {
          [weak_self hideToolbar];
        } else {
          [weak_self showToolbar];
        }
      });
    summary_.viewpointCallback->Add(^(int64_t viewpoint_id, PhotoView* photo_view) {
        [env_ contactTrapdoorsSelection:viewpoint_id];
      });

    toolbar_ = [[SummaryToolbar alloc] initWithTarget:weak_self];
    [toolbar_ showContactTrapdoorsItems:false];
    [self addSubview:toolbar_];

    toolbar_.title = Format("%s (%d)",
                            state->contact_manager()->FirstName(contact_id),
                            LocalizedNumberFormat(summary_.numRows));
  }
  return self;
}

- (void)layoutSubviews {
  [super layoutSubviews];

  toolbar_.frame = CGRectMake(
      0, 0, self.frameWidth,
      toolbar_.intrinsicHeight + state_->status_bar_height());

  summary_.frame = self.bounds;
  summary_.toolbarBottom = toolbar_.frameBottom;
  [summary_ updateScrollView];
  [summary_ layoutSubviews];

  if (need_rebuild_) {
    need_rebuild_ = false;
    [summary_ rebuild];
  }
}

- (void)updateToolbar:(bool)modal {
  if (modal) {
    [toolbar_ showSearchInboxItems:true];
    toolbar_.exitItem.customView.hidden =
        (summary_.viewfinder.mode == VF_JUMP_SCROLLING);
  } else {
    [toolbar_ showContactTrapdoorsItems:true];
  }
}

- (void)hideToolbar {
  toolbar_top_ = -(toolbar_.frameHeight + 1);
  [self layoutSubviews];
}

- (void)showToolbar {
  toolbar_top_ = 0;
  [self layoutSubviews];
}

- (bool)empty {
  return summary_.numRows == 0;
}

- (void)toolbarBack {
  if (summary_.isModal) {
    [summary_ navbarExit];
  } else {
    [env_ contactTrapdoorsExit];
  }
}

- (void)toolbarExit {
  [summary_ navbarExit];
}

@end  // ContactTrapdoorsView
