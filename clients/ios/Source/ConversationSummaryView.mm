// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import "Analytics.h"
#import "Appearance.h"
#import "AsyncState.h"
#import "AttrStringUtils.h"
#import "Callback.h"
#import "CommentTable.h"
#import "ConversationLayoutController.h"
#import "ConversationSummaryView.h"
#import "ConversationUtils.h"
#import "CppDelegate.h"
#import "ExportUtils.h"
#import "FullTextIndex.h"
#import "InboxCardRowView.h"
#import "PhotoSelection.h"
#import "PhotoUtils.h"
#import "RootViewController.h"
#import "StatusBar.h"
#import "UIAppState.h"
#import "UIView+geometry.h"
#import "ViewpointTable.h"

namespace {

const float kInboxCardTextLeftMargin = 16;
const float kInboxCardTextRightMargin = 24;
const float kInboxCardTextWithCoverPhotoLeftMargin = 60;
const float kInboxCardTextTopMargin = 41;
const float kMutedIconWidth = 44;

LazyStaticImage kZeroConversations(@"zero_conversations.png");

}  // namespace

@implementation ConversationSummaryView

- (id)initWithState:(UIAppState*)state withType:(SummaryType)type {
  if (self = [super initWithState:state withType:type]) {
    __weak ConversationSummaryView* weak_self = self;
    self.selectionCallback->Add(^{
        [weak_self updateMessage];
      });
  }
  return self;
}

- (float)textLeftMargin:(int)row_index {
  SummaryRow row;
  if (![super getSummaryRow:row_index rowSink:&row withSnapshot:snapshot_]) {
    return kInboxCardTextLeftMargin;
  }
  return row.photo_count() > 0 ? kInboxCardTextWithCoverPhotoLeftMargin :  kInboxCardTextLeftMargin;
}

- (float)maxWidth:(const TrapdoorHandle&)trh {
  const bool interactive = type_ == SUMMARY_CONVERSATIONS;
  float max_width = self.rowWidth - kInboxCardTextRightMargin;
  max_width -= trh->has_cover_photo() ?
               kInboxCardTextWithCoverPhotoLeftMargin : kInboxCardTextLeftMargin;
  if (interactive && trh->muted()) {
    max_width -= kMutedIconWidth;
  }
  return max_width;
}

- (float)textTopMargin {
  return kInboxCardTextTopMargin;
}

- (string)name {
  return "summary(conversations)";
}

- (NSString*)searchPlaceholder {
  return @"Search inbox";
}

- (float)defaultScrollCacheBoundsPercentage {
  return 0.05;
}

- (float)contentInsetBottom {
  return type_ == SUMMARY_CONVERSATIONS ? kStatsHeight : 0;
}

- (int)unfilteredNumRows {
  return snapshot_->conversations()->row_count();
}

- (float)unfilteredTotalHeight {
  return snapshot_->conversations()->total_height();
}

- (float)totalHeight {
  float total_height = super.totalHeight;
  if (self.isRowExpanded) {
    SummaryRow orig_row;
    // Note that we call [super getSummaryRow] instead of [self getSummaryRow]
    // because we don't want the adjustment to the SummaryRow.height() field
    // that [self getSummaryRow] performs.
    DCHECK([super getSummaryRow:self.expandedRowIndex
                        rowSink:&orig_row
                   withSnapshot:snapshot_]);
    const float height_delta = self.expandedRowHeight - orig_row.height();
    total_height += height_delta;
  }
  return total_height;
}

- (bool)photoSelectionEnabled:(int)row_index {
  return self.editModeActive && self.expandedRowIndex == row_index;
}

- (bool)rowSelectionEnabled:(int)row_index {
  return false;
}

- (bool)singleViewpointSelectionEnabled {
  return type_ == SUMMARY_CONVERSATION_PICKER;
}

- (void)navbarExit {
  [viewfinder_ close:true];
}

- (void)initLayoutRow:(SummaryLayoutRow*)row
          forRowIndex:(int)row_index {
  TrapdoorHandle trh = snapshot_->LoadTrapdoor(
      row->summary_row.identifier());
  ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
      trh->viewpoint_id(), snapshot_->db());
  const bool interactive = type_ == SUMMARY_CONVERSATIONS;
  InitInboxCard(state_, row, trh, vh, interactive, row->summary_row.weight(), self.rowWidth);
  InboxCardRowView* inbox_row_view = (InboxCardRowView*)row->view;
  inbox_row_view.inboxCardRowEnv = self;

  row->view.textLayer.maxWidth = [self maxWidth:trh];
}

- (int)getCurrentRowIndex {
  if (self.controllerState.current_viewpoint != 0) {
    return snapshot_->conversations()->GetViewpointRowIndex(
        self.controllerState.current_viewpoint);
  }
  return -1;
}

- (int64_t)getCurrentRowId {
  return controller_state_.current_viewpoint;
}

- (void)clearCurrentRowId {
  controller_state_.current_viewpoint = 0;
}

- (bool)getSummaryRow:(int)row_index
              rowSink:(SummaryRow*)row
         withSnapshot:(const DayTable::SnapshotHandle&)snapshot {
  // The superclass's version of this method returns a summary row without adjustments
  // for any expanded row.
  if (![super getSummaryRow:row_index rowSink:row withSnapshot:snapshot]) {
    return false;
  }
  if (self.isRowExpanded) {
    SummaryRow orig_row;
    DCHECK([super getSummaryRow:self.expandedRowIndex rowSink:&orig_row withSnapshot:snapshot]);
    if (row_index > self.expandedRowIndex) {
      const float height_delta = self.expandedRowHeight - orig_row.height();
      row->set_position(row->position() + height_delta);
    } else if (row_index == self.expandedRowIndex) {
      row->set_height(self.expandedRowHeight);
    }
  }
  return true;
}

- (bool)getUnfilteredSummaryRow:(int)row_index
                        rowSink:(SummaryRow*)row
                   withSnapshot:(const DayTable::SnapshotHandle&)snapshot {
  return snapshot->conversations()->GetSummaryRow(row_index, row);
}

- (bool)displayStats {
  return true;
}

- (NSMutableAttributedString*)getStatsAttrStrWithAttributes:(const Dict&)attrs
                                       withNumberAttributes:(const Dict&)num_attrs {
  NSMutableAttributedString* attr_str = [NSMutableAttributedString new];
  if (self.searching) {
    AppendAttrString(attr_str, "Found ", attrs);
    AppendAttrString(attr_str, LocalizedNumberFormat(self.numRows), num_attrs);
    AppendAttrString(attr_str, ToString(Format(" matching conversation%s", Pluralize(self.numRows))), attrs);
  } else {
    AppendAttrString(attr_str, "You have ", attrs);
    if (type_ == SUMMARY_CONVERSATIONS) {
      const int photo_count = snapshot_->conversations()->photo_count();
      AppendAttrString(attr_str, LocalizedNumberFormat(photo_count), num_attrs);
      AppendAttrString(attr_str, ToString(Format(" photo%s in ", Pluralize(photo_count))), attrs);
    }
    const int convo_count = snapshot_->conversations()->row_count();
    AppendAttrString(attr_str, LocalizedNumberFormat(convo_count), num_attrs);
    AppendAttrString(attr_str, ToString(Format(" conversation%s", Pluralize(convo_count))), attrs);
  }
  return attr_str;
}

- (CGPoint)rowTextOffset:(int)row_index {
  return CGPointMake([self textLeftMargin:row_index], self.textTopMargin);
}

- (CompositeTextLayer*)getTextLayer:(const SummaryRow&)summary_row {
  TrapdoorHandle trh = snapshot_->LoadTrapdoor(
      summary_row.identifier());
  ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
      trh->viewpoint_id(), snapshot_->db());
  CompositeTextLayer* layer =
      [InboxCardRowView newTextLayerWithTrapdoor:*trh
                                   withViewpoint:vh
                                       withWidth:self.rowWidth
                                      withWeight:summary_row.weight()];
  layer.maxWidth = [self maxWidth:trh];
  return layer;
}

// Returns whether there is only one unread system-sent "welcome"
// conversation in the inbox.
- (bool)welcomeState {
  if (snapshot_->conversations()->row_count() != 1) {
    return false;
  }
  SummaryRow row;
  snapshot_->conversations()->GetSummaryRow(0, &row);
  ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
      row.identifier(), state_->db());
  return vh->type() == "system" && vh->viewed_seq() < vh->update_seq();
}

- (void)initPlaceholder {
  if (self.zeroState) {
    if (!placeholder_) {
      placeholder_ = [[UIImageView alloc] initWithImage:kZeroConversations];
      [self addSubview:placeholder_];
      [placeholder_ centerFrameWithinSuperview];
    }
  } else {
    [self clearPlaceholder];
  }
}

- (void)clearPlaceholder {
  [placeholder_ removeFromSuperview];
  placeholder_ = NULL;
}

- (void)scrollToCurrentPhotoInRowView:(RowView*)row_view {
  // Need to scroll within the inbox card photos scroll view if necessary.
  if (controller_state_.current_photo) {
    const int64_t photo_id = controller_state_.current_photo.photoId;
    const PhotoView* p = [row_view findPhotoView:photo_id];
    if (p) {
      InboxCardRowView* inbox_row_view = (InboxCardRowView*)row_view;
      const UIScrollView* sv = inbox_row_view.photoSection;
      sv.contentOffsetY = std::min<float>(p.frame.origin.y, sv.contentOffsetMaxY);
    }
  }
}

- (void)updateMessage {
  NSString* message;
  if (self.numSelected == 0) {
    message = @"Select Photos to Unshare, Export or Forward";
  } else {
    message = Format("%d Photo%s Selected", self.numSelected,
                     Pluralize(self.numSelected));
  }
  [state_->root_view_controller().statusBar
      setMessage:message
      activity:false
      type:STATUS_MESSAGE_UI];
}

- (int64_t)getIdForSummaryRow:(const SummaryRow&)row {
  return row.identifier();
}

- (int)getUnfilteredRowIndexForId:(int64_t)row_id {
  return snapshot_->conversations()->GetViewpointRowIndex(row_id);
}

- (void)inboxCardAddPhotos:(InboxCardRowView*)row_view {
  ControllerState new_controller_state;
  new_controller_state.current_viewpoint = row_view.trapdoor->viewpoint_id();
  state_->root_view_controller().conversationLayoutController.pendingAddPhotos = true;
  [state_->root_view_controller() showConversation:new_controller_state];
}

- (void)inboxCardMuteConvo:(InboxCardRowView*)row_view {
  MuteConversations(state_, row_view.frame, self,
                    L(row_view.trapdoor->viewpoint_id()), true, ^(bool finished) {});
}

- (void)inboxCardRemoveConvo:(InboxCardRowView*)row_view {
  RemoveConversations(state_, row_view.frame, self,
                      L(row_view.trapdoor->viewpoint_id()), ^(bool finished) {});
}

- (void)inboxCardUnmuteConvo:(InboxCardRowView*)row_view {
  MuteConversations(state_, row_view.frame, self,
                    L(row_view.trapdoor->viewpoint_id()), false, ^(bool finished) {});
}

- (void)toggleExpandRow:(InboxCardRowView*)row_view {
  if (!self.isRowExpanded) {
    state_->analytics()->InboxCardExpand();
  }
  [self animateExpandRow:row_view.index completion:NULL];
}

- (void)inboxCardDidScroll:(InboxCardRowView*)row_view
                scrollView:(UIScrollView*)scroll_view {
  // Pass along scroll view delegate call so that thumbnails and
  // images are properly loaded when revealed in the row view's
  // own scroll views.
  [self scrollViewDidScroll:scroll_view];
}

- (void)setCurrentPhotos:(const TrapdoorHandle&)trh {
  // Build a vector of the unique photos in the conversation.
  ControllerState controller_state =
      [state_->root_view_controller() photoLayoutController].controllerState;
  CurrentPhotos* cp = &controller_state.current_photos;
  cp->prev_callback = NULL;
  cp->next_callback = NULL;
  PhotoIdVec* v = &cp->photo_ids;
  v->clear();

  // Get a vector of all photos using PHOTOS activity rows, which yield
  // a unique set of all photos displayed in the conversation besides the
  // cover photo.
  for (int i = 0; i < trh->photos_size(); ++i) {
    const DayPhoto& photo = trh->photos(i);
    v->push_back(std::make_pair(photo.photo_id(), photo.episode_id()));
  }

  // Setup refresh callback to re-load the viewpoint summary.
  const int64_t viewpoint_id = trh->viewpoint_id();
  cp->refresh_callback = ^{
    // Take new snapshot.
    DayTable::SnapshotHandle new_snapshot = state_->day_table()->GetSnapshot(NULL);
    TrapdoorHandle new_trh = new_snapshot->LoadTrapdoor(viewpoint_id);
    [self setCurrentPhotos:new_trh];
  };

  [state_->root_view_controller() photoLayoutController].controllerState = controller_state;
}

- (void)selectPhoto:(PhotoView*)photo_view inRow:(int)row_index {
  // LOG("tapped photo %d, episode %d", photo_view.photoId, photo_view.episodeId);
  // Build a vector of the unique photos in the event.
  const int64_t vp_id = [self getIdForRowIndex:row_index];
  TrapdoorHandle trh = snapshot_->LoadTrapdoor(vp_id);
  [self setCurrentPhotos:trh];
  ControllerState new_controller_state =
      [state_->root_view_controller() photoLayoutController].controllerState;
  new_controller_state.current_photo = photo_view;
  new_controller_state.current_episode = photo_view.episodeId;
  new_controller_state.current_viewpoint = vp_id;
  [state_->root_view_controller() showPhoto:new_controller_state];
}

- (void)populateAutocomplete:(SummaryAutocompleteResults*)results forQuery:(const Slice&)query {
  PopulateConversationAutocomplete(state_, results, query);
}

- (void)populateSearchResults:(vector<SummaryRow>*)results forQuery:(const Slice&)s {
  PopulateConversationSearchResults(state_, snapshot_->conversations(), results, s, &row_map_);
}

@end  // ConversationSummaryView
