// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "Appearance.h"
#import "BadgeView.h"
#import "Navbar.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

const int kAddPhotosButtonIndex = 3;

namespace {

const int kMaxButtonsInTray = 4;

const float kHideDuration = 0.150;
const float kShowDuration = 0.150;

// For BUTTON_COMPOSE type.
const float kNavbarComposeHeight = 52;
const float kNavbarComposeTopMargin = 8;
const float kNavbarComposeLeftMargin = 8;

// For BUTTON_SINGLE_PHOTO type.
const float kSinglePhotoRelatedConvosButtonWidth = 48;
const float kSinglePhotoButtonWidth = 95;
const float kSinglePhotoButtonMiddleWidth = 89;
const float kSinglePhotoButtonHeight = 44;

const float kNavControlTextTopMargin = 30;

LazyStaticUIFont kBadgeUIFont = {
  kProximaNovaBold, 12
};
LazyStaticUIFont kComposeButtonUIFont = {
  kProximaNovaSemibold, 18
};
LazyStaticUIFont kNavControlButtonUIFont = {
  kProximaNovaRegular, 11
};
LazyStaticUIFont kNavbarButtonUIFont = {
  kProximaNovaBold, 15
};
LazyStaticUIFont kGreenButtonUIFont = {
  kProximaNovaBold, 16
};

LazyStaticHexColor kComposeButtonColor = { "#3f3e3e" };
LazyStaticHexColor kNavControlButtonColor = { "#ffffffff" };
LazyStaticHexColor kNavControlButtonActiveColor = { "#ffffff7f" };
LazyStaticHexColor kNavbarButtonColor = { "#ffffffff" };
LazyStaticHexColor kNavbarButtonActiveColor = { "#ffffff7f" };
LazyStaticHexColor kGreenButtonColor = { "#ffffff" };
LazyStaticHexColor kGreenButtonActiveColor = { "#9f9e9e" };
LazyStaticHexColor kGreenButtonDisabledColor = { "#ffffff7f" };

LazyStaticImage kActionBarBottom(@"action-bar-bottom.png");
LazyStaticImage kActionBarButtonGreyLeft(
    @"action-bar-button-grey-left", UIEdgeInsetsMake(0, 7, 0, 1));
LazyStaticImage kActionBarButtonGreyLeftActive(
    @"action-bar-button-grey-left-active", UIEdgeInsetsMake(0, 7, 0, 1));
LazyStaticImage kActionBarButtonGreyMiddle(
    @"action-bar-button-grey-middle", UIEdgeInsetsMake(0, 1, 0, 1));
LazyStaticImage kActionBarButtonGreyMiddleActive(
    @"action-bar-button-grey-middle-active", UIEdgeInsetsMake(0, 1, 0, 1));
LazyStaticImage kActionBarButtonGreyRight(
    @"action-bar-button-grey-right", UIEdgeInsetsMake(0, 1, 0, 7));
LazyStaticImage kActionBarButtonGreyRightActive(
    @"action-bar-button-grey-right-active", UIEdgeInsetsMake(0, 1, 0, 7));
LazyStaticImage kActionBarButtonRedLeft(
    @"action-bar-button-red-left", UIEdgeInsetsMake(0, 7, 0, 1));
LazyStaticImage kActionBarButtonRedLeftActive(
    @"action-bar-button-red-left-active", UIEdgeInsetsMake(0, 7, 0, 1));
LazyStaticImage kActionBarButtonRedMiddle(
    @"action-bar-button-red-middle", UIEdgeInsetsMake(0, 1, 0, 1));
LazyStaticImage kActionBarButtonRedMiddleActive(
    @"action-bar-button-red-middle-active", UIEdgeInsetsMake(0, 1, 0, 1));
LazyStaticImage kActionBarButtonRedRight(
    @"action-bar-button-red-right", UIEdgeInsetsMake(0, 1, 0, 7));
LazyStaticImage kActionBarButtonRedRightActive(
    @"action-bar-button-red-right-active", UIEdgeInsetsMake(0, 1, 0, 7));

LazyStaticImage kConvoSuggestionBar(@"convo-suggestion-bar.png");
LazyStaticImage kConvoSuggestionIcon(@"convo-suggestion-icon.png");

LazyStaticImage kSinglePhotoBottomGradient(@"single-photo-bottom-gradient.png");
LazyStaticImage kSinglePhotoIconRelatedConvos(@"single-photo-icon-related-convos.png");
LazyStaticImage kSinglePhotoButtonLeft(
    @"single-photo-button-left", UIEdgeInsetsMake(0, 20, 0, 1));
LazyStaticImage kSinglePhotoButtonLeftActive(
    @"single-photo-button-left-active", UIEdgeInsetsMake(0, 20, 0, 1));
LazyStaticImage kSinglePhotoButtonMiddle(
    @"single-photo-button-middle", UIEdgeInsetsMake(0, 2, 0, 2));
LazyStaticImage kSinglePhotoButtonMiddleActive(
    @"single-photo-button-middle-active", UIEdgeInsetsMake(0, 2, 0, 2));
LazyStaticImage kSinglePhotoButtonRight(
    @"single-photo-button-right", UIEdgeInsetsMake(0, 1, 0, 20));
LazyStaticImage kSinglePhotoButtonRightActive(
    @"single-photo-button-right-active", UIEdgeInsetsMake(0, 1, 0, 20));
LazyStaticImage kSinglePhotoButtonSingle(
    @"single-photo-button-single", UIEdgeInsetsMake(0, 11, 0, 11));
LazyStaticImage kSinglePhotoButtonSingleActive(
    @"single-photo-button-single-active", UIEdgeInsetsMake(0, 11, 0, 11));

LazyStaticImage kNavbarBack(@"navbar-back.png");

UIView* NewComposeButton(
    const ButtonDefinition& def, float width, id target) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.showsTouchWhenHighlighted = NO;
  b.frameSize = CGSizeMake(width, kNavbarComposeHeight);
  b.contentEdgeInsets = UIEdgeInsetsMake(kNavbarComposeTopMargin, 0, 0, 0);
  if (def.image) {
    [b setImage:def.image
       forState:UIControlStateNormal];
  }
  if (def.title) {
    b.titleLabel.font = kComposeButtonUIFont.get();
    [b setTitle:def.title forState:UIControlStateNormal];
    [b setTitleColor:kComposeButtonColor.get()
            forState:UIControlStateNormal];
  }

  if (target && def.selector) {
    [b addTarget:target
          action:def.selector
       forControlEvents:UIControlEventTouchUpInside];
  } else {
    b.enabled = NO;
  }
  return b;
}

UIView* NewNavbarButton(
    const ButtonDefinition& def, UIImage* bg_image, UIImage* bg_active,
    float width, id target) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.showsTouchWhenHighlighted = NO;
  b.frameSize = CGSizeMake(width, bg_image.size.height);
  if (def.image) {
    DCHECK(!def.title);
    [b setImage:def.image
       forState:UIControlStateNormal];
    b.imageEdgeInsets = UIEdgeInsetsMake(2, 0, 0, 0);
  } else if (def.title) {
    b.titleLabel.font = kNavbarButtonUIFont.get();
    b.titleLabel.lineBreakMode = NSLineBreakByTruncatingTail;
    [b setTitle:def.title forState:UIControlStateNormal];
    [b setTitleColor:kNavbarButtonColor.get()
            forState:UIControlStateNormal];
    [b setTitleColor:kNavbarButtonActiveColor.get()
            forState:UIControlStateHighlighted];
  }
  if (bg_image) {
    [b setBackgroundImage:bg_image forState:UIControlStateNormal];
  }
  if (bg_active) {
    [b setBackgroundImage:bg_active forState:UIControlStateHighlighted];
  }

  if (target && def.selector) {
    [b addTarget:target
          action:def.selector
       forControlEvents:UIControlEventTouchUpInside];
  } else {
    b.enabled = NO;
  }
  return b;
}

enum NavbarButtonType {
  BUTTON_COMPOSE,        // anchored nav with text-only buttons
  BUTTON_SINGLE_PHOTO,   // transparent single-photo view buttons
};

UIView* NewNavControlLeftButton(
    const ButtonDefinition& def, NavbarButtonType type, float width, id target) {
  switch (type) {
    case BUTTON_COMPOSE:
      return NewComposeButton(def, width, target);
    case BUTTON_SINGLE_PHOTO:
      return NewNavbarButton(def, kSinglePhotoButtonSingle, kSinglePhotoButtonSingleActive, width, target);
  }
}

UIView* NewNavControlMiddleButton(
    const ButtonDefinition& def, NavbarButtonType type, int index, float width, id target) {
  switch (type) {
    case BUTTON_COMPOSE:
      return NewComposeButton(def, width, target);
    case BUTTON_SINGLE_PHOTO: {
      UIButton* b;
      if (index == 1) {
        b = (UIButton*)NewNavbarButton(
            def, kSinglePhotoButtonLeft, kSinglePhotoButtonLeftActive, width, target);
        [b setTitleEdgeInsets:UIEdgeInsetsMake(0, 7, 0, 0)];
      } else {
        b = (UIButton*)NewNavbarButton(
            def, kSinglePhotoButtonMiddle, kSinglePhotoButtonMiddleActive, width, target);
      }
      return b;
    }
  }
}

UIView* NewNavControlRightButton(
    const ButtonDefinition& def, NavbarButtonType type, float width, id target) {
  switch (type) {
    case BUTTON_COMPOSE:
      return NewComposeButton(def, width, target);
    case BUTTON_SINGLE_PHOTO: {
      UIButton* b = (UIButton*)NewNavbarButton(
          def, kSinglePhotoButtonRight, kSinglePhotoButtonRightActive, width, target);
      [b setTitleEdgeInsets:UIEdgeInsetsMake(0, 0, 0, 7)];
      return b;
    }
  }
}

}  // namespace

@implementation Navbar

@synthesize env = env_;
@synthesize navbarState = navbar_state_;

- (id)init {
  if (self = [super init]) {
    navbar_state_ = NAVBAR_UNINITIALIZED;

    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleTopMargin | UIViewAutoresizingFlexibleWidth;
    self.backgroundColor = [UIColor clearColor];

    navbar_auto_suggest_def_ = ButtonDefinition(
        ButtonDefinition::COMPOSE, kConvoSuggestionIcon, @"Want a suggestion?", @selector(navbarAutoSuggest));
    navbar_export_def_ = ButtonDefinition(
        ButtonDefinition::GREY_ACTION, NULL, @"Export", @selector(navbarActionExport));
    navbar_forward_def_ = ButtonDefinition(
        ButtonDefinition::GREY_ACTION, NULL, @"Forward", @selector(navbarActionShare));
    navbar_mute_def_ = ButtonDefinition(
        ButtonDefinition::GREY_ACTION, NULL, @"Mute", @selector(navbarActionMute));
    navbar_related_convos_def_ = ButtonDefinition(
        ButtonDefinition::ICON, kSinglePhotoIconRelatedConvos, NULL, @selector(navbarRelatedConvos));
    navbar_remove_convos_def_ = ButtonDefinition(
        ButtonDefinition::RED_ACTION, NULL, @"Remove", @selector(navbarActionRemoveConvo));
    navbar_remove_photos_def_ = ButtonDefinition(
        ButtonDefinition::RED_ACTION, NULL, @"Remove", @selector(navbarActionRemove));
    navbar_share_def_ = ButtonDefinition(
        ButtonDefinition::GREY_ACTION, NULL, @"Share", @selector(navbarActionShare));
    navbar_share_new_def_ = ButtonDefinition(
        ButtonDefinition::GREEN_ACTION, NULL, @"Share to New", @selector(navbarActionShareNew));
    navbar_share_existing_def_ = ButtonDefinition(
        ButtonDefinition::GREEN_ACTION, NULL, @"Share to Existing", @selector(navbarActionShareExisting));
    navbar_unmute_def_ = ButtonDefinition(
        ButtonDefinition::GREY_ACTION, NULL, @"Unmute", @selector(navbarActionUnmute));
    navbar_unshare_def_ = ButtonDefinition(
        ButtonDefinition::RED_ACTION, NULL, @"Unshare", @selector(navbarActionUnshare));
 }

  return self;
}

- (float)intrinsicHeight {
  return tray_map_[navbar_state_].frameHeight;
}

- (id<NavbarEnv>)envOrNull {
  if (self.userInteractionEnabled) {
    return env_;
  }
  return NULL;
}

// A level of indirection between navbar button presses and the
// possibly-changing env_.
- (void)navbarAction {
  [self.envOrNull navbarAction];
}
- (void)navbarAddPhotos {
  [self.envOrNull navbarAddPhotos];
}
- (void)navbarAutoSuggest {
  [self.envOrNull navbarAutoSuggest];
}
- (void)navbarBack {
  [self.envOrNull navbarBack];
}
- (void)navbarDial {
  [self.envOrNull navbarDial];
}
- (void)navbarExit {
  [self.envOrNull navbarExit];
}
- (void)navbarRelatedConvos {
  [self.envOrNull navbarRelatedConvos];
}
- (void)navbarActionExit {
  [self.envOrNull navbarActionExit];
}
- (void)navbarActionExport {
  [self.envOrNull navbarActionExport];
}
- (void)navbarActionMute {
  [self.envOrNull navbarActionMute];
}
- (void)navbarActionRemove {
  [self.envOrNull navbarActionRemove];
}
- (void)navbarActionRemoveConvo {
  [self.envOrNull navbarActionRemoveConvo];
}
- (void)navbarActionShare {
  [self.envOrNull navbarActionShare];
}
- (void)navbarActionShareNew {
  [self.envOrNull navbarActionShareNew];
}
- (void)navbarActionShareExisting {
  [self.envOrNull navbarActionShareExisting];
}
- (void)navbarActionUnmute {
  [self.envOrNull navbarActionUnmute];
}
- (void)navbarActionUnshare {
  [self.envOrNull navbarActionUnshare];
}
- (void)navbarActionBack {
  [self.envOrNull navbarActionBack];
}

- (UIView*)hitTest:(CGPoint)point
         withEvent:(UIEvent*)event {
  // Allow the event to go to any UIControl subview. Otherwise, return NULL.
  UIView* v = [super hitTest:point withEvent:event];
  if ([v isKindOfClass:[UIControl class]]) {
    return v;
  }
  return NULL;
}

- (void)show {
  for (ButtonTrayMap::iterator iter = tray_map_.begin();
       iter != tray_map_.end();
       ++iter) {
    iter->second.alpha = 0;
  }
  BeginIgnoringInteractionEvents();
  [UIView animateWithDuration:kShowDuration
                        delay:0
                      options:UIViewAnimationOptionBeginFromCurrentState
                   animations:^{
      for (ButtonTrayMap::iterator iter = tray_map_.begin();
           iter != tray_map_.end();
           ++iter) {
        iter->second.alpha = 1;
      }
    }
                   completion:^(BOOL finished) {
      EndIgnoringInteractionEvents();
    }];
}

- (void)hide {
  BeginIgnoringInteractionEvents();
  [UIView animateWithDuration:kHideDuration
                        delay:0
                      options:UIViewAnimationOptionBeginFromCurrentState
                   animations:^{
      for (ButtonTrayMap::iterator iter = tray_map_.begin();
           iter != tray_map_.end();
           ++iter) {
        iter->second.alpha = 0;
      }
    }
                   completion:^(BOOL finished) {
      EndIgnoringInteractionEvents();
    }];
}

- (UIView*)createTrayOfType:(NavbarButtonType)type
                withButtons:(const vector<ButtonDefinition>&)buttons {
  UIView* tray = [UIView new];
  tray.autoresizesSubviews = YES;
  tray.autoresizingMask = UIViewAutoresizingFlexibleWidth;
  tray.backgroundColor = [UIColor clearColor];
  tray.frame = tray_frame_;
  tray.hidden = YES;
  [self addSubview:tray];

  vector<int> widths;
  vector<CGPoint> positions;
  if (type == BUTTON_COMPOSE) {
    DCHECK_EQ(buttons.size(), 1);
    tray.frame = CGRectMake(0, 0, self.frameWidth, kNavbarComposeHeight);

    UIImageView* bg = [[UIImageView alloc] initWithImage:kConvoSuggestionBar];
    bg.frame = tray.bounds;
    [tray addSubview:bg];

    const float w = int((self.frameWidth - kNavbarComposeLeftMargin * 2) / buttons.size());
    float last_pos = kNavbarComposeLeftMargin;
    for (int i = 0; i < buttons.size(); ++i) {
      widths.push_back(w);
      positions.push_back(CGPointMake(last_pos, 0));
      last_pos += w;
    }
  } else if (type == BUTTON_SINGLE_PHOTO) {
    const float height = kSinglePhotoBottomGradient.get().size.height;
    const float y = height - kSinglePhotoButtonHeight;
    tray.frame = CGRectMake(0, 0, self.frameWidth, height);
    UIImageView* gradient_bg = [[UIImageView alloc] initWithImage:kSinglePhotoBottomGradient];
    gradient_bg.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    gradient_bg.frame = tray.bounds;
    [tray addSubview:gradient_bg];

    // Only handles cases of all four buttons or just one.
    if (buttons.size() == 1) {
      widths.push_back(kSinglePhotoButtonWidth);
      positions.push_back(CGPointMake(0, y));
    } else {
      widths.push_back(kSinglePhotoRelatedConvosButtonWidth);
      widths.push_back(kSinglePhotoButtonWidth);
      widths.push_back(kSinglePhotoButtonMiddleWidth);
      widths.push_back(kSinglePhotoButtonWidth);
      positions.push_back(CGPointMake(0, y));
      positions.push_back(CGPointMake(widths[0] - 7, y));  // overlap the two buttons
      positions.push_back(CGPointMake(positions[1].x + widths[1], y));
      positions.push_back(CGPointMake(positions[2].x + widths[2], y));
    }
  } else {
    const float w = int(tray_frame_.size.width / kMaxButtonsInTray);
    int r = int(tray_frame_.size.width) % kMaxButtonsInTray;
    widths.push_back(w + (--r >= 0 ? 1 : 0));
    widths.push_back(w);
    widths.push_back(w);
    widths.push_back(w + r);
    positions.push_back(CGPointMake(0, 0));
    positions.push_back(CGPointMake(widths[0], 0));
    positions.push_back(CGPointMake(positions[1].x + widths[1], 0));
    positions.push_back(CGPointMake(positions[2].x + widths[2], 0));
  }

  float max_height = 0;
  vector<UIView*> views;
  for (int i = 0; i < buttons.size(); ++i) {
    UIView* b;
    if (i == 0) {
      b = NewNavControlLeftButton(buttons[i], type, widths[i], self);
    } else if (i == buttons.size() - 1) {
      b = NewNavControlRightButton(buttons[i], type, widths[i], self);
    } else {
      b = NewNavControlMiddleButton(buttons[i], type, i, widths[i], self);
    }
    b.frameOrigin = positions[i];
    b.tag = i + 1;  // can't use tag 0!
    [tray addSubview:b];
    views.push_back(b);
    max_height = std::max<float>(max_height, b.frameHeight);
  }

  for (int i = 0; i < views.size(); ++i) {
    UIView* v = views[i];
    v.frameTop = positions[i].y + (max_height - v.frameHeight) / 2;
    if (v.frameLeft < 0) {
      v.frameLeft = 0;
    } else if (v.frameRight > tray.boundsWidth) {
      v.frameRight = tray.boundsWidth;
    }
  }

  return tray;
}

- (UIView*)createTrayForState:(NavbarState)state {
  switch (state) {
    case NAVBAR_UNINITIALIZED:
      DIE("cannot create a tray for state uninitialized");
      return NULL;
    case NAVBAR_CAMERA_PHOTO :
      return [self createTrayOfType:BUTTON_SINGLE_PHOTO
                        withButtons:L(navbar_remove_photos_def_)];
    case NAVBAR_COMPOSE :
      return [self createTrayOfType:BUTTON_COMPOSE
                        withButtons:L(navbar_auto_suggest_def_)];
    case NAVBAR_CONVERSATIONS_PHOTO :
      return [self createTrayOfType:BUTTON_SINGLE_PHOTO
                        withButtons:L(navbar_related_convos_def_, navbar_unshare_def_,
                                      navbar_export_def_, navbar_forward_def_)];
    case NAVBAR_PROFILE_PHOTO :
      return [self createTrayOfType:BUTTON_SINGLE_PHOTO
                        withButtons:L(navbar_related_convos_def_, navbar_remove_photos_def_,
                                      navbar_export_def_, navbar_share_def_)];
  }
}

- (void)setNewState:(NavbarState)new_state {
  if (!ContainsKey(tray_map_, new_state)) {
    tray_map_[new_state] = [self createTrayForState:new_state];
  }
  UIView* show_tray = tray_map_[new_state];

  // If we're already in the right state, return.
  if (navbar_state_ == new_state) {
    return;
  }
  navbar_state_ = new_state;

  UIView* hide_tray = current_tray_ != show_tray ? current_tray_ : NULL;
  current_tray_ = show_tray;

  if (hide_tray && hide_tray != show_tray) {
    hide_tray.hidden = YES;
  }
  show_tray.hidden = NO;

  self.frameHeight = show_tray.frameHeight;
}

- (void)showCameraPhotoItems {
  [self setNewState:NAVBAR_CAMERA_PHOTO];
}

- (void)showComposeItems {
  [self setNewState:NAVBAR_COMPOSE];
}

- (void)showConversationsPhotoItems {
  [self setNewState:NAVBAR_CONVERSATIONS_PHOTO];
}

- (void)showProfilePhotoItems {
  [self setNewState:NAVBAR_PROFILE_PHOTO];
}

@end  // Navbar
