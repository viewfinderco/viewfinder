// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

// TODO(peter): Merge accounts if /link/viewfinder says the identity is already
// linked to a viewfinder account.

#import <MessageUI/MessageUI.h>
#import "Analytics.h"
#import "AsyncState.h"
#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "ComposeLayoutController.h"
#import "ContactInfoController.h"
#import "ContactManager.h"
#import "ContactsController.h"
#import "ContactUtils.h"
#import "ControlDelegate.h"
#import "CppDelegate.h"
#import "DashboardCard.h"
#import "DashboardCardContainer.h"
#import "IdentityManager.h"
#import "RootViewController.h"
#import "StatusBar.h"
#import "STLUtils.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kCellCornerRadius = 3;
const float kCellMargin = 9;
const float kNameFieldSpacing = 8;
const float kNameFieldHeight = 25;
const float kSpacing = 8;

LazyStaticImage kContactInfoEmail(
    @"contact-info-email.png");
LazyStaticImage kContactInfoFacebook(
    @"contact-info-fb.png");
LazyStaticImage kContactInfoMobile(
    @"contact-info-mobile.png");
LazyStaticImage kContactInfoName(
    @"contact-info-name.png");
LazyStaticImage kContactInfoNameVFUser(
    @"contact-info-name-vf-user.png");
LazyStaticImage kContactInfoNickname(
    @"contact-info-nickname.png");
LazyStaticImage kEditIcon(
    @"edit-icon.png");
LazyStaticImage kSignupErrorIcon(
    @"signup_error_icon.png");

LazyStaticUIFont kSignupButtonUIFont = {
  kProximaNovaSemibold, 18
};
LazyStaticUIFont kSubtitleFont = {
  kProximaNovaRegular, 14
};
LazyStaticUIFont kUnconfirmedIdentityUIFont = {
  kProximaNovaRegular, 10
};

LazyStaticHexColor kUnconfirmedIdentityTextColor = { "#c73926" };

UITextField* NewOverlayTextField(UILabel* label, int tag) {
  UITextField* text_field = [UITextField new];
  text_field.autocorrectionType = UITextAutocorrectionTypeNo;
  text_field.clearButtonMode = UITextFieldViewModeWhileEditing;
  text_field.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
  text_field.font = label.font;
  text_field.inputAccessoryView = [UIView new];
  text_field.keyboardAppearance = UIKeyboardAppearanceAlert;
  text_field.spellCheckingType = UITextSpellCheckingTypeNo;
  text_field.tag = tag;
  text_field.textColor = UIStyle::kSettingsTextColor;
  text_field.frame = label.frame;
  text_field.frameWidth = text_field.frameWidth - 10;
  return text_field;
}

UIView* NewEditIcon() {
  UIImageView* v = [[UIImageView alloc] initWithImage:kEditIcon];
  v.contentMode = UIViewContentModeLeft;
  v.frameWidth = v.frameWidth + 8;
  return v;
}

UIView* NewUnconfirmedIdentityIcon() {
  UIImageView* v = [[UIImageView alloc] initWithImage:kSignupErrorIcon];
  v.contentMode = UIViewContentModeLeft;
  v.frameWidth = v.frameWidth + 8;
  return v;
}

int CellWidth() {
  return 300 + ((kSDKVersion >= "7" && kIOSVersion >= "7") ? 10 : 0);
}

enum IdentityType {
  EMAIL = LoginEntryDetails::EMAIL,
  PHONE = LoginEntryDetails::PHONE,
  FACEBOOK,
};

}  // namespace

class AddIdentitySettingsSection : public SettingsSection {
 public:
  AddIdentitySettingsSection()
      : SettingsSection() {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    UIButton* b = UIStyle::NewSignupButtonGreen(
        @"Add Email or Mobile", kSignupButtonUIFont, NULL, NULL);
    AddButtonCallback(b, ^{
        Select(index);
      });
    AddButtonToTableCell(b, cell);
  }

  virtual void InitBackground(UITableViewCell* cell, int index) const {
    cell.backgroundColor = [UIColor clearColor];
    cell.backgroundView = cell.selectedBackgroundView =
        [[UIImageView alloc] initWithImage:UIStyle::kTransparent1x1];
  }

  virtual NSString* cell_identifier() const {
    return @"ContactInfoControllerAddIdentityStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleDefault;
  }

  int size() const { return 1; }
};

class BasicInfoSettingsSection : public SettingsSection {
  enum {
    kFullNameFieldTag = 1,
    kFirstNameFieldTag,
    kSpacerViewTag,
    kLastNameFieldTag,
    kUnconfirmedIdentityFieldTag,
    kUnconfirmedIdentityLabelTag,
  };

 public:
  BasicInfoSettingsSection(UIAppState* state, const ContactMetadata* metadata,
                           UITableViewController* table_view_controller)
      : SettingsSection(),
        state_(state),
        metadata_(metadata),
        table_view_controller_(table_view_controller) {
    Refresh();
  }

  void Refresh() {
    name_ = metadata_->name();

    identities_.clear();
    for (int i = 0; i < metadata_->identities_size(); i++) {
      // Filter metadata_->identities to only include those we can usefully
      // display (not the internal "VF" identity).
      const string& identity = metadata_->identities(i).identity();
      if (IdentityManager::IsEmailIdentity(identity)) {
        identities_.push_back(std::make_pair(EMAIL, identity));
      } else if (IdentityManager::IsPhoneIdentity(identity)) {
        identities_.push_back(std::make_pair(PHONE, identity));
      }
      // TODO(peter): Figure out something useful to display here for Facebook
      // identities. Spencer suggests showing the Facebook profile photo.
      // if (IdentityManager::IsFacebookIdentity(identity)) {
      //   identities_.push_back(std::make_pair(FACEBOOK, identity));
      // }
    }

    if (it_is_me()) {
      if (name_.empty()) {
        name_ = "User name not set";
      }
      first_name_ = metadata_->first_name();
      last_name_ = metadata_->last_name();

      SetCallback(0, ^{
          BeginEditName();
          return false;
        });
      // Watch either text field for an empty value; If one exists, disable
      // right bar button (Done) item to disallow attempts at saving.
      text_field_delegate_.Add(
          @protocol(UITextFieldDelegate),
          @selector(textField:shouldChangeCharactersInRange:replacementString:),
          ^(UITextField* text_field, NSRange range, NSString* str) {
            NSString* new_str = [text_field.text
                                    stringByReplacingCharactersInRange:range
                                    withString:str];
            table_view_controller_.navigationItem.rightBarButtonItem.enabled =
                (new_str.length == 0) ? NO : YES;
            return YES;
          });
      text_field_delegate_.Add(
          @protocol(UITextFieldDelegate), @selector(textFieldShouldClear:),
          ^(UITextField* text_field) {
            table_view_controller_.navigationItem.rightBarButtonItem.enabled = NO;
            return YES;
          });
      text_field_delegate_.Add(
          @protocol(UITextFieldDelegate), @selector(textFieldShouldReturn:),
          ^(UITextField* text_field) {
            if (text_field == weak_first_) {
              [weak_last_ becomeFirstResponder];
            } else {
              [weak_first_ becomeFirstResponder];
            }
            return NO;
          });

      unconfirmed_identity_.Clear();
      GetLoginEntryDetails(state_, kAddIdentityKey, &unconfirmed_identity_);
      if ((unconfirmed_identity_.type() != LoginEntryDetails::LINK &&
           unconfirmed_identity_.type() != LoginEntryDetails::MERGE) ||
          unconfirmed_identity_.identity_text().empty()) {
        unconfirmed_identity_.Clear();
      }
      // Suppress the unconfirmed identity if it matches a confirmed identity.
      for (int i = 0; i < identities_.size(); ++i) {
        if (identities_[i].second == unconfirmed_identity_.identity_key()) {
          LOG("suppressing unconfirmed identity: %s",
              unconfirmed_identity_.identity_key());
          unconfirmed_identity_.Clear();
          break;
        }
      }
    }
  }

  void EndEditing(bool save) {
    if (weak_name_.hidden && save) {
      first_name_ = weak_first_ ? ToString(weak_first_.text) : "";
      last_name_ = weak_last_ ? ToString(weak_last_.text) : "";
      if (!first_name_.empty() && !last_name_.empty()) {
        name_ = state_->contact_manager()->ConstructFullName(first_name_, last_name_);
        state_->contact_manager()->SetMyName(first_name_, last_name_, name_);
      }
    }
    [weak_first_ resignFirstResponder];
    [weak_last_ resignFirstResponder];
    if (weak_name_.hidden) {
      weak_name_.text = NewNSString(name_);
      weak_name_.alpha = 0;

      [UIView animateWithDuration:0.3
                       animations:^{
          weak_first_.alpha = 0;
          weak_spacer_.alpha = 0;
          weak_last_.alpha = 0;
          weak_name_.alpha = 1;
          weak_name_.hidden = NO;
        }
                       completion:^(BOOL finished) {
          weak_first_.hidden = YES;
          weak_spacer_.hidden = YES;
          weak_last_.hidden = YES;
        }];
    }
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    ClearViews(cell);
    if (index == 0) {
      if (it_is_me()) {
        InitEditableNameCell(cell);
      } else {
        InitNameCell(cell);
      }
      return;
    }
    if (it_is_me() && index == unconfirmed_identity_index()) {
      InitUnconfirmedIdentityCell(cell);
      return;
    }
    InitIdentityCell(cell, index);
  }

  virtual void InitBackground(UITableViewCell* cell, int index) const {
    SettingsSection::InitBackground(cell, index);
  }

  virtual NSString* cell_identifier() const {
    return @"ContactInfoControllerBasicInfoStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleDefault;
  }

  int size() const {
    return identities_.size() + 1 + (unconfirmed_identity_index() != -1);
  }
  int editing_index() {
    if ([weak_first_ isFirstResponder] || [weak_last_ isFirstResponder]) {
      return 0;
    }
    return -1;
  }
  int unconfirmed_identity_index() const {
    if (unconfirmed_identity_.type() == LoginEntryDetails::LINK ||
        unconfirmed_identity_.type() == LoginEntryDetails::MERGE) {
      return identities_.size() + 1;
    }
    return -1;
  }
  bool it_is_me() const {
    return metadata_->user_id() == state_->user_id();
  }

 private:
  void ClearViews(UITableViewCell* cell) const {
    [[cell.contentView viewWithTag:kFullNameFieldTag] removeFromSuperview];
    [[cell.contentView viewWithTag:kFirstNameFieldTag] removeFromSuperview];
    [[cell.contentView viewWithTag:kSpacerViewTag] removeFromSuperview];
    [[cell.contentView viewWithTag:kLastNameFieldTag] removeFromSuperview];
    [[cell.contentView viewWithTag:kUnconfirmedIdentityFieldTag] removeFromSuperview];
    [[cell.contentView viewWithTag:kUnconfirmedIdentityLabelTag] removeFromSuperview];
  }

  void InitNameCell(UITableViewCell* cell) const {
    string label;
    if (name_ != IdentityManager::IdentityToDisplayName(metadata_->primary_identity())) {
      label = name_;
    }
    if (metadata_->has_user_id()) {
      cell.imageView.image = kContactInfoNameVFUser;
    } else {
      cell.imageView.image = kContactInfoName;
    }
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
    cell.textLabel.font = UIStyle::kContactsListBoldLabelUIFont;
    cell.textLabel.highlightedTextColor = NULL;
    cell.textLabel.text = NewNSString(label);
  }

  void InitEditableNameCell(UITableViewCell* cell) const {
    InitNameCell(cell);
    cell.textLabel.textColor = [UIColor clearColor];

    // Only add the text fields and spacer if they don't already exist.
    UITextField* name_field =
        (UITextField*)[cell.contentView viewWithTag:kFullNameFieldTag];
    if (!name_field) {
      name_field = NewTextField(kFullNameFieldTag, @"");
      name_field.font = cell.textLabel.font;
      name_field.rightView = NewEditIcon();
      name_field.rightViewMode = UITextFieldViewModeAlways;
      name_field.text = cell.textLabel.text;
      name_field.userInteractionEnabled = NO;
      [cell.contentView addSubview:name_field];
    }
    weak_name_ = name_field;

    UITextField* first_field =
        (UITextField*)[cell.contentView viewWithTag:kFirstNameFieldTag];
    if (!first_field) {
      first_field = NewTextField(kFirstNameFieldTag, @"First name");
      [cell.contentView addSubview:first_field];
    }
    weak_first_ = first_field;

    UIImageView* spacer =
        (UIImageView*)[cell.contentView viewWithTag:kSpacerViewTag];
    if (!spacer) {
      spacer = [[UIImageView alloc] initWithImage:UIStyle::kSpacer];
      [cell.contentView addSubview:spacer];
    }
    weak_spacer_ = spacer;

    UITextField* last_field =
        (UITextField*)[cell.contentView viewWithTag:kLastNameFieldTag];
    if (!last_field) {
      last_field = NewTextField(kLastNameFieldTag, @"Last name");
      [cell.contentView addSubview:last_field];
    }
    weak_last_ = last_field;

    weak_first_.text = !first_name_.empty() ? NewNSString(first_name_) : NULL;
    weak_last_.text = !last_name_.empty() ? NewNSString(last_name_) : NULL;

    weak_first_.alpha = 0;
    weak_first_.hidden = YES;
    weak_spacer_.alpha = 0;
    weak_spacer_.hidden = YES;
    weak_last_.alpha = 0;
    weak_last_.hidden = YES;

    // Need to layout the cell subviews in order for cell.textLabel to be
    // sized/positioned correctly.
    [cell layoutSubviews];

    weak_name_.frameLeft = cell.textLabel.frameLeft;
    weak_name_.frameWidth = CellWidth() - weak_name_.frameLeft;
    weak_name_.frameTop = cell.textLabel.frameTop;
    weak_name_.frameHeight = cell.textLabel.frameHeight;

    weak_first_.frameLeft = cell.textLabel.frameLeft;
    weak_first_.frameWidth = (CellWidth() - kNameFieldSpacing -
                              cell.textLabel.frameLeft) / 2;
    weak_first_.frameTop = cell.textLabel.frameTop;
    weak_first_.frameHeight = cell.textLabel.frameHeight;

    weak_spacer_.frameLeft = weak_first_.frameRight;
    weak_spacer_.frameTop = weak_first_.frameTop +
        (weak_first_.frameHeight - weak_spacer_.frameHeight) / 2;

    weak_last_.frameLeft = weak_spacer_.frameRight + kNameFieldSpacing;
    weak_last_.frameWidth = weak_first_.frameWidth;
    weak_last_.frameTop = cell.textLabel.frameTop;
    weak_last_.frameHeight = cell.textLabel.frameHeight;
  }

  void InitIdentityIcon(UIImageView* view, int type) const {
    switch (type) {
      case EMAIL:
        view.image = kContactInfoEmail;
        view.hidden = NO;
        break;
      case FACEBOOK:
        view.image = kContactInfoFacebook;
        view.hidden = NO;
        break;
      case PHONE:
        view.image = kContactInfoMobile;
        view.hidden = NO;
        break;
      default:
        view.image = kContactInfoEmail;
        view.hidden = YES;
        break;
    }
  }

  void InitIdentityCell(UITableViewCell* cell, int index) const {
    const pair<IdentityType, string>& identity = identities_[index - 1];
    InitIdentityIcon(cell.imageView, identity.first);
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
    cell.textLabel.font = UIStyle::kContactsListLabelUIFont;
    cell.textLabel.highlightedTextColor = NULL;
    cell.textLabel.text = NewNSString(
        IdentityManager::IdentityToDisplayName(identity.second));
  }

  void InitUnconfirmedIdentityCell(UITableViewCell* cell) const {
    InitIdentityIcon(cell.imageView, unconfirmed_identity_.identity_type());
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
    cell.textLabel.font = UIStyle::kContactsListLabelUIFont;
    cell.textLabel.highlightedTextColor = NULL;
    cell.textLabel.text = NewNSString(unconfirmed_identity_.identity_text());
    cell.textLabel.textColor = [UIColor clearColor];

    // Only add the text fields and spacer if they don't already exist.
    UITextField* field =
        (UITextField*)[cell.contentView viewWithTag:kUnconfirmedIdentityFieldTag];
    if (!field) {
      field = NewTextField(kUnconfirmedIdentityFieldTag, @"");
      field.font = cell.textLabel.font;
      field.rightView = NewUnconfirmedIdentityIcon();
      field.rightViewMode = UITextFieldViewModeAlways;
      field.text = cell.textLabel.text;
      field.userInteractionEnabled = NO;
      [cell.contentView addSubview:field];
    }

    UILabel* label =
        (UILabel*)[cell.contentView viewWithTag:kUnconfirmedIdentityLabelTag];
    if (!label) {
      label = [UILabel new];
      label.tag = kUnconfirmedIdentityLabelTag;
      label.font = kUnconfirmedIdentityUIFont;
      label.text = unconfirmed_identity_.merging() ? @"Combining" : @"Unconfirmed";
      label.textColor = kUnconfirmedIdentityTextColor;
      [label sizeToFit];
      [cell.contentView addSubview:label];
    }

    [cell layoutSubviews];
    field.frameLeft = cell.textLabel.frameLeft;
    field.frameWidth = CellWidth() - field.frameLeft;
    field.frameTop = cell.textLabel.frameTop;
    field.frameHeight = cell.textLabel.frameHeight;

    label.frameLeft = cell.textLabel.frameLeft;
    label.frameBottom = cell.textLabel.frameHeight;
  }

  UITextField* NewTextField(int tag, NSString* placeholder) const {
    UITextField* text_field = [UITextField new];
    text_field.autoresizingMask =
        UIViewAutoresizingFlexibleTopMargin |
        UIViewAutoresizingFlexibleBottomMargin;
    text_field.autocapitalizationType = UITextAutocapitalizationTypeWords;
    text_field.backgroundColor = [UIColor clearColor];
    text_field.borderStyle = UITextBorderStyleNone;
    text_field.clearButtonMode = UITextFieldViewModeWhileEditing;
    text_field.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
    text_field.delegate = text_field_delegate_.delegate();
    text_field.font = UIStyle::kContactsListLabelUIFont;
    text_field.frameHeight = kNameFieldHeight;
    text_field.inputAccessoryView = [UIView new];
    text_field.keyboardAppearance = UIKeyboardAppearanceAlert;
    text_field.placeholder = placeholder;
    text_field.returnKeyType = UIReturnKeyNext;
    text_field.tag = tag;
    text_field.textColor = UIStyle::kSettingsTextColor;
    return text_field;
  }

  void BeginEditName() {
    if (!weak_name_.hidden) {
      [UIView animateWithDuration:0.3
                       animations:^{
          weak_first_.alpha = 1;
          weak_first_.hidden = NO;
          weak_spacer_.alpha = 1;
          weak_spacer_.hidden = NO;
          weak_last_.alpha = 1;
          weak_last_.hidden = NO;
          weak_name_.alpha = 0;
        }
                       completion:^(BOOL finished) {
          weak_name_.hidden = YES;
        }];


      UITableView* table_view = table_view_controller_.tableView;
      [table_view scrollToRowAtIndexPath:
            [NSIndexPath indexPathForRow:0 inSection:0]
                        atScrollPosition:UITableViewScrollPositionNone
                                animated:YES];
      [weak_first_ becomeFirstResponder];
    }
  }

 private:
  UIAppState* const state_;
  const ContactMetadata* const metadata_;
  UITableViewController* const table_view_controller_;
  string name_;
  string first_name_;
  string last_name_;
  vector<pair<IdentityType, string> > identities_;
  LoginEntryDetails unconfirmed_identity_;
  mutable __weak UITextField* weak_name_;
  mutable __weak UITextField* weak_first_;
  mutable __weak UIImageView* weak_spacer_;
  mutable __weak UITextField* weak_last_;
  CppDelegate text_field_delegate_;
};

class NicknameSettingsSection : public SettingsSection {
 public:
  NicknameSettingsSection(UIAppState* state, ContactMetadata* metadata)
      : SettingsSection(),
        state_(state),
        metadata_(metadata) {
    SetCallback(0, ^{
        weak_text_field_.rightViewMode = UITextFieldViewModeNever;
        [weak_text_field_ becomeFirstResponder];
        return false;
      });
  }

  void SetEditing(bool editing, bool save) {
    if (editing) {
      [weak_text_field_ becomeFirstResponder];
    } else if ([weak_text_field_ isFirstResponder]) {
      if (save) {
        if (weak_text_field_.text) {
          metadata_->set_nickname(ToString(weak_text_field_.text));
        } else {
          metadata_->clear_nickname();
        }
        state_->contact_manager()->SetFriendNickname(
            metadata_->user_id(), metadata_->nickname());
      }
      InitNickname();
      [weak_text_field_ resignFirstResponder];
    }
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    cell.imageView.image = kContactInfoNickname;
    cell.selectionStyle = UITableViewCellSelectionStyleNone;

    // In order to have the text field automatically positioned correctly, we
    // add it as a subview of the textLabel. But in order to have the textLabel
    // positioned correctly it has to have non-empty text and the same font as
    // the text field.
    cell.textLabel.font = UIStyle::kContactsListLabelUIFont;
    cell.textLabel.text = @"Add Nickname";
    cell.textLabel.textColor = [UIColor clearColor];

    // Only add the text field if it doesn't already exist.
    static const int kNicknameFieldTag = 2;
    UITextField* text_field =
        (UITextField*)[cell.contentView viewWithTag:kNicknameFieldTag];
    if (!text_field) {
      [cell layoutSubviews];
      text_field = NewOverlayTextField(cell.textLabel, kNicknameFieldTag);
      text_field.autocapitalizationType = UITextAutocapitalizationTypeWords;
      text_field.placeholder = cell.textLabel.text;
      text_field.rightView = NewEditIcon();
      [cell.contentView addSubview:text_field];
    }
    weak_text_field_ = text_field;

    InitNickname();
  }

  virtual NSString* cell_identifier() const {
    return @"ContactInfoControllerNicknameStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleDefault;
  }

  int size() const { return 1; }
  int editing_index() const {
    if ([weak_text_field_ isFirstResponder]) {
      return 0;
    }
    return -1;
  }

 private:
  void InitNickname() const {
    if (!metadata_->nickname().empty()) {
      weak_text_field_.rightViewMode = UITextFieldViewModeUnlessEditing;
      weak_text_field_.text = NewNSString(metadata_->nickname());
    } else {
      weak_text_field_.rightViewMode = UITextFieldViewModeNever;
      weak_text_field_.text = NULL;
    }
  }

 private:
  UIAppState* const state_;
  ContactMetadata* const metadata_;
  mutable __weak UITextField* weak_text_field_;
};

class PasswordSettingsSection : public SettingsSection {
 public:
  PasswordSettingsSection(UIAppState* state)
      : SettingsSection(),
        state_(state) {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    UIButton* b = UIStyle::NewSignupButtonGrey(
        state_->no_password() ? @"Set Password" : @"Change Password",
        kSignupButtonUIFont, NULL, NULL);
    AddButtonCallback(b, ^{
        Select(index);
      });
    AddButtonToTableCell(b, cell);
  }

  virtual void InitBackground(UITableViewCell* cell, int index) const {
    cell.backgroundColor = [UIColor clearColor];
    cell.backgroundView = cell.selectedBackgroundView =
        [[UIImageView alloc] initWithImage:UIStyle::kTransparent1x1];
  }

  virtual NSString* cell_identifier() const {
    return @"ContactInfoControllerPasswordStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleDefault;
  }

  int size() const { return 1; }

 private:
  UIAppState* const state_;
};

class ShowConversationsSettingsSection : public SettingsSection {
 public:
  ShowConversationsSettingsSection()
      : SettingsSection() {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    UIButton* b = UIStyle::NewSignupButtonGreen(
        @"Show Conversations", kSignupButtonUIFont, NULL, NULL);
    AddButtonCallback(b, ^{
        Select(index);
      });
    AddButtonToTableCell(b, cell);
  }

  virtual void InitBackground(UITableViewCell* cell, int index) const {
    cell.backgroundColor = [UIColor clearColor];
    cell.backgroundView = cell.selectedBackgroundView =
        [[UIImageView alloc] initWithImage:UIStyle::kTransparent1x1];
  }

  virtual NSString* cell_identifier() const {
    return @"ContactInfoControllerShowConversationsStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleDefault;
  }

  int size() const { return 1; }
};

@interface EditingOverlayView : UIView {
 @private
  CGRect cutout_;
}

@end  // EditingOverlayView

@implementation EditingOverlayView

- (id)initWithCutout:(CGRect)cutout {
  if (self = [super init]) {
    cutout_ = cutout;
  }
  return self;
}

- (BOOL)pointInside:(CGPoint)point
          withEvent:(UIEvent*)event {
  if (![super pointInside:point withEvent:event]) {
    return false;
  }
  return !CGRectContainsPoint(cutout_, point);
}

@end  // EditingOverlayView

@implementation ContactInfoController

- (id)initWithState:(UIAppState*)state
            contact:(const ContactMetadata&)metadata {
  if (self = [super init]) {
    state_ = state;
    metadata_ = metadata;
    if (metadata.user_id() == state_->user_id()) {
      self.title = @"My Info";
    } else {
      self.title = @"Contact Info";
    }

    contact_changed_id_ = -1;
    if (metadata.has_user_id()) {
      contact_changed_id_ = state_->contact_manager()->contact_changed()->Add(^{
          state_->async()->dispatch_main(^{
              ContactMetadata new_metadata;
              if (!state_->contact_manager()->LookupUser(
                      metadata_.user_id(), &new_metadata)) {
                return;
              }
              if (metadata_.SerializeAsString() == new_metadata.SerializeAsString()) {
                // The metadata is unchanged.
                return;
              }
              metadata_ = new_metadata;
              [self refreshSections];
            });
      });
    }

    settings_changed_id_ = -1;
    if (metadata.user_id() == state_->user_id()) {
      settings_changed_id_ = state_->settings_changed()->Add(^(bool downloaded) {
          state_->async()->dispatch_main(^{
              [self refreshSections];
            });
        });
    }

    basic_info_.reset(new BasicInfoSettingsSection(state_, &metadata_, self));

    if (basic_info_->it_is_me()) {
      add_identity_.reset(new AddIdentitySettingsSection);
      add_identity_->SetCallback(0, ^{
          state_->analytics()->ContactInfoAddIdentity();
          [self showLinkIdentityCard];
          return false;
        });

      password_.reset(new PasswordSettingsSection(state_));
      password_->SetCallback(0, ^{
          state_->analytics()->ContactInfoChangePassword();
          [self showPasswordCard];
          return false;
        });
    } else if (metadata_.has_user_id()) {
      show_conversations_.reset(new ShowConversationsSettingsSection);
      show_conversations_->SetCallback(0, ^{
          state_->analytics()->ContactInfoShowConversations();
          [self showContactTrapdoors];
          return false;
        });
    }

    // Do not show the nickname field on the "My Info" page.
    if (!basic_info_->it_is_me()) {
      if (metadata_.has_user_id()) {
        nickname_.reset(new NicknameSettingsSection(state_, &metadata_));
      }

      string email;
      string phone;
      if (metadata_.has_user_id() ||
          ContactManager::EmailForContact(metadata_, &email) ||
          ContactManager::PhoneForContact(metadata_, &phone)) {
        show_compose_button_ = true;
      }
    }

    [self refreshSections];
  }
  return self;
}

- (void)showContactTrapdoors {
  contact_trapdoors_ = [[ContactTrapdoorsView alloc] initWithState:state_
                                                     withContactId:metadata_.user_id()];
  if (contact_trapdoors_.empty) {
    UIAlertView* a =
        [[UIAlertView alloc]
              initWithTitle:Format("You currently have no conversations with %s",
                                   state_->contact_manager()->FirstName(metadata_.user_id()))
                    message:Format("Start a conversation with %s now to connect and share memories.",
                                   state_->contact_manager()->FirstName(metadata_.user_id()))
                   delegate:NULL
          cancelButtonTitle:@"OK"
          otherButtonTitles:NULL];
    [a show];
    contact_trapdoors_ = NULL;
    return;
  }

  contact_trapdoors_.hidden = YES;
  contact_trapdoors_.env = self;
  contact_trapdoors_.frame = [[UIScreen mainScreen] bounds];

  const int index = IndexOf(sections_, show_conversations_.get());
  UITableViewCell* cell =
      [self.tableView cellForRowAtIndexPath:
               [NSIndexPath indexPathForRow:0 inSection:index]];
  const CGRect f = [cell.superview convertRect:cell.frame toView:self.view.superview];
  [contact_trapdoors_ showFromRect:f];
}

- (void)contactTrapdoorsSelection:(int64_t)viewpoint_id {
  ControllerTransition transition;
  transition.type = TRANSITION_FADE_IN;
  transition.state.current_viewpoint = viewpoint_id;
  [self contactTrapdoorsExit];
  [state_->root_view_controller() showConversation:transition];
}

- (void)contactTrapdoorsExit {
  if (!contact_trapdoors_) {
    return;
  }
  [contact_trapdoors_ hide:true];
  contact_trapdoors_ = NULL;
}

- (void)startConversation {
  if (metadata_.has_user_id() || metadata_.identities_size() == 1) {
    [self startConversationWithContact:metadata_];
  } else {
    ChooseIdentityForContact(
        metadata_, self.view,
        ^(const ContactMetadata* contact) {
          if (contact) {
            [self startConversationWithContact:*contact];
          }
        });
  }
}

- (void)startConversationWithContact:(const ContactMetadata&)contact {
  ContactManager::ContactVec contacts;
  contacts.push_back(contact);
  state_->root_view_controller().composeLayoutController.allContacts = contacts;
  [state_->root_view_controller() showCompose:ControllerTransition()];
}

- (void)refreshSections {
  for (int i = 1; i < basic_info_->size(); ++i) {
    basic_info_->SetCallback(i, NULL);
  }
  basic_info_->Refresh();
  if (basic_info_->unconfirmed_identity_index() != -1) {
    basic_info_->SetCallback(basic_info_->unconfirmed_identity_index(), ^{
        [self showLinkIdentityCard];
        return false;
      });
  }

  vector<SettingsSection*> sections;
  sections.push_back(basic_info_.get());
  if (add_identity_.get() &&
      basic_info_->unconfirmed_identity_index() == -1) {
    sections.push_back(add_identity_.get());
  }
  if (password_.get()) {
    sections.push_back(password_.get());
  }
  if (nickname_.get()) {
    sections.push_back(nickname_.get());
  }
  if (show_conversations_.get()) {
    sections.push_back(show_conversations_.get());
  }
  [self setSections:sections];
}

- (UIBarButtonItem*)backButtonItem {
  if (!back_button_item_) {
    back_button_item_ = UIStyle::NewToolbarBack(
        self, @selector(toolbarBack));
    UIStyle::InitLeftBarButton(back_button_item_);
  }
  return back_button_item_;
}

- (UIBarButtonItem*)cancelButtonItem {
  if (!cancel_button_item_) {
    cancel_button_item_ = UIStyle::NewToolbarCancel(
        self, @selector(toolbarCancel));
    UIStyle::InitLeftBarButton(cancel_button_item_);
  }
  return cancel_button_item_;
}

- (UIBarButtonItem*)composeButtonItem {
  if (!compose_button_item_) {
    compose_button_item_ = UIStyle::NewToolbarCompose(
        self, @selector(toolbarCompose));
    UIStyle::InitRightBarButton(compose_button_item_);
  }
  return compose_button_item_;
}

- (UIBarButtonItem*)doneButtonItem {
  if (!done_button_item_) {
    done_button_item_ = UIStyle::NewToolbarGreenButton(
        @"Done", self, @selector(toolbarDone));
    UIStyle::InitRightBarButton(done_button_item_);
  }
  return done_button_item_;
}

- (UINavigationItem*)navigationItem {
  UINavigationItem* i = [super navigationItem];
  if (!i.leftBarButtonItem) {
    i.leftBarButtonItem = self.backButtonItem;
  }
  if (!i.rightBarButtonItem && show_compose_button_) {
    i.rightBarButtonItem = self.composeButtonItem;
  }
  if (!i.titleView) {
    i.titleView = UIStyle::NewContactsTitleView(self.title);
  }
  return i;
}

- (void)setEditing:(BOOL)editing
          animated:(BOOL)animated {
  [super setEditing:editing animated:animated];
  if (!editing) {
    self.navigationItem.leftBarButtonItem = self.backButtonItem;
    self.navigationItem.rightBarButtonItem =
        show_compose_button_ ? self.composeButtonItem : NULL;
    basic_info_->EndEditing(true /* save */);
    if (nickname_.get()) {
      nickname_->SetEditing(false, true /* save */);
    }
    [self hideEditingOverlay];
  } else {
    self.navigationItem.leftBarButtonItem = self.cancelButtonItem;
    self.navigationItem.rightBarButtonItem = self.doneButtonItem;
    [self showEditingOverlay];
  }
  self.tableView.scrollEnabled = !editing;
  [self.tableView setEditing:NO animated:NO];
}

- (void)viewWillAppear:(BOOL)animated {
  [super viewWillAppear:animated];
  state_->analytics()->ContactInfoPage(basic_info_->it_is_me());
  if (!keyboard_will_show_.get()) {
    keyboard_will_show_.Init(
        UIKeyboardWillShowNotification,
        ^(NSNotification* n) {
          if (!self.editing && !card_container_) {
            [self setEditing:YES animated:YES];
          }
        });
  }
}

- (void)viewWillDisappear:(BOOL)animated {
  [super viewWillDisappear:animated];
  keyboard_will_show_.Clear();
  basic_info_->EndEditing(false /* save */);
  if (nickname_.get()) {
    nickname_->SetEditing(false, false /* save */);
  }
  [self hideEditingOverlay];
  [self contactTrapdoorsExit];
}

- (void)toolbarBack {
  if (self.navigationController.viewControllers.count == 1) {
    [state_->root_view_controller() dismissViewController:ControllerState()];
  } else {
    [self.navigationController popViewControllerAnimated:YES];
  }
}

- (void)toolbarCancel {
  basic_info_->EndEditing(false /* save */);
  if (nickname_.get()) {
    nickname_->SetEditing(false, false /* save */);
  }
  [self setEditing:NO animated:YES];
}

- (void)toolbarCompose {
  state_->analytics()->ContactInfoStartConversation();
  [self startConversation];
}

- (void)toolbarDone {
  [self setEditing:NO animated:YES];
}

- (int)sectionIndex:(SettingsSection*)section {
  for (int i = 0; i < sections_.size(); ++i) {
    if (section == sections_[i]) {
      return i;
    }
  }
  return -1;
}

- (NSIndexPath*)editingIndexPath {
  int row = basic_info_->editing_index();
  if (row != -1) {
    return [NSIndexPath indexPathForRow:row
                              inSection:[self sectionIndex:basic_info_.get()]];
  }
  if (nickname_.get()) {
    int row = nickname_->editing_index();
    if (row != -1) {
      return [NSIndexPath indexPathForRow:row
                                inSection:[self sectionIndex:nickname_.get()]];
    }
  }
  return NULL;
}

- (void)showLoginSignupCard:(const string&)key {
  card_container_ = [[DashboardCardContainer alloc]
                      initWithState:state_
                         withParent:self.navigationController.view
                            withKey:key
                       withCallback:^(DashboardCardContainer* container) {
      [card_container_ removeFromSuperview];
      card_container_ = NULL;
    }];
  [self.navigationController.view addSubview:card_container_];
}

- (void)showLinkIdentityCard {
  [LoginSignupDashboardCard
    prepareForLinkIdentity:state_
                    forKey:kAddIdentityKey];
  [self showLoginSignupCard:kAddIdentityKey];
}

- (void)showPasswordCard {
  [LoginSignupDashboardCard
    prepareForChangePassword:state_
                      forKey:kChangePasswordKey];
  [self showLoginSignupCard:kChangePasswordKey];
}

- (void)showEditingOverlay {
  NSIndexPath* index_path = self.editingIndexPath;
  if (!index_path) {
    return;
  }

  // Find the rectangle that encloses the editing cell.
  UITableViewCell* cell = [self.tableView cellForRowAtIndexPath:index_path];
  const CGRect cell_frame = CGRectOffset(
      CGRectInset([self.view convertRect:cell.bounds fromView:cell],
                  kCellMargin, 0),
      0, self.tableView.contentInset.top);

  // Create an overlay that hides taps except in the editing cell.
  editing_overlay_ = [[EditingOverlayView alloc] initWithCutout:cell_frame];
  editing_overlay_.alpha = 0;
  editing_overlay_.frame = self.view.bounds;
  [self.view addSubview:editing_overlay_];

  // Create a CAShapeLayer that matches the shape of the editing cell. It would
  // be better (more robust) if we could directly use the background image to
  // create the mask. But hard coding the shape as is done below is more
  // expedient.
  int corners = 0;
  if (index_path.row == 0) {
    corners |= UIRectCornerTopLeft | UIRectCornerTopRight;
  }
  if (index_path.row + 1 == sections_[index_path.section]->cached_size()) {
    corners |= UIRectCornerBottomLeft | UIRectCornerBottomRight;
  }
  const CGSize radii = CGSizeMake(kCellCornerRadius, kCellCornerRadius);

  ScopedRef<CGMutablePathRef> path(CGPathCreateMutable());
  CGPathAddRect(path, NULL, self.view.bounds);
  CGPathAddPath(path, NULL,
                [UIBezierPath bezierPathWithRoundedRect:cell_frame
                                      byRoundingCorners:corners
                                            cornerRadii:radii].CGPath);

  CAShapeLayer* l = [CAShapeLayer new];
  l.path = path;
  l.fillColor = [UIColor blackColor].CGColor;
  l.fillRule = kCAFillRuleEvenOdd;
  [editing_overlay_.layer addSublayer:l];

  [UIView animateWithDuration:0.3
                   animations:^{
      editing_overlay_.alpha = 0.3;
    }];
}

- (void)hideEditingOverlay {
  if (!editing_overlay_) {
    return;
  }
  [UIView animateWithDuration:0.3
                   animations:^{
      editing_overlay_.alpha = 0;
    }
                     completion:^(BOOL finished) {
      [editing_overlay_ removeFromSuperview];
      editing_overlay_ = NULL;
    }];
}

- (void)dealloc {
  if (contact_changed_id_ != -1) {
    state_->contact_manager()->contact_changed()->Remove(contact_changed_id_);
  }
  if (settings_changed_id_ != -1) {
    state_->settings_changed()->Remove(settings_changed_id_);
  }
}

@end  // ContactInfoController
