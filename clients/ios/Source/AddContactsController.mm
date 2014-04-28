// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIActivityIndicatorView.h>
#import "AddContactsController.h"
#import "AddressBookManager.h"
#import "Analytics.h"
#import "AsyncState.h"
#import "AttrStringUtils.h"
#import "AuthService.h"
#import "CALayer+geometry.h"
#import "ContactInfoController.h"
#import "ContactManager.h"
#import "ContactMetadata.pb.h"
#import "ContactsController.h"
#import "ContactsTableViewCell.h"
#import "ControlDelegate.h"
#import "CppDelegate.h"
#import "DashboardCardContainer.h"
#import "IdentityManager.h"
#import "IdentityTextField.h"
#import "RootViewController.h"
#import "TextLayer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const int kRowBorder = 10;
const int kCellBorder = 15;
const int kCellHeight = 44 + 2 * kCellBorder;

const int kContactSourceIconOffset = 15;
const int kContactSourceLine1Offset = 15;
const int kContactSourceLine2Offset = 36;
const int kContactSourceLine3Offset = 50;

const float kIconSpacing = 6;

const float kSuccessIconDuration = 5;
// The error icon is often shown with an alert message, so it should be displayed for longer.
const float kErrorIconDuration = 15;

LazyStaticUIFont kContactFetchFont = {
  kProximaNovaBold, 17
};

LazyStaticUIFont kContactSourceHeaderFont = {
  kProximaNovaBold, 18
};

LazyStaticUIFont kContactSourceDetailFont = {
  kProximaNovaRegular, 12
};

LazyStaticHexColor kContactFetchLabelColor = { "#fefefe" };
LazyStaticHexColor kContactSourceHeaderColor = { "#3f3e3e" };
LazyStaticHexColor kContactSourceDetailColor = { "#9f9c9c" };

UIView* NewContactsFetchRow(
    UIImage* icon, UIButton* fetch, float width) {
  UIImageView* background =
      [[UIImageView alloc] initWithImage:UIStyle::kContactsCellBackground1];
  background.frameHeight = kCellHeight;
  background.frameLeft = kRowBorder;
  background.frameWidth = width - 2 * kRowBorder;
  background.userInteractionEnabled = YES;

  UIImageView* v = [[UIImageView alloc] initWithImage:icon];
  v.autoresizingMask =
      UIViewAutoresizingFlexibleBottomMargin |
      UIViewAutoresizingFlexibleTopMargin;
  v.frameTop = kCellBorder;
  v.frameLeft = kCellBorder;
  [background addSubview:v];

  fetch.frameLeft = v.frameRight + kCellBorder;
  fetch.frameWidth = background.frameWidth - fetch.frameLeft - kCellBorder;
  fetch.frameTop = kCellBorder;
  fetch.frameHeight = v.frameHeight;
  [background addSubview:fetch];

  return background;
}

UIButton* NewContactsFetchButton(
    NSString* title, void (^callback)()) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.autoresizingMask =
      UIViewAutoresizingFlexibleBottomMargin |
      UIViewAutoresizingFlexibleTopMargin;
  b.titleLabel.font = kContactFetchFont;
  [b setTitle:title
     forState:UIControlStateNormal];
  [b setTitleColor:kContactFetchLabelColor
          forState:UIControlStateNormal];
  [b setBackgroundImage:UIStyle::kTallButtonGrey
               forState:UIControlStateNormal];
  [b setBackgroundImage:UIStyle::kTallButtonGreyActive
               forState:UIControlStateHighlighted];
  AddButtonCallback(b, callback);
  return b;
}

UIButton* NewContactsActionButton(
    UIImage* image, UIImage* background,
    UIImage* background_active, void (^callback)()) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.autoresizingMask =
      UIViewAutoresizingFlexibleBottomMargin |
      UIViewAutoresizingFlexibleTopMargin;
  [b setImage:image
     forState:UIControlStateNormal];
  [b setImage:image
     forState:UIControlStateHighlighted];
  [b setImage:UIStyle::kTransparent1x1
     forState:UIControlStateDisabled];
  [b setBackgroundImage:background
               forState:UIControlStateNormal];
  [b setBackgroundImage:background_active
               forState:UIControlStateHighlighted];
  [b setBackgroundImage:background
               forState:UIControlStateDisabled];
  b.frameSize = UIStyle::kIconGmail.get().size;
  AddButtonCallback(b, callback);
  return b;
}

class ContactsRefreshButton {
 public:
  enum State {
    REFRESH,
    SUCCESS,
    ERROR,
  };

  ContactsRefreshButton(void (^callback)())
      : callback_(callback),
        state_(REFRESH),
        view_([UIView new]),
        button_(NULL) {
    view_.autoresizesSubviews = true;
    view_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    SetState(REFRESH);
  }

  UIView* view() { return view_; };
  State state() const { return state_; }

  void SetState(State state) {
    if (button_ && state_ == state) {
      return;
    }
    UIButton* old_button = button_;
    state_ = state;
    if (state == REFRESH) {
      button_ = NewContactsActionButton(UIStyle::kIconBigRefresh,
                                        UIStyle::kTallButtonGreen, UIStyle::kTallButtonGreenActive,
                                        callback_);
    } else if (state == SUCCESS) {
      button_ = NewContactsActionButton(UIStyle::kIconBigCheckmark,
                                        UIStyle::kTallButtonBlue, UIStyle::kTallButtonBlueActive,
                                        callback_);
    } else if (state == ERROR) {
      button_ = NewContactsActionButton(UIStyle::kIconBigError,
                                        UIStyle::kTallButtonRed, UIStyle::kTallButtonRedActive,
                                        callback_);
    }
    view_.frameSize = button_.frameSize;
    if (old_button) {
      [UIView transitionFromView:old_button
                          toView:button_
                        duration:0.3
                         options:UIViewAnimationOptionTransitionCrossDissolve
                      completion:NULL];
    } else {
      [view_ addSubview:button_];
    }
  }

  void StartActivity() {
    CHECK(activity_ == NULL);
    activity_ =
        [[UIActivityIndicatorView alloc]
         initWithFrame:button_.imageView.frame];
    [activity_ startAnimating];
    [button_ addSubview:activity_];
    button_.enabled = NO;
  }

  void StopActivity() {
    CHECK(activity_);
    [activity_ removeFromSuperview];
    activity_ = NULL;
    button_.enabled = YES;
  }

 private:
  void (^callback_)();
  State state_;
  UIView* view_;
  UIButton* button_;
  UIActivityIndicatorView* activity_;
};

class ContactsSection {
 public:
  ContactsSection(UIAppState* state, const string& contact_source_prefix)
      : state_(state),
        fetch_contacts_(false),
        contact_source_prefix_(contact_source_prefix),
        contacts_counted_(false),
        contact_count_(0),
        vf_contact_count_(0),
        previous_contact_count_(0),
        previous_vf_contact_count_(0),
        width_(0),
        fetching_contacts_(false),
        reset_seq_no_(0) {
  }
  virtual ~ContactsSection() {
  }

  virtual UIView* BuildView(float width) {
    width_ = width;
    if (!contacts_counted_) {
      CountContacts();
    }
    UpdateView();
    return view_;
  }

  void ClearView() {
    [view_ removeFromSuperview];
    view_ = NULL;
    [row_ removeFromSuperview];
    row_ = NULL;
    refresh_.reset(NULL);
    activity_ = NULL;
  }

  void set_navigation_controller(UINavigationController* c) {
    navigation_controller_ = c;
  }

  UIView* view() { return view_; }
  int width() const { return width_; }

  void CountContacts() {
    contacts_counted_ = true;
    previous_contact_count_ = contact_count_;
    contact_count_ = state_->contact_manager()->CountContactsForSource(contact_source_prefix_);
    previous_vf_contact_count_ = vf_contact_count_;
    vf_contact_count_ = state_->contact_manager()->CountViewfinderContactsForSource(contact_source_prefix_);
  }

  WallTime GetLastImportTime() {
    return state_->contact_manager()->GetLastImportTimeForSource(contact_source_prefix());
  }

 protected:
  virtual UIImage* NewFetchIcon() = 0;
  virtual UIButton* NewFetchButton() = 0;

  virtual NSString* GetHeaderText() = 0;
  virtual NSString* GetDetailText(int count, int vf_count, bool is_new) = 0;

  NSString* GetLastImportedText() {
    const WallTime timestamp = GetLastImportTime();
    if (timestamp) {
      return Format("Last imported %s", FormatTimeAgo(timestamp, WallTime_Now(), TIME_AGO_LONG));
    }
    return @"";
  }

  virtual bool IsLinked() = 0;

  virtual UIView* NewFetchRow(float width) {
    header_label_ = detail_label_ = last_imported_label_ = NULL;
    return NewContactsFetchRow(
        NewFetchIcon(),
        NewFetchButton(),
        width);
  }

  virtual UIView* NewRefreshRow(float width) {
    UIImageView* background =
        [[UIImageView alloc] initWithImage:UIStyle::kContactsCellBackground1];
    background.frameHeight = kCellHeight;
    background.frameLeft = kRowBorder;
    background.frameWidth = width - 2 * kRowBorder;
    background.userInteractionEnabled = YES;

    CHECK(refresh_.get());
    refresh_->view().frameTop = kCellBorder;
    refresh_->view().frameLeft = kCellBorder;
    [background addSubview:refresh_->view()];

    const float dim = kContactSourceHeaderFont.get().lineHeight * 0.90;
    UIImageView* i1 = [[UIImageView alloc] initWithImage:NewFetchIcon()];
    i1.frameLeft = refresh_->view().frameRight + kCellBorder;
    i1.frameTop = kContactSourceIconOffset;
    i1.frameSize = CGSizeMake(dim, dim);
    [background addSubview:i1];

    UILabel* l1 = [UILabel new];
    l1.tag = 3;
    l1.backgroundColor = [UIColor clearColor];
    l1.font = kContactSourceHeaderFont;
    l1.textColor = kContactSourceHeaderColor;
    l1.lineBreakMode = NSLineBreakByTruncatingTail;
    l1.frameLeft = i1.frameRight + kIconSpacing;
    l1.frameTop = kContactSourceLine1Offset;
    l1.frameWidth = background.frameWidth - l1.frameLeft - kCellBorder;
    l1.frameHeight = l1.font.lineHeight;
    [background addSubview:l1];
    header_label_ = l1;

    UILabel* l2 = [UILabel new];
    l2.tag = 4;
    l2.backgroundColor = [UIColor clearColor];
    l2.font = kContactSourceDetailFont;
    l2.textColor = kContactSourceDetailColor;
    l2.lineBreakMode = NSLineBreakByTruncatingTail;
    l2.frameLeft = i1.frameLeft;
    l2.frameTop = kContactSourceLine2Offset;
    l2.frameWidth = background.frameWidth - l2.frameLeft - kCellBorder;
    l2.frameHeight = l2.font.lineHeight;
    [background addSubview:l2];
    detail_label_ = l2;

    UILabel* l3 = [UILabel new];
    l3.tag = 5;
    l3.backgroundColor = [UIColor clearColor];
    l3.font = kContactSourceDetailFont;
    l3.textColor = kContactSourceDetailColor;
    l3.lineBreakMode = NSLineBreakByTruncatingTail;
    l3.frameLeft = i1.frameLeft;
    l3.frameTop = kContactSourceLine3Offset;
    l3.frameWidth = background.frameWidth - l3.frameLeft - kCellBorder;
    l3.frameHeight = l3.font.lineHeight;
    [background addSubview:l3];
    last_imported_label_ = l3;

    SetLabelText();

    return background;
  }

  void StartActivity() {
    if (refresh_.get()) {
      refresh_->StartActivity();
    }
    fetching_contacts_ = true;
  }

  void StopActivity() {
    CHECK(fetching_contacts_);
    if (refresh_.get()) {
      refresh_->StopActivity();
    }
    fetching_contacts_ = false;
  }

  void ShowSuccess() {
    if (refresh_.get()) {
      refresh_->SetState(ContactsRefreshButton::SUCCESS);
    }
    SetLabelText();
    ResetButton(kSuccessIconDuration);
  }

  void ShowError() {
    if (refresh_.get()) {
      refresh_->SetState(ContactsRefreshButton::ERROR);
    }
    ResetButton(kErrorIconDuration);
  }

  virtual void FetchContacts() = 0;

  virtual void Refresh() = 0;

 protected:
  void UpdateView() {
    if (!view_) {
      view_ = [UIView new];
    }

    UIView* old_row = row_;
    if (old_row && old_row.tag == IsLinked()) {
      // A row already exists with the desired service validity.
      // Update the text in place.
      SetLabelText();
      return;
    }

    if (IsLinked()) {
      refresh_.reset(new ContactsRefreshButton(^{ Refresh(); }));
      row_ = NewRefreshRow(width_);

      if (fetching_contacts_) {
        // The service is already fetching contacts.
        StartActivity();
      } else if (fetch_contacts_) {
        // The service has transitioned from invalid to valid.
        FetchContacts();
        fetch_contacts_ = false;
      }
    } else {
      refresh_.reset(NULL);
      row_ = NewFetchRow(width_);
    }
    row_.tag = IsLinked();
    [view_ addSubview:row_];
    view_.frameSize = row_.frameSize;

    // Animate the new row into position if an old row existed.
    if (old_row) {
      row_.frameRight = 0;
      [UIView animateWithDuration:0.3
                       animations:^{
          row_.frameLeft = old_row.frameLeft;
          old_row.frameLeft = width_;
        }
                       completion:^(BOOL finished) {
          [old_row removeFromSuperview];
        }];
    }
  }

  void FetchContactsComplete() {
    StopActivity();
    state_->contact_manager()->SetLastImportTimeForSource(contact_source_prefix_, WallTime_Now());
    CountContacts();
    UpdateView();
    ShowSuccess();
  }

 private:
  void ResetButton(float delay) {
    if (!async_.get()) {
      async_.reset(new AsyncState);
    }
    const int reset_seq_no = ++reset_seq_no_;
    async_->dispatch_after_main(delay, ^{
        if (reset_seq_no != reset_seq_no_) {
          // If the button changed state before the timer fired, ignore the old timer event.
          return;
        }
        if (refresh_.get()) {
          refresh_->SetState(ContactsRefreshButton::REFRESH);
          SetLabelText();
        }
      });
  }

  void SetLabelText() {
    if (header_label_) {
      header_label_.text = GetHeaderText();
    }
    if (detail_label_) {
      const int delta = contact_count_ - previous_contact_count_;
      const int vf_delta = vf_contact_count_ - previous_vf_contact_count_;
      if (refresh_.get() &&
          refresh_->state() == ContactsRefreshButton::SUCCESS &&
          delta > 0 &&
          delta < contact_count_) {
        // Show the number of new contacts if we recently imported (and that import added new contacts,
        // and this wasn't the first import when everything counts as new)
        detail_label_.text = GetDetailText(delta, vf_delta, true);
      } else {
        detail_label_.text = GetDetailText(contact_count_, vf_contact_count_, false);
      }
    }
    if (last_imported_label_) {
      last_imported_label_.text = GetLastImportedText();
    }
  }

 protected:
  const string& contact_source_prefix() const { return contact_source_prefix_; }

  UIAppState* const state_;
  UINavigationController* navigation_controller_;
  bool fetch_contacts_;

 private:
  const string contact_source_prefix_;
  bool contacts_counted_;
  int contact_count_;
  int vf_contact_count_;
  int previous_contact_count_;
  int previous_vf_contact_count_;
  UIView* view_;
  int width_;
  UIView* row_;
  ScopedPtr<ContactsRefreshButton> refresh_;
  UIActivityIndicatorView* activity_;
  bool fetching_contacts_;
  ScopedPtr<AsyncState> async_;
  int reset_seq_no_;
  UILabel* header_label_;
  UILabel* detail_label_;
  UILabel* last_imported_label_;
};

}  // namespace

class AuthServiceContactsSection : public ContactsSection {
 public:
  AuthServiceContactsSection(UIAppState* state, AuthService* service, const string& contact_source_prefix)
      : ContactsSection(state, contact_source_prefix),
        service_(service),
        session_changed_id_(-1) {
  }

  virtual ~AuthServiceContactsSection() {
    if (session_changed_id_ >= 0) {
      service_.sessionChanged->Remove(session_changed_id_);
    }
  }

  UIView* BuildView(float width) {
    if (session_changed_id_ < 0 && service_) {
      session_changed_id_ = service_.sessionChanged->Add(^{
          UpdateView();
        });
    }
    return ContactsSection::BuildView(width);
  }

  virtual NSString* GetHeaderText() {
    return service_.primaryId;
  }

  virtual bool IsLinked() {
    return service_.valid;
  }

  void Fetch() {
    state_->analytics()->ContactsFetch(service_name());
    fetch_contacts_ = true;
    [service_ login:navigation_controller_];
  }

  void Refresh() {
    state_->analytics()->ContactsRefresh(service_name());
    FetchContacts();
  }

  void Remove() {
    state_->analytics()->ContactsRemove(service_name());
    [service_ logout];
  }

 protected:
  string service_name() const { return ToString(service_.serviceName); };

  AuthService* const service_;

 private:
  int session_changed_id_;
};

class GoogleSection : public AuthServiceContactsSection {
 public:
  GoogleSection(UIAppState* state)
      : AuthServiceContactsSection(state, state->google(), ContactManager::kContactSourceGmail) {
  }

 private:
  virtual UIImage* NewFetchIcon() {
    return UIStyle::kIconGmail;
  }

  virtual UIButton* NewFetchButton() {
    return NewContactsFetchButton(
        @"Import Gmail Contacts",
        ^{ Fetch(); });
  }

  virtual NSString* GetDetailText(int count, int vf_count, bool is_new) {
    return Format("%d %scontact%s",
                  count,
                  is_new ? "new " : "",
                  Pluralize(count));
  }

  void FetchContacts() {
    if (state_->contact_manager()->FetchGoogleContacts(
            ToString(service_.refreshToken), ^{
              state_->analytics()->ContactsFetchComplete(service_name());
              FetchContactsComplete();
            })) {
      StartActivity();
    } else {
      state_->analytics()->ContactsFetchError(service_name(), "fetch_failed");
      state_->ShowNetworkDownAlert();
      ShowError();
    }
  }
};

class FacebookSection : public AuthServiceContactsSection {
 public:
  FacebookSection(UIAppState* state)
      : AuthServiceContactsSection(state, state->facebook(), ContactManager::kContactSourceFacebook) {
  }

 private:
  virtual UIImage* NewFetchIcon() {
    return UIStyle::kIconFacebook;
  }

  virtual UIButton* NewFetchButton() {
    return NewContactsFetchButton(
        @"Import Facebook Friends",
        ^{ Fetch(); });
  }

  virtual NSString* GetDetailText(int count, int vf_count, bool is_new) {
    return Format("%d %sfriend%s",
                  count,
                  is_new ? "new " : "",
                  Pluralize(count));
  }

  void FetchContacts() {
    if (state_->contact_manager()->FetchFacebookContacts(
            ToString(service_.accessToken), ^{
              state_->analytics()->ContactsFetchComplete(service_name());
              FetchContactsComplete();
            })) {
      StartActivity();
    } else {
      state_->analytics()->ContactsFetchError(service_name(), "fetch_failed");
      state_->ShowNetworkDownAlert();
      ShowError();
    }
  }
};

class AddressBookSection : public ContactsSection {
 public:
  AddressBookSection(UIAppState* state)
      : ContactsSection(state, ContactManager::kContactSourceIOSAddressBook),
        is_linked_(GetLastImportTime() > 0) {
  }

 private:
  virtual UIImage* NewFetchIcon() {
    return UIStyle::kIconAddressBook;
  }

  virtual UIButton* NewFetchButton() {
    return NewContactsFetchButton(
        @"Import Address Book",
        ^{ Fetch(); });
  }

  virtual NSString* GetHeaderText() {
    return @"Address Book";
  }

  virtual NSString* GetDetailText(int count, int vf_count, bool is_new) {
    return Format("%d %scontact%s",
                  count,
                  is_new ? "new " : "",
                  Pluralize(count));
  }

  virtual bool IsLinked() {
    return is_linked_;
  }

  bool HasPhoneLinked() {
    ContactMetadata m;
    state_->contact_manager()->LookupUser(state_->user_id(), &m);
    if (ContactManager::GetPhoneIdentity(m, NULL)) {
      // A fully linked and confirmed identity.
      return true;
    }

    LoginEntryDetails details;
    GetLoginEntryDetails(state_, kAddIdentityKey, &details);
    if (details.identity_type() == LoginEntryDetails::PHONE &&
        details.merging()) {
      // A phone number has been confirmed and the merge is in-progress.  No need to wait for the
      // merge to complete before letting the import proceed.
      return true;
    }
    return false;
  }

  void FetchContacts() {
    StartActivity();
    if (HasPhoneLinked()) {
      ImportContacts();
    } else {
      state_->analytics()->AddContactsLinkPhoneStart();
      CppDelegate* cpp_delegate = new CppDelegate;
      cpp_delegate->Add(
          @protocol(UIAlertViewDelegate), @selector(alertView:clickedButtonAtIndex:),
          ^(UIAlertView* alert, NSInteger index) {
            if (index == 1) {
              ShowLinkPrompt();
            } else {
              ImportContacts();
            }
            alert.delegate = NULL;
            delete cpp_delegate;
          });

      [[[UIAlertView alloc]
           initWithTitle:@"Add Mobile Number"
                 message:@"You're looking for your contacts; link your number to help them find you, too."
                delegate:cpp_delegate->delegate()
           cancelButtonTitle:@"Cancel"
           otherButtonTitles:@"OK", NULL] show];
    }
  }

  void ShowLinkPrompt() {
    [LoginSignupDashboardCard
        prepareForLinkMobileIdentity:state_
                              forKey:kAddIdentityKey];
    UIView* container = [[DashboardCardContainer alloc]
                            initWithState:state_
                               withParent:navigation_controller_.view
                                  withKey:kAddIdentityKey
                             withCallback:^(DashboardCardContainer* container) {
        [container removeFromSuperview];
        if (HasPhoneLinked()) {
          state_->analytics()->AddContactsLinkPhoneComplete();
        }
        ImportContacts();
      }];
    [navigation_controller_.view addSubview:container];
  }

  void ImportContacts() {
    state_->address_book_manager()->ImportContacts(^(bool success) {
        if (success) {
          state_->analytics()->ContactsFetchComplete(service_name());
          FetchContactsComplete();
        } else {
          [[[UIAlertView alloc]
            initWithTitle:@"Permission denied"
            message:@"To import your address book you must grant access to your contacts. "
            "Enable access via: Settings > Privacy > Contacts > Viewfinder"
            delegate:NULL
            cancelButtonTitle:@"OK"
            otherButtonTitles:NULL]
           show];
          StopActivity();
          state_->analytics()->ContactsFetchError(service_name(), "import_failed");
          ShowError();
        }
      });
  }

  void Fetch() {
    state_->analytics()->ContactsFetch(service_name());
    is_linked_ = true;
    fetch_contacts_ = true;
    UpdateView();
  }

  void Refresh() {
    state_->analytics()->ContactsRefresh(service_name());
    FetchContacts();
  }

  void Remove() {
    state_->analytics()->ContactsRemove(service_name());
    // TODO(ben)
  }

 private:
  string service_name() const { return "AddressBook"; };

  bool is_linked_;
};

@implementation AddContactsController

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;
    self.title = @"Add Contacts";

    address_book_.reset(new AddressBookSection(state_));
    google_.reset(new GoogleSection(state_));
    facebook_.reset(new FacebookSection(state_));
  }
  return self;
}

- (void)loadView {
  [super loadView];
  scroll_view_ = [UIScrollView new];
  scroll_view_.alwaysBounceVertical = YES;
  scroll_view_.autoresizesSubviews = YES;
  scroll_view_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
  scroll_view_.backgroundColor = UIStyle::kSettingsBackgroundColor;
  self.view = scroll_view_;

  // add_footer_ = [UIView new];
  // add_footer_.alpha = 0;
  // add_footer_.frameOrigin = CGPointMake(-10000, 0);
  // [scroll_view_ addSubview:add_footer_];

  // attr_str = [NSMutableAttributedString new];
  // AppendAttrString(attr_str,
  //                  "Insert helpful text explaining how to add a contact "
  //                  "by email or mobile.",
  //                  UIStyle::kSettingsFooterFont,
  //                  UIStyle::kSettingsTextFooterColor);
  // TextLayer* add_footer_text = [TextLayer new];
  // add_footer_text.maxWidth = 270;
  // add_footer_text.attrStr = AttrCenterAlignment(attr_str);
  // add_footer_text.frameWidth = 270;
  // add_footer_text.frameOrigin = CGPointMake(0, 0);
  // [add_footer_.layer addSublayer:add_footer_text];
  // add_footer_.frameHeight = add_footer_text.frameHeight;

  import_header_ = [UIView new];
  import_header_.frameOrigin = CGPointMake(-10000, 0);
  [scroll_view_ addSubview:import_header_];

  NSMutableAttributedString* attr_str = [NSMutableAttributedString new];
  AppendAttrString(attr_str,
                   "Import Third Party Contacts",
                   UIStyle::kSettingsHeaderFont,
                   UIStyle::kSettingsTextHeaderColor);
  TextLayer* import_header_text = [TextLayer new];
  import_header_text.maxWidth = 270;
  import_header_text.attrStr = attr_str;
  import_header_text.frameWidth = 270;
  import_header_text.frameOrigin = CGPointMake(0, 0);
  [import_header_.layer addSublayer:import_header_text];
  import_header_.frameHeight = import_header_text.frameHeight;

  AuthService* kServices[] = { state_->google(), state_->facebook() };
  for (int i = 0; i < ARRAYSIZE(kServices); ++i) {
    [kServices[i] loadIfNecessary];
  }
}

- (WallTime)lastImportTime {
  WallTime lit = address_book_->GetLastImportTime();
  lit = std::max<WallTime>(lit, google_->GetLastImportTime());
  lit = std::max<WallTime>(lit, facebook_->GetLastImportTime());
  return lit;
}

- (UINavigationItem*)navigationItem {
  if (!navigation_item_) {
    [self updateNavigation];
  }
  return navigation_item_;
}

- (void)updateNavigation {
  navigation_item_ = [super navigationItem];
  navigation_item_.leftBarButtonItem = UIStyle::NewToolbarBack(
      self, @selector(toolbarBack));
  UIStyle::InitLeftBarButton(navigation_item_.leftBarButtonItem);
  if (!navigation_item_.titleView) {
    navigation_item_.titleView = UIStyle::NewContactsTitleView(self.title);
  }
}

- (void)clearState {
  address_book_->ClearView();
  facebook_->ClearView();
  [login_entry_ removeFromSuperview];
  login_entry_ = NULL;
}

- (void)rebuildState {
  if (!state_->is_registered()) {
    state_->ShowNotRegisteredAlert();
    return;
  }

  const ScopedDisableCAActions disable_ca_actions;
  [self clearState];

  vector<UIView*> sections;
  const float width = self.view.frameWidth;

  address_book_->set_navigation_controller(self.navigationController);
  sections.push_back(address_book_->BuildView(width));

  google_->set_navigation_controller(self.navigationController);
  sections.push_back(google_->BuildView(width));

  float y = kRowBorder;

  if (state_->contact_manager()->count() > 1) {
    facebook_->set_navigation_controller(self.navigationController);
    sections.push_back(facebook_->BuildView(width));

    add_footer_.frameOrigin = CGPointMake(15, y);
    import_header_.frameOrigin = CGPointMake(15, y);
    y = import_header_.frameBottom + kRowBorder;
  }

  for (int i = 0; i < sections.size(); ++i) {
    UIView* s = sections[i];
    s.frameTop = y;
    y = s.frameBottom + kRowBorder;
    [self.view addSubview:s];
  }

  scroll_view_.contentSize = CGSizeMake(width, y);
}

- (void)viewWillAppear:(BOOL)animated {
  // LOG("contacts: view will appear");
  [super viewWillAppear:animated];
  state_->analytics()->AddContactsPage();
  [self rebuildState];
}

- (void)viewDidDisappear:(BOOL)animated {
  // LOG("contacts: view did disappear");
  [super viewDidDisappear:animated];
  [self clearState];
}

- (void)toolbarBack {
  if (self.navigationController.viewControllers.count == 1) {
    [state_->root_view_controller() dismissViewController:ControllerState()];
  } else {
    [self.navigationController popViewControllerAnimated:YES];
  }
}

@end  // AddContactsController

// local variables:
// mode: c++
// end:
