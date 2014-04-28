// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <UIKit/UIKit.h>
#import "Analytics.h"
#import "Callback.h"
#import "ContactManager.h"
#import "ContactsTableViewCell.h"
#import "ContactUtils.h"
#import "CppDelegate.h"
#import "DBFormat.h"
#import "FollowerFieldView.h"
#import "IdentityManager.h"
#import "LayoutUtils.h"
#import "LazyStaticPtr.h"
#import "LocaleUtils.h"
#import "PeopleRank.h"
#import "PhoneUtils.h"
#import "RootViewController.h"
#import "StringUtils.h"
#import "TokenizedTextView.h"
#import "UIStyle.h"
#import "UIScrollView+visibleBounds.h"
#import "UIView+geometry.h"

namespace {

const float kDuration = 0.3;
const float kTableHeaderHeight = 24;
const float kMinFollowerFieldHeight = 44;
const float kFollowerLabelHeight = 44;
const float kFollowerLabelSpacing = 4;
const float kFollowerLabelLeftMargin = 40;
const float kFollowerLabelTopMargin = 11;
const float kFollowerLabelBottomMargin = 8;

LazyStaticImage kTokenIconRemoveUserExisting(@"token-icon-remove-user-existing.png");
LazyStaticImage kTokenIconRemoveUserExistingSelected(@"token-icon-remove-user-existing-selected.png");
LazyStaticImage kTokenIconRemoveUserNew(@"token-icon-remove-user-new.png");
LazyStaticImage kTokenIconRemoveUserNewSelected(@"token-icon-remove-user-new-selected.png");

LazyStaticUIFont kFollowerTokenizedTextFont = { kProximaNovaRegular, 15 };
LazyStaticUIFont kFollowerTokenizedTextBoldFont = { kProximaNovaSemibold, 15 };

const string kSuggestionsTutorialKey = DBFormat::metadata_key("suggestions_tutorial");

class FollowerToken : public TextViewToken {
 public:
  FollowerToken(const ContactMetadata& metadata,
                TokenColorScheme scheme,
                bool removable = true)
      : metadata_(metadata),
        scheme_(scheme),
        name_(ContactManager::FormatName(metadata_, false)),
        removable_(scheme_ == NEW || removable) {
  }

  virtual const string& text() const {
    return name_;
  }

  virtual TokenColorScheme colors() const {
    return scheme_;
  }

  virtual TokenProspectiveType prospective() const {
    if (metadata_.has_user_id() &&
        ContactManager::IsRegistered(metadata_)) {
      return NONE;
    }
    int reachability = ContactManager::Reachability(metadata_);
    // First, look at valid identities.
    if (reachability & ContactManager::REACHABLE_BY_EMAIL) {
      return EMAIL;
    } else if (reachability & ContactManager::REACHABLE_BY_SMS) {
      return SMS;
    }
    // Next look at the unverified phone and email fields.
    if (metadata_.has_email()) {
      return EMAIL;
    } else if (metadata_.has_phone()) {
      return SMS;
    }

    // If all else fails default to email.
    return EMAIL;
  }

  virtual bool frozen() const {
    return (scheme_ == SELF || scheme_ == EXISTING) && !removable_;
  }

  virtual bool removable() const {
    return removable_;
  }

  virtual UIImage* remove_image(bool selected) const {
    if (colors() == TextViewToken::SELF) {
      return selected ? kTokenIconRemoveUserExistingSelected : kTokenIconRemoveUserExisting;
    } else if (colors() == TextViewToken::NEW) {
      return selected ? kTokenIconRemoveUserNewSelected : kTokenIconRemoveUserNew;
    } else if (colors() == TextViewToken::EXISTING) {
      return selected ? kTokenIconRemoveUserExistingSelected : kTokenIconRemoveUserExisting;
    } else {
      return NULL;
    }
  }

  const ContactMetadata& metadata() const {
    return metadata_;
  }

 private:
  const ContactMetadata metadata_;
  const TokenColorScheme scheme_;
  const string name_;
  const bool removable_;
};

string FormatFollowers(
    const vector<ContactMetadata>& participants, bool shorten) {
  vector<string> names;
  for (int i = 0; i < participants.size(); ++i) {
    // Long lists of names can be extremely difficult to read when they're
    // broken up across lines. To minimize this, replace whitespace with
    // non-breaking spaces so word wrap will treat names as a single token.
    // Use the non-i18n Split instead of SplitWords because we only want to
    // replace normal spaces and not other breaking punctuation.
    const vector<string> parts =
        Split(ContactManager::FormatName(participants[i], shorten, false), " ");
    names.push_back(Join(parts, "\u00a0"));
  }
  return Join(names, ", ");
}

bool IsViableAutocomplete(const ContactMetadata& m) {
  string identity;
  return ContactManager::IsRegistered(m) ||
      ContactManager::GetEmailIdentity(m, &identity) ||
      ContactManager::GetPhoneIdentity(m, &identity) ||
      m.has_name();
}

LazyStaticUIFont kComposeTextEntryFont = {
  kProximaNovaRegular, 18
};

LazyStaticUIFont kFollowerLabelFont = {
  kProximaNovaSemibold, 17
};

LazyStaticUIFont kFullFollowerLabelFont = {
  kProximaNovaRegular, 17
};

LazyStaticUIFont kFollowerPlaceholderFont = {
  kProximaNovaRegular, 17
};

LazyStaticUIFont kTableHeaderFont = {
  kProximaNovaBold, 15
};

LazyStaticHexColor kTableHeaderColor = { "#3f3e3e" };
LazyStaticHexColor kFollowerLabelColor = { "#3f3e3e" };
LazyStaticHexColor kFollowerLabelUnavailableColor = { "#cfcbcb" };
LazyStaticHexColor kFollowerPlaceholderColor = { "#cfcbcb" };
LazyStaticHexColor kFollowerBackgroundUnavailableColor = { "#ece9e9" };
LazyStaticHexColor kFullFollowerLabelColor = { "#9f9c9c" };
LazyStaticHexColor kTableHeaderBackgroundColor = { "#ece9e9" };

LazyStaticImage kOpenDropdownSelected(@"open-dropdown-selected.png");
LazyStaticImage kOpenDropdownSelectedActive(@"open-dropdown-selected-active.png");
LazyStaticImage kOpenDropdownUnselected(@"open-dropdown-unselected.png");
LazyStaticImage kOpenDropdownUnselectedActive(@"open-dropdown-unselected-active.png");

LazyStaticImage kConvoUsersIcon(@"convo-users-icon.png");
LazyStaticImage kConvoUsersIconUnavailable(@"convo-users-icon-unavailable.png");

UIButton* NewDropdownButton(UIImage* image, UIImage* active, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  [b setImage:image forState:UIControlStateNormal];
  [b setImage:active forState:UIControlStateHighlighted];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  return b;
}

UIButton* NewEditButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  [b setImage:UIStyle::kConvoEditIconGrey forState:UIControlStateNormal];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  return b;
}

}  // namespace


@interface FollowerLabel : UIView {
 @private
  UILabel* trunc_label_;
  UILabel* full_label_;
  UIImageView* icon_;
  UIButton* edit_;
  bool enabled_;
  bool empty_;
  bool show_all_followers_;
  bool show_edit_icon_;
}

@property (nonatomic) bool enabled;
@property (nonatomic, readonly) bool empty;
@property (nonatomic) bool showAllFollowers;
@property (nonatomic) bool showEditIcon;
@property (nonatomic, readonly) UIButton* edit;

@end  // FollowerLabel

@implementation FollowerLabel

@synthesize enabled = enabled_;
@synthesize empty = empty_;
@synthesize showAllFollowers = show_all_followers_;
@synthesize showEditIcon = show_edit_icon_;
@synthesize edit = edit_;

- (id)initWithTarget:(id)target {
  if (self = [super init]) {
    self.autoresizesSubviews = YES;

    icon_ = [[UIImageView alloc] initWithImage:kConvoUsersIcon];
    [self addSubview:icon_];

    trunc_label_ = [UILabel new];
    trunc_label_.lineBreakMode = NSLineBreakByTruncatingTail;
    trunc_label_.numberOfLines = 1;
    trunc_label_.font = kFollowerLabelFont;
    trunc_label_.textColor = kFollowerLabelColor;
    [self addSubview:trunc_label_];

    full_label_ = [UILabel new];
    full_label_.lineBreakMode = NSLineBreakByWordWrapping;
    full_label_.numberOfLines = 0;
    full_label_.font = kFullFollowerLabelFont;
    full_label_.textColor = kFullFollowerLabelColor;
    full_label_.alpha = 0;
    [self addSubview:full_label_];

    edit_ = NewEditButton(target, @selector(editFollowersFromEditButton));
    edit_.autoresizingMask = UIViewAutoresizingFlexibleTopMargin;
    [self addSubview:edit_];
  }
  return self;
}

- (void)layoutSubviews {
  [super layoutSubviews];
  trunc_label_.frameTop = kFollowerLabelTopMargin;
  trunc_label_.frameLeft = kFollowerLabelLeftMargin;
  full_label_.frameTop = kFollowerLabelTopMargin;
  full_label_.frameLeft = kFollowerLabelLeftMargin;
  edit_.frameRight = self.frameWidth;
  edit_.frameBottom = self.frameHeight;
}

- (void)setContacts:(const ContactManager::ContactVec&)r
         withSelfId:(int64_t)self_user_id {
  if (r.empty() || (r.size() == 1 && r[0].user_id() == self_user_id)) {
    trunc_label_.font = kFollowerPlaceholderFont;
    trunc_label_.textColor = kFollowerPlaceholderColor;
    trunc_label_.text = @"Add People";
    full_label_.text = @"Add People";
    empty_ = true;
  } else {
    trunc_label_.font = kFollowerLabelFont;
    trunc_label_.textColor = kFollowerLabelColor;
    trunc_label_.text = NewNSString(FormatFollowers(r, true));
    full_label_.text = NewNSString(FormatFollowers(r, false));
    empty_ = false;
  }
}

- (void)setShowAllFollowers:(bool)show_all_followers {
  show_all_followers_ = show_all_followers;
  trunc_label_.alpha = show_all_followers_ ? 0 : 1;
  full_label_.alpha = show_all_followers_ ? 1 : 0;
}

- (void)setShowEditIcon:(bool)show_edit_icon {
  show_edit_icon_ = show_edit_icon;
  if (show_edit_icon) {
    [self addSubview:edit_];
  } else {
    [edit_ removeFromSuperview];
  }
}

- (void)setEnabled:(bool)enabled {
  enabled_ = enabled;
  self.backgroundColor =
      enabled ? [UIColor whiteColor] : kFollowerBackgroundUnavailableColor;
  icon_.image =
      enabled ? kConvoUsersIcon : kConvoUsersIconUnavailable;
  trunc_label_.textColor =
      enabled ? kFollowerLabelColor : kFollowerLabelUnavailableColor;
  edit_.hidden = enabled ? NO : YES;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
}

- (CGSize)sizeThatFits:(CGSize)size {
  const float avail_width = size.width - kFollowerLabelLeftMargin - edit_.frameWidth;

  const CGSize full_size = [full_label_ sizeThatFits:CGSizeMake(avail_width, CGFLOAT_MAX)];
  full_label_.frameSize = CGSizeMake(avail_width, full_size.height + kFollowerLabelBottomMargin);

  const CGSize trunc_size = [full_label_ sizeThatFits:CGSizeMake(CGFLOAT_MAX, CGFLOAT_MAX)];
  trunc_label_.frameSize = CGSizeMake(avail_width, trunc_size.height + kFollowerLabelBottomMargin);

  CGSize label_size = CGSizeMake(size.width, show_all_followers_ ?
                                 full_label_.frameBottom : trunc_label_.frameBottom);
  label_size.height = std::max<float>(kFollowerLabelHeight, label_size.height + kFollowerLabelBottomMargin);
  return label_size;
}

@end  // FollowerLabel


@implementation FollowerFieldView

@synthesize editable = editable_;
@synthesize editing = editing_;
@synthesize enabled = enabled_;
@synthesize editIconStyle = edit_icon_style_;
@synthesize delegate = delegate_;
@synthesize tokenizedView = tokenized_view_;

- (id)initWithState:(UIAppState*)state
        provisional:(bool)provisional
              width:(float)width {
  if (self = [super init]) {
    state_ = state;
    provisional_ = provisional;
    width_ = width;

    // Avoid a reference cycle by using a weak pointer to self.
    __weak FollowerFieldView* weak_self = self;
    contact_callback_id_ = state_->contact_manager()->contact_resolved()->Add(
        ^(const string& ident, const ContactMetadata* metadata) {
            [weak_self updateContact:ident withMetadata:metadata];
        });

    label_ = [[FollowerLabel alloc] initWithTarget:self];
    label_.tag = kConversationFollowersTag;
    [self addSubview:label_];

    edit_recognizer_ = [[UITapGestureRecognizer alloc]
                         initWithTarget:self
                                 action:@selector(handleSingleTap:)];
    edit_recognizer_.cancelsTouchesInView = NO;
    edit_recognizer_.delegate = self;
    [self addGestureRecognizer:edit_recognizer_];

    self.frameWidth = width_;
    self.frameHeight = self.labelHeight;

    editable_ = false;
  }
  return self;
}

- (void)willMoveToSuperview:(UIView*)new_superview {
  if (!new_superview) {
    // TODO(spencer,ben): I don't love how this view is controlling
    // the scroll of the parent. Too confusing and fragile. Making
    // sure we enable the parent scroll saves us from some edge cases
    // where the dismissal of the FollowerFieldView doesn't reenable
    // the parent scroll view after we've disabled it. However, if
    // the parent scroll view itself intended to be disabled, this
    // would incorrectly enable it.
    [self parentScrollView].scrollEnabled = YES;
  }
}

- (void)dealloc {
  state_->contact_manager()->contact_resolved()->Remove(contact_callback_id_);
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  label_.frameSize = [label_ sizeThatFits:f.size];
}

- (void)setEnabled:(bool)enabled {
  enabled_ = enabled;
  label_.enabled = enabled;
  [self initLabelText];
}

- (bool)empty {
  return label_.empty;
}

- (void)layoutSubviews {
  [super layoutSubviews];
  if (self.frameHeight != 0 && tokenized_view_.field.frameHeight != 0) {
    [self maybeShowTutorial];
  }
}

- (float)contentHeight {
  return editing_ ? (tokenized_view_.frameHeight + autocomplete_table_.frameHeight) : label_.frameHeight;
}

- (bool)hasFocus {
  return [tokenized_view_.field isFirstResponder] || show_dropdown_;
}

- (float)labelHeight {
  return [label_ sizeThatFits:CGSizeMake(width_, CGFLOAT_MAX)].height;
}

- (ContactManager::ContactVec)allContacts {
  ContactManager::ContactVec r;
  if (tokenized_view_) {
    for (int i = 0; i < tokenized_view_.numTokens; ++i) {
      const FollowerToken& token =
          static_cast<const FollowerToken&>([tokenized_view_ getToken:i]);
      r.push_back(token.metadata());
    }
  } else {
    std::unordered_set<int64_t> removable_set;
    [delegate_ followerFieldViewListFollowers:self followers:&r removable:&removable_set];
  }
  return r;
}

- (ContactManager::ContactVec)newContacts {
  ContactManager::ContactVec r;
  for (int i = 0; i < tokenized_view_.numTokens; ++i) {
    const FollowerToken& token =
        static_cast<const FollowerToken&>([tokenized_view_ getToken:i]);
    if (token.colors() == TextViewToken::NEW) {
      r.push_back(token.metadata());
    }
  }
  return r;
}

- (vector<int64_t>)removedIds {
  std::unordered_set<int64_t> original_ids;
  for (int i = 0; i < original_followers_.size(); ++i) {
    original_ids.insert(original_followers_[i].user_id());
  }

  ContactManager::ContactVec all = [self allContacts];
  for (int i = 0; i < all.size(); ++i) {
    if (all[i].has_user_id()) {
      original_ids.erase(all[i].user_id());
    }
  }

  return vector<int64_t>(original_ids.begin(), original_ids.end());;
}

- (void)resetTokens {
  while (tokenized_view_.numTokens) {
    [tokenized_view_ removeToken:0];
  }
}

- (vector<int64_t>)allUserIds {
  vector<int64_t> user_ids;
  ContactManager::ContactVec contacts = [self allContacts];
  for (int i = 0; i < contacts.size(); ++i) {
    if (contacts[i].has_user_id()) {
      user_ids.push_back(contacts[i].user_id());
    }
  }
  return user_ids;
}

- (void)setDelegate:(id<FollowerFieldViewDelegate>)delegate {
  delegate_ = delegate;
  [self initLabelText];
}

- (void)setEditable:(bool)value {
  if (editable_ == value) {
    return;
  }
  editable_ = value;
  label_.edit.hidden = value ? NO : YES;
  if (!editable_) {
    [self stopEditing];
  }
}

- (void)editFollowersFromEditButton {
  [self editFollowers];
  if (self.editIconStyle == EDIT_ICON_DROPDOWN) {
    [self performSelector:@selector(showDropdown)
               withObject:NULL
               afterDelay:0];
  }
}

- (void)editFollowers {
  if (editable_) {
    [delegate_ followerFieldViewDidBeginEditing:self];
    [self startEditing];
  }
}

- (bool)showAllFollowers {
  return label_.showAllFollowers;
}

- (void)setShowAllFollowers:(bool)show_all_followers {
  if (!self.enabled) {
    return;
  }
  [UIView animateWithDuration:kDuration
                   animations:^{
      label_.showAllFollowers = show_all_followers;
      label_.frameHeight = [label_ sizeThatFits:CGSizeMake(width_, CGFLOAT_MAX)].height;
      [delegate_ followerFieldViewDidChange:self];
    }];
}

- (bool)showEditIcon {
  return label_.showEditIcon;
}

- (void)setShowEditIcon:(bool)value {
  label_.showEditIcon = value;
}

- (void)setEditIconStyle:(EditIconStyle)edit_icon_style {
  edit_icon_style_ = edit_icon_style;
  UIImage* image;
  switch (edit_icon_style_) {
    case EDIT_ICON_PENCIL:
      image = UIStyle::kConvoEditIconGrey;
      break;
    case EDIT_ICON_DROPDOWN:
      image = kOpenDropdownUnselected;
      break;
  }
  [label_.edit setImage:image forState:UIControlStateNormal];
}

- (void)handleSingleTap:(UITapGestureRecognizer*)sender {
  if (sender.state != UIGestureRecognizerStateEnded) {
    return;
  }
  [self editFollowers];
}

- (void)initLabelText {
  [label_ setContacts:[self allContacts] withSelfId:state_->user_id()];
}

- (void)startEditing {
  if (editing_) {
    if (!show_dropdown_) {
      [self resetAutocomplete];
      [tokenized_view_.field becomeFirstResponder];
    }
    return;
  }
  editing_ = true;
  edit_recognizer_.enabled = NO;

  if (!tokenized_view_) {
    TokenizedTextViewOptions options;
    options.font = kFollowerTokenizedTextFont;
    options.bold_font = kFollowerTokenizedTextBoldFont;
    options.min_height = kMinFollowerFieldHeight;
    options.margin_x = 6;
    options.margin_y = 8;
    options.padding_x = 6;
    options.padding_y = 4;
    options.inset_x = 6;
    options.top_inset_y = 5;
    options.bottom_inset_y = 4;
    options.text_top_inset_y = 8;
    options.token_corner_radius = 3;
    options.emoji_extra_height_factor = 1.35;
    // Always start the text entry on its own line so we have room for the placeholder.
    options.text_wrap_width = width_;
    tokenized_view_ = [[TokenizedTextView alloc] initWithDelegate:self withOptions:options];
    tokenized_view_.frameWidth = width_;
    tokenized_view_.field.tag = kConversationFollowersTag;
    tokenized_view_.field.placeholder = @"Email, phone or contact name";
    tokenized_view_.field.keyboardType = UIKeyboardTypeEmailAddress;
    tokenized_view_.field.returnKeyType = UIReturnKeyDone;

    UIImageView* icon = [[UIImageView alloc] initWithImage:kConvoUsersIcon];
    tokenized_view_.field.leftView = icon;
    tokenized_view_.field.leftViewMode = UITextFieldViewModeAlways;
    tokenized_view_.field.rightViewMode = UITextFieldViewModeAlways;

    dropdown_unselected_ =
        NewDropdownButton(kOpenDropdownUnselected, kOpenDropdownUnselectedActive,
                          self, @selector(showDropdown));
    dropdown_selected_ =
        NewDropdownButton(kOpenDropdownSelected, kOpenDropdownSelectedActive,
                          self, @selector(hideDropdown));

    [self setDropdownButton:dropdown_unselected_];

    // Add participants last, as the left and right views need to be
    // in place in order to properly compute the available width for
    // participant tokens.
    [self initializeTokens];
    [tokenized_view_ layoutIfNeeded];

    autocomplete_table_ = [UITableView new];
    autocomplete_table_.alwaysBounceVertical = YES;
    autocomplete_table_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    autocomplete_table_.scrollsToTop = NO;
    autocomplete_table_.delegate = self;
    autocomplete_table_.dataSource = self;
    autocomplete_table_.backgroundColor = [UIColor whiteColor];
    autocomplete_table_.rowHeight = [ContactsTableViewCell rowHeight];
    autocomplete_table_.frameWidth = width_;
  }

  tokenized_view_.alpha = 0;
  [self addSubview:tokenized_view_];
  [self addSubview:autocomplete_table_];

  // Note(peter): The following hack prevents the keyboard from being shown
  // with a view controller transition animation and speeds up transitions to
  // ConversationLayoutController.
  [tokenized_view_.field performSelector:@selector(becomeFirstResponder)
                              withObject:NULL
                              afterDelay:0];

  [UIView animateWithDuration:kDuration
                   animations:^{
      label_.alpha = 0;
      tokenized_view_.alpha = 1;
      [tokenized_view_ layoutIfNeeded];
      [delegate_ followerFieldViewDidChange:self];
    }
                   completion:^(BOOL finished) {
      [self updateAutocomplete];
    }];
}

- (void)initializeTokens {
  std::unordered_set<int64_t> removable_set;
  original_followers_.clear();
  [delegate_ followerFieldViewListFollowers:self
                                  followers:&original_followers_
                                  removable:&removable_set];
  for (int i = 0; i < original_followers_.size(); i++) {
    // Skip the current user if the viewpoint is in provisional 'compose' mode.
    if (provisional_ &&
        original_followers_[i].user_id() == state_->user_id()) {
      continue;
    }
    const bool is_user = state_->user_id() == original_followers_[i].user_id();
    const TextViewToken::TokenColorScheme scheme =
        provisional_ ? TextViewToken::NEW :
        (is_user ? TextViewToken::SELF : TextViewToken::EXISTING);
    const bool removable = (provisional_ ||
                            (original_followers_[i].has_user_id() &&
                             ContainsKey(removable_set, original_followers_[i].user_id())));
    [tokenized_view_ addToken:new FollowerToken(original_followers_[i], scheme, removable)];
  }
}

- (void)maybeShowTutorial {
  // Don't draw attention to the suggestion button unless we have someone to suggest.
  if (state_->contact_manager()->viewfinder_count() > 1 &&
      !state_->db()->Get<bool>(kSuggestionsTutorialKey, false)) {
    CGRect rect = [tokenized_view_.field rightViewRectForBounds:tokenized_view_.field.bounds];
    rect = [self.superview convertRect:rect fromView:tokenized_view_.field];

    __weak FollowerFieldView* weak_self = self;
    tutorial_ = [TutorialOverlayView
                    createTutorialWithText:"Suggestions"
                                    toRect:rect
                           withOrientation:provisional_ ? TUTORIAL_UNDER : TUTORIAL_OVER
                                 withBlock:^{
        [weak_self showDropdown];
      }];
    tutorial_.maxDisplayTime = 1.5;
    [self.superview addSubview:tutorial_];
    [tutorial_ show];

    state_->db()->Put<bool>(kSuggestionsTutorialKey, true);
  }
}

- (void)setDropdownButton:(UIButton*)button {
  // Maintain the frame from the previous button.
  if (tokenized_view_.field.rightView) {
    button.frame = tokenized_view_.field.rightView.frame;
  } else {
    button.frameRight = width_;
  }
  tokenized_view_.field.rightView = button;
}

- (void)showDropdown {
  if (tutorial_) {
    [tutorial_ removeFromSuperview];
    tutorial_ = NULL;
  }
  if (editable_) {
    [self setDropdownButton:dropdown_selected_];
    show_dropdown_ = true;
    tokenized_view_.field.showFullTable = true;
    [self refreshAutocomplete];
    [[self.superview findFirstResponder] resignFirstResponder];
  }
}

- (void)hideDropdown {
  if (editable_) {
    [self resetAutocomplete];
    [tokenized_view_.field becomeFirstResponder];
  }
}

- (bool)canEndEditing {
  if (!tokenized_view_) {
    return true;
  }
  return tokenized_view_.canEndEditing;
}

- (void)resetAutocomplete {
  if (editable_) {
    [tokenized_view_ clearText];
    [self setDropdownButton:dropdown_unselected_];
    show_all_contacts_ = false;
    show_dropdown_ = false;
    tokenized_view_.field.showFullTable = false;
    [self refreshAutocomplete];
  }
}

- (void)stopEditing {
  if (!editing_) {
    return;
  }
  editing_ = false;
  edit_recognizer_.enabled = YES;
  [self parentScrollView].scrollEnabled = YES;

  [self resetTokens];
  [self initializeTokens];

  contact_autocomplete_.clear();
  group_autocomplete_.clear();
  dummy_autocomplete_ = NULL;
  [self initLabelText];

  [UIView animateWithDuration:kDuration
                   animations:^{
      if (editable_) {
        [delegate_ followerFieldViewDidEndEditing:self];
        [delegate_ followerFieldViewDidChange:self];
      }
      label_.alpha = 1;
      tokenized_view_.alpha = 0;
      [tokenized_view_ removeFromSuperview];
      [autocomplete_table_ removeFromSuperview];
      if (!editable_) {
        tokenized_view_ = NULL;
        autocomplete_table_ = NULL;
      }
    }];
}

- (void)clear {
  [self stopEditing];
  [tokenized_view_ removeFromSuperview];
  [autocomplete_table_ removeFromSuperview];
  tokenized_view_ = NULL;
  autocomplete_table_ = NULL;
  [self initLabelText];
}

- (BOOL)tokenizedTextViewShouldBeginEditing:(TokenizedTextView*)field {
  return editable_ ? YES : NO;
}

- (void)tokenizedTextViewDidBeginEditing:(TokenizedTextView*)view {
  show_dropdown_ = false;
  [self editFollowers];
}

- (BOOL)tokenizedTextViewShouldEndEditing:(TokenizedTextView*)view {
  if (Trim(ToString(view.field.text)).empty()) {
    return true;
  }
  if (self.autocompleteRowCount == 1) {
    if ([self canSelectRow:0]) {
      [self selectRow:0];
      return true;
    }
    return false;
  } else if (self.autocompleteRowCount > 1) {
    [[[UIAlertView alloc]
       initWithTitle:@"Choose a Contact"
             message:@"Make sure you select an existing contact or enter an email or mobile number."
            delegate:NULL
       cancelButtonTitle:@"OK"
       otherButtonTitles:NULL] show];
    return false;
  }

  [[[UIAlertView alloc]
       initWithTitle:@"Invalid Contact"
             message:@"Try typing again with an existing contact, email, or mobile number."
            delegate:NULL
       cancelButtonTitle:@"OK"
       otherButtonTitles:NULL] show];
  return false;
}

- (void)tokenizedTextViewDidEndEditing:(TokenizedTextView*)view {
  // Do nothing here. The tokenized text view is no longer the first responder,
  // but we want to stay in editing mode so that it can become the first
  // responder again without startEditing being called.
  [self parentScrollView].scrollEnabled = YES;
}

- (void)tokenizedTextViewChangedSize:(TokenizedTextView*)view {
  [delegate_ followerFieldViewDidChange:self];
}

- (void)tokenizedTextViewChangedText:(TokenizedTextView*)view {
  [self updateAutocomplete];
}

- (void)tokenizedTextViewChangedTokens:(TokenizedTextView*)view {
  // If not editing, skip delegate callbacks. This happens when
  // we set editable to false and reset the tokens.
  if (!editing_) {
    return;
  }
  [tokenized_view_ clearText];
  [self refreshAutocomplete];
  [delegate_ followerFieldViewDidChange:self];
}

- (void)tokenizedTextViewQueryRemoveToken:(TokenizedTextView*)view
                                    token:(const TextViewToken&)token
                             withCallback:(RemoveTokenCallback)done {
  if (token.colors() == TextViewToken::NEW) {
    done();
  } else {
    const bool is_user = state_->user_id() ==
                         ((const FollowerToken*)&token)->metadata().user_id();
    CppDelegate* cpp_delegate = new CppDelegate;
    cpp_delegate->Add(
        @protocol(UIAlertViewDelegate), @selector(alertView:clickedButtonAtIndex:),
        ^(UIAlertView* alert, NSInteger index) {
          if (index == 1) {
            done();
            // If the user removes himself, exit editing mode
            // immediately after removing the token.
            if (is_user) {
              [delegate_ followerFieldViewStopEditing:self commit:true];
            }
          }
          alert.delegate = NULL;
          delete cpp_delegate;
        });

    [[[UIAlertView alloc]
       initWithTitle:(is_user ? @"Leave Conversation?" : Format("Remove %s?", token.text()))
             message:(is_user ? @"Permanently remove yourself from the conversation? This will "
                      "not notify other participants." :
                      Format("Remove %s permanently from the conversation? This will not notify "
                             "%s or any other participants", token.text(), token.text()))
            delegate:cpp_delegate->delegate()
       cancelButtonTitle:@"Cancel"
       otherButtonTitles:@"OK", NULL] show];
  }
}

- (void)refreshAutocomplete {
  dispatch_after_main(0, ^{
      [self updateAutocomplete];
    });
}

- (void)updateAutocomplete {
  const string text = Trim(ToString(tokenized_view_.field.text));
  if (!text.empty()) {
    show_dropdown_ = false;
    [self setDropdownButton:dropdown_selected_];
  } else if (!show_dropdown_) {
    [self setDropdownButton:dropdown_unselected_];
  }

  if (show_dropdown_) {
    [self searchFollowerGroups];
  } else {
    autocomplete_table_.tableHeaderView = NULL;
    autocomplete_table_.tableFooterView = NULL;
    [self searchContacts:text allowEmpty:false];
  }

  [autocomplete_table_ reloadData];
  [autocomplete_table_ setContentOffset:CGPointMake(0, 0) animated:YES];

  [tokenized_view_ layoutSubviews];

  CGRect table_frame = autocomplete_table_.frame;
  table_frame.origin.y = tokenized_view_.frameBottom;
  float editing_field_height = tokenized_view_.editingFieldHeight;
  if (tokenized_view_.field.isEditing) {
    float height = autocomplete_table_.rowHeight * self.autocompleteRowCount +
                   autocomplete_table_.tableHeaderView.frameHeight + autocomplete_table_.tableFooterView.frameHeight;
    // Limit the editing field height to the scroll visible bounds to ensure
    // that cursor is displayed within the visible bounds. This also avoids
    // computing a negative value for the height of the table.
    const float visible_height = [self tokenizedTextViewVisibleBounds:tokenized_view_].size.height;
    editing_field_height = std::min(editing_field_height, visible_height);
    height = std::min(height, visible_height - editing_field_height);
    table_frame.size.height = height;
  } else {
    table_frame.size.height = 0;
  }

  [UIView animateWithDuration:kDuration
                        delay:0
                      options:UIViewAnimationOptionBeginFromCurrentState
                   animations:^{
      autocomplete_table_.frame = table_frame;

      [delegate_ followerFieldViewDidChange:self];

      UIScrollView* parent_scroll = [self parentScrollView];
      if (parent_scroll) {
        CGRect frame_to_view = table_frame;
        frame_to_view.origin.y -= editing_field_height;
        frame_to_view.size.height += editing_field_height;
        if (tokenized_view_.field.isEditing) {
          CGRect f = [parent_scroll convertRect:frame_to_view fromView:self];
          // Only animate the scroll if we're not showing dropdown suggestions.
          // Otherwise, each new contact added causes the tokenized text view
          // to expand vertically and the scroll to animate it back into place.
          // The result is a choppy "bump" with each name selected.
          [parent_scroll scrollRectToVisible:f animated:!show_dropdown_];
        }
        if (autocomplete_table_.frameHeight &&
            autocomplete_table_.contentSize.height > autocomplete_table_.frameHeight) {
          // Only one scrolling view at a time.
          parent_scroll.scrollEnabled = NO;
        } else {
          parent_scroll.scrollEnabled = YES;
        }
      }
    }
                   completion:NULL];
}

- (UIView*)createTableHeaderView:(const string&)text {
  UILabel* label = [UILabel new];
  label.autoresizesSubviews = YES;
  label.autoresizingMask = UIViewAutoresizingFlexibleWidth;
  label.textAlignment = NSTextAlignmentCenter;
  label.text = NewNSString(text);
  label.backgroundColor = kTableHeaderBackgroundColor;
  label.font = kTableHeaderFont;
  label.textColor = kTableHeaderColor;
  label.frameHeight = kTableHeaderHeight;

  UIView* separator = [UIView new];
  separator.autoresizingMask = UIViewAutoresizingFlexibleWidth;
  separator.backgroundColor = UIStyle::kContactsListSeparatorColor;
  separator.frameHeight = 0.5;
  [label addSubview:separator];

  return label;
}

- (void)showAllContacts {
  show_all_contacts_ = true;
  autocomplete_table_.tableHeaderView = NULL;
  autocomplete_table_.tableFooterView = NULL;
  [self refreshAutocomplete];
}

- (void)searchFollowerGroups {
  vector<int64_t> user_ids = [self allUserIds];
  bool found_current_user = false;
  for (int i = 0; i < user_ids.size(); ++i) {
    if (state_->user_id() == user_ids[i]) {
      found_current_user = true;
      break;
    }
  }
  if (!found_current_user) {
    user_ids.push_back(state_->user_id());
  }

  group_autocomplete_.clear();
  contact_autocomplete_.clear();
  dummy_autocomplete_ = NULL;

  if (!show_all_contacts_) {
    // If no users have yet been chosen (excluding current user), show
    // most likely groups of users.
    if (user_ids.size() == 1) {
      state_->people_rank()->FindBestGroups(user_ids, &group_autocomplete_);
      if (!group_autocomplete_.empty()) {
        autocomplete_table_.tableHeaderView = [self createTableHeaderView:"Suggestions"];
      }
    } else {
      // Otherwise, suggest most likely contacts based on currently added ones.
      state_->people_rank()->FindBestContacts(user_ids, &contact_autocomplete_);
      if (!contact_autocomplete_.empty()) {
        autocomplete_table_.tableHeaderView = [self createTableHeaderView:"Suggested People"];
      }
    }
    if (!group_autocomplete_.empty() || !contact_autocomplete_.empty()) {
      UIButton* b = UIStyle::NewBigButtonGrey(@"Show All Contacts", self, @selector(showAllContacts));
      autocomplete_table_.tableFooterView = b;
    }
 }

  // Show all contacts in rank-sorted order if there are no appropriate suggestions.
  if (group_autocomplete_.empty() && contact_autocomplete_.empty()) {
    show_dropdown_ = false;
    [self searchContacts:"" allowEmpty:true];

    UIButton* b = UIStyle::NewBigButtonGrey(@"Add Contacts", self, @selector(addContacts));
    autocomplete_table_.tableFooterView = b;
  } else {
    autocomplete_table_.tableFooterView = NULL;
  }
}

- (void)searchContacts:(const string&)text
            allowEmpty:(bool)allow_empty {
  ContactManager::ContactVec matches;
  int search_options = ContactManager::SORT_BY_RANK | ContactManager::PREFIX_MATCH;
  if (allow_empty) {
    search_options |= ContactManager::ALLOW_EMPTY_SEARCH;
  }
  state_->contact_manager()->Search(
      text, &matches, &autocomplete_filter_, search_options);

  // "Existing" identities and users are those that are already followers of this conversation.
  std::unordered_set<string> existing_identities;
  std::unordered_set<int64_t> existing_user_ids;
  for (int i = 0; i < tokenized_view_.numTokens; ++i) {
    const FollowerToken& token = static_cast<const FollowerToken&>([tokenized_view_ getToken:i]);
    if (!token.metadata().primary_identity().empty()) {
      existing_identities.insert(token.metadata().primary_identity());
    }
    if (token.metadata().has_user_id()) {
      existing_user_ids.insert(token.metadata().user_id());
    }
  }

  std::unordered_set<string> autocomplete_identities;
  contact_autocomplete_.clear();
  dummy_autocomplete_ = NULL;
  for (int i = 0; i < matches.size(); ++i) {
    ContactMetadata* m = &matches[i];
    if (!IsViableAutocomplete(*m) ||
        ContainsKey(existing_identities, m->primary_identity()) ||
        ContainsKey(existing_user_ids, m->user_id())) {
      continue;
    }
    if (!m->primary_identity().empty()) {
      autocomplete_identities.insert(m->primary_identity());
    }
    contact_autocomplete_.push_back(ContactMetadata());
    contact_autocomplete_.back().Swap(m);
  }

  if (IsValidPhoneNumber(ToString(text), GetPhoneNumberCountryCode())) {
    // If they typed a phone number, try to resolve it.
    // Note that a string of digits is both a valid phone number and a prefix of an email address,
    // but it's probably meant as a phone number if it has the right number of digits.
    // Phone numbers do not display the dummy autocomplete row since we do not support prospective users via phone,
    // so phone numbers that do not resolve to a current user will not work.
    const string identity(IdentityManager::IdentityForPhone(NormalizedPhoneNumber(
                                                                ToString(text), GetPhoneNumberCountryCode())));
    if (!ContainsKey(autocomplete_identities, identity)) {
      // Due to differences in normalization, phone numbers are not always found by search.
      // Use LookupUserByIdentity to find the user in the local DB too.
      // If it's a VF user that's not already in the conversation, add it to the autocomplete.
      ContactMetadata m;
      if ((state_->contact_manager()->LookupUserByIdentity(identity, &m) ||
           state_->contact_manager()->GetCachedResolvedContact(identity, &m)) &&
          m.has_user_id()) {
        if (!ContainsKey(existing_identities, identity) &&
            !ContainsKey(existing_user_ids, m.user_id())) {
          if (!m.has_contact_source()) {
            m.set_contact_source(ContactManager::kContactSourceManual);
          }
          contact_autocomplete_.push_back(m);
          dummy_autocomplete_ = &contact_autocomplete_.back();
        }
      } else {
        // We couldn't find this identity in the resolve cache (or it was there but didn't have a
        // user id), so resolve it now.
        LOG("share: starting resolve for %s", identity);
        state_->contact_manager()->ResolveContact(identity);

        ContactMetadata m;
        m.set_name(FormatPhoneNumberPrefix(ToString(text), GetPhoneNumberCountryCode()));
        m.set_first_name(m.name());
        m.set_last_name("");
        m.set_phone(IdentityManager::RawPhoneFromIdentity(identity));
        m.set_primary_identity(identity);
        m.add_identities()->set_identity(identity);
        m.set_contact_source(ContactManager::kContactSourceManual);
        contact_autocomplete_.push_back(m);
        dummy_autocomplete_ = &contact_autocomplete_.back();
      }
    }
  } else if (ContactManager::IsResolvableEmail(text)) {
    // Add a dummy autocomplete entry to prompt user to invite the entered email address.
    const string email(text);
    const string identity(IdentityManager::IdentityForEmail(email));

    // Don't add the dummy entry if it's redundant with one already in the list.
    if (!ContainsKey(autocomplete_identities, identity)) {
      ContactMetadata m;
      if (!state_->contact_manager()->GetCachedResolvedContact(identity, &m) ||
          !m.has_user_id()) {
        m.set_primary_identity(identity);
        m.add_identities()->set_identity(identity);
        m.set_name(email);
        m.set_first_name(email);
        m.set_last_name("");
        m.set_email(email);
        m.set_contact_source(ContactManager::kContactSourceManual);
      }

      // If there are no autocomplete entries, reset the filter to match
      // the exact string being entered.
      if (contact_autocomplete_.empty()) {
        autocomplete_filter_.reset(new RE2(Format("^(%s)", RE2::QuoteMeta(text))));
      }

      contact_autocomplete_.push_back(m);
      dummy_autocomplete_ = &contact_autocomplete_.back();

      // If they have entered a plausible email address, try to resolve it.
      if (!m.has_user_id() && ContactManager::IsResolvableEmail(text)) {
        LOG("share: starting resolve for %s", identity);
        state_->contact_manager()->ResolveContact(identity);
      }
    }
  }

  // Show table header if there are any auto complete contacts.
  if (!contact_autocomplete_.empty()) {
    const string title = text.empty() ? "Suggested Contacts" :
                         (contact_autocomplete_.size() == 1 && dummy_autocomplete_ ?
                          "Invite" : "Matching Contacts");
    autocomplete_table_.tableHeaderView = [self createTableHeaderView:title];
  }
  autocomplete_table_.tableFooterView = NULL;
}

- (void)addContacts {
  [state_->root_view_controller() showAddContacts:ControllerTransition(TRANSITION_SLIDE_OVER_UP)];
}

- (int)autocompleteRowCount {
  return show_dropdown_ && !group_autocomplete_.empty() ?
      group_autocomplete_.size() : contact_autocomplete_.size();
}

- (UITableViewCell*)tokenizedTextView:(TokenizedTextView*)view
                           cellForRow:(int)row
                              inTable:(UITableView*)table {
  static NSString* kIdentifier = @"FollowerFieldViewCellIdentifier";

  ContactsTableViewCell* cell =
      [table dequeueReusableCellWithIdentifier:kIdentifier];
  if (!cell) {
    cell = [[ContactsTableViewCell alloc]
             initWithReuseIdentifier:kIdentifier
                          tableWidth:table.frameWidth];
  }
  if (show_dropdown_ && !group_autocomplete_.empty()) {
    const vector<int64_t> user_ids([self allUserIds]);
    std::unordered_set<int64_t> user_ids_set(user_ids.begin(), user_ids.end());
    [cell setFollowerGroupRow:*group_autocomplete_[row]
                    withState:state_
               excludingUsers:user_ids_set];
  } else {
    const ContactMetadata& m = contact_autocomplete_[row];
    const bool is_dummy = (&m == dummy_autocomplete_ && !m.has_user_id());
    [cell setContactRow:m
           searchFilter:autocomplete_filter_.get()
          isPlaceholder:is_dummy
             showInvite:true];
  }
  return cell;
}

- (bool)canSelectRow:(int)row {
  if (show_dropdown_) {
    return true;
  }

  const ContactMetadata& m = contact_autocomplete_[row];

  // If it's a full user, go ahead and allow it.
  if (m.user_id() > 0) {
    return true;
  }

  // If it's the dummy as-you-type entry, see if it's valid.
  if (&m == dummy_autocomplete_) {
    DCHECK(!m.primary_identity().empty());
    string display_identity;
    if (IdentityManager::IsEmailIdentity(m.primary_identity())) {
      const string email = IdentityManager::EmailFromIdentity(m.primary_identity());
      DCHECK(ContactManager::IsResolvableEmail(email)) << "; " << email;
      display_identity = email;
    } else if (IdentityManager::IsPhoneIdentity(m.primary_identity())) {
      // We only populate the phone identity if it is complete.
      display_identity = IdentityManager::PhoneFromIdentity(m.primary_identity());
    } else {
      DCHECK(false) << "unknown identity for dummy autocomplete: " << m.primary_identity();
      return false;
    }

    // The identity entered is well-formed but hasn't been matched to a user.
    // Create a contact for it so we will get notified when the identity is bound to a user id.
    if (dummy_autocomplete_) {
      LOG("adding %s to contacts", *dummy_autocomplete_);
      DBHandle updates = state_->NewDBTransaction();
      state_->contact_manager()->SaveContact(*dummy_autocomplete_, true, WallTime_Now(), updates);
      updates->Commit();
      [self selectRow:row];
    }
    return false;
  }

  // We've autocompleted to a contact without a user id. If we have enough information to
  // send a prospective user invite, do so; otherwise prompt for an email address.
  if (!IsViableAutocomplete(m)) {
    return false;
  } else if (ContactManager::GetEmailIdentity(m, NULL) ||
             ContactManager::GetPhoneIdentity(m, NULL)) {
    return true;
  } else {
    ContactsTableViewCell* cell = (ContactsTableViewCell*)[self cellForRow:row];
    if (cell.editingEmailAddress) {
      [cell finishEditingEmailAddress];
      return false;
    }
    [self scrollToRow:row];
    // The contact selected has no email address. Prompt user to
    // either enter an email address manually or cancel selection.
    __weak FollowerFieldView* weak_self = self;
    CppDelegate* cpp_delegate = new CppDelegate;
    cpp_delegate->Add(
        @protocol(UIAlertViewDelegate), @selector(alertView:clickedButtonAtIndex:),
        ^(UIAlertView* alert, NSInteger index) {
          if (index == 1) {
            [tokenized_view_ pauseEditing];
            ContactsTableViewCell* cell = (ContactsTableViewCell*)[self cellForRow:row];
            [cell startEditingEmailAddress:^(string email) {
                if (email.empty()) {
                  [tokenized_view_ resumeEditing];
                  return;
                }
                ContactMetadata* sc = &contact_autocomplete_[row];
                ContactMetadata c;
                if (sc->has_name()) {
                  c.set_name(sc->name());
                }
                if (sc->has_first_name()) {
                  c.set_first_name(sc->first_name());
                }
                if (sc->has_last_name()) {
                  c.set_last_name(sc->last_name());
                }
                c.set_primary_identity(IdentityManager::IdentityForEmail(email));
                c.add_identities()->set_identity(c.primary_identity());
                c.set_contact_source(ContactManager::kContactSourceManual);
                LOG("creating new contact from %s => %s", *sc, c);
                sc->CopyFrom(c);
                DBHandle updates = state_->NewDBTransaction();
                state_->contact_manager()->SaveContact(c, true, WallTime_Now(), updates);
                updates->Commit();
                [weak_self selectRow:row];
                [weak_self.tokenizedView resumeEditing];
              }];
          }
          alert.delegate = NULL;
          delete cpp_delegate;
        });
    [[[UIAlertView alloc]
       initWithTitle:@"Email Address Required"
         message:Format("We need an email address to invite %s to the conversation. "
                        "Your %s contact does't include one.",
                        m.name(), IdentityManager::IdentityType(m.primary_identity()))
            delegate:cpp_delegate->delegate()
       cancelButtonTitle:@"Cancel"
       otherButtonTitles:@"Enter Email", NULL] show];
    return false;
  }
}

- (bool)tokenizedTextViewShouldReturn:(TokenizedTextView*)view {
  if (self.autocompleteRowCount > 0) {
    if ([self canSelectRow:0]) {
      [self selectRow:0];
    }
    return false;
  } else {
    const string text = Trim(ToString(tokenized_view_.field.text));
    if (!text.empty()) {
      if (IsPhoneNumberPrefix(ToString(text))) {
        [[[UIAlertView alloc]
           initWithTitle:@"That's Not A Valid Mobile Number"
                 message:@"Try using your entire number with country code, "
           @"preceded by a plus. (example: +1 555 555 5555)."
                delegate:NULL
           cancelButtonTitle:@"Let me fix that…"
           otherButtonTitles:NULL] show];
      } else {
        // Note that ShowInvalidEmailAlert() does something intelligent if error is
        // empty (e.g. because IsValidEmailAddress() returned true).
        string error;
        IsValidEmailAddress(text, &error);
        UIAppState::ShowInvalidEmailAlert(text, error);
      }
      return false;
    }
  }
  if (![delegate_ followerFieldViewEnableDone:self]) {
    return true;
  }
  return [delegate_ followerFieldViewDone:self];
}

- (void)tokenizedTextView:(TokenizedTextView*)view
       createTokensForRow:(int)row
             withCallback:(CreateTokensCallback)callback {

  if (show_dropdown_ && !group_autocomplete_.empty()) {
    vector<const TextViewToken*> tokens;
    const vector<int64_t> user_ids([self allUserIds]);
    std::unordered_set<int64_t> user_ids_set(user_ids.begin(), user_ids.end());
    user_ids_set.insert(state_->user_id());
    const FollowerGroup* group = group_autocomplete_[row];
    state_->analytics()->ConversationSelectFollowerGroup(group->user_ids_size());
    for (int i = 0; i < group->user_ids_size(); ++i) {
      ContactMetadata cm;
      if (!ContainsKey(user_ids_set, group->user_ids(i)) &&
          state_->contact_manager()->LookupUser(group->user_ids(i), &cm)) {
        tokens.push_back([self createTokenForContact:cm]);
      }
    }
    callback(tokens);
  } else {
    const ContactMetadata& contact = contact_autocomplete_[row];

    state_->analytics()->ConversationSelectFollower(contact);
    if (contact.has_user_id() || contact.identities_size() == 1) {
      callback(L([self createTokenForContact:contact]));
      return;
    }
    DCHECK_GT(contact.identities_size(), 1);
    // The chosen contact has multiple identities, so present a choice.
    [self chooseIdentityForContact:contact withCallback:callback];
  }
}

- (void)chooseIdentityForContact:(const ContactMetadata&)base_contact
                    withCallback:(CreateTokensCallback)callback {
  ChooseIdentityForContact(
      base_contact, self,
      ^(const ContactMetadata* new_contact) {
        vector<const TextViewToken*> tokens;
        if (new_contact) {
          state_->analytics()->ConversationSelectFollowerIdentity(base_contact, new_contact->primary_identity());
          tokens.push_back([self createTokenForContact:*new_contact]);
        }
        callback(tokens);
      });
}


- (const TextViewToken*)createTokenForContact:(const ContactMetadata&)m {
  string identity;
  if (!IsViableAutocomplete(m)) {
    // Not a selectable row; give up.
    return NULL;
  }

  if (m.has_user_id()) {
    // It's a user (who may or may not be registered, and may be the user we just resolved).

    if (&m == dummy_autocomplete_) {
      // If the dummy autocomplete row has a user id, we resolved the email address as it was typed,
      // and it's time to save the result to the database.
      LOG("follower: saving resolved contact %s", m);
      DBHandle updates = state_->NewDBTransaction();
      state_->contact_manager()->MergeResolvedContact(m, updates);
      updates->Commit();
    }

    return new FollowerToken(m, TextViewToken::NEW);
  }

  // Otherwise, we must have a viable email address at least, or we wouldn't
  // have passed IsViableAutocomplete above.
  return new FollowerToken(m, TextViewToken::NEW);
}

- (CGRect)tokenizedTextViewVisibleBounds:(TokenizedTextView*)view {
  // TODO(ben): refactor things so we can find the right bounds without going the hack of parentScrollView.
  return self.parentScrollView.visibleBounds;
}

- (NSInteger)numberOfSectionsInTableView:(UITableView*)view {
  return 1;
}

- (NSInteger)tableView:(UITableView*)table_view
 numberOfRowsInSection:(NSInteger)section {
  return self.autocompleteRowCount;
}

- (NSString*)tableView:(UITableView*)table_view
titleForHeaderInSection:(NSInteger)section {
  return NULL;
}

- (NSIndexPath*)tableView:(UITableView*)table_view
  willSelectRowAtIndexPath:(NSIndexPath*)index_path {
  if ([self canSelectRow:index_path.row]) {
    return index_path;
  }
  return NULL;
}

- (void)scrollToRow:(int)row {
  NSIndexPath* path = [NSIndexPath indexPathForRow:row inSection:0];
  [autocomplete_table_ scrollToRowAtIndexPath:path
                             atScrollPosition:UITableViewScrollPositionMiddle
                                     animated:YES];
}

- (UITableViewCell*)cellForRow:(int)row {
  NSIndexPath* path = [NSIndexPath indexPathForRow:row inSection:0];
  return [autocomplete_table_ cellForRowAtIndexPath:path];
}

- (void)selectRow:(int)row {
  NSIndexPath* path = [NSIndexPath indexPathForRow:row inSection:0];
  [self tableView:autocomplete_table_ didSelectRowAtIndexPath:path];
}

- (void)tableView:(UITableView*)table_view
didSelectRowAtIndexPath:(NSIndexPath*)index_path {
  ScopedDisableUIViewAnimations disabled_animations;
  [self tokenizedTextView:tokenized_view_
       createTokensForRow:index_path.row
             withCallback:^(const vector<const TextViewToken*>& tokens) {
      for (int i = 0; i < tokens.size(); ++i) {
        [tokenized_view_ addToken:tokens[i]];
      }
      [tokenized_view_ clearText];
      [self updateAutocomplete];
    }];
}

- (UITableViewCell*)tableView:(UITableView*)table_view
        cellForRowAtIndexPath:(NSIndexPath*)index_path {
  return [self tokenizedTextView:tokenized_view_ cellForRow:index_path.row inTable:autocomplete_table_];
}

- (void)updateContact:(const string&)identity withMetadata:(const ContactMetadata*)metadata {
  if (metadata && metadata->has_user_id()) {
    LOG("share: resolved contact %s, refreshing autocomplete", identity);
    [self refreshAutocomplete];
  } else {
    LOG("share: resolved contact %s, no results", identity);
  }
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
  // Allow edits via simply clicking label if the label is empty.
  return editable_;
}

@end  // FollowerFieldView
