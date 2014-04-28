// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "Analytics.h"
#import "Appearance.h"
#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "ContactManager.h"
#import "DashboardNotice.h"
#import "FacebookService.h"
#import "FindNearbyUsersController.h"
#import "GoogleService.h"
#import "LayoutUtils.h"
#import "Logging.h"
#import "NetworkManager.h"
#import "PhotoStorage.h"
#import "RootViewController.h"
#import "SettingsViewController.h"
#import "STLUtils.h"
#import "SubscriptionManagerIOS.h"
#import "SummaryLayoutController.h"
#import "TextLayer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"
#import "ValueUtils.h"

@interface CallbackTarget : NSObject {
 @private
  CallbackSet1<id> callbacks_;
}

@property (readonly) CallbackSet1<id>* callbacks;

- (void)dispatch:(id)sender;

@end  // CallbackTarget

@implementation CallbackTarget

- (void)dispatch:(id)sender {
  // Reference self while the callbacks are being run to prevent self from
  // being deleted.
  __block CallbackTarget* self_ref = self;
  void (^ref_block)() = ^{ self_ref = NULL; };
  callbacks_.Run(sender);
  ref_block();
}

- (CallbackSet1<id>*)callbacks {
  return &callbacks_;
}

@end  // CallbackTarget

@implementation SettingsDisclosure

- (id)initWithColor:(UIColor*)normal
        highlighted:(UIColor*)highlighted {
  if (self = [super initWithFrame:CGRectMake(0, 0, 11, 15)]) {
    self.backgroundColor = [UIColor clearColor];
    normal_ = normal;
    highlighted_ = highlighted;
  }
  return self;
}

- (void)setHighlighted:(BOOL)highlighted {
  [super setHighlighted:highlighted];
  [self setNeedsDisplay];
}

- (void)drawRect:(CGRect)rect {
  const float x = CGRectGetMaxX(self.bounds) - 3.0;
  const float y = CGRectGetMidY(self.bounds);
  const float r = 4.5;
  CGContextRef context = UIGraphicsGetCurrentContext();
  CGContextMoveToPoint(context, x - r, y - r);
  CGContextAddLineToPoint(context, x, y);
  CGContextAddLineToPoint(context, x - r, y + r);
  CGContextSetLineCap(context, kCGLineCapSquare);
  CGContextSetLineJoin(context, kCGLineJoinMiter);
  CGContextSetLineWidth(context, 3);

  if (self.highlighted) {
    [highlighted_ setStroke];
  } else {
    [normal_ setStroke];
  }

  CGContextStrokePath(context);
}

@end  // SettingsDisclosure

namespace {

const bool kCloudStorageEnabled = false;
const int kTermsOfServiceIndex = 0;
const int kPrivacyPolicyIndex = 1;
const int kFAQIndex = 0;
const int kSendFeedbackIndex = 1;
const int kActionSheetUnlinkTag = 1;
const int kLoadingProgressTag = 2000;
const float kSettingsSectionSpacing = 10;

const int64_t kKilobyte = 1024LL;
const int64_t kMegabyte = 1024 * kKilobyte;
const int64_t kGigabyte = 1024 * kMegabyte;
const int64_t kTerabyte = 1024 * kGigabyte;

const int64_t kFreeTierSpace = 1 * kGigabyte;

LazyStaticImage kTableCellBackgroundBottom(
    @"table-cell-background-bottom.png", UIEdgeInsetsMake(1, 3, 3, 3));
LazyStaticImage kTableCellBackgroundMiddle(
    @"table-cell-background-middle.png", UIEdgeInsetsMake(1, 0, 0, 0));
LazyStaticImage kTableCellBackgroundSingle(
    @"table-cell-background-single.png", UIEdgeInsetsMake(3, 3, 3, 3));
LazyStaticImage kTableCellBackgroundTop(
    @"table-cell-background-top.png", UIEdgeInsetsMake(3, 3, 0, 3));
LazyStaticImage kTableCellSelectedBackgroundBottom(
    @"table-cell-selected-background-bottom.png", UIEdgeInsetsMake(1, 3, 3, 3));
LazyStaticImage kTableCellSelectedBackgroundMiddle(
    @"table-cell-selected-background-middle.png", UIEdgeInsetsMake(1, 3, 0, 3));
LazyStaticImage kTableCellSelectedBackgroundSingle(
    @"table-cell-selected-background-single.png", UIEdgeInsetsMake(3, 3, 3, 3));
LazyStaticImage kTableCellSelectedBackgroundTop(
    @"table-cell-selected-background-top.png", UIEdgeInsetsMake(3, 3, 0, 3));

enum DevSettings {
  kFakeLogoutIndex,
  kFakeMaintenanceIndex,
  kFakeNotAuthorizedIndex,
  kFakeZeroState,
  kFake401,
  kResetNotices,
  kBenchmarkDownload,
  kResetAllContacts,
  kCheckFalseIndex,
  kFindNearbyUsers,
  kNumDevSettings,
};

class StorageSettingsSection : public SettingsSection {
 public:
  StorageSettingsSection(UIAppState* state)
      : SettingsSection(),
        state_(state) {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    static const int kLocalBytesLimitTag = 1;

    NSString* title = NULL;
    NSString* limit = NULL;
    NSString* detail = NULL;

    switch (index) {
      case 0:
        title = @"Local Storage";
        limit = LocalStorageLimit();
        detail = LocalStorageDetail();
        break;
      case 1:
        title = @"Cloud Storage";
        limit = CloudStorageLimit();
        detail = CloudStorageDetail();
        break;
    }

    cell.accessoryView =
        [[SettingsDisclosure alloc]
          initWithColor:UIStyle::kSettingsTextColor
            highlighted:UIStyle::kSettingsTextSelectedColor];
    cell.contentView.autoresizesSubviews = YES;
    cell.textLabel.text = title;
    cell.textLabel.textAlignment = NSTextAlignmentLeft;
    cell.detailTextLabel.text = detail;

    UILabel* label = (UILabel*)[cell.contentView viewWithTag:kLocalBytesLimitTag];
    if (!label) {
      label = [UILabel new];
      label.autoresizingMask =
          UIViewAutoresizingFlexibleLeftMargin |
          UIViewAutoresizingFlexibleBottomMargin;
      label.backgroundColor = [UIColor clearColor];
      label.font = UIStyle::kSettingsCellUIFont;
      label.highlightedTextColor = UIStyle::kSettingsTextSelectedColor;
      label.tag = kLocalBytesLimitTag;
      label.textAlignment = NSTextAlignmentRight;
      label.textColor = UIStyle::kSettingsTextColor;
      [cell.contentView addSubview:label];
    }
    label.text = limit;
    if (label.text) {
      [label sizeToFit];
      CGRect f = label.frame;
      // TODO(pmattis): Ugh, the constants 10 and 14 were experimentally
      // determined to match the UITableViewCellStyleValue1 positioning of the
      // detailTextLabel. We can't use that style because we want the
      // detailTextLabel to appear as a subtitle.
      f.origin.x = cell.contentView.frame.size.width - f.size.width - 10;
      f.origin.y = 14;
      label.frame = f;
    }
  }

  virtual NSString* cell_identifier() const {
    return @"SettingsViewControllerLocalStorageStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleSubtitle;
  }

  virtual NSAttributedString* header() const {
    return NewHeaderString("Storage");
  }

  virtual NSAttributedString* footer() const {
    return NewFooterString(
        state_->is_registered() ?
        "The maximum amount of space for\nlocal and cloud photo storage." :
        "The maximum amount of space\nfor local photo storage.\n");
  }

  int size() const { return 1 + state_->is_registered(); }

 private:
  int64_t LocalStorageLimitBytes() const {
    const vector<PhotoStorage::Setting>& settings =
        state_->photo_storage()->settings();
    const int sindex =
        state_->photo_storage()->setting_index(
            state_->photo_storage()->local_bytes_limit());
    return settings[sindex].value;
  }

  NSString* LocalStorageLimit() const {
    const vector<PhotoStorage::Setting>& settings =
        state_->photo_storage()->settings();
    const int sindex =
        state_->photo_storage()->setting_index(
            state_->photo_storage()->local_bytes_limit());
    return NewNSString(settings[sindex].title);
  }

  NSString* LocalStorageDetail() const {
    const int64_t local_bytes =
        std::max<int64_t>(0, state_->photo_storage()->local_bytes());
    return Format("%s (%.1f%%) Used", SIUnitFormat(local_bytes),
                  (100.0 * local_bytes) / LocalStorageLimitBytes());
  }

  int64_t CloudStorageLimitBytes() const {
    SubscriptionManagerIOS* sub = state_->subscription_manager_ios();
    const vector<Product*>& subscriptions = sub->subscriptions();
    int64_t bytes = 0;
    for (int i = 0; i < subscriptions.size(); ++i) {
      bytes += subscriptions[i]->space_bytes();
    }
    return bytes;
  }

  NSString* CloudStorageLimit() const {
    return Format("%.0f GB", CloudStorageLimitBytes() / double(kGigabyte));
  }

  NSString* CloudStorageDetail() const {
    // Figure out a number from the usage returned by state_->photo_storage()->remote_usage()
    return @"";
    // TODO(pmattis): Fill in the number of bytes of cloud storage used.
    // int64_t cloud_bytes = 0;
    // if (cloud_bytes == 0) {
    //   return @"Empty";
    // }
    // return Format("%s (%.01f%%) Used", SIUnitFormat(cloud_bytes),
    //               (100.0 * cloud_bytes) / CloudStorageLimitBytes());
  }

  static string SIUnitFormat(const int64_t v) {
    if (v < kMegabyte) {
      return Format("%.1f KB", double(v) / kKilobyte);
    }
    if (v < kGigabyte) {
      return Format("%.1f MB", double(v) / kMegabyte);
    }
    if (v < kTerabyte) {
      return Format("%.1f GB", double(v) / kGigabyte);
    }
    return Format("%.1f TB", double(v) / kTerabyte);
  }

 private:
  UIAppState* const state_;
};

class CloudStorageSettingsSection : public SettingsSection {
 public:
  CloudStorageSettingsSection(UIAppState* state)
      : SettingsSection(),
        state_(state) {
  }

  void ToggleCell(int index) {
    if (toggle_.size() <= index) {
      toggle_.resize(index + 1, false);
    }
    toggle_[index] = !toggle_[index];
  }

  void SetToggleCell(int index, bool value) {
    if (toggle_.size() <= index) {
      toggle_.resize(index + 1, false);
    }
    toggle_[index] = value;
  }

  void ClearToggle() {
    toggle_.clear();
  }

  virtual NSString* cell_identifier() const {
    return @"SettingsViewControllerCloudStorageStyle";
  }
  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleSubtitle;
  }

  virtual NSString* cell_detail(int index) const = 0;
  virtual int64_t cell_space(int index) const = 0;
  virtual double cell_price(int index) const = 0;
  virtual NSString* cell_price_str(int index) const = 0;
  virtual bool cell_checked(int index) const = 0;
  virtual bool cell_pending(int index) const = 0;

 protected:
  void InitCloudStorageCell(UITableViewCell* cell, int index, bool selectable) const {
    static const int kCloudStoragePriceTag = 1;

    cell.accessoryView = cell_accessory(index);
    cell.selectionStyle = selectable ? UITableViewCellSelectionStyleBlue :
        UITableViewCellSelectionStyleNone;
    cell.textLabel.text = Format("%.0f GB", double(cell_space(index)) / kGigabyte);
    cell.detailTextLabel.text = cell_detail(index);

    if (!selectable) {
      cell.detailTextLabel.highlightedTextColor = cell.detailTextLabel.textColor;
      cell.textLabel.highlightedTextColor = cell.textLabel.textColor;
    }

    UILabel* label = (UILabel*)[cell.contentView viewWithTag:kCloudStoragePriceTag];
    if (!label) {
      label = [UILabel new];
      label.autoresizingMask =
          UIViewAutoresizingFlexibleLeftMargin |
          UIViewAutoresizingFlexibleBottomMargin;
      label.backgroundColor = [UIColor clearColor];
      label.font = UIStyle::kSettingsCellUIFont;
      if (selectable) {
        label.highlightedTextColor = UIStyle::kSettingsTextSelectedColor;
      } else {
        label.highlightedTextColor = UIStyle::kSettingsTextColor;
      }
      label.tag = kCloudStoragePriceTag;
      label.textAlignment = NSTextAlignmentRight;
      label.textColor = UIStyle::kSettingsTextColor;
      [cell.contentView addSubview:label];
    }
    label.text = cell_price_str(index);
    [label sizeToFit];
    CGRect f = label.frame;
    // TODO(pmattis): Ugh, the constants 10 and 14 were experimentally
    // determined to match the UITableViewCellStyleValue1 positioning of the
    // detailTextLabel. We can't use that style because we want the
    // detailTextLabel to appear as a subtitle.
    f.origin.x = cell.contentView.frame.size.width - f.size.width - 10;
    f.origin.y = 14;
    label.frame = f;
  }


  bool cell_toggled(int index) const {
    if (index < toggle_.size()) {
      return toggle_[index];
    }
    return false;
  }

 private:
  UIView* cell_accessory(int index) const {
    UIImage* checkmark = UIStyle::kCheckmark;
    if (cell_checked(index)) {
      return [[UIImageView alloc] initWithImage:checkmark];
    } else if (cell_pending(index)) {
      UIActivityIndicatorView* activity_view =
          [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleGray];
      [activity_view startAnimating];
      activity_view.frameSize = checkmark.size;
      return activity_view;
    }
    UIView* v = [UIView new];
    v.frameSize = checkmark.size;
    return v;
  }

 protected:
  UIAppState* const state_;
  vector<bool> toggle_;
};

class CurrentCloudStorageSettingsSection : public CloudStorageSettingsSection {
 public:
  CurrentCloudStorageSettingsSection(UIAppState* state)
      : CloudStorageSettingsSection(state) {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    InitCloudStorageCell(cell, index, false);
  }
  virtual NSString* cell_detail(int index) const {
    const Product* p = GetSubscription(index);
    return NewNSString(p->title());
  }
  virtual int64_t cell_space(int index) const {
    const Product* p = GetSubscription(index);
    return p->space_bytes();
  }
  virtual double cell_price(int index) const {
    const Product* p = GetSubscription(index);
    return p->price();
  }
  virtual NSString* cell_price_str(int index) const {
    const Product* p = GetSubscription(index);
    return NewNSString(p->price_str());
  }
  virtual bool cell_checked(int index) const {
    return !cell_toggled(index);
  }
  virtual bool cell_pending(int index) const {
    return false;
  }

  virtual NSAttributedString* header() const {
    return NewHeaderString(Format("Current Plan%s", Pluralize(size())));
  }
  virtual int size() const {
    SubscriptionManagerIOS* sub = state_->subscription_manager_ios();
    return sub->subscriptions().size();
  }

 private:
  const Product* GetSubscription(int index) const {
    SubscriptionManagerIOS* sub = state_->subscription_manager_ios();
    const vector<Product*>& subscriptions = sub->subscriptions();
    if (index >= subscriptions.size()) {
      return NULL;
    }
    return subscriptions[index];
  }
};

class AvailableCloudStorageSettingsSection : public CloudStorageSettingsSection {
 public:
  AvailableCloudStorageSettingsSection(UIAppState* state)
      : CloudStorageSettingsSection(state) {
  }

  Product* GetSelectedProduct() {
    for (int i = 0, n = size(); i < n; ++i) {
      if (cell_checked(i)) {
        return GetUnsubscribedProduct(i);
      }
    }
    return NULL;
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    InitCloudStorageCell(cell, index, true);
  }
  virtual NSString* cell_detail(int index) const {
    Product* p = GetUnsubscribedProduct(index);
    return NewNSString(p->title());
  }
  virtual int64_t cell_space(int index) const {
    Product* p = GetUnsubscribedProduct(index);
    return p->space_bytes();
  }
  virtual double cell_price(int index) const {
    Product* p = GetUnsubscribedProduct(index);
    return p->price();
  }
  virtual NSString* cell_price_str(int index) const {
    Product* p = GetUnsubscribedProduct(index);
    return NewNSString(p->price_str());
  }
  virtual bool cell_checked(int index) const {
    return cell_toggled(index);
  }
  virtual bool cell_pending(int index) const {
    Product* p = GetUnsubscribedProduct(index);
    return state_->subscription_manager_ios()->HasPendingSubscription(p->product_type());
  }

  virtual NSAttributedString* header() const {
    return NewHeaderString(Format("Available Plan%s", Pluralize(size())));
  }
  virtual int size() const {
    SubscriptionManagerIOS* sub = state_->subscription_manager_ios();
    const vector<Product*>& products = sub->products();
    int count = 0;
    for (int i = 0; i < products.size(); ++i) {
      if (!sub->HasSubscription(products[i]->product_type())) {
        ++count;
      }
    }
    return count;
  }

 private:
  Product* GetUnsubscribedProduct(int index) const {
    SubscriptionManagerIOS* sub = state_->subscription_manager_ios();
    const vector<Product*>& products = sub->products();
    for (int i = 0; i < products.size(); ++i) {
      Product* p = products[i];
      if (sub->HasSubscription(p->product_type())) {
        continue;
      }
      if (index == 0) {
        return p;
      }
      --index;
    }
    return NULL;
  }
};

class TotalCloudStorageSettingsSection : public CloudStorageSettingsSection {
 public:
  TotalCloudStorageSettingsSection(UIAppState* state)
      : CloudStorageSettingsSection(state),
        space_(0),
        price_(0) {
  }

  void SetTotal(int64_t space, double price) {
    space_ = space;
    price_ = price;
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    InitCloudStorageCell(cell, index, false);
  }
  virtual NSString* cell_detail(int index) const {
    return NULL;
  }
  virtual int64_t cell_space(int index) const {
    return space_;
  }
  virtual double cell_price(int index) const {
    return price_;
  }
  virtual NSString* cell_price_str(int index) const {
    SubscriptionManagerIOS* const sub = state_->subscription_manager_ios();
    return NewNSString(Product::FormatPrice(cell_price(index), sub->price_locale()));
  }
  virtual bool cell_checked(int index) const {
    return false;
  }
  virtual bool cell_pending(int index) const {
    return false;
  }

  virtual NSAttributedString* header() const {
    return NewHeaderString("Total");
  }
  virtual int size() const { return 1; }

 private:
  int64_t space_;
  double price_;
};

class SwitchSettingsSection : public SettingsSection {
  typedef std::unordered_map<int, CallbackTarget*> TargetMap;

 public:
  SwitchSettingsSection()
      : SettingsSection() {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    UISwitch* s = [UISwitch new];
    s.on = value_get(index);
    s.onTintColor = UIStyle::kSettingsSwitchOnColor;
    if (kIOSVersion >= "6.0") {
      s.tintColor = UIStyle::kSettingsSwitchOffColor;
    }
    CallbackTarget* target = [CallbackTarget new];
    target.callbacks->Add(^(id sender) {
        value_set(index, s.on);
      });
    targets_[index] = target;
    [s addTarget:target
          action:@selector(dispatch:)
       forControlEvents:UIControlEventValueChanged];
    cell.accessoryView = s;

    cell.textLabel.text = cell_title(index);
    cell.textLabel.textAlignment = NSTextAlignmentLeft;
    cell.textLabel.textColor = UIStyle::kSettingsTextColor;
    cell.detailTextLabel.text = NULL;
  }

  virtual bool value_get(int index) const = 0;
  virtual void value_set(int index, bool v) const = 0;
  virtual NSString* cell_title(int index) const = 0;

  virtual NSString* cell_identifier() const {
    return @"SettingsViewControllerSwitchStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleSubtitle;
  }

  int size() const { return 1; }

 private:
  mutable TargetMap targets_;
};

class StoreOriginalsSettingsSection : public SwitchSettingsSection {
 public:
  StoreOriginalsSettingsSection(UIAppState* state)
      : SwitchSettingsSection(),
        state_(state) {
  }

  virtual bool value_get(int index) const {
    switch (index) {
      case 0:
        return state_->cloud_storage();
      case 1:
        return state_->store_originals();
    }
    return false;
  }
  virtual void value_set(int index, bool v) const {
    switch (index) {
      case 0:
        state_->set_cloud_storage(v);
        break;
      case 1:
        state_->set_store_originals(v);
        break;
    }
    state_->settings_changed()->Run(false);
  }
  virtual NSString* cell_title(int index) const {
    switch (index) {
      case 0:
        return @"Cloud Storage";
      case 1:
        return @"Store Originals";
    }
    return NULL;
  }
  virtual NSAttributedString* header() const {
    return NewHeaderString("Storage");
  }
  // TODO(peter): Uncomment if the cloud storage stuff is re-enabled.
  // virtual NSAttributedString* footer() const {
  //   return NewFooterString(
  //       "Store original (full resolution) photos in the cloud. This "
  //       "consumes more cloud storage space but ensures your originals "
  //       "are never lost.\n");
  // }
  virtual int size() const {
    if (state_->cloud_storage()) {
      return 2;
    }
    return 1;
  }

 private:
  UIAppState* const state_;
};

class UnlinkSettingsSection : public SettingsSection {
 public:
  UnlinkSettingsSection()
      : SettingsSection() {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
    b.layer.cornerRadius = 7;
    b.layer.masksToBounds = YES;
    cell.textLabel.font = UIStyle::kSettingsCellUIFont;
    b.titleLabel.shadowOffset = CGSizeMake(0, -1);
    [b setTitle:@"Unlink iPhone from Viewfinder"
       forState:UIControlStateNormal];
    [b setTitleColor:[UIColor whiteColor]
            forState:UIControlStateNormal];
    [b setTitleShadowColor:[UIColor blackColor]
                  forState:UIControlStateNormal];
    [b setBackgroundImage:UIStyle::kDeleteNormalBackground
                 forState:UIControlStateNormal];
    [b setBackgroundImage:UIStyle::kDeleteHighlightedBackground
                 forState:UIControlStateHighlighted];

    if (!target_) {
      target_ = [CallbackTarget new];
      target_.callbacks->Add(^(id sender) {
          Select(index);
        });
    }
    [b addTarget:target_ action:@selector(dispatch:)
       forControlEvents:UIControlEventTouchUpInside];

    AddButtonToTableCell(b, cell);
  }

  virtual void InitBackground(UITableViewCell* cell, int index) const {
    cell.backgroundColor = [UIColor clearColor];
    cell.backgroundView = cell.selectedBackgroundView =
        [[UIImageView alloc] initWithImage:UIStyle::kTransparent1x1];
  }

  virtual NSString* cell_identifier() const {
    return @"SettingsViewControllerUnlinkStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleDefault;
  }

  int size() const { return 1; }

 private:
  mutable CallbackTarget* target_;
};

class LegalSettingsSection : public SettingsSection {
 public:
  LegalSettingsSection(UIAppState* state)
      : SettingsSection() {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    cell.accessoryView =
        [[SettingsDisclosure alloc]
          initWithColor:UIStyle::kSettingsTextColor
            highlighted:UIStyle::kSettingsTextSelectedColor];
    cell.textLabel.text = TitleForIndex(index);
    cell.textLabel.textAlignment = NSTextAlignmentLeft;
  }

  virtual NSString* cell_identifier() const {
    return @"SettingsViewControllerLegalStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleDefault;
  }

  virtual NSAttributedString* header() const {
    return NewHeaderString("Legalese");
  }

  int size() const { return 2; }

 private:
  NSString* TitleForIndex(int index) const {
    switch (index) {
      case kTermsOfServiceIndex: return @"Terms of Service";
      case kPrivacyPolicyIndex:  return @"Privacy Policy";
      default:                   CHECK(false);
    }
    return NULL;
  }
};

class HelpSettingsSection : public SettingsSection {
 public:
  HelpSettingsSection(UIAppState* state)
      : SettingsSection() {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    cell.accessoryView =
        [[SettingsDisclosure alloc]
            initWithColor:UIStyle::kSettingsTextColor
              highlighted:UIStyle::kSettingsTextSelectedColor];
    cell.textLabel.text = TitleForIndex(index);
    cell.textLabel.textAlignment = NSTextAlignmentLeft;
  }

  virtual NSString* cell_identifier() const {
    return @"SettingsViewControllerHelpStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleDefault;
  }

  virtual NSAttributedString* header() const {
    return NewHeaderString("Help");
  }

  int size() const { return 2; }

 private:
  NSString* TitleForIndex(int index) const {
    switch (index) {
      case kFAQIndex:           return @"FAQ";
      case kSendFeedbackIndex:  return @"Send Feedback";
      default:                  CHECK(false);
    }
    return NULL;
  }
};

class DebugLogsSettingsSection : public SwitchSettingsSection {
 public:
  DebugLogsSettingsSection(UIAppState* state)
      : SwitchSettingsSection(),
        state_(state) {
  }

  virtual bool value_get(int index) const {
    return state_->upload_logs();
  }

  virtual void value_set(int index, bool v) const {
    state_->set_upload_logs(v);
  }

  virtual NSString* cell_title(int index) const {
    return @"Debug Logs";
  }

  int size() const { return 1; };

  virtual NSAttributedString* footer() const {
    return NewFooterString(Format("Version %s\n", AppVersion()));
  }

 private:
  UIAppState* state_;
};

class DevSettingsSection : public SettingsSection {
 public:
  DevSettingsSection()
      : SettingsSection() {
  }

  virtual void InitCell(UITableViewCell* cell, int index) const {
    cell.textLabel.text = TitleForIndex(index);
    cell.textLabel.textAlignment = NSTextAlignmentCenter;
  }

  virtual NSString* cell_identifier() const {
    return @"SettingsViewControllerDevStyle";
  }

  virtual UITableViewCellStyle cell_style() const {
    return UITableViewCellStyleDefault;
  }

  virtual NSAttributedString* header() const {
    return NewHeaderString("Development");
  }

  int size() const { return kNumDevSettings; }

 private:
  NSString* TitleForIndex(int index) const {
    switch (index) {
      case kFakeLogoutIndex:        return @"Fake Logout";
      case kFakeMaintenanceIndex:   return @"Fake Maintenance";
      case kFakeNotAuthorizedIndex: return @"Fake Not Authorized";
      case kFakeZeroState:          return @"Fake Zero State";
      case kFake401:                return @"Fake 401";
      case kResetNotices:           return @"Reset Notices";
      case kBenchmarkDownload:      return @"Run download benchmark";
      case kResetAllContacts:       return @"Reset all contacts";
      case kCheckFalseIndex:        return @"Crash";
      case kFindNearbyUsers:        return @"Find nearby users (iOS7)";
      default:                      CHECK(false);
    }
    return NULL;
  }
};

void SetHighlighted(UIView* v, BOOL highlighted) {
  if ([v isKindOfClass:[UILabel class]]) {
    UILabel* l = (UILabel*)v;
    l.highlighted = highlighted;
  } else if ([v isKindOfClass:[UIControl class]]) {
    UIControl* c = (UIControl*)v;
    c.highlighted = highlighted;
  }
  for (UIView* s in v.subviews) {
    SetHighlighted(s, highlighted);
  }
}

// Returns an NSIndexSet contain the indexes of all elements in vector a that
// are not in vector b.
template <typename T>
NSIndexSet* DeltaIndexes(const vector<T>& a, const vector<T>& b) {
  const std::unordered_set<T> set(b.begin(), b.end());
  NSMutableIndexSet* index_set = [NSMutableIndexSet new];
  for (int i = 0; i < a.size(); ++i) {
    if (!ContainsKey(set, a[i])) {
      [index_set addIndex:i];
    }
  }
  return index_set;
}

}  // namespace

// A small extension of UIImageView which overrides setFrame in order to add
// left and right borders to grouped table view backgrounds.
@interface SettingsSectionBackgroundView : UIImageView
@end  // SettingsSectionBackgroundView

@implementation SettingsSectionBackgroundView

- (void)setFrame:(CGRect)f {
  if (kSDKVersion >= "7" && kIOSVersion >= "7") {
    f = CGRectInset(f, 9, 0);
  }
  [super setFrame:f];
}

@end  // SettingsSectionBackgroundView

void AddButtonToTableCell(UIView* v, UITableViewCell* cell) {
  v.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  if (kSDKVersion >= "7" && kIOSVersion >= "7") {
    v.frame = CGRectInset(cell.contentView.bounds, 10, 0);
  } else {
    v.frame = cell.contentView.bounds;
  }
  cell.contentView.autoresizesSubviews = YES;
  [cell.contentView addSubview:v];
}

SettingsSection::SettingsSection()
  : cached_size_(0) {
}

void SettingsSection::SetCallback(int index, ScopedCallback callback) {
  if (callbacks_.size() <= index) {
    callbacks_.resize(index + 1, ScopedCallback());
  }
  callbacks_[index] = [callback copy];
}

bool SettingsSection::Select(int index) const {
  if (index < callbacks_.size()) {
    const ScopedCallback& c = callbacks_[index];
    if (c) {
      return c();
    }
  }
  return false;
}

void SettingsSection::InitBackground(UITableViewCell* cell, int index) const {
  UIImage* normal;
  UIImage* selected;
  if (index == 0 && index + 1 == cached_size()) {
    normal = kTableCellBackgroundSingle;
    selected = kTableCellSelectedBackgroundSingle;
  } else if (index == 0) {
    normal = kTableCellBackgroundTop;
    selected = kTableCellSelectedBackgroundTop;
  } else if (index + 1 == cached_size()) {
    normal = kTableCellBackgroundBottom;
    selected = kTableCellSelectedBackgroundBottom;
  } else {
    normal = kTableCellBackgroundMiddle;
    selected = kTableCellSelectedBackgroundMiddle;
  }

  cell.backgroundColor = [UIColor clearColor];
  cell.backgroundView =
      [[SettingsSectionBackgroundView alloc] initWithImage:normal];
  cell.selectedBackgroundView =
      [[SettingsSectionBackgroundView alloc] initWithImage:selected];
}

NSMutableAttributedString* SettingsSection::NewFooterString(const string& s) const {
  return AttrCenterAlignment(
      NewAttrString(
          s, UIStyle::kSettingsFooterFont,
          UIStyle::kSettingsTextFooterColor));
}

NSMutableAttributedString* SettingsSection::NewHeaderString(const string& s) const {
  return NewAttrString(
      s, UIStyle::kSettingsHeaderFont,
      UIStyle::kSettingsTextHeaderColor);
}

@interface WebViewController
    : UIViewController<UIWebViewDelegate> {
 @private
  string url_;
  UIActivityIndicatorView* activity_view_;
  UIWebView* web_view_;
}

@property (nonatomic) string url;

- (id)init;

@end  // UIViewController

@implementation WebViewController

- (id)init {
  if (self = [super init]) {
  }
  return self;
}

- (void)setUrl:(string)url {
  url_ = url;
  if (web_view_) {
    [self loadURL:url_];
  }
}

- (string)url {
  return url_;
}

- (void)loadView {
  self.view = [UIView new];
  self.view.autoresizesSubviews = YES;
  self.view.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  self.view.backgroundColor = [UIColor whiteColor];

  web_view_ = [UIWebView new];
  web_view_.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  web_view_.delegate = self;
  [web_view_ loadHTMLString:
               @"<html><body bgcolor=white></body></html>"
                    baseURL:NULL];
  [self.view addSubview:web_view_];

  activity_view_ = [UIActivityIndicatorView new];
  activity_view_.autoresizingMask =
      UIViewAutoresizingFlexibleLeftMargin |
      UIViewAutoresizingFlexibleRightMargin |
      UIViewAutoresizingFlexibleTopMargin |
      UIViewAutoresizingFlexibleBottomMargin;
  activity_view_.color = [UIColor blackColor];
  activity_view_.hidesWhenStopped = YES;
  activity_view_.frameSize = CGSizeMake(40, 40);
  [self.view addSubview:activity_view_];

  [self loadURL:url_];
}

- (UINavigationItem*)navigationItem {
  UINavigationItem* i = [super navigationItem];
  if (!i.leftBarButtonItem) {
    i.leftBarButtonItem = UIStyle::NewToolbarBack(
        self, @selector(toolbarBack));
    UIStyle::InitLeftBarButton(i.leftBarButtonItem);
  }
  return i;
}

- (void)loadURL:(const string&)url {
  if (url.empty()) {
    return;
  }
  NSURLRequest* r = [[NSURLRequest alloc] initWithURL:NewNSURL(url)];
  [web_view_ loadRequest:r];
}

- (BOOL)webView:(UIWebView*)web_view
shouldStartLoadWithRequest:(NSURLRequest*)request
 navigationType:(UIWebViewNavigationType)navigationType {
  return YES;
}

- (void)webViewDidFinishLoad:(UIWebView*)web_view {
  [activity_view_ stopAnimating];
}

- (void)webViewDidStartLoad:(UIWebView*)web_view {
  [activity_view_ startAnimating];
}

- (void)webView:(UIWebView*)web_view
didFailLoadWithError:(NSError*)error {
  LOG("settings: did fail load: %s", error);
}

- (void)toolbarBack {
  [self.navigationController popViewControllerAnimated:YES];
}

@end  // UIViewController

@interface SettingsTableViewCell : UITableViewCell {
 @private
}

@end  // SettingsTableViewCell

@implementation SettingsTableViewCell

- (id)initWithStyle:(UITableViewCellStyle)style
    reuseIdentifier:(NSString*)identifier {
  if (self = [super initWithStyle:style reuseIdentifier:identifier]) {
  }
  return self;
}

- (void)setHighlighted:(BOOL)highlighted
              animated:(BOOL)animated {
  [super setHighlighted:highlighted animated:animated];
  SetHighlighted(self, highlighted || self.selected);
}

- (void)setSelected:(BOOL)selected
           animated:(BOOL)animated {
  [super setSelected:selected animated:animated];
  SetHighlighted(self, selected || self.highlighted);
}

- (void)layoutSubviews {
  [super layoutSubviews];
  if (kSDKVersion >= "7" && kIOSVersion >= "7") {
    // On iOS 7, adjust for the position of the imageView to account for the
    // different default grouped table cell width.
    self.imageView.frameLeft = self.imageView.frameLeft + 5;
  }
}

@end  // SettingsTableViewCell

@implementation SettingsViewTableController

- (id)init {
  if (self = [super initWithStyle:UITableViewStyleGrouped]) {
  }
  return self;
}

- (void)loadView {
  [super loadView];
  self.tableView.backgroundView = NULL;
  self.tableView.backgroundColor =
      UIStyle::kSettingsBackgroundColor;
  self.tableView.rowHeight =
      kTableCellBackgroundSingle.get().size.height;
  self.tableView.separatorStyle = UITableViewCellSeparatorStyleNone;
}

- (UINavigationItem*)navigationItem {
  UINavigationItem* i = [super navigationItem];
  if ([self.navigationController.viewControllers
          indexOfObject:self] == 0) {
    // Don't touch the navigation item if this is the bottom view controller.
    return i;
  }
  if (!i.leftBarButtonItem) {
    i.leftBarButtonItem = UIStyle::NewToolbarBack(
        self, @selector(toolbarBack));
    UIStyle::InitLeftBarButton(i.leftBarButtonItem);
  }
  return i;
}

- (NSInteger)numberOfSectionsInTableView:(UITableView*)table_view {
  return sections_.size();
}

- (NSInteger)tableView:(UITableView*)table_view
 numberOfRowsInSection:(NSInteger)section {
  if (section < sections_.size()) {
    return sections_[section]->cached_size();
  }
  return 0;
}

- (CGFloat)tableView:(UITableView*)table_view
heightForFooterInSection:(NSInteger)section {
  if (section >= sections_.size()) {
    return 0;
  }
  NSAttributedString* s = sections_[section]->footer();
  if (!s) {
    return kSettingsSectionSpacing;
  }
  return AttrStringSize(s, CGSizeMake(270, CGFLOAT_MAX)).height + 10;
}

- (CGFloat)tableView:(UITableView*)table_view
heightForHeaderInSection:(NSInteger)section {
  if (section >= sections_.size()) {
    return 0;
  }
  NSAttributedString* s = sections_[section]->header();
  if (!s) {
    return kSettingsSectionSpacing;
  }
  return AttrStringSize(s, CGSizeMake(270, CGFLOAT_MAX)).height + 10;
}

- (UIView*)tableView:(UITableView*)table_view
    viewForFooterInSection:(NSInteger)section {
  if (section >= sections_.size()) {
    return NULL;
  }

  NSAttributedString* s = sections_[section]->footer();
  if (!s) {
    return NULL;
  }

  TextLayer* l = [TextLayer new];
  l.maxWidth = 270;
  l.attrStr = s;
  l.frameOrigin = CGPointMake(25, 5);
  l.frameWidth = 270;

  UIView* v = [UIView new];
  v.frame = CGRectInset(l.frame, -(320 - l.frameWidth) / 2, -l.frameTop);
  [v.layer addSublayer:l];
  return v;
}

- (UIView*)tableView:(UITableView*)table_view
    viewForHeaderInSection:(NSInteger)section {
  if (section >= sections_.size()) {
    return NULL;
  }

  NSAttributedString* s = sections_[section]->header();
  if (!s) {
    return NULL;
  }

  TextLayer* l = [TextLayer new];
  l.maxWidth = 270;
  l.attrStr = s;
  l.frameOrigin = CGPointMake(25, 5);
  l.frameWidth = 270;

  UIView* v = [UIView new];
  v.frame = CGRectInset(l.frame, -(320 - l.frameWidth) / 2, -l.frameTop);
  [v.layer addSublayer:l];
  return v;
}

- (NSIndexPath*)tableView:(UITableView*)table_view
  willSelectRowAtIndexPath:(NSIndexPath*)index_path {
  if (index_path.section < sections_.size()) {
    if (sections_[index_path.section]->Select(index_path.row)) {
      return index_path;
    }
  }
  return NULL;
}

- (void)tableView:(UITableView*)table_view
didSelectRowAtIndexPath:(NSIndexPath*)index_path {
}

- (UITableViewCell*)tableView:(UITableView*)table_view
        cellForRowAtIndexPath:(NSIndexPath*)index_path {
  SettingsSection* s = sections_[index_path.section];

  UITableViewCell* cell =
      [self.tableView dequeueReusableCellWithIdentifier:s->cell_identifier()];
  if (!cell) {
    cell = [[SettingsTableViewCell alloc]
              initWithStyle:s->cell_style()
              reuseIdentifier:s->cell_identifier()];
  }

  cell.detailTextLabel.font =
      UIStyle::kSettingsCellDetailUIFont;
  cell.detailTextLabel.highlightedTextColor =
      UIStyle::kSettingsTextSelectedColor;
  cell.detailTextLabel.textColor =
      UIStyle::kSettingsTextColor;
  cell.textLabel.font =
      UIStyle::kSettingsCellUIFont;
  cell.textLabel.highlightedTextColor =
      UIStyle::kSettingsTextSelectedColor;
  cell.textLabel.textColor =
      UIStyle::kSettingsTextColor;
  s->InitBackground(cell, index_path.row);
  s->InitCell(cell, index_path.row);
  return cell;
}

- (void)setSections:(const vector<SettingsSection*>&)new_sections {
  vector<SettingsSection*> old_sections;
  std::swap(old_sections, sections_);
  sections_ = new_sections;

  NSIndexSet* deletions = DeltaIndexes(old_sections, sections_);
  NSIndexSet* insertions = DeltaIndexes(sections_, old_sections);
  [self.tableView beginUpdates];
  // Reload any unchanged section in order to properly handle row
  // insertions/deletions.
  for (int i = 0; i < sections_.size(); ++i) {
    SettingsSection* s = sections_[i];
    const int old_size = s->cached_size();
    s->update_cached_size();
    const int old_index = IndexOf(old_sections, s);
    if (old_index == -1) {
      continue;
    }
    if (old_size == s->cached_size()) {
      [self.tableView reloadSections:[NSIndexSet indexSetWithIndex:old_index]
                    withRowAnimation:self.sectionReplaceAnimation];
      continue;
    }
    [self.tableView reloadSections:[NSIndexSet indexSetWithIndex:old_index]
                  withRowAnimation:self.sectionReloadAnimation];
  }
  // Process section deletions.
  if (deletions.count > 0) {
    [self.tableView deleteSections:deletions
                  withRowAnimation:self.sectionDeletionAnimation];
  }
  // Process section insertions.
  if (insertions.count > 0) {
    [self.tableView insertSections:insertions
                  withRowAnimation:self.sectionInsertionAnimation];
  }
  [self.tableView endUpdates];
}

- (void)updateCell:(int)row
           section:(SettingsSection*)section {
  const int index = IndexOf(sections_, section);
  if (index == -1) {
    return;
  }
  UITableViewCell* cell =
      [self.tableView cellForRowAtIndexPath:
               [NSIndexPath indexPathForRow:row inSection:index]];
  if (cell) {
    section->InitCell(cell, row);
  }
}

- (UITableViewRowAnimation)sectionDeletionAnimation {
  return UITableViewRowAnimationAutomatic;
}

- (UITableViewRowAnimation)sectionInsertionAnimation {
  return UITableViewRowAnimationAutomatic;
}

- (UITableViewRowAnimation)sectionReloadAnimation {
  return UITableViewRowAnimationAutomatic;
}

- (UITableViewRowAnimation)sectionReplaceAnimation {
  return UITableViewRowAnimationAutomatic;
}

- (void)toolbarBack {
  [self.navigationController popViewControllerAnimated:YES];
}

@end  // SettingsViewTableController

@interface CloudStorageSettingsController : SettingsViewTableController {
 @private
  UIAppState* state_;
  ScopedPtr<CurrentCloudStorageSettingsSection> current_;
  ScopedPtr<AvailableCloudStorageSettingsSection> available_;
  ScopedPtr<TotalCloudStorageSettingsSection> total_;
  ScopedPtr<StoreOriginalsSettingsSection> store_originals_;
  bool purchase_in_progress_;
}

- (id)initWithState:(UIAppState*)state;

@end  // CloudStorageSettingsController

@implementation CloudStorageSettingsController

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;
    self.title = @"Cloud Storage";

    current_.reset(new CurrentCloudStorageSettingsSection(state));
    available_.reset(new AvailableCloudStorageSettingsSection(state));
    total_.reset(new TotalCloudStorageSettingsSection(state));
    store_originals_.reset(new StoreOriginalsSettingsSection(state));

    state->settings_changed()->Add(
      ^(bool downloaded) {
        CHECK(dispatch_is_main_thread());
        [self updateSections];
      });

    [self updateSections];
  }
  return self;
}

- (void)loadView {
  [super loadView];

  // TODO(peter): Do we need UIStyle::NewToolbarBlueButton()?
  UIBarButtonItem* buy_item = UIStyle::NewToolbarGreenButton(
      @"Buy", self, @selector(buy));
  buy_item.tintColor = UIStyle::kBuyColor;
  buy_item.enabled = NO;
  UIStyle::InitRightBarButton(buy_item);
  self.navigationItem.rightBarButtonItem = buy_item;
}

- (void)viewWillAppear:(BOOL)animated {
  if (![SKPaymentQueue canMakePayments]) {
    [[[UIAlertView alloc]
       initWithTitle:@"Your Purchases Are Disabled."
             message:
         @"Adjust your Settings (Settings > iTunes & App Stores) "
          @"and then: Dollar. Dollar. Bills. Y'all."
            delegate:NULL
       cancelButtonTitle:@"OK"
       otherButtonTitles:NULL] show];
  }

  SubscriptionManagerIOS* sub = state_->subscription_manager_ios();
  if (sub->loading() || sub->products().empty()) {
    UIView* loading_progress = [UIView new];
    loading_progress.backgroundColor = MakeUIColor(0, 0, 0, 0.4);
    loading_progress.frame = self.view.bounds;
    loading_progress.userInteractionEnabled = YES;
    loading_progress.tag = kLoadingProgressTag;
    [self.view addSubview:loading_progress];

    UIActivityIndicatorView* activity = [UIActivityIndicatorView new];
    activity.frame = loading_progress.bounds;
    [loading_progress addSubview:activity];
    [activity startAnimating];
  }

  // Pre-load subscription info.
  sub->MaybeLoad(^{
      UIView* loading_progress =
          [self.view viewWithTag:kLoadingProgressTag];
      [UIView animateWithDuration:0.3
                       animations:^{
          loading_progress.alpha = 0;
        }
                       completion:^(BOOL finished) {
          [loading_progress removeFromSuperview];
        }];

      // Only allow selection if payments are enabled.
      if ([SKPaymentQueue canMakePayments]) {
        for (int i = 0; i < available_->size(); ++i) {
          available_->SetCallback(i, ^{
              for (int j = 0; j < available_->size(); ++j) {
                if (i != j) {
                  available_->SetToggleCell(j, false);
                }
              }
              available_->ToggleCell(i);
              [self updateCells];
              return false;
            });
        }
      }
      [self updateSections];
    });
}

- (void)updateCells {
  int64_t total_space = 0;
  double total_price = 0;
  for (int i = 0; i < current_->size(); ++i) {
    if (current_->cell_checked(i)) {
      total_space += current_->cell_space(i);
      total_price += current_->cell_price(i);
    }
  }
  for (int i = 0; i < available_->size(); ++i) {
    if (available_->cell_checked(i)) {
      total_space += available_->cell_space(i);
      total_price += available_->cell_price(i);
    }
  }
  total_->SetTotal(total_space, total_price);

  for (int i = 0; i < sections_.size(); ++i) {
    SettingsSection* s = sections_[i];
    for (int j = 0; j < s->cached_size(); ++j) {
      UITableViewCell* cell =
          [self.tableView cellForRowAtIndexPath:
                   [NSIndexPath indexPathForRow:j inSection:i]];
      if (cell) {
        s->InitCell(cell, j);
      }
    }
  }

  bool buy = false;
  if (!purchase_in_progress_) {
    for (int i = 0; i < available_->size(); ++i) {
      if (available_->cell_checked(i)) {
        buy = true;
        break;
      }
    }
  }
  self.navigationItem.rightBarButtonItem.enabled = buy;
}

- (void)updateSections {
  [self updateCells];

  vector<SettingsSection*> new_sections;
  new_sections.push_back(current_.get());
  if (available_->size() > 0) {
    new_sections.push_back(available_.get());
  }
  new_sections.push_back(total_.get());
  if (kCloudStorageEnabled && state_->subscription_manager_ios()->HasCloudStorage()) {
    new_sections.push_back(store_originals_.get());
  }
  [self setSections:new_sections];
}

- (void)buy {
  SubscriptionManagerIOS* const sub = state_->subscription_manager_ios();
  SKProduct* p = sub->GetSKProduct(available_->GetSelectedProduct()->product_type());
  if (p) {
    self.navigationItem.rightBarButtonItem.enabled = NO;
    purchase_in_progress_ = true;
    sub->PurchaseProduct(
        p, ^(SubscriptionManagerIOS::PurchaseStatus status) {
          self.navigationItem.rightBarButtonItem.enabled = YES;
          purchase_in_progress_ = false;
          if (status == SubscriptionManagerIOS::kPurchaseSuccess) {
            // Enable cloud storage when a subscription is made.
            state_->set_cloud_storage(true);
            state_->settings_changed()->Run(false);
          }
          // Remove the product from "available" and add it to "current"
          [self updateSections];
        });
    // Change the "available" product's checkmark to a spinner.
    available_->ClearToggle();
    [self updateSections];
  }
}

@end  // CloudStorageSettingsController

@interface TopLevelSettingsController
    : SettingsViewTableController<UIActionSheetDelegate,
                                  UIPickerViewDataSource,
                                  UIPickerViewDelegate> {
 @private
  UIAppState* state_;
  UIView* local_storage_picker_;
  ScopedPtr<StorageSettingsSection> storage_;
  ScopedPtr<StoreOriginalsSettingsSection> store_originals_;
  ScopedPtr<LegalSettingsSection> legal_;
  ScopedPtr<HelpSettingsSection> help_;
  ScopedPtr<DebugLogsSettingsSection> debug_logs_;
  ScopedPtr<UnlinkSettingsSection> unlink_;
  ScopedPtr<DevSettingsSection> dev_;
  UIBarButtonItem* back_button_item_;
  UIBarButtonItem* cancel_button_item_;
}

- (id)initWithState:(UIAppState*)state;

@end  // TopLevelSettingsController

@implementation TopLevelSettingsController

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;
    self.title = @"Settings";

    storage_.reset(new StorageSettingsSection(state));
    storage_->SetCallback(0, ^{
        if (!local_storage_picker_) {
          [self localStoragePickerShow];
          return true;
        }
        [self localStoragePickerHide];
        return false;
      });
    storage_->SetCallback(1, ^{
        state_->analytics()->SettingsCloudStorage();
        UIViewController* v =
            [[CloudStorageSettingsController alloc] initWithState:state_];
        [self.navigationController pushViewController:v animated:YES];
        return false;
      });
    state_->subscription_manager_ios()->changed()->Add(^{
        [self updateCell:1 section:storage_.get()];
      });

    store_originals_.reset(new StoreOriginalsSettingsSection(state));

    legal_.reset(new LegalSettingsSection(state));
    legal_->SetCallback(kTermsOfServiceIndex, ^{
        state_->analytics()->SettingsTermsOfService();
        WebViewController* v = [WebViewController new];
        v.title = @"Terms of Service";
        v.url = "http://www.viewfinder.co/terms";
        [self.navigationController pushViewController:v animated:YES];
        return false;
      });
    legal_->SetCallback(kPrivacyPolicyIndex, ^{
        state_->analytics()->SettingsPrivacyPolicy();
        WebViewController* v = [WebViewController new];
        v.title = @"Privacy Policy";
        v.url = "http://www.viewfinder.co/privacy";
        [self.navigationController pushViewController:v animated:YES];
        return false;
      });

    help_.reset(new HelpSettingsSection(state));
    help_->SetCallback(kFAQIndex, ^{
        WebViewController* v = [WebViewController new];
        v.title = @"FAQ";
        v.url = "http://www.viewfinder.co/faq";
        [self.navigationController pushViewController:v animated:YES];
        return false;
      });
    help_->SetCallback(kSendFeedbackIndex, ^{
        state_->SendFeedback(state_->root_view_controller());
        return false;
      });

    debug_logs_.reset(new DebugLogsSettingsSection(state));

#ifndef APPSTORE
    unlink_.reset(new UnlinkSettingsSection());
    unlink_->SetCallback(0, ^{
        UIActionSheet* confirm =
            [[UIActionSheet alloc]
              initWithTitle:@"This will remove all photos from your Viewfinder "
              @"account from this iPhone. Are you sure?"
                   delegate:self
              cancelButtonTitle:@"Cancel"
              destructiveButtonTitle:@"Unlink iPhone"
              otherButtonTitles:NULL];
        confirm.tag = kActionSheetUnlinkTag;
        [confirm setActionSheetStyle:UIActionSheetStyleBlackOpaque];
        [confirm showInView:self.view];
        return false;
      });
#endif  // !APPSTORE

#ifdef DEVELOPMENT
    dev_.reset(new DevSettingsSection());
    dev_->SetCallback(kFakeLogoutIndex, ^{
        state_->FakeLogout();
        return false;
      });
    dev_->SetCallback(kFakeMaintenanceIndex, ^{
        state_->FakeMaintenance();
        return false;
      });
    dev_->SetCallback(kFakeNotAuthorizedIndex, ^{
        state_->FakeAssetsNotAuthorized();
        return false;
      });
    dev_->SetCallback(kFakeZeroState, ^{
        state_->FakeZeroState();
        [self toolbarBack];
        return false;
      });
    dev_->SetCallback(kFake401, ^{
        state_->Fake401();
        [self toolbarBack];
        return false;
      });
    dev_->SetCallback(kResetNotices, ^{
        DashboardNoticeResetAll(state_);
        [self toolbarBack];
        return false;
      });
    dev_->SetCallback(kBenchmarkDownload, ^{
        state_->net_manager()->RunDownloadBenchmark();
        [self toolbarBack];
        return false;
      });
    dev_->SetCallback(kResetAllContacts, ^{
        state_->contact_manager()->ResetAll();
        [self toolbarBack];
        return false;
      });
    dev_->SetCallback(kCheckFalseIndex, ^{
        CHECK(false);
        return false;
      });
    dev_->SetCallback(kFindNearbyUsers, ^{
        if (kIOSVersion >= "7") {
          UIViewController* v =
              [[FindNearbyUsersController alloc] initWithState:state_];
          [self.navigationController pushViewController:v animated:YES];
        }
        return false;
      });
#endif  // DEVELOPMENT

    state->settings_changed()->Add(
      ^(bool downloaded) {
        CHECK(dispatch_is_main_thread());
        [self updateSections];
      });
    state->photo_storage()->changed()->Add(^{
        CHECK(dispatch_is_main_thread());
        [self updateCell:0 section:storage_.get()];
      });
    [self updateSections];
  }
  return self;
}

- (void)loadView {
  [super loadView];
  [self.tableView.panGestureRecognizer
      addTarget:self action:@selector(tablePanned)];
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
    cancel_button_item_ = UIStyle::NewToolbarBack(
        self, @selector(toolbarCancel));
    UIStyle::InitLeftBarButton(cancel_button_item_);
  }
  return cancel_button_item_;
}

- (UINavigationItem*)navigationItem {
  UINavigationItem* i = [super navigationItem];
  if (!i.leftBarButtonItem) {
    i.leftBarButtonItem = self.backButtonItem;
  }
  return i;
}

- (void)setEditing:(BOOL)editing
          animated:(BOOL)animated {
  [super setEditing:editing animated:animated];
  self.navigationItem.leftBarButtonItem =
      editing ? self.cancelButtonItem : self.backButtonItem;
  self.navigationItem.rightBarButtonItem =
      editing ? self.editButtonItem : NULL;
  UIStyle::InitRightBarButton(self.navigationItem.rightBarButtonItem);
  [self.tableView setEditing:NO animated:NO];
}

- (void)viewWillAppear:(BOOL)animated {
  [super viewWillAppear:animated];

  // TODO(peter): Remove.
  // Pre-load subscription info.
  // state_->subscription_manager_ios()->MaybeLoad(NULL);
}

- (void)viewWillDisappear:(BOOL)animated {
  [super viewWillDisappear:animated];
  [self localStoragePickerHide];
  [self.view endEditing:animated];
}

- (CGRect)pickerVisibleFrame {
  const CGRect screen_rect = [[UIScreen mainScreen] applicationFrame];
  const CGSize picker_size = local_storage_picker_.bounds.size;
  return CGRectMake(
      0, screen_rect.origin.y + screen_rect.size.height - picker_size.height,
      picker_size.width, picker_size.height);
}

- (CGRect)pickerHiddenFrame {
  const CGRect screen_rect = [[UIScreen mainScreen] applicationFrame];
  const CGSize picker_size = local_storage_picker_.bounds.size;
  return CGRectMake(
      0, screen_rect.origin.y + screen_rect.size.height,
      picker_size.width, picker_size.height);
}

- (void)localStoragePickerShow {
  if (!local_storage_picker_) {
    const int row =
        state_->photo_storage()->setting_index(
            state_->photo_storage()->local_bytes_limit());

    UIPickerView* picker = [UIPickerView new];
    picker.dataSource = self;
    picker.delegate = self;
    picker.showsSelectionIndicator = YES;
    [picker sizeToFit];
    [picker selectRow:row
          inComponent:0
             animated:NO];

    // On iOS 7, UIPickerViews are transparent and are intended to be displayed
    // inline with the table. As a hack, we place the UIPickerView inside a
    // view with a solid white background. The result is unchanged on iOS 6.
    local_storage_picker_ = [UIView new];
    local_storage_picker_.backgroundColor = [UIColor whiteColor];
    local_storage_picker_.bounds = picker.frame;
    [local_storage_picker_ addSubview:picker];
    [self.view.window addSubview:local_storage_picker_];

    local_storage_picker_.frame = self.pickerHiddenFrame;
    [UIView animateWithDuration:0.3
                     animations:^{
        local_storage_picker_.frame = self.pickerVisibleFrame;
      }];
  }
}

- (void)localStoragePickerHide {
  if (local_storage_picker_) {
    [UIView animateWithDuration:0.3
                          delay:0
                        options:UIViewAnimationOptionCurveEaseOut
                     animations:^{
        local_storage_picker_.frame = self.pickerHiddenFrame;
      }
                     completion:^(BOOL finished){
        [local_storage_picker_ removeFromSuperview];
        local_storage_picker_ = NULL;
      }];

    const int section = IndexOf(sections_, storage_.get());
    [self.tableView deselectRowAtIndexPath:
              [NSIndexPath indexPathForRow:0 inSection:section]
                                  animated:YES];
  }
}

- (void)tablePanned {
  if (local_storage_picker_) {
    [self panToDismissEditor:local_storage_picker_
               originalFrame:self.pickerVisibleFrame
                     dismiss:^{
        [self localStoragePickerHide];
      }];
  }
}

- (void)panToDismissEditor:(UIView*)editor
             originalFrame:(CGRect)original_frame
                   dismiss:(void (^)())dismiss {
  UIPanGestureRecognizer* pan = self.tableView.panGestureRecognizer;
  const float max_y = self.view.window.frameHeight;
  const float min_y = max_y - editor.frameHeight;

  switch (pan.state) {
    case UIGestureRecognizerStateBegan:
      break;
    case UIGestureRecognizerStateChanged: {
      const CGPoint p = [pan locationInView:self.view.window];
      // Animate within a zero-duration block to prevent any implicit animation
      // on the editor frame from doing something else.
      [UIView animateWithDuration:0.0
                       animations:^{
          editor.frameTop = std::min(std::max(p.y, min_y), max_y);
        }];
      break;
    }
    case UIGestureRecognizerStateEnded:
      if (editor.frameTop > min_y) {
        const CGPoint v = [pan velocityInView:self.view.window];
        if (v.y >= 0) {
          dismiss();
        } else {
          [UIView animateWithDuration:0.3
                                delay:0
                              options:UIViewAnimationOptionCurveEaseOut
                           animations:^{
              editor.frame = original_frame;
            }
                           completion:NULL];
        }
      }
    case UIGestureRecognizerStateCancelled:
    default:
      break;
  }
}

- (void)actionSheet:(UIActionSheet*)sheet
clickedButtonAtIndex:(NSInteger)index {
  if (sheet.tag == kActionSheetUnlinkTag) {
    if (index == 0) {
      state_->analytics()->SettingsUnlink();
      state_->UnlinkDevice();
    }
  }
}

- (NSInteger)numberOfComponentsInPickerView:(UIPickerView*)picker {
  return 1;
}

- (NSInteger)pickerView:(UIPickerView*)picker
numberOfRowsInComponent:(NSInteger)component {
  return state_->photo_storage()->settings().size();
}

- (UIView*)pickerView:(UIPickerView*)picker
           viewForRow:(NSInteger)row
         forComponent:(NSInteger)component
          reusingView:(UIView*)view {
  const vector<PhotoStorage::Setting>& settings =
      state_->photo_storage()->settings();

  UIView* v = [UIView new];
  v.autoresizesSubviews = YES;

  UILabel* l = [UILabel new];
  l.autoresizingMask =
      UIViewAutoresizingFlexibleRightMargin |
      UIViewAutoresizingFlexibleTopMargin |
      UIViewAutoresizingFlexibleBottomMargin;
  l.backgroundColor = [UIColor clearColor];
  l.font = [UIFont boldSystemFontOfSize:18];
  l.shadowColor = [UIColor whiteColor];
  l.shadowOffset = CGSizeMake(0, 1);
  l.text = NewNSString(settings[row].title);
  [l sizeToFit];
  l.frame = CGRectOffset(l.frame, 10, 0);
  [v addSubview:l];

  UILabel* d = [UILabel new];
  d.autoresizingMask =
      UIViewAutoresizingFlexibleLeftMargin |
      UIViewAutoresizingFlexibleTopMargin |
      UIViewAutoresizingFlexibleBottomMargin;
  d.backgroundColor = [UIColor clearColor];
  d.font = [UIFont systemFontOfSize:14];
  d.shadowColor = [UIColor whiteColor];
  d.shadowOffset = CGSizeMake(0, 1);
  d.text = NewNSString(settings[row].detail);
  [d sizeToFit];
  d.frame = CGRectOffset(d.frame, -10 - d.frame.size.width, 0);
  [v addSubview:d];

  return v;
}

- (void)pickerView:(UIPickerView*)picker
      didSelectRow:(NSInteger)row
       inComponent:(NSInteger)component {
  const vector<PhotoStorage::Setting>& settings =
      state_->photo_storage()->settings();

  state_->photo_storage()->set_local_bytes_limit(settings[row].value);
  state_->settings_changed()->Run(false);

  [self updateCell:0 section:storage_.get()];
}

- (void)updateSections {
  vector<SettingsSection*> new_sections;

  // TODO(peter): Delete the StorageSettingsSection code.
  // new_sections.push_back(storage_.get());
  if (kCloudStorageEnabled && state_->subscription_manager_ios()->HasCloudStorage()) {
    new_sections.push_back(store_originals_.get());
  }
  new_sections.push_back(help_.get());
  new_sections.push_back(legal_.get());
  if (state_->is_registered()) {
    new_sections.push_back(debug_logs_.get());
#ifndef APPSTORE
    new_sections.push_back(unlink_.get());
#endif  // APPSTORE
#ifdef DEVELOPMENT
    new_sections.push_back(dev_.get());
#endif
  }

  [self setSections:new_sections];
}

- (void)toolbarCancel {
  [self setEditing:NO animated:YES];
}

- (void)toolbarBack {
  [self localStoragePickerHide];
  [self.view endEditing:YES];
  [state_->root_view_controller() dismissViewController:ControllerState()];
}

@end  // TopLevelSettingsController

@implementation SettingsViewController

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;
    settings_ = [[TopLevelSettingsController alloc] initWithState:state_];
  }
  return self;
}

- (bool)statusBarLightContent {
  return true;
}

- (void)loadView {
  [super loadView];
  self.viewControllers = Array(settings_);
}

- (void)viewDidUnload {
  [self setViewControllers:NULL animated:NO];
  [super viewDidUnload];
}

- (void)viewWillAppear:(BOOL)animated {
  [super viewWillAppear:animated];
  state_->analytics()->SettingsPage();
}

@end  // SettingsViewController
