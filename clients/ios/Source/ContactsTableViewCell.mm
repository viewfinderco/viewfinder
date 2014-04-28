// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "ContactManager.h"
#import "ContactMetadata.pb.h"
#import "ContactsTableViewCell.h"
#import "FollowerGroup.pb.h"
#import "IdentityManager.h"
#import "PeopleRank.h"
#import "StringUtils.h"
#import "TextLayer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"
#import "ViewpointTable.h"

namespace {

const float kCellDetailSize = 28;
const float kCellPadding = 8;

inline string FormatContactName(const ContactMetadata& m) {
  if (!m.nickname().empty()) {
    return m.name();
  }
  return string();
}

inline string FormatContactNickname(const ContactMetadata& m) {
  // Use the nickname if available, otherwise fall back to the name. Note that
  // FormatContactName will only return the name if a nickname is present.
  if (!m.nickname().empty()) {
    return m.nickname() + " ";
  }
  if (!m.name().empty()) {
    return m.name();
  }
  if (!m.primary_identity().empty()) {
    return IdentityManager::IdentityToName(m.primary_identity());
  }
  if (!m.email().empty()) {
    // We do not in general want to display the email field if it's not an identity,
    // but if the name is empty and there are no other identities we have no choice.
    return m.email();
  }
  return "";
}

inline string FormatContactIdentity(const ContactMetadata& m) {
  const string ident_name = IdentityManager::IdentityToDisplayName(m.primary_identity());
  // Don't display the email address if it is being used for the name.
  if (m.name().empty() || ident_name == m.name()) {
    return string();
  }
  return ident_name;
}

inline string FormatIdentityDetails(const ContactMetadata& m) {
  if (m.identities_size() > 1) {
    return Format(" (and %d more)", m.identities_size() - 1);
  }
  return "";
}

const float kContactsInviteWidth = 44;
const float kContactsInviteHeight = 32;
const float kContactsInviteRightMargin = 8;
const float kContactsInviteTopMargin = 8;
const float kContactsInviteTextTopMargin = 40;
const float kContactsEmailEditFieldHeight = 23;

LazyStaticUIFont kContactsInviteUIFont = {
  kProximaNovaRegular, 12
};

LazyStaticUIFont kContactsEditEmailUIFont = {
  kProximaNovaRegular, 14
};

LazyStaticHexColor kContactsInviteTextColor = { "#3f3e3e" };
LazyStaticHexColor kContactsInviteTextActiveColor = { "#9f9c9c" };
LazyStaticHexColor kContactsInviteTextDisabledColor = { "#3f3e3e7f" };
// The alternate background is used both as the highlight color for selected rows
// and the summary result count row at the end of the list.
LazyStaticHexColor kAlternateBackgroundColor = { "#f9f5f5" };

LazyStaticImage kContactCellGradient(@"contact-cell-gradient.png");

LazyStaticImage kContactsEmailInvite(@"contacts-email-invite.png");
LazyStaticImage kContactsEmailInviteActive(@"contacts-email-invite-active.png");
LazyStaticImage kContactsSMSInviteActive(@"contacts-sms-invite-active.png");
LazyStaticImage kContactsSMSInvite(@"contacts-sms-invite.png");
LazyStaticImage kContactInviteEmailSentIcon(@"contact-invite-email-sent-icon.png");
LazyStaticImage kContactInviteSMSSentIcon(@"contact-invite-sms-sent-icon.png");

LazyStaticImage kContactNonUser(@"contact-nonuser.png");
LazyStaticImage kContactUserProspectiveEmail(@"contact-user-prospective-email.png");
LazyStaticImage kContactUserProspectiveSMS(@"contact-user-prospective-sms.png");
LazyStaticImage kContactUserViewfinder(@"contact-user-viewfinder.png");
LazyStaticImage kContactUserGroup(@"contact-user-group.png");

}  // namespace

// A scroll view which passes touch events to the next responder
// in the event it isn't being dragged. This allows the coexistence
// of the scroll view gesture recognizers and table cell selection.
//
// TODO(spencer): consider some alternative. It's kind of weak that
//   we are forced to forward these events. Why, if the scroll view
//   can't ultimately recognize the gestures, doesn't it do this
//   forwarding on its own?
@interface ContactsCellScrollView : UIScrollView {
}
@end

@implementation ContactsCellScrollView

- (void)touchesBegan:(NSSet*)touches withEvent:(UIEvent*)event {
  // If not dragging, send event to next responder.
  if (!self.dragging) {
    [self.nextResponder touchesBegan:touches withEvent:event];
  } else {
    [super touchesBegan:touches withEvent:event];
  }
}

- (void)touchesEnded:(NSSet*)touches withEvent:(UIEvent*)event {
  // If not dragging, send event to next responder.
  if (!self.dragging) {
    [self.nextResponder touchesEnded:touches withEvent:event];
  } else {
    [super touchesEnded:touches withEvent:event];
  }
}

@end

@implementation ContactsTableViewCell

- (id)initWithReuseIdentifier:(NSString*)identifier
                   tableWidth:(float)table_width {
  if (self = [super initWithStyle:UITableViewCellStyleSubtitle
                      reuseIdentifier:identifier]) {
    table_width_ = table_width;
    right_margin_ = 0;
    scroll_view_ = [ContactsCellScrollView new];
    scroll_view_.showsHorizontalScrollIndicator = NO;
    label_ = [TextLayer new];
    sublabel_ = [TextLayer new];
    gradient_ = [[UIImageView alloc] initWithImage:kContactCellGradient];
    detail_ = [UIImageView new];
    self.backgroundView = [UIView new];
    self.selectedBackgroundView = [UIView new];
    [self.contentView addSubview:scroll_view_];
    [scroll_view_.layer addSublayer:label_];
    [scroll_view_.layer addSublayer:sublabel_];
    [self.contentView addSubview:gradient_];
    [self.contentView addSubview:detail_];
  }
  return self;
}

- (bool)editingEmailAddress {
  return email_callback_ != NULL;
}

- (void)layoutSubviews {
  const ScopedDisableUIViewAnimations disabled_uiview_animations;
  const ScopedDisableCAActions disable_ca_actions;
  [super layoutSubviews];
  scroll_view_.frameHeight = self.frameHeight;
  if (self.detailImage) {
    scroll_view_.frameLeft = kCellDetailSize + 2 * kCellPadding;
    scroll_view_.frameWidth = table_width_ - 3 * kCellPadding - kCellDetailSize - right_margin_;
  } else {
    scroll_view_.frameLeft = 0;
    scroll_view_.frameWidth = table_width_;
  }
  gradient_.frameRight = scroll_view_.frameRight;
  gradient_.frameHeight = self.frameHeight;
  // extra 25% for emoji
  const float label_height =
      1.25 * UIStyle::kContactsListLabelFont.height();
  const float sublabel_height =
      1.25 * UIStyle::kContactsListSublabelFont.height();
  if (center_alignment_) {
    label_.frameLeft = (table_width_ - label_.frameWidth) / 2 - scroll_view_.frameLeft;
    sublabel_.frameLeft = (table_width_ - sublabel_.frameWidth) / 2 - scroll_view_.frameLeft;
  } else {
    label_.frameLeft = sublabel_.frameLeft = 0;
  }
  if (center_alignment_) {
    label_.frameTop = (self.frameHeight - label_.frameHeight) / 2 - 1;
  } else if (!sublabel_.attrStr) {
    label_.frameTop = (self.frameHeight - label_height) / 2 - 1;
  } else {
    label_.frameTop = (self.frameHeight - (label_height + sublabel_height)) / 2 - 1;
    sublabel_.frameTop = label_.frameTop + label_height;
  }
  detail_.frameTop = (self.boundsHeight - detail_.frameHeight) / 2;
  detail_.frameLeft = scroll_view_.frameLeft - kCellDetailSize - kCellPadding;
  detail_.frameSize = CGSizeMake(kCellDetailSize, kCellDetailSize);

  // Adjust scroll view width and if width of either label exceeds
  // frame width, position the gradient image; otherwise, hide the
  // gradient image.
  const float max_label_width = std::max<float>(label_.frameWidth, sublabel_.frameWidth);
  const bool need_gradient = max_label_width > scroll_view_.frameWidth;
  scroll_view_.contentOffset = CGPointMake(0, 0);
  scroll_view_.contentSize =
      CGSizeMake(std::max<float>(scroll_view_.frameWidth,
                                 max_label_width +
                                 (need_gradient ? kContactCellGradient.get().size.width : 0)),
                 scroll_view_.frameHeight);
  if (need_gradient) {
    gradient_.alpha = 1;
  } else {
    gradient_.alpha = 0;
  }
}

- (void)addEmailInviteButton {
  switch (contact_type_) {
    case CONTACT_TYPE_UNKNOWN_EMAIL:
    case CONTACT_TYPE_UNKNOWN_SMS: {
      UIImage* image = (contact_type_ == CONTACT_TYPE_UNKNOWN_EMAIL) ?
                       kContactsEmailInvite : kContactsSMSInvite;
      UIImage* active = (contact_type_ == CONTACT_TYPE_UNKNOWN_EMAIL) ?
                        kContactsEmailInviteActive : kContactsSMSInviteActive;
      prospective_invite_ = [UIButton buttonWithType:UIButtonTypeCustom];
      prospective_invite_.frameSize = CGSizeMake(kContactsInviteWidth,
                                                 kContactsInviteHeight);
      prospective_invite_.showsTouchWhenHighlighted = NO;
      prospective_invite_.imageEdgeInsets = UIEdgeInsetsMake(
          0, (kContactsInviteWidth - image.size.width) / 2,
          0, (kContactsInviteWidth - image.size.width) / 2);
      [prospective_invite_ setImage:image forState:UIControlStateNormal];
      [prospective_invite_ setImage:active forState:UIControlStateHighlighted];

      prospective_invite_.titleLabel.font = kContactsInviteUIFont.get();
      [prospective_invite_ setTitle:@"Invite" forState:UIControlStateNormal];
      [prospective_invite_ setTitleColor:kContactsInviteTextColor.get()
                                forState:UIControlStateNormal];
      [prospective_invite_ setTitleColor:kContactsInviteTextActiveColor.get()
                                forState:UIControlStateHighlighted];
      [prospective_invite_ setTitleColor:kContactsInviteTextDisabledColor.get()
                                forState:UIControlStateDisabled];
      [prospective_invite_ setTitleEdgeInsets:UIEdgeInsetsMake(
            kContactsInviteTextTopMargin, -image.size.width, 0, 0)];

      [prospective_invite_ addTarget:self
                              action:@selector(finishEmailEdit)
                    forControlEvents:UIControlEventTouchUpInside];

      right_margin_ = kContactsInviteWidth;
      break;
    }
    case CONTACT_TYPE_PROSPECTIVE_EMAIL:
    case CONTACT_TYPE_PROSPECTIVE_SMS: {
      UIImage* image = (contact_type_ == CONTACT_TYPE_PROSPECTIVE_EMAIL) ?
                       kContactInviteEmailSentIcon : kContactInviteSMSSentIcon;
      prospective_invite_ = [UIButton buttonWithType:UIButtonTypeCustom];
      prospective_invite_.frameSize = CGSizeMake(kContactsInviteWidth,
                                                 kContactsInviteHeight);
      prospective_invite_.showsTouchWhenHighlighted = NO;
      prospective_invite_.imageEdgeInsets = UIEdgeInsetsMake(
          0, (kContactsInviteWidth - image.size.width) / 2,
          0, (kContactsInviteWidth - image.size.width) / 2);
      [prospective_invite_ setImage:image forState:UIControlStateNormal];

      prospective_invite_.titleLabel.font = kContactsInviteUIFont.get();
      [prospective_invite_ setTitle:@"Invited" forState:UIControlStateNormal];
      [prospective_invite_ setTitleColor:kContactsInviteTextColor.get()
                          forState:UIControlStateNormal];
      [prospective_invite_ setTitleColor:kContactsInviteTextDisabledColor.get()
                          forState:UIControlStateDisabled];
      [prospective_invite_ setTitleEdgeInsets:UIEdgeInsetsMake(
            kContactsInviteTextTopMargin, -image.size.width, 0, 0)];

      right_margin_ = kContactsInviteWidth;
      break;
    }
    case CONTACT_TYPE_VIEWFINDER:
    case CONTACT_TYPE_GROUP:
      right_margin_ = 0;
      break;
  }

  if (prospective_invite_) {
    [self.contentView addSubview:prospective_invite_];
    prospective_invite_.frameRight = table_width_ - kContactsInviteRightMargin;
    prospective_invite_.frameTop = kContactsInviteTopMargin;
    prospective_invite_.enabled = NO;
  }
}

- (void)finishEmailEdit {
  if (!email_field_) {
    return;
  }
  if (email_field_.text.length == 0) {
    [[[UIAlertView alloc]
       initWithTitle:@"Enter An Email Address First"
             message:Format("Unfortunately, this app can't guess email "
                            "addresses for you. Maybe next version.")
            delegate:NULL
       cancelButtonTitle:@"Oh, right…"
       otherButtonTitles:NULL] show];
    return;
  }
  const string email = ToString(email_field_.text);
  if (!ContactManager::IsResolvableEmail(email)) {
    string error;
    IsValidEmailAddress(email, &error);
    // Note that ShowInvalidEmailAlert() does something intelligent of error is
    // empty (e.g. because IsValidEmailAddress() returned true).
    UIAppState::ShowInvalidEmailAlert(email, error);
    return;
  }
  email_callback_(ToString(email_field_.text));
  email_callback_ = NULL;
  [self finishEditingEmailAddress];
}

- (void)setLabel:(NSAttributedString*)s {
  label_.attrStr = s;
  [label_ displayIfNeeded];
}

- (void)setSublabel:(NSAttributedString*)s {
  sublabel_.attrStr = s;
  [sublabel_ displayIfNeeded];
}

- (UIImage*)detailImage {
  return detail_.image;
}

- (void)setDetailImage:(UIImage*)i {
  detail_.image = i;
}

- (void)setCenteredRow:(NSAttributedString*)s {
  const ScopedDisableCAActions disable_ca_actions;
  center_alignment_ = true;
  scroll_view_.alwaysBounceHorizontal = NO;
  self.label = s;
  self.sublabel = NULL;
  self.detailImage = NULL;
  self.backgroundView.backgroundColor = kAlternateBackgroundColor;
  self.layer.zPosition = 0;
  [prospective_invite_ removeFromSuperview];
  prospective_invite_ = NULL;
}

- (void)setContactRow:(const ContactMetadata&)m
         searchFilter:(RE2*)search_filter
        isPlaceholder:(bool)is_placeholder
           showInvite:(bool)show_invite {
  // If both nickname and name are present, they go into the appropriately-named field.
  // If only name is present, it goes in the nickname field.
  const Dict& nickname_attrs = search_filter ?
                               UIStyle::kContactsListLabelNormalAttributes :
                               UIStyle::kContactsListLabelBoldAttributes;
  const Dict& name_attrs = search_filter ?
                           UIStyle::kContactsListItalicNormalAttributes :
                           UIStyle::kContactsListItalicBoldAttributes;
  const Dict& identity_attrs = UIStyle::kContactsListSublabelNormalAttributes;

  const string nickname = FormatContactNickname(m);
  const string name = FormatContactName(m);
  const string identity = is_placeholder ? "" : FormatContactIdentity(m);
  // Identity details are a separate string because the search_filter is never applied to them.
  const string identity_details = FormatIdentityDetails(m);

  NSMutableAttributedString* attr_nickname = NewAttrString(nickname, nickname_attrs);
  NSMutableAttributedString* attr_name = NewAttrString(name, name_attrs);
  NSMutableAttributedString* attr_identity = NewAttrString(identity, identity_attrs);
  NSMutableAttributedString* attr_identity_details = NewAttrString(identity_details, identity_attrs);

  if (search_filter) {
    ApplySearchFilter(search_filter, nickname, attr_nickname, UIStyle::kContactsListLabelBoldAttributes);
    ApplySearchFilter(search_filter, name, attr_name, UIStyle::kContactsListLabelBoldAttributes);
    ApplySearchFilter(search_filter, identity, attr_identity, UIStyle::kContactsListSublabelBoldAttributes);
  }

  if (!name.empty()) {
    [attr_nickname appendAttributedString:attr_name];
  }
  if (!identity_details.empty()) {
    [attr_identity appendAttributedString:attr_identity_details];
  }

  const ScopedDisableUIViewAnimations disable_animations;
  const ScopedDisableCAActions disable_ca_actions;

  self.backgroundView.backgroundColor = [UIColor whiteColor];
  self.selectedBackgroundView.backgroundColor = kAlternateBackgroundColor;
  gradient_.image = kContactCellGradient;

  if (ContactManager::IsRegistered(m)) {
    contact_type_ = CONTACT_TYPE_VIEWFINDER;
    self.detailImage = kContactUserViewfinder;
  } else if (ContactManager::IsProspective(m)) {
    int reachability = ContactManager::Reachability(m);
    if ((reachability & ContactManager::REACHABLE_BY_SMS) &&
        !(reachability & ContactManager::REACHABLE_BY_EMAIL)) {
      contact_type_ = CONTACT_TYPE_PROSPECTIVE_SMS;
      self.detailImage = kContactUserProspectiveSMS;
    } else {
      contact_type_ = CONTACT_TYPE_PROSPECTIVE_EMAIL;
      self.detailImage = kContactUserProspectiveEmail;
    }
  } else {
    int reachability = ContactManager::Reachability(m);
    if ((reachability & ContactManager::REACHABLE_BY_SMS) &&
        !(reachability & ContactManager::REACHABLE_BY_EMAIL)) {
      contact_type_ = CONTACT_TYPE_UNKNOWN_SMS;
    } else {
      contact_type_ = CONTACT_TYPE_UNKNOWN_EMAIL;
    }
    self.detailImage = kContactNonUser;
  }

  [prospective_invite_ removeFromSuperview];
  prospective_invite_ = NULL;
  if (show_invite) {
    [self addEmailInviteButton];
  }

  center_alignment_ = false;

  scroll_view_.alwaysBounceHorizontal = NO;
  self.label = attr_nickname;
  self.sublabel = attr_identity;
  self.layer.zPosition = 0;

  // iOS does not automatically call layoutSubviews when reusing a table cell.  Assigning a non-empty
  // string to label or sublabel appears to do so, but if label and sublabel are both null the old
  // layout will be used.  The previous layout may have been center-aligned, so we must re-layout to
  // ensure the detail icon is in the right place even in the degenerate case in which we have no
  // text.
  [self layoutSubviews];
}

- (void)setFollowerGroupRow:(const FollowerGroup&)group
                  withState:(UIAppState*)state
             excludingUsers:(const std::unordered_set<int64_t>&)exclude {
  string full_name;
  vector<string> names;
  for (int i = 0; i < group.user_ids_size(); ++i) {
    if (!ContainsKey(exclude, group.user_ids(i)) &&
        group.user_ids(i) != state->user_id()) {
      if (full_name.empty()) {
        full_name = state->contact_manager()->FullName(group.user_ids(i));
      }
      names.push_back(state->contact_manager()->FirstName(group.user_ids(i)));
    }
  }
  // Use full name if there's only one user; otherwise sort alphabetically.
  if (names.size() == 1) {
    names[0] = full_name;
  } else {
    std::sort(names.begin(), names.end());
  }
  const string members_str = Join(names, ", ");
  NSMutableAttributedString* attr_members =
      [[NSMutableAttributedString alloc]
        initWithString:NewNSString(members_str)
            attributes:UIStyle::kFollowerGroupLabelBoldAttributes];

  vector<int64_t> vp_ids = PeopleRank::MostRecentViewpoints(group, 3);
  vector<string> convos;
  for (int i = 0; i < vp_ids.size(); ++i) {
    ViewpointHandle vh = state->viewpoint_table()->LoadViewpoint(vp_ids[i], state->db());
    if (vh.get()) {
      convos.push_back(vh->FormatTitle(true, true));
    }
  }
  string convos_str = Join(convos, ", ");
  NSMutableAttributedString* attr_convos =
      [[NSMutableAttributedString alloc]
        initWithString:NewNSString(convos_str)
            attributes:UIStyle::kFollowerGroupSublabelNormalAttributes];

  if (group.viewpoints_size() > 3) {
    const int extra = group.viewpoints_size() - 3;
    const string extra_str = Format(" and %d other%s", extra, Pluralize(extra));
    AppendAttrString(attr_convos, extra_str,
                     UIStyle::kFollowerGroupSublabelItalicNormalAttributes);
  }

  const ScopedDisableUIViewAnimations disable_animations;
  const ScopedDisableCAActions disable_ca_actions;

  self.backgroundView.backgroundColor = [UIColor whiteColor];
  self.selectedBackgroundView.backgroundColor = kAlternateBackgroundColor;

  contact_type_ = CONTACT_TYPE_GROUP;
  [prospective_invite_ removeFromSuperview];
  prospective_invite_ = NULL;
  center_alignment_ = false;
  right_margin_ = 0;
  gradient_.image = kContactCellGradient;

  scroll_view_.alwaysBounceHorizontal = YES;
  self.label = attr_members;
  self.sublabel = attr_convos;
  self.layer.zPosition = 0;
  if (names.size() == 1) {
    self.detailImage = kContactUserViewfinder;
  } else {
    self.detailImage = kContactUserGroup;
  }

  // iOS does not automatically call layoutSubviews when reusing a table cell.  Assigning a non-empty
  // string to label or sublabel appears to do so, but if label and sublabel are both null the old
  // layout will be used.  The previous layout may have been center-aligned, so we must re-layout to
  // ensure the detail icon is in the right place even in the degenerate case in which we have no
  // text.
  [self layoutSubviews];
}

- (void)setDummyRow {
  const ScopedDisableCAActions disable_ca_actions;
  // Force the dummy row cell to appear below sibling views. This is
  // important for when the search view is a member of the table as we can't
  // otherwise easily force the search view to be above the dummy row and
  // UITableViewCells appear to have an opaque background. Note that we
  // change the dummy row zPosition instead of the search view zPosition
  // because the search view needs to still lie under the section index.
  self.layer.zPosition = -1;
  self.label = NULL;
  self.sublabel = NULL;
  self.detailImage = NULL;
}

- (void)startEditingEmailAddress:(EditEmailCallback)email_callback {
  email_callback_ = email_callback;
  sublabel_.hidden = YES;

  DCHECK(!prospective_invite_.hidden);
  prospective_invite_.enabled = YES;

  if (email_field_view_) {
    [email_field_view_ removeFromSuperview];
  }
  email_field_view_ = [UIView new];
  email_field_view_.backgroundColor = [UIColor whiteColor];
  email_field_view_.layer.borderWidth = 1;
  email_field_view_.layer.borderColor = [UIColor darkGrayColor].CGColor;
  email_field_view_.frame = CGRectMake(sublabel_.frameLeft, sublabel_.frameTop,
                                       scroll_view_.frameWidth, kContactsEmailEditFieldHeight);
  [scroll_view_ addSubview:email_field_view_];

  email_field_ = [UITextField new];
  email_field_.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
  email_field_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
  email_field_.autocapitalizationType = UITextAutocapitalizationTypeNone;
  email_field_.autocorrectionType = UITextAutocorrectionTypeNo;
  email_field_.spellCheckingType = UITextSpellCheckingTypeNo;
  email_field_.inputAccessoryView = [UIView new];
  email_field_.keyboardAppearance = UIKeyboardAppearanceAlert;
  email_field_.keyboardType = UIKeyboardTypeEmailAddress;
  email_field_.clearButtonMode = UITextFieldViewModeAlways;
  email_field_.font = kContactsEditEmailUIFont;
  email_field_.placeholder = @"Enter email address…";
  email_field_.textColor = kContactsInviteTextColor;
  email_field_.delegate = self;
  email_field_.frame = CGRectMake(6, 0, email_field_view_.boundsWidth - 6,
                                  email_field_view_.boundsHeight);
  [email_field_view_ addSubview:email_field_];
  [email_field_ becomeFirstResponder];
}

- (void)finishEditingEmailAddress {
  if (email_callback_) {
    email_callback_("");
    email_callback_ = NULL;
  }
  email_field_.delegate = NULL;
  [email_field_view_ removeFromSuperview];
  email_field_view_ = NULL;
  email_field_ = NULL;
  sublabel_.hidden = NO;
  prospective_invite_.hidden = YES;
}

- (void)textFieldDidEndEditing:(UITextField*)text_field {
  if (!email_field_) {
    return;
  }
  [self finishEditingEmailAddress];
}

- (BOOL)textFieldShouldReturn:(UITextField*)text_field {
  [self finishEmailEdit];
  return NO;
}

+ (int)rowHeight {
  return 52;
}

@end  // ContactsTableViewCell
