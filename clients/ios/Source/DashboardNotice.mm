// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "Analytics.h"
#import "Appearance.h"
#import "CALayer+geometry.h"
#import "ContactManager.h"
#import "DashboardNotice.h"
#import "JailbreakUtils.h"
#import "Logging.h"
#import "PhotoTable.h"
#import "UIAppState.h"
#import "UIView+geometry.h"

namespace {

const float kCornerRadius = 6.5;
const float kMargin = 5;
const float kPadding = 12;
const float kSpacing = 8;

const int kDesiredPushNotificationTypes =
    UIRemoteNotificationTypeAlert |
    UIRemoteNotificationTypeBadge;
const string kPushNotificationsNoticeRemoveKey =
    DBFormat::metadata_key("push_notifications_notice_removed");
const string kHelloJailbreakerNoticeRemoveKey =
    DBFormat::metadata_key("hello_jailbreaker_notice_removed");
const string kSystemMessageNoticeRemoveKey =
    DBFormat::metadata_key("system_message_notice_removed");
const string kNewUsersNoticeRemoveKey =
    DBFormat::metadata_key("new_users_notice_removed");

LazyStaticImage kDashboardNoticeButtonArrow(
    @"dashboard-notice-button-arrow.png");
LazyStaticImage kDashboardNoticeButtonChevron(
    @"dashboard-notice-button-chevron.png");
LazyStaticImage kDashboardNoticeButtonInfo(
    @"dashboard-notice-button-info.png");
LazyStaticImage kDashboardNoticeButtonInfoActive(
    @"dashboard-notice-button-info-active.png");
LazyStaticImage kDashboardNoticeButtonRemove(
    @"dashboard-notice-button-remove.png");
LazyStaticImage kDashboardNoticeOrange(
    @"dashboard_notice_orange.png", UIEdgeInsetsMake(26, 14, 27, 15));
LazyStaticImage kDashboardNoticeOrangePressed(
    @"dashboard_notice_orange_pressed.png", UIEdgeInsetsMake(26, 14, 27, 15));
LazyStaticImage kDashboardNoticeRed(
    @"dashboard_notice_red.png", UIEdgeInsetsMake(26, 14, 27, 15));
LazyStaticImage kDashboardNoticeRedPressed(
    @"dashboard_notice_red_pressed.png", UIEdgeInsetsMake(26, 14, 27, 15));

LazyStaticHexColor kDashboardNoticeRedColor = { "#c23825" };
LazyStaticHexColor kDashboardNoticeTextColor = { "#faf7f7" };
LazyStaticHexColor kDashboardTextHighlightedColor = { "#ffffff7f" };

LazyStaticUIFont kSubtitleFont = {
  kProximaNovaBold, 15
};
LazyStaticUIFont kTitleFont = {
  kProximaNovaBold, 17
};

UIImage* DashboardNormalImage(UIAppState* state, DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_PUSH_NOTIFICATIONS:
      return kDashboardNoticeRed;
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE:
      if (state->system_message().severity() == SystemMessage::DISABLE_NETWORK ||
          state->system_message().severity() == SystemMessage::ATTENTION) {
        return kDashboardNoticeRed;
      } else {
        return kDashboardNoticeOrange;
      }
    case DASHBOARD_NOTICE_HELLO_JAILBREAKER:
    case DASHBOARD_NOTICE_NEW_USERS:
    default:
      return kDashboardNoticeOrange;
  }
  return NULL;
}

UIImage* DashboardPressedImage(UIAppState* state, DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_PUSH_NOTIFICATIONS:
      return kDashboardNoticeRedPressed;
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE:
      if (state->system_message().severity() == SystemMessage::DISABLE_NETWORK ||
          state->system_message().severity() == SystemMessage::ATTENTION) {
        return kDashboardNoticeRedPressed;
      } else {
        return kDashboardNoticeOrangePressed;
      }
    case DASHBOARD_NOTICE_HELLO_JAILBREAKER:
    case DASHBOARD_NOTICE_NEW_USERS:
    default:
      return kDashboardNoticeOrangePressed;
  }
  return NULL;
}

UIImage* DashboardDetailImage(DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_HELLO_JAILBREAKER:
    case DASHBOARD_NOTICE_PUSH_NOTIFICATIONS:
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE:
    case DASHBOARD_NOTICE_NEW_USERS:
      return kDashboardNoticeButtonInfo;
    default:
      return kDashboardNoticeButtonArrow;
  }
  return NULL;
}

NSString* DashboardNoticeTitle(UIAppState* state, DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_HELLO_JAILBREAKER:
      return @"Hello Jailbreaker";
    case DASHBOARD_NOTICE_PUSH_NOTIFICATIONS:
      return @"Your Notifications Are Off";
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE:
      return NewNSString(state->system_message().title());
    case DASHBOARD_NOTICE_NEW_USERS: {
      vector<ContactMetadata> new_users;
      state->contact_manager()->GetNewUsers(&new_users);
      if (new_users.size() == 1) {
        return Format("New Viewfinder contact: %s", ContactManager::FormatName(new_users[0], true, false));
      } else {
        return Format("%d new Viewfinder contacts", new_users.size());
      }
    }
    default:
      break;
  }
  return NULL;
}

NSString* DashboardNoticeBody(UIAppState* state, DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_PUSH_NOTIFICATIONS:
      return @"To turn on notifications when you receive a photo or message, "
          @"go to Settings > Notifications > Viewfinder.";
    case DASHBOARD_NOTICE_HELLO_JAILBREAKER:
      return @"You are running an extension which injects code into the Viewfinder "
          @"app, presenting a situation we cannot test ahead of time. If you "
          @"experience crashes, please contact support@emailscrubbed.com and we'll "
          @"try our best to resolve them.";
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE:
      if (!state->system_message().body().empty()) {
        return NewNSString(state->system_message().body());
      }
      break;
    case DASHBOARD_NOTICE_NEW_USERS: {
      vector<ContactMetadata> new_users;
      state->contact_manager()->GetNewUsers(&new_users);
      vector<string> names;
      // 9 rows will fit on an iPhone 4 screen (assuming no other notices are present).
      // Consider removing this limit when we have support for scrolling long notices.
      const int kMaxRows = 9;
      for (int i = 0; i < std::min<int>(new_users.size(), kMaxRows); i++) {
        names.push_back(ContactManager::FormatName(new_users[i], false, true));
      }
      if (new_users.size() > kMaxRows) {
        names.push_back(Format("and %d more", new_users.size() - kMaxRows));
      }
      return NewNSString(Join(names, "\n"));
    }
    default:
      break;
  }
  return NULL;
}

NSURL* DashboardNoticeBodyUrl(UIAppState* state, DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE:
      if (!state->system_message().link().empty()) {
        return NewNSURL(state->system_message().link());
      }
    default:
      break;
  }
  return NULL;
}

bool DashboardNoticeCanBeRemoved(UIAppState* state, DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE:
      return (state->system_message().severity() != SystemMessage::DISABLE_NETWORK);
    default:
      break;
  }
  return true;
}

string DashboardNoticeRemoveKey(DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_HELLO_JAILBREAKER:
      return kHelloJailbreakerNoticeRemoveKey;
    case DASHBOARD_NOTICE_PUSH_NOTIFICATIONS:
      return kPushNotificationsNoticeRemoveKey;
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE:
      return kSystemMessageNoticeRemoveKey;
    case DASHBOARD_NOTICE_NEW_USERS:
      return kNewUsersNoticeRemoveKey;
    default:
      break;
  }
  return "";
}

void DashboardNoticeRemoveHook(UIAppState* state, DashboardNoticeType type, const DBHandle& updates) {
  switch (type) {
    case DASHBOARD_NOTICE_NEW_USERS:
      state->contact_manager()->ResetNewUsers(updates);
      break;
    default:
      break;
  }
}

string DashboardNoticeIdentifier(UIAppState* state, DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_HELLO_JAILBREAKER:
      return "hello_jailbreaker";
    case DASHBOARD_NOTICE_PUSH_NOTIFICATIONS:
      return "push_notifications";
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE:
      return state->system_message().identifier();
    case DASHBOARD_NOTICE_NEW_USERS: {
      vector<ContactMetadata> new_users;
      state->contact_manager()->GetNewUsers(&new_users);
      if (new_users.size() > 0) {
        // Return an arbitrary user id from the list.
        return ToString(new_users[0].user_id());
      }
      return "";
    }
    default:
      break;
  }
  return "";
}

UIButton* NewDashboardActivateButton(
    UIAppState* state, DashboardNoticeType type, float width, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.adjustsImageWhenHighlighted = NO;
  b.contentHorizontalAlignment = UIControlContentHorizontalAlignmentLeft;
  b.contentVerticalAlignment = UIControlContentVerticalAlignmentTop;
  b.titleLabel.font = kTitleFont;
  b.titleLabel.lineBreakMode = NSLineBreakByTruncatingTail;
  [b setTitle:DashboardNoticeTitle(state, type)
     forState:UIControlStateNormal];
  [b setTitleColor:kDashboardNoticeTextColor
          forState:UIControlStateNormal];
  UIImage* normal = DashboardNormalImage(state, type);
  [b setBackgroundImage:normal
               forState:UIControlStateNormal];
  [b setBackgroundImage:DashboardPressedImage(state, type)
               forState:UIControlStateHighlighted];
  [b addTarget:target
        action:selector
    forControlEvents:UIControlEventTouchUpInside];
  b.frame = CGRectMake(
      kSpacing - kMargin, -kMargin,
      width - (kSpacing - kMargin) * 2, normal.size.height);
  const CGSize size = kDashboardNoticeButtonInfo.get().size;
  b.imageEdgeInsets = UIEdgeInsetsMake(
      kPadding + kMargin, b.frameWidth - kPadding - kMargin - size.width, 0, 0);
  b.titleEdgeInsets = UIEdgeInsetsMake(
      kPadding + kMargin + 2, -2, 0, kPadding + kMargin * 2 + size.width);
  return b;
}

UIButton* NewDashboardBody(id target, NSString* body_text, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.contentHorizontalAlignment = UIControlContentHorizontalAlignmentLeft;
  b.contentVerticalAlignment = UIControlContentVerticalAlignmentBottom;
  b.titleLabel.font = kSubtitleFont;
  b.titleLabel.lineBreakMode = NSLineBreakByWordWrapping;
  b.titleLabel.numberOfLines = 0;
  b.titleLabel.textAlignment = NSTextAlignmentLeft;
  [b setTitle:body_text
     forState:UIControlStateNormal];
  [b setTitleColor:[UIColor whiteColor]
          forState:UIControlStateNormal];
  [b setTitleColor:kDashboardTextHighlightedColor
          forState:UIControlStateHighlighted];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

NSString* DashboardRemoveTitle(DashboardNoticeType type) {
  switch (type) {
    case DASHBOARD_NOTICE_NEW_USERS:
      return @"OK";
    default:
      break;
  }
  return @"Remove";
}

UIButton* NewDashboardRemoveButton(DashboardNoticeType type, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.adjustsImageWhenHighlighted = NO;
  b.contentHorizontalAlignment = UIControlContentHorizontalAlignmentLeft;
  b.titleLabel.font = kSubtitleFont;
  [b setTitle:DashboardRemoveTitle(type)
     forState:UIControlStateNormal];
  [b setTitleColor:[UIColor whiteColor]
          forState:UIControlStateNormal];
  [b setTitleColor:kDashboardTextHighlightedColor
          forState:UIControlStateHighlighted];
  UIImage* image = kDashboardNoticeButtonRemove;
  [b setImage:image
     forState:UIControlStateNormal];
  b.contentEdgeInsets = UIEdgeInsetsMake(
      kPadding, kPadding, kPadding, kPadding);
  b.imageEdgeInsets = UIEdgeInsetsMake(
      0, [b.titleLabel sizeThatFits:CGSizeZero].width + kSpacing, 0, 0);
  b.titleEdgeInsets = UIEdgeInsetsMake(0, -image.size.width, 0, 0);
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  b.frameWidth = b.frameWidth + kSpacing;
  return b;
}

}  // namespace

@implementation DashboardNotice

@synthesize removed = removed_;
@synthesize tapped = tapped_;
@synthesize toggled = toggled_;
@synthesize type = type_;
@synthesize updated = updated_;
@synthesize identifier = identifier_;

- (id)initWithState:(UIAppState*)state
           withType:(DashboardNoticeType)type
         withWidth:(float)width
         withIdentifier:(string)identifier {
  if (self = [super initWithFrame:CGRectMake(0, 0, width, 0)]) {
    self.clipsToBounds = YES;

    // This is subtle. By default, when setting the alpha of a view, iOS sets
    // the alpha of every sub-view. This is a bit unexpected as intuitively you
    // would expect the alpha of the composited view+subviews to have the alpha
    // applied to it. We can get the expected behavior by setting the
    // CALayer.shouldRasterize flag. This has a slight performance penalty
    // (which is why it isn't the default), but that doesn't matter here.
    self.layer.rasterizationScale = [UIScreen mainScreen].scale;
    self.layer.shouldRasterize = YES;

    state_ = state;
    type_ = type;
    identifier_ = identifier;

    activate_ = NewDashboardActivateButton(state, type, width, self, @selector(activate));
    activate_.clipsToBounds = YES;
    [self addSubview:activate_];

    tray_ = [[UIImageView alloc] initWithImage:DashboardNormalImage(state, type)];
    tray_.frameLeft = kSpacing - kMargin;
    tray_.frameTop = kSpacing - kMargin;
    tray_.frameWidth = self.boundsWidth - (kSpacing - kMargin) * 2;
    tray_.userInteractionEnabled = YES;
    [self insertSubview:tray_ belowSubview:activate_];

    NSString* body_text = DashboardNoticeBody(state, type);
    if (body_text) {
      body_ = NewDashboardBody(self, body_text, @selector(activateBody));
      [tray_ addSubview:body_];
    } else {
      body_ = NULL;
    }

    if (DashboardNoticeCanBeRemoved(state, type)) {
      remove_ = NewDashboardRemoveButton(type, self, @selector(remove));
      [tray_ addSubview:remove_];
    } else {
      remove_ = NULL;
    }
  }
  return self;
}

- (float)baseHeight {
  return activate_.frameHeight - kMargin * 2 + kSpacing;
}

- (float)desiredHeight {
  if (self.removed) {
    return 0;
  }
  float base_height = self.baseHeight;
  if (!self.expanded) {
    return base_height;
  }
  if (body_) {
    base_height += self.bodyFrame.size.height;
  }
  if (remove_) {
    base_height += remove_.frameHeight;
  }
  return base_height;
}

- (bool)expanded {
  return expanded_;
}

- (void)setExpanded:(bool)expanded {
  if (expanded_ != expanded) {
    expanded_ = expanded;
  }
}

- (NSString*)title {
  return [activate_ titleForState:UIControlStateNormal];
}

- (void)setTitle:(NSString*)title {
  [activate_ setTitle:title
             forState:UIControlStateNormal];
}

- (CGRect)activateFrame {
  CGRect f = activate_.frame;
  if (self.removed) {
    f.size.height = 0;
  }
  return f;
}

- (CGRect)bodyFrame {
  const float w = tray_.boundsWidth - 2 * (kMargin + kPadding);
  CGSize s = [body_.titleLabel sizeThatFits:CGSizeMake(w, 0)];
  s.height += kPadding;
  return CGRectMake(
      kMargin + kPadding, self.removeFrame.origin.y - s.height,
      w, s.height);
}

- (CGRect)removeFrame {
  CGRect f = remove_.frame;
  f.origin.x = tray_.boundsWidth - f.size.width - kMargin;
  f.origin.y = tray_.boundsHeight - f.size.height - kMargin;
  return f;
}

- (CGRect)trayFrame {
  CGRect f = tray_.frame;
  f.size.height = std::max<float>(
      0, self.boundsHeight - (kSpacing - kMargin) - f.origin.y);
  return f;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];

  {
    const ScopedDisableCAActions disable_ca_actions;
    [self resetDetailImage];
  }

  activate_.frame = self.activateFrame;
  activate_.imageView.alpha = self.removed ? 0 : 1;
  activate_.titleLabel.alpha = activate_.imageView.alpha;

  tray_.frame = self.trayFrame;
  if (body_) {
    body_.frame = self.bodyFrame;
  }
  if (remove_) {
    remove_.frame = self.removeFrame;
  }
}

- (void)resetDetailImage {
  if (self.expanded) {
    [activate_ setImage:kDashboardNoticeButtonChevron
               forState:UIControlStateNormal];
  } else {
    [activate_ setImage:DashboardDetailImage(type_)
               forState:UIControlStateNormal];
  }
}

- (void)activate {
  if (body_) {
    if (self.toggled) {
      self.toggled();
    }
  } else if (self.tapped) {
    self.tapped();
  }
}

- (void)activateBody {
  NSURL* url = DashboardNoticeBodyUrl(state_, type_);
  if (url) {
    UIApplication* a = [UIApplication sharedApplication];
    [a openURL:url];
  } else if (self.tapped) {
    self.tapped();
  }
}

- (void)remove {
  state_->analytics()->DashboardNoticeDismiss(type_);
  DashboardNoticeRemove(state_, type_, identifier_);
  if (self.updated) {
    self.updated();
  }
}

@end  // DashboardNotice

DashboardNotice* NewDashboardNotice(
    UIAppState* state, DashboardNoticeType type, const string& identifier, float width) {
  return [[DashboardNotice alloc]
           initWithState:state
                withType:type
               withWidth:width
               withIdentifier:identifier];
}

string DashboardNoticeNeededIdentifier(UIAppState* state, DashboardNoticeType type) {
  const string remove_key = DashboardNoticeRemoveKey(type);
  switch (type) {
    case DASHBOARD_NOTICE_PUSH_NOTIFICATIONS: {
      const int enabled_types = state->remote_notification_types();
      if (enabled_types == 0) {
        // Push notifications are disabled. Use the "removed_identifier" logic.
        break;
      }
      // Push notifications are enabled;
      if (state->db()->Exists(remove_key)) {
        state->db()->Delete(remove_key);
      }
      return "";
    }
    case DASHBOARD_NOTICE_HELLO_JAILBREAKER:
      if (!HasMobileSubstrateDynamicLibrary()) {
        return "";
      }
      break;
    case DASHBOARD_NOTICE_SYSTEM_MESSAGE: {
      const SystemMessage& system_msg = state->system_message();
      // Filter out empty system messages, and those with non-displayable severity.
      if (system_msg.identifier().empty() ||
          system_msg.severity() < SystemMessage::INFO ||
          system_msg.severity() > SystemMessage::DISABLE_NETWORK) {
        return "";
      }
      break;
    }
    case DASHBOARD_NOTICE_NEW_USERS:
      break;
    default:
      break;
  }
  string removed_identifier;
  string needed_identifier = DashboardNoticeIdentifier(state, type);
  if (!state->db()->Get(remove_key, &removed_identifier)) {
    // No "dismissed" entry in the DB for this notice. Return the needed identifier.
    return needed_identifier;
  } else if (needed_identifier == removed_identifier) {
    // We have dismissed this notice.
    return "";
  }
  // Return any removed identifier. If it matches the existing notice, nothing will be done.
  return needed_identifier;
}

void DashboardNoticeRemove(UIAppState* state, DashboardNoticeType type, const string& identifier) {
  const string key = DashboardNoticeRemoveKey(type);
  if (!key.empty()) {
    DBHandle updates = state->NewDBTransaction();
    updates->Put(key, identifier);
    DashboardNoticeRemoveHook(state, type, updates);
    updates->Commit();
  }
}

void DashboardNoticeReset(UIAppState* state, DashboardNoticeType type) {
  const string key = DashboardNoticeRemoveKey(type);
  if (!key.empty()) {
    state->db()->Delete(key);
  }
}

void DashboardNoticeResetAll(UIAppState* state) {
  for (int i = 0; i < DASHBOARD_NOTICE_COUNT; ++i) {
    DashboardNoticeReset(state, static_cast<DashboardNoticeType>(i));
  }
}
