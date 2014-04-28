// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "Appearance.h"
#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "CheckmarkBadge.h"
#import "CompositeTextLayers.h"
#import "DayTable.h"
#import "InboxCardRowView.h"
#import "LayoutUtils.h"
#import "Logging.h"
#import "PhotoView.h"
#import "TileLayout.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"
#import "ViewpointTable.h"

namespace {

const float kTitleHeight = 58;
const float kTitleHeightUnviewed = 62;
const float kFooterHeight = 24;
const float kTopMargin = 6;
const float kBottomMargin = 6;
const float kInboxCardMargin = 8;
const float kAddPhotoTopMargin = 0.5;
const float kFloatingBottomMargin = 2;
const float kFloatingStatsMargin = 20;
const float kFloatingStatsTopMargin = 13.5;
const float kFooterStatsMargin = 16;
const float kFooterStatsTopMargin = 4;
const float kInboxCardMutedRightMargin = 12;
const float kInboxCardCoverPhotoHeight = 36;
const float kInboxCardCoverPhotoWidth = 36;
const float kInboxCardIconWidth = 28;
const int kInboxCardMaxThumbnails = 4;
const float kOptionButtonHeight = 52;
const float kOptionButtonHeightUnviewed = 56;
const float kOptionsOverhang = 32;
const float kOptionsOpenThreshold = 64;

LazyStaticUIFont kOptionsButtonFont = {
  kProximaNovaSemibold, 17
};
LazyStaticCTFont kInboxCardInfoFont = {
  kProximaNovaRegular, 11
};
LazyStaticCTFont kInboxCardSymbolFont = {
  kProximaNovaRegular, 12
};
LazyStaticUIFont kInboxCardExpandFont = {
  kProximaNovaRegular, 11
};
LazyStaticUIFont kInboxCardAddPhotosFont = {
  kProximaNovaRegular, 12
};

LazyStaticHexColor kInboxCardExpandColor = { "#ffffff" };
LazyStaticHexColor kInboxCardInfoColor = { "#ffffff" };
LazyStaticHexColor kInboxCardInfoNewColor = { "#fe9524" };
LazyStaticHexColor kInboxCardInfoFooterColor = { "#686666" };
LazyStaticHexColor kInboxCardAddPhotosColor = { "#2070aa" };

LazyStaticHexColor kRemoveBackgroundColor = { "#c73926" };
LazyStaticHexColor kMuteBackgroundColor = { "#7f7c7c" };
LazyStaticHexColor kOptionsTextColor = { "#ffffff" };
LazyStaticHexColor kOptionsTextActiveColor = { "#c7c9c9" };

LazyStaticImage kInboxCardContainerTop(
    @"inbox-card-container-top.png", UIEdgeInsetsMake(0, 13, 0, 13));
LazyStaticImage kInboxCardContainerBottom(
    @"inbox-card-container-bottom.png", UIEdgeInsetsMake(0, 13, 0, 13));
LazyStaticImage kInboxCardContainerUnread(
    @"inbox-card-container-unread.png", UIEdgeInsetsMake(0, 13, 0, 13));
LazyStaticImage kInboxCardContainerMask(
    @"inbox-card-container-mask.png");
LazyStaticImage kInboxCardCoverphotoCorners(
    @"inbox-card-coverphoto-corners.png");
LazyStaticImage kInboxCardGradient(
    @"inbox-card-gradient.png");
LazyStaticImage kInboxCardIconAddPhotos(
    @"inbox-card-icon-addphotos.png");
LazyStaticImage kInboxCardIconCollapse(
    @"inbox-card-icon-collapse.png");
LazyStaticImage kInboxCardIconExpand(
    @"inbox-card-icon-expand.png");
LazyStaticImage kInboxCardIconFloating(
    @"inbox-card-icon-floating.png", UIEdgeInsetsMake(0, 21, 0, 21));
LazyStaticImage kInboxCardIconMuted(
    @"inbox-card-icon-muted.png");
LazyStaticImage kInboxCardRidges(
    @"inbox-card-ridges.png");

// Enum constants describing the various stages of layout:
// 1. Prepare - places all layers at starting positions for animation
// 2. Commit - places all layers at ending positions for animation
// 3. Finalize - places all layers in finalized positions for viewing
enum LayoutStep {
  LAYOUT_PREPARE = 1,
  LAYOUT_COMMIT,
  LAYOUT_FINALIZE,
};

UIButton* NewOptionButton(NSString* title, id target, SEL selector,
                          UIColor* bg_color, float width, float height) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.titleLabel.font = kOptionsButtonFont;
  [b setTitle:title
     forState:UIControlStateNormal];
  [b setTitleColor:kOptionsTextColor.get()
          forState:UIControlStateNormal];
  [b setTitleColor:kOptionsTextActiveColor.get()
          forState:UIControlStateHighlighted];
  b.backgroundColor = bg_color;
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  b.frameSize = CGSizeMake(width, height);
  return b;
}

UIButton* NewExpandButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.titleLabel.font = kInboxCardExpandFont;
  [b setBackgroundImage:kInboxCardIconFloating
               forState:UIControlStateNormal];
  [b setTitleColor:kInboxCardExpandColor.get()
          forState:UIControlStateNormal];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  return b;
}

UIButton* NewRidgesButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  [b setBackgroundImage:kInboxCardRidges
               forState:UIControlStateNormal];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  return b;
}

UIButton* NewAddPhotosButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.titleLabel.font = kInboxCardAddPhotosFont;
  UIImage* image = kInboxCardIconAddPhotos;
  [b setTitle:@"Add Photo  "
     forState:UIControlStateNormal];
  [b setImage:image
     forState:UIControlStateNormal];
  [b setTitleColor:kInboxCardAddPhotosColor.get()
          forState:UIControlStateNormal];
  const CGSize size = [[b titleForState:UIControlStateNormal] sizeWithFont:kInboxCardAddPhotosFont];
  b.titleEdgeInsets = UIEdgeInsetsMake(1, -image.size.width, 0, 0);
  b.imageEdgeInsets = UIEdgeInsetsMake(0, size.width, 0, 0);
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  b.frameHeight = kFooterHeight;
  return b;
}

}  // namespace

@implementation InboxCardRowView

@synthesize trapdoor = trh_;
@synthesize inboxCardRowEnv = inbox_card_row_env_;
@synthesize photoSection = photo_section_;

- (id)initWithState:(UIAppState*)state
       withTrapdoor:(const TrapdoorHandle&)trh
        interactive:(bool)interactive
          withWidth:(float)width {
  if (self = [super init]) {
    state_ = state;
    trh_ = trh;
    width_ = width;
    expanded_ = false;

    self.autoresizesSubviews = YES;
    self.backgroundColor = [UIColor clearColor];
    self.tag = kInboxCardTag;
    self.viewpointId = trh_->viewpoint_id();

    // Initialize the photo layouts to get height of photos in collapsed layout.
    bool can_expand = false;
    photo_section_ = [UIScrollView new];
    photo_height_ = InitInboxCardPhotos(
        state_, self, photo_section_, trh_->photos(), SUMMARY_COLLAPSED_LAYOUT,
        width_ - kInboxCardMargin * 2, &can_expand);
    for (int i = 0; i < self.photos->size(); ++i) {
      PhotoView* p = (*self.photos)[i];
      p.viewpointId = trh->viewpoint_id();
      collapsed_photos_.push_back(p);
      collapsed_frames_[p] = p.frame;
    }

    // Compute the size of the title.
    title_height_ = trh_->unviewed_content() ? kTitleHeightUnviewed : kTitleHeight;
    footer_height_ = can_expand ? 0 : kFooterHeight;

    // The size of the full card includes top & bottom margins.
    height_ = title_height_ + photo_height_ + footer_height_ + kBottomMargin;
    self.frame = CGRectMake(0, 0, width_, height_);
    const CGRect b = self.bounds;

    // Configure layer mask for card.
    UIImage* mask_image = kInboxCardContainerMask.get();
    mask_ = [CALayer layer];
    mask_.contents = (id)mask_image.CGImage;
    mask_.contentsScale = [UIScreen mainScreen].scale;
    mask_.contentsCenter = CGRectMake(12.5 / mask_image.size.width, 10.5 / mask_image.size.height,
                                      1.0 / mask_image.size.width, 1.0 / mask_image.size.height);
    mask_.frame = b;
    self.layer.mask = mask_;

    title_section_ = [UIScrollView new];
    title_section_.autoresizesSubviews = YES;
    title_section_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleBottomMargin;
    title_section_.scrollsToTop = NO;
    title_section_.bounces = NO;
    title_section_.showsHorizontalScrollIndicator = NO;
    title_section_.frameSize = CGSizeMake(b.size.width, title_height_);
    title_section_.contentSize = CGSizeMake(b.size.width * 2 - kOptionsOverhang, title_height_);
    title_section_.delegate = self;
    title_section_.scrollEnabled = interactive;
    [self addSubview:title_section_];

    // Mute & remove.
    if (interactive) {
      button_tray_ = [UIView new];  // button tray is pinned in scroll view
      button_tray_.frame = title_section_.bounds;
      [title_section_ addSubview:button_tray_];
      [self configureOptionButtons];
    }

    ContentView* title_content = [ContentView new];
    title_content.viewpointId = trh_->viewpoint_id();
    title_content.frame = title_section_.bounds;
    [title_section_ addSubview:title_content];

    // Set title section scroll offset if one was saved.
    if (ContainsKey(*[InboxCardRowView cardStateMap], trh_->viewpoint_id())) {
      const float offset = (*[InboxCardRowView cardStateMap])[trh_->viewpoint_id()].title_offset;
      title_section_.contentOffset = CGPointMake(offset, 0);
      [self scrollViewDidScroll:title_section_];
    }

    UIImageView* bg;
    if (trh_->unviewed_content()) {
      bg = [[UIImageView alloc] initWithImage:kInboxCardContainerUnread];
    } else {
      bg = [[UIImageView alloc] initWithImage:kInboxCardContainerTop];
    }
    bg.frame = title_content.bounds;
    [title_content addSubview:bg];

    // Add cover photo.
    if (trh_->has_cover_photo()) {
      const CGRect cover_photo_frame =
          CGRectMake(kInboxCardMargin * 2, title_height_ - kInboxCardMargin - kInboxCardCoverPhotoHeight,
                     kInboxCardCoverPhotoWidth, kInboxCardCoverPhotoHeight);
      cover_photo_ = NewPhotoView(state, trh_->cover_photo().episode_id(),
                                  trh_->cover_photo().photo_id(),
                                  trh_->cover_photo().aspect_ratio(),
                                  cover_photo_frame);
      cover_photo_.autoresizingMask = UIViewAutoresizingFlexibleBottomMargin;
      cover_photo_.selectable = false;
      cover_photo_.tag = kInboxCardThumbnailTag;
      cover_photo_.viewpointId = trh_->viewpoint_id();
      self.photos->push_back(cover_photo_);

      // Configure layer mask for cover photo.
      UIImageView* mask = [[UIImageView alloc] initWithImage:kInboxCardCoverphotoCorners];
      [cover_photo_ addSubview:mask];

      [title_content addSubview:cover_photo_];
    }

    if (interactive) {
      ridges_button_ = NewRidgesButton(self, @selector(toggleShowOptions));
      ridges_button_.frameRight = self.boundsWidth;
      ridges_button_.frameBottom = title_height_;
      [title_content addSubview:ridges_button_];

      // Add muted icon to card if applicable.
      if (trh_->muted()) {
        muted_ = [[UIImageView alloc] initWithImage:kInboxCardIconMuted];
        muted_.frameBottom = title_height_;
        muted_.frameRight = self.boundsWidth - kInboxCardMutedRightMargin;
        [title_content addSubview:muted_];
      }
    }

    photo_section_.backgroundColor = [UIColor blackColor];
    photo_section_.clipsToBounds = YES;
    photo_section_.scrollsToTop = NO;
    photo_section_.bounces = NO;  // this allows the nested scroll views to work together properly
    photo_section_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    photo_section_.frame = CGRectMake(kInboxCardMargin, title_height_,
                                      b.size.width - kInboxCardMargin * 2, photo_height_);
    photo_section_.tag = kEventBodySectionTag;
    photo_section_.delegate = self;
    [self addSubview:photo_section_];

    // Info text.
    NSMutableAttributedString* attr_str = [NSMutableAttributedString new];
    if (trh_->photo_count() > 0) {
      UIColor* color = trh_->new_photo_count() > 0 ? kInboxCardInfoNewColor :
                       can_expand ? kInboxCardInfoColor : kInboxCardInfoFooterColor;
      [attr_str appendAttributedString:NewAttrString(
            kPhotoSymbol, kInboxCardSymbolFont, color.CGColor)];
      [attr_str appendAttributedString:NewAttrString(
            Format(" %s", trh_->FormatPhotoCount()), kInboxCardInfoFont, color.CGColor)];
    }
    if (trh_->comment_count() > 0) {
      UIColor* color = trh_->new_comment_count() > 0 ? kInboxCardInfoNewColor :
                       can_expand ? kInboxCardInfoColor : kInboxCardInfoFooterColor;
      [attr_str appendAttributedString:NewAttrString(
            Format("%s%s", trh_->photo_count() > 0 ? kSpaceSymbol : "", kCommentSymbol),
            kInboxCardSymbolFont, color.CGColor)];
      [attr_str appendAttributedString:NewAttrString(
            Format(" %s", trh_->FormatCommentCount()), kInboxCardInfoFont, color.CGColor)];
    }
    TextLayer* info = [TextLayer new];
    info.attrStr = attr_str;
    info.maxWidth = width_;

    // Init the see more/fewer buttons if we can expand.
    if (can_expand) {
      if (interactive) {
        // Gradient over photos.
        gradient_ = [[UIImageView alloc] initWithImage:kInboxCardGradient];
        gradient_.autoresizingMask =
            UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleTopMargin;
        gradient_.frameLeft = kInboxCardMargin;
        gradient_.frameBottom = height_ - kBottomMargin;
        gradient_.frameWidth = photo_section_.frameWidth;
        [self addSubview:gradient_];

        expand_button_ = NewExpandButton(self, @selector(toggleExpandRow));
        expand_button_.autoresizingMask = UIViewAutoresizingFlexibleTopMargin;
        expand_button_.frameRight = self.boundsWidth;
        expand_button_.frameBottom = (expanded_ ? expanded_height_ : height_) + kFloatingBottomMargin;
        [self addSubview:expand_button_];
        [self configureExpandButton];

        UIImageView* floating = [[UIImageView alloc] initWithImage:kInboxCardIconFloating];
        floating.autoresizingMask = UIViewAutoresizingFlexibleTopMargin;
        floating.frameBottom = height_ + kFloatingBottomMargin;
        [self addSubview:floating];

        const float floating_width = info.frameWidth + kFloatingStatsMargin * 2;
        floating.frameWidth = floating_width;
        [floating.layer addSublayer:info];
        info.frameLeft = kFloatingStatsMargin;
        info.frameTop = kFloatingStatsTopMargin;
      }
    } else {
      UIImageView* bottom = [[UIImageView alloc] initWithImage:kInboxCardContainerBottom];
      bottom.autoresizingMask = UIViewAutoresizingFlexibleWidth;
      bottom.frameWidth = self.frameWidth;
      bottom.frameTop = title_height_;
      [self addSubview:bottom];

      [bottom.layer addSublayer:info];
      info.frameLeft = kFooterStatsMargin;
      info.frameTop = kFooterStatsTopMargin;

      // "Add Photo >" button.
      if (interactive) {
        UIButton* add_photo = NewAddPhotosButton(self, @selector(addPhoto));
        add_photo.frameRight = self.boundsWidth - kInboxCardMargin * 2;
        add_photo.frameTop = bottom.frameTop + kAddPhotoTopMargin;
        [self addSubview:add_photo];
      }
    }
  }

  return self;
}

- (void)configureExpandButton {
  UIImage* image = expanded_ ? kInboxCardIconCollapse : kInboxCardIconExpand;
  [expand_button_ setTitle:expanded_ ? @"Less " : @"More " forState:UIControlStateNormal];
  [expand_button_ setImage:image forState:UIControlStateNormal];
  const CGSize size = [[expand_button_ titleForState:UIControlStateNormal] sizeWithFont:kInboxCardExpandFont];
  const float width = 18 * 2 + image.size.width + size.width;
  expand_button_.titleEdgeInsets = UIEdgeInsetsMake(1, 6, 0, image.size.width + 18);
  expand_button_.imageEdgeInsets = UIEdgeInsetsMake(0, size.width + 18, 0, 16);
  expand_button_.frameSize = CGSizeMake(width, kInboxCardIconFloating.get().size.height);
  expand_button_.frameRight = self.boundsWidth;
}

- (void)configureOptionButtons {
  [mute_button_ removeFromSuperview];
  [remove_button_ removeFromSuperview];

  const float width = (self.boundsWidth - kInboxCardMargin * 2) / 2;
  const float height = trh_->unviewed_content() ? kOptionButtonHeightUnviewed : kOptionButtonHeight;
  if (trh_->muted()) {
    mute_button_ = NewOptionButton(
        @"Unmute", self, @selector(unmuteConvo), kMuteBackgroundColor, width, height);
  } else {
    mute_button_ = NewOptionButton(
        @"Mute", self, @selector(muteConvo), kMuteBackgroundColor, width, height);
  }
  [button_tray_ insertSubview:mute_button_ atIndex:0];
  remove_button_ = NewOptionButton(
      @"Remove", self, @selector(removeConvo), kRemoveBackgroundColor, width, height);
  [button_tray_ insertSubview:remove_button_ atIndex:0];

  mute_button_.frameTop = kTopMargin;
  mute_button_.frameLeft = kInboxCardMargin;
  remove_button_.frameTop = kTopMargin;
  remove_button_.frameLeft = mute_button_.frameRight;
}

- (void)addTextLayer:(CompositeTextLayer*)layer {
  [super addTextLayer:layer];
  [title_section_.layer addSublayer:layer];
  layer.transition = 0;
}

- (void)toggleShowOptions {
  float new_offset = 0;
  if (title_section_.contentOffset.x == 0) {
    new_offset = self.frameWidth - kOptionsOverhang;
  }
  [UIView animateWithDuration:0.3
                        delay:0.0
                      options:UIViewAnimationCurveEaseOut
                   animations:^{
      title_section_.contentOffset = CGPointMake(new_offset, 0);
    }
                   completion:NULL];
}

- (void)addPhoto {
  [inbox_card_row_env_ inboxCardAddPhotos:self];
}

- (void)muteConvo {
  [inbox_card_row_env_ inboxCardMuteConvo:self];
  [self toggleShowOptions];
}

- (void)removeConvo {
  [inbox_card_row_env_ inboxCardRemoveConvo:self];
  [self toggleShowOptions];
}

- (void)unmuteConvo {
  [inbox_card_row_env_ inboxCardUnmuteConvo:self];
  [self toggleShowOptions];
}

- (void)toggleExpandRow {
  [inbox_card_row_env_ toggleExpandRow:self];
}

- (void)willMoveToSuperview:(UIView*)new_superview {
  if (!new_superview) {
    // Maintain the scroll offsets map.
    if (expanded_ || title_section_.contentOffset.x != 0) {
      CardState& state = (*[InboxCardRowView cardStateMap])[trh_->viewpoint_id()];
      state.photo_offset = photo_section_.contentOffset.y;
      state.title_offset = title_section_.contentOffset.x;
    } else {
      [InboxCardRowView cardStateMap]->erase(trh_->viewpoint_id());
    }
  }
}

- (bool)hasPhoto:(int64_t)photo_id {
  for (int i = 0; i < trh_->photos_size(); ++i) {
    if (photo_id == trh_->photos(i).photo_id()) {
      return true;
    }
  }
  return false;
}

- (float)animateToggleExpandPrepare:(float)max_height {
  return [self animateToggleExpandPrepare:max_height animated:true];
}

- (float)animateToggleExpandPrepare:(float)max_height
                           animated:(bool)animated {
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  if (!expanded_) {
    if (!expanded_initialized_) {
      const float extra_height = title_height_ + kBottomMargin + footer_height_;
      [self initExpandedLayout];
      expanded_height_ =
          std::min<float>(max_height, expanded_photo_height_ + extra_height);
      expanded_photo_frame_height_ = expanded_height_ - extra_height;
      expanded_initialized_ = true;
    }

    *self.photos = expanded_photos_;
    [self layoutExpandedPhotos:LAYOUT_PREPARE];
  } else {
    *self.photos = collapsed_photos_;
    [self layoutCollapsedPhotos:LAYOUT_PREPARE];
  }
  self.photos->push_back(cover_photo_);
  [CATransaction commit];

  return expanded_ ? height_ : expanded_height_;
}

- (void)animateToggleExpandCommit {
  [self animateToggleExpandCommit:true];
}

- (void)animateToggleExpandCommit:(bool)animated {
  // Toggle expansion.
  expanded_ = !expanded_;

  // If no longer expanded, clear the scroll offset map.
  if (!expanded_) {
    [InboxCardRowView cardStateMap]->erase(trh_->viewpoint_id());
  }

  self.layer.mask = nil;
  if (expanded_) {
    title_section_.contentOffset = CGPointMake(0, 0);
    photo_section_.frameHeight = expanded_photo_frame_height_;
    ridges_button_.alpha = trh_->photos_size() ? 0 : 1;
    gradient_.alpha = trh_->photos_size() ? 0 : 1;
    [self layoutExpandedPhotos:LAYOUT_COMMIT];
  } else {
    photo_section_.frameHeight = photo_height_;
    [photo_section_ setContentOffset:CGPointMake(0, 0) animated:animated];
    ridges_button_.alpha = 1;
    gradient_.alpha = 1;
    [self layoutCollapsedPhotos:LAYOUT_COMMIT];
  }
}

- (void)animateToggleExpandFinalize {
  [self animateToggleExpandFinalize:true];
}

- (void)animateToggleExpandFinalize:(bool)animated {
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  if (!expanded_) {
    [self layoutCollapsedPhotos:LAYOUT_FINALIZE];
    title_section_.scrollEnabled = YES;
    photo_section_.contentSize = photo_section_.frameSize;
    mask_.frameHeight = height_;
  } else {
    [self layoutExpandedPhotos:LAYOUT_FINALIZE];
    title_section_.scrollEnabled = NO;
    photo_section_.contentSize =
        CGSizeMake(photo_section_.frameWidth, expanded_photo_height_);
    mask_.frameHeight = expanded_height_;
  }
  self.layer.mask = mask_;
  [self configureExpandButton];

  [CATransaction commit];
}

- (float)toggleExpand:(float)max_height {
  const float height = [self animateToggleExpandPrepare:max_height animated:false];
  self.frameHeight = height;
  [self animateToggleExpandCommit:false];
  [self animateToggleExpandFinalize:false];
  const int64_t vp_id = trh_->viewpoint_id();
  if (ContainsKey(*[InboxCardRowView cardStateMap], vp_id)) {
    const float offset = (*[InboxCardRowView cardStateMap])[vp_id].photo_offset;
    photo_section_.contentOffset = CGPointMake(0, offset);
  }
  return height;
}

- (void)initExpandedLayout {
  std::unordered_map<int64_t, PhotoView*> photo_map;
  for (int i = 0; i < collapsed_photos_.size(); ++i) {
    PhotoView* pv = collapsed_photos_[i];
    photo_map[pv.photoId] = pv;
  }

  // Create a temporary view to hold expanded layout.
  RowView* row_view = [RowView new];
  expanded_photo_height_ = InitInboxCardPhotos(
      state_, row_view, row_view, trh_->photos(), SUMMARY_EXPANDED_LAYOUT,
      width_ - kInboxCardMargin * 2, NULL);
  UIView* top_photo_view = NULL;

  // Move all photo views out of the episode row and into photo_section_.
  for (int i = 0; i < row_view.photos->size(); ++i) {
    // Build map from collapsed to expanded view & vice versa.
    PhotoView* pv = (*row_view.photos)[i];
    pv.viewpointId = trh_->viewpoint_id();

    // If the photo id matches a collapsed photo view, don't insert
    // the photo but record the linkage--we always just animate the
    // collapsed photo.
    PhotoView* ov = FindOrNull(&photo_map, pv.photoId);
    if (ov) {
      expanded_frames_[ov] = pv.frame;
      expanded_photos_.push_back(ov);
    } else {
      expanded_frames_[pv] = pv.frame;
      expanded_photos_.push_back(pv);
      pv.frame = expanded_frames_[pv];

      pv.layer.rasterizationScale = 2.0;
      pv.layer.shouldRasterize = YES;

      // Move photo to photo_section_ view. Start at index 1 and then
      // always add the latest photo on top of the previous. This helps
      // the animation by allowing sampled photos which have to travel
      // the furthest to avoid being obscured as they travel.
      if (!top_photo_view) {
        [photo_section_ insertSubview:pv atIndex:1];
      } else {
        [photo_section_ insertSubview:pv aboveSubview:top_photo_view];
      }
      top_photo_view = pv;
    }
  }

  // Verify that all collapsed frames map to an expanded version.
  for (ViewFrameMap::iterator iter = collapsed_frames_.begin();
       iter != collapsed_frames_.end();
       ++iter) {
    DCHECK(ContainsKey(expanded_frames_, iter->first));
  }
}

- (void)layoutCollapsedPhotos:(LayoutStep)l_step {
  // If preparing, set frames of collapsed views to expanded versions.
  for (ViewFrameMap::iterator iter = collapsed_frames_.begin();
       iter != collapsed_frames_.end();
       ++iter) {
    PhotoView* v = iter->first;
    v.layer.zPosition = 1;
    if (l_step == LAYOUT_PREPARE) {
      v.frame = expanded_frames_[v];
    } else {
      v.frame = collapsed_frames_[v];
    }
  }
}

- (void)layoutExpandedPhotos:(LayoutStep)l_step {
  // If preparing, show expanded views which also have collapsed
  // counterparts with collapsed frames; all others are hidden.
  // If !preparing, show all expanded views at expanded frames.
  for (ViewFrameMap::iterator iter = expanded_frames_.begin();
       iter != expanded_frames_.end();
       ++iter) {
    PhotoView* v = iter->first;
    const bool has_counterpart = ContainsKey(collapsed_frames_, v);
    if (has_counterpart && l_step == LAYOUT_PREPARE) {
      v.layer.zPosition = 1;
      v.frame = collapsed_frames_[v];
    } else {
      v.frame = expanded_frames_[v];
    }
  }
}

- (void)scrollViewDidScroll:(UIScrollView*)scroll_view {
  // Pin the button tray.
  if (scroll_view == title_section_) {
    button_tray_.frameLeft = scroll_view.contentOffset.x;
  }
  [inbox_card_row_env_ inboxCardDidScroll:self scrollView:scroll_view];
}

- (void)scrollViewWillEndDragging:(UIScrollView*)scroll_view
                     withVelocity:(CGPoint)velocity
              targetContentOffset:(inout CGPoint *)target {
  if (velocity.x > 0 ||
      (velocity.x == 0 &&
       scroll_view.contentOffset.x > kOptionsOpenThreshold)) {
    target->x = self.frameWidth - kOptionsOverhang;
  } else {
    target->x = 0;
  }
}

+ (CardStateMap*)cardStateMap {
  static CardStateMap* card_state_map = NULL;

  DCHECK(dispatch_is_main_thread());
  if (card_state_map == NULL) {
    card_state_map = new CardStateMap;
  }

  return card_state_map;
}

+ (float)getInboxCardHeightWithState:(UIAppState*)state
                        withTrapdoor:(const Trapdoor&)trap
                           withWidth:(float)width {
  const float title_height = trap.unviewed_content() ? kTitleHeightUnviewed : kTitleHeight;
  bool can_expand = false;
  const float photo_height = InitInboxCardPhotos(
      state, NULL, NULL, trap.photos(), SUMMARY_COLLAPSED_LAYOUT,
      width - kInboxCardMargin * 2, &can_expand);
  const float footer_height = can_expand ? 0 : kFooterHeight;
  return title_height + photo_height + footer_height + kBottomMargin;
}

+ (CompositeTextLayer*)newTextLayerWithTrapdoor:(const Trapdoor&)trap
                                  withViewpoint:(const ViewpointHandle&)vh
                                      withWidth:(float)width
                                     withWeight:(float)weight {
  return [[InboxCardTextLayer alloc] initWithTrapdoor:trap
                                        withViewpoint:vh
                                           withWeight:weight];
}

@end  // InboxCardRowView
