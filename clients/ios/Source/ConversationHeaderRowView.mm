// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AttrStringUtils.h"
#import "ConversationHeaderRowView.h"
#import "FollowerFieldView.h"
#import "LayoutUtils.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kConversationMargin = 8;
const float kConversationSpacing = 8;
const float kConversationTopOffset = 64;
const float kCoverPhotoRatio = 0.95;
const float kCallToActionCornerRadius = 5;
const float kCallToActionWidth = 304;
const float kCallToActionHeight = 88;
const float kMinConversationHeaderYOffset = 150;
const float kTitleLeftMargin = 12;
const float kTitleTopMargin = -2;
const float kTitleBottomMargin = 6;

LazyStaticCTFont kTitleFont = {
  kProximaNovaRegular, 28
};
LazyStaticUIFont kCallToActionFont = {
  kProximaNovaSemibold, 16
};

LazyStaticHexColor kTitleColor = { "#3f3e3e" };
LazyStaticHexColor kTitlePlaceholderColor = { "#cfc9c9" };
LazyStaticHexColor kAddCoverPhotoColor = { "#ffffff" };
LazyStaticHexColor kAddCoverPhotoBackgroundColor = { "#00000033" };
LazyStaticHexColor kAddTitleColor = { "#3f3e3e" };

LazyStaticDict kTitleAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)kTitleFont.get(),
        kCTForegroundColorAttributeName,
        (__bridge id)kTitleColor.get().CGColor);
  }
};

LazyStaticDict kTitlePlaceholderAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)kTitleFont.get(),
        kCTForegroundColorAttributeName,
        (__bridge id)kTitlePlaceholderColor.get().CGColor);
  }
};

LazyStaticImage kConvoCoverGradient(
    @"convo-cover-gradient.png");

LazyStaticImage kOpenDropdownUnselected(@"open-dropdown-unselected.png");
LazyStaticImage kOpenDropdownUnselectedActive(@"open-dropdown-unselected-active.png");

UIView* NewSeparator() {
  UIView* v = [UIView new];
  v.backgroundColor = UIStyle::kConversationThreadColor;
  return v;
}

UIButton* NewComposeCTAButton(NSString* title, UIColor* textColor, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];

  UIImage* image = kOpenDropdownUnselected;
  const float x = (kCallToActionWidth - image.size.width) / 2;
  b.imageEdgeInsets = UIEdgeInsetsMake(10, x, 34, x);
  [b setImage:kOpenDropdownUnselected forState:UIControlStateNormal];
  [b setImage:kOpenDropdownUnselectedActive forState:UIControlStateHighlighted];

  b.titleLabel.font = kCallToActionFont.get();
  b.titleLabel.lineBreakMode = NSLineBreakByTruncatingTail;
  [b setTitle:title forState:UIControlStateNormal];
  [b setTitleColor:textColor forState:UIControlStateNormal];
  b.titleEdgeInsets = UIEdgeInsetsMake(25, -image.size.width, 0, 0);

  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];

  b.frameSize = CGSizeMake(kCallToActionWidth, kCallToActionHeight);
  return b;
}

UIButton* NewEditTitleButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  [b setImage:UIStyle::kConvoEditIconGrey forState:UIControlStateNormal];
  [b sizeToFit];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

}  // namespace

@implementation ConversationHeaderRowView

@synthesize header = header_;
@synthesize coverPhotoHeight = cover_photo_height_;
@synthesize editCoverPhotoButton = edit_cover_photo_button_;
@synthesize coverPhotoCTA = cover_photo_cta_;

- (id)initWithState:(UIAppState*)state
        viewpointId:(int64_t)viewpoint_id
      hasCoverPhoto:(bool)has_cover_photo
              width:(float)width {
  if (self = [super initWithFrame:CGRectMake(0, 0, width, 0)]) {
    vh_ = state->viewpoint_table()->LoadViewpoint(viewpoint_id, state->db());
    provisional_ = vh_->provisional();
    state_ = state;
    default_title_ = vh_->DefaultTitle();
    cover_photo_height_ = width * kCoverPhotoRatio;

    if (has_cover_photo) {
      min_height_ = cover_photo_height_;
      min_header_y_ = kMinConversationHeaderYOffset;
    } else {
      min_height_ = min_header_y_ = kCallToActionHeight +
          kConversationTopOffset + kConversationMargin * 3;

      UIView* cta_bg = [UIView new];
      cta_bg.backgroundColor = kAddCoverPhotoBackgroundColor;
      cta_bg.layer.cornerRadius = kCallToActionCornerRadius;
      cta_bg.frame = CGRectMake(
          kConversationMargin, kConversationMargin + kConversationTopOffset,
          kCallToActionWidth, kCallToActionHeight);
      [self addSubview:cta_bg];

      cover_photo_cta_ = NewComposeCTAButton(@"Add Cover Photo", kAddCoverPhotoColor, self, @selector(editCoverPhoto));
      [cta_bg addSubview:cover_photo_cta_];
    }

    header_ = [UIView new];
    header_.autoresizesSubviews = YES;
    header_.backgroundColor = [UIColor whiteColor];

    title_container_ = [UIView new];
    title_container_.autoresizesSubviews = YES;
    [header_ addSubview:title_container_];

    title_ = [[TextView alloc] initWithFrame:CGRectMake(0, 0, self.textWidth, 0)];
    title_.autoresizingMask = UIViewAutoresizingFlexibleHeight;
    title_.autocorrectionType = UITextAutocorrectionTypeDefault;
    title_.autocapitalizationType = UITextAutocapitalizationTypeSentences;
    title_.autoresizesSubviews = YES;
    title_.delegate = self;
    title_.linkStyle = UIStyle::kLinkAttributes;
    title_.keyboardAppearance = UIKeyboardAppearanceAlert;
    title_.returnKeyType = UIReturnKeyDone;
    title_.tag = kConversationTitleTag;
    title_.placeholderAttrText = NewAttrString(default_title_, kTitlePlaceholderAttributes);
    [title_ setAttributes:kTitleAttributes];
    title_.editableText = NewNSString(vh_->has_title() ? vh_->FormatTitle(false) : "");
    [title_container_ addSubview:title_];

    title_container_.frame = self.titleContainerFrame;

    title_edit_ = NewEditTitleButton(self, @selector(startEditingTitle));
    title_edit_.autoresizingMask =
        UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleTopMargin;
    title_edit_.frameRight = title_container_.frameWidth - kConversationMargin * 2;
    title_edit_.frameBottom = title_container_.frameHeight;
    [title_container_ addSubview:title_edit_];

    title_cta_ = NewComposeCTAButton(@"Add Title", kAddTitleColor, self, @selector(startEditingTitle));
    title_cta_.frame = CGRectMake(0, 0, kCallToActionWidth, kCallToActionHeight);
    [header_ addSubview:title_cta_];

    show_title_cta_ = false;
    [self maybeCreateTitleCTA];

    title_separator_ = NewSeparator();
    title_separator_.frame = self.titleSeparatorFrame;

    followers_ = [[FollowerFieldView alloc] initWithState:state_
                                              provisional:provisional_
                                                    width:self.headerWidth];
    followers_.enabled = !provisional_;
    followers_.hidden = (provisional_ && followers_.empty) ? YES : NO;
    followers_.delegate = self;

    followers_separator_ = NewSeparator();
    followers_separator_.frame = self.followersSeparatorFrame;

    header_.frame = self.headerFrame;
    [header_ addSubview:title_separator_];
    [header_ addSubview:followers_];
    [header_ addSubview:followers_separator_];

    [self addSubview:header_];

    header_cap_ = [[UIImageView alloc] initWithImage:UIStyle::kConvoHeaderCap];
    header_cap_.autoresizingMask = UIViewAutoresizingFlexibleBottomMargin;
    header_cap_.frame = self.headerCapFrame;
    [self insertSubview:header_cap_ belowSubview:header_];

    self.frameSize = [self sizeThatFits:CGSizeZero];
    self.tag = kConversationHeaderRowTag;

    [self setEditMode:EDIT_HEADER_NONE];
  }
  return self;
}

// If a point falls outside the title container or followers view, it
// should cancel the current editing mode.
- (bool)maybeStopEditing:(CGPoint)p {
  if (provisional_) {
    return false;  // provisional convo edits require an intentional commit via "Done" button
  }
  if ((self.editingTitle &&
       ![title_container_ pointInside:[title_container_ convertPoint:p fromView:self] withEvent:NULL]) ||
      (self.editingFollowers &&
       ![followers_ pointInside:[followers_ convertPoint:p fromView:self] withEvent:NULL])) {
    // TODO(spencer): evaluate whether commit should be true here or not.
    [self.env rowViewStopEditing:self commit:true];
    [self setEditMode:EDIT_HEADER_NONE];
    return true;
  }
  return false;
}

- (void)maybeCreateTitleCTA {
  if (self.emptyTitle && !self.editingTitle) {
    show_title_cta_ = true;
    title_container_.alpha = 0;
    title_cta_.alpha = 1;
    [self layoutSubviews];
  } else {
    show_title_cta_ = false;
    title_container_.alpha = 1;
    title_cta_.alpha = 0;
    [self layoutSubviews];
  }
}

- (bool)hasFocus {
  // We have focus if either the keyboard is up for either title or
  // followers, or the followers field view has focus.
  return [title_ isFirstResponder] || followers_.hasFocus;
}

- (void)setEditMode:(HeaderEditMode)edit_mode {
  edit_mode_ = edit_mode;
  switch (edit_mode_) {
    case EDIT_HEADER_NONE:
      title_.editable = YES;
      title_.userInteractionEnabled = YES;
      title_edit_.hidden = NO;
      followers_.editable = followers_.enabled;
      followers_.userInteractionEnabled = YES;
      cover_photo_cta_.userInteractionEnabled = YES;
      break;
    case EDIT_HEADER_TITLE:
      title_.editable = YES;
      title_.userInteractionEnabled = YES;
      title_edit_.hidden = YES;
      followers_.editable = NO;
      followers_.userInteractionEnabled = NO;
      cover_photo_cta_.userInteractionEnabled = NO;
      break;
    case EDIT_HEADER_FOLLOWERS:
      title_.editable = NO;
      title_.userInteractionEnabled = NO;
      title_edit_.hidden = YES;
      followers_.editable = YES;
      followers_.userInteractionEnabled = YES;
      cover_photo_cta_.userInteractionEnabled = NO;
      break;
    case EDIT_HEADER_PHOTOS:
      title_.editable = NO;
      title_.userInteractionEnabled = NO;
      title_edit_.hidden = YES;
      followers_.editable = NO;
      followers_.userInteractionEnabled = NO;
      cover_photo_cta_.userInteractionEnabled = NO;
      break;
  }
}

- (bool)editing {
  return edit_mode_ != EDIT_HEADER_NONE;
}

- (void)setEditing:(bool)value {
  if (value) {
    if (edit_mode_ == EDIT_HEADER_NONE) {
      [self setEditMode:EDIT_HEADER_PHOTOS];
    }
    // We're entering edit mode, stash away the original text.
    if (!title_orig_text_) {
      title_orig_text_ = title_.editableText;
    }
  } else {
    [self setEditMode:EDIT_HEADER_NONE];
    // We're exiting edit mode, revert the text.
    if (title_orig_text_) {
      title_.editableText = title_orig_text_;
      title_orig_text_ = NULL;
    }
    [self stopEditingTitle];
    [self stopEditingFollowers];
  }
}

- (UIView*)editingView {
  if (edit_mode_ == EDIT_HEADER_TITLE) {
    return title_;
  } else if (edit_mode_ == EDIT_HEADER_FOLLOWERS) {
    return followers_;
  }
  return NULL;
}

- (bool)modified {
  if (followers_.editing) {
    return true;
  }
  if (!title_orig_text_) {
    return false;
  }
  return ToSlice(title_.editableText) != ToSlice(title_orig_text_);
}

- (bool)selected {
  return false;
}

- (void)setSelected:(bool)value {
}

- (bool)showAllFollowers {
  return followers_.showAllFollowers;;
}

- (void)setShowAllFollowers:(bool)value {
  followers_.showAllFollowers = value;
}

- (bool)editingTitle {
  return edit_mode_ == EDIT_HEADER_TITLE;
}

- (bool)editingFollowers {
  return edit_mode_ == EDIT_HEADER_FOLLOWERS;
}

- (int)numContacts {
  return followers_.allContacts.size();
}

- (NSString*)title {
  return title_.editableText;
}

- (bool)emptyTitle {
  return [title_.editableText length] == 0;
}

- (CallbackSet*)editCoverPhotoCallback {
  return &edit_cover_photo_callback_;
}

- (void)commitEdits {
  // If we commit edits (done button), and if the title was being
  // edited but is empty, treat that as acceptance of the default
  // title used as the placeholder.
  if (self.editingTitle && ToSlice(title_.editableText).empty()) {
    title_.editableText = NewNSString(default_title_);
  }

  // Calling resign first responder commits any autosuggestions.
  [title_ resignFirstResponder];

  if (ToSlice(title_.editableText) != ToSlice(title_orig_text_)) {
    title_orig_text_ = title_.editableText;
    [self.env rowViewCommitText:self text:title_.editableText];
  }
  [self.env rowViewCommitFollowers:self
                     addedContacts:[followers_ newContacts]
                        removedIds:[followers_ removedIds]];
}

- (float)headerWidth {
  return self.frameWidth - kConversationMargin * 2;
}

- (float)textWidth {
  return self.headerWidth - kTitleLeftMargin -
      UIStyle::kConvoEditIconGrey.get().size.width;
}

// The frame of the title container (includes title + edit button).
- (CGRect)titleContainerFrame {
  if (show_title_cta_) {
    return CGRectMake(
        0, 0, kCallToActionWidth, kCallToActionHeight);
  } else {
    return CGRectMake(
        0, kTitleTopMargin, self.frameWidth,
        title_.contentHeight + kTitleBottomMargin);
  }
}

// The frame of the title or title CTA depending.
- (CGRect)titleFrame {
    return CGRectMake(
        kConversationSpacing, kTitleTopMargin, self.textWidth,
        title_.contentHeight + kTitleBottomMargin);
}

- (CGRect)titleSeparatorFrame {
  return CGRectMake(0, CGRectGetMaxY(self.titleContainerFrame), self.headerWidth, UIStyle::kDividerSize);
}

- (CGRect)followersFrame {
  CGRect f = followers_.frame;
  f.origin.y = CGRectGetMaxY(self.titleSeparatorFrame);
  if (provisional_ && followers_.empty) {
    f.size.height = 0;
  } else {
    f.size.height = followers_.contentHeight;
  }
  return f;
}

- (CGRect)followersSeparatorFrame {
  return CGRectMake(
      0, CGRectGetMaxY(self.followersFrame),
      self.headerWidth, (provisional_ && followers_.empty) ? 0 : UIStyle::kDividerSize);
}

- (CGRect)headerFrame {
  const float bottom = std::max<float>(CGRectGetMaxY(self.followersSeparatorFrame),
                                       CGRectGetMaxY(self.titleSeparatorFrame));
  const float y = std::max(min_height_ - bottom, min_header_y_);
  return CGRectMake(kConversationMargin, y, self.headerWidth, bottom);
}

- (CGRect)headerCapFrame {
  const float height = header_cap_.frameHeight;
  return CGRectMake(
      kConversationMargin, CGRectGetMinY(self.headerFrame) - height,
      self.headerWidth, height);
}

- (CGSize)sizeThatFits:(CGSize)size {
  return CGSizeMake(self.frameWidth, CGRectGetMaxY(self.headerFrame));
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  [self layoutIfNeeded];
}

- (void)layoutSubviews {
  [super layoutSubviews];
  title_container_.frame = self.titleContainerFrame;
  title_container_.hidden = show_title_cta_ ? YES : NO;
  title_.frame = self.titleFrame;
  title_separator_.frame = self.titleSeparatorFrame;
  followers_.frame = self.followersFrame;
  followers_separator_.frame = self.followersSeparatorFrame;
  header_.frame = self.headerFrame;
  header_cap_.frame = self.headerCapFrame;

  const float desired_height = self.desiredFrameHeight;
  if (self.frameHeight != desired_height) {
    self.frameHeight = desired_height;
  }
}

- (void)textViewDidBeginEditing:(TextView*)text_view {
  // Reset followers auto-complete in case it's currently active. This is
  // essential when viewing the suggested groups or people, as they keyboard
  // is already resigned so we won't receive a did-end-editing callback.
  [followers_ resetAutocomplete];
  [self setEditMode:EDIT_HEADER_TITLE];
  [self.env rowViewDidBeginEditing:self];
}

- (void)textViewDidEndEditing:(TextView*)text_view {
  [self maybeCreateTitleCTA];
  [self.env rowViewDidEndEditing:self];
  [self setEditMode:EDIT_HEADER_NONE];
}

- (void)textViewDidChange:(TextView*)text_view {
  [self.env rowViewDidChange:self];
  if (title_container_.frameHeight != title_.contentHeight) {
    [self layoutSubviews];
  }
}

- (bool)textViewShouldReturn:(TextView*)text_view {
  const bool commit = !provisional_ || !self.emptyTitle;
  [self.env rowViewStopEditing:self commit:commit];
  [self setEditMode:EDIT_HEADER_NONE];
  return false;
}

- (void)followerFieldViewStopEditing:(FollowerFieldView*)field
                              commit:(bool)commit {
  [self.env rowViewStopEditing:self commit:commit];
  [self setEditMode:EDIT_HEADER_NONE];
}

// Lists the followers, including full contact metadata.
// If the viewpoint is prospective, the followers are taken from the
// first share_new activity. Otherwise, they're taken from the DayTable.
// This method is on FollowerFieldView instead of ViewpointTable because
// we're reluctant to depend on the DayTable from other data model classes.
- (void)followerFieldViewListFollowers:(FollowerFieldView*)field
                              followers:(ContactManager::ContactVec*)followers
                              removable:(std::unordered_set<int64_t>*)removable {
  if (provisional_) {
    ActivityHandle ah = state_->activity_table()->GetFirstActivity(vh_->id().local_id(), state_->db());
    if (ah.get() && ah->has_share_new()) {
      for (int i = 0; i < ah->share_new().contacts_size(); ++i) {
        followers->push_back(ah->share_new().contacts(i));
      }
    }
    return;
  }

  vh_->GetRemovableFollowers(removable);

  DayTable::SnapshotHandle snapshot = state_->day_table()->GetSnapshot(NULL);
  DayTable::ViewpointSummaryHandle vsh = snapshot->LoadViewpointSummary(vh_->id().local_id());
  for (int i = 0; i < vsh->contributors_size(); i++) {
    const ViewpointSummaryMetadata::Contributor& contrib = vsh->contributors(i);
    ContactMetadata cm;
    if (contrib.user_id()) {
      if (!state_->contact_manager()->LookupUser(contrib.user_id(), &cm)) {
        LOG("failed to lookup user %d", contrib.user_id());
        continue;
      }
      if (cm.label_terminated()) {
        continue;
      }
    } else {
      DCHECK(!contrib.identity().empty());
      cm.set_primary_identity(contrib.identity());
      cm.add_identities()->set_identity(contrib.identity());
    }
    followers->push_back(cm);
  }
}

- (void)followerFieldViewDidBeginEditing:(FollowerFieldView*)field {
  [self setEditMode:EDIT_HEADER_FOLLOWERS];
  [self.env rowViewDidBeginEditing:self];
}

- (void)followerFieldViewDidEndEditing:(FollowerFieldView*)field {
  [self.env rowViewDidEndEditing:self];
  [self setEditMode:EDIT_HEADER_NONE];
}

- (void)followerFieldViewDidChange:(FollowerFieldView*)field {
  [self.env rowViewDidChange:self];
  if (followers_.frameHeight != followers_.contentHeight) {
    [self layoutSubviews];
  }
}

- (bool)followerFieldViewEnableDone:(FollowerFieldView*)field {
  return true;
}

- (bool)followerFieldViewDone:(FollowerFieldView*)field {
  [self.env rowViewStopEditing:self commit:true];
  [self setEditMode:EDIT_HEADER_NONE];
  return false;
}

- (void)editCoverPhoto {
  edit_cover_photo_callback_.Run();
}

- (void)setCoverPhoto:(PhotoView*)p {
  if (p.photoId != 0) {
    p.selectable = true;
    UIImageView* cover_gradient =
        [[UIImageView alloc] initWithImage:kConvoCoverGradient];
    cover_gradient.tag = kCoverGradientTag;
    const float gradient_height = cover_gradient.image.size.height;
    cover_gradient.frame = CGRectMake(
        0, p.boundsHeight - gradient_height, p.boundsWidth, gradient_height);
    [p addSubview:cover_gradient];

    edit_cover_photo_button_ = UIStyle::NewEditButton(self, @selector(editCoverPhoto));
    edit_cover_photo_button_.autoresizingMask =
        UIViewAutoresizingFlexibleBottomMargin | UIViewAutoresizingFlexibleLeftMargin;
    edit_cover_photo_button_.frameRight = self.boundsWidth;
    edit_cover_photo_button_.frameTop = kConversationTopOffset;
    [p addSubview:edit_cover_photo_button_];
  } else {
    return;
  }

  p.tag = kConversationCoverTag;
  p.editBadgeOffset = CGPointMake(0, kConversationTopOffset);
  photos_.push_back(p);
  [self insertSubview:p atIndex:0];
}

- (void)startEditingHeaderInfo {
  // Possibly change the header height.
  for (int i = 0; i < photos_.size(); ++i) {
    photos_[i].editing = false;
  }
  [UIView animateWithDuration:0.3
                   animations:^{
      [self maybeCreateTitleCTA];
      [self.env rowViewDidChange:self];
    }];
}

- (void)startEditingTitle {
  [self setEditMode:EDIT_HEADER_TITLE];
  // Position the cursor at the end of the title.
  title_.selectedRange = NSMakeRange(title_.attrText.length, 0);
  [title_ becomeFirstResponder];
  [self startEditingHeaderInfo];
}

- (void)stopEditingTitle {
  title_.editable = false;  // toggle editable setting to resign first responder
  title_.editable = true;
  [UIView animateWithDuration:0.3
                   animations:^{
      [self maybeCreateTitleCTA];
      [self.env rowViewDidChange:self];
    }];
}

- (void)startEditingFollowers {
  if (!followers_.enabled) {
    return;
  }
  [self setEditMode:EDIT_HEADER_FOLLOWERS];
  [followers_ startEditing];
  [self startEditingHeaderInfo];
}

- (void)stopEditingFollowers {
  [followers_ stopEditing];
}

- (bool)canEndEditing {
  return followers_.canEndEditing;
}

@end  // ConversationHeaderRowView
