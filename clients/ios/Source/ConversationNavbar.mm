// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "AttrStringUtils.h"
#import "ConversationNavbar.h"
#import "LayoutUtils.h"
#import "Logging.h"
#import "MathUtils.h"
#import "PhotoView.h"
#import "ScopedRef.h"
#import "STLUtils.h"
#import "StringUtils.h"
#import "UIStyle.h"
#import "UIView+geometry.h"
#import "ValueUtils.h"

namespace {

const int kReplyToTag = 1;

const float kDuration = 0.300;
const float kMinHeight = 44;
const float kRightMargin = 7;
const float kBottomMargin = 6;
const float kButtonMargin = 7;
const float kButtonTextTopMargin = 35;
const float kExtraTextHeight = 20;
const float kNotificationFadeSeconds = 1.5;
const float kReplyToThumbnailDim = 56;
const float kNavbarButtonHeight = 30;
const float kDrawerLatchMargin = 20;
const float kDrawerLatchMultiple = 2.5;

const float kNavbarActionLeftMargin = 8;
const float kNavbarActionTopMargin = 7;
const float kNavbarActionWidth = 101;

const float kMessageDrawerHeight = 56;
const float kMessageDrawerButtonTitleTopMargin = 32;

LazyStaticImage kConvoBarIconAdd(
    @"convo-bar-icon-add.png");
LazyStaticImage kConvoBarIconExit(
    @"convo-bar-icon-x.png");
LazyStaticImage kConvoBarButtonGrey(
    @"convo-bar-button-grey.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage kConvoBarButtonGreyActive(
    @"convo-bar-button-grey-active.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage kConvoBarButtonSend(
    @"convo-bar-button-send.png", UIEdgeInsetsMake(6, 4, 6, 4));
LazyStaticImage kConvoBarButtonSendActive(
    @"convo-bar-button-send-active.png", UIEdgeInsetsMake(6, 4, 6, 4));
LazyStaticImage kConvoBarButtonUnavailable(
    @"convo-bar-button-unavailable.png", UIEdgeInsetsMake(6, 4, 6, 4));
LazyStaticImage kConvoBarTextField(
    @"convo-bar-text-field.png", UIEdgeInsetsMake(6, 4, 6, 4));
LazyStaticImage kConvoBarTextFieldUnavailable(
    @"convo-bar-text-field-unavailable.png", UIEdgeInsetsMake(6, 4, 6, 4));

LazyStaticImage kConvoBarAddPeople(
    @"convo-bar-edit-people.png");
LazyStaticImage kConvoBarAddPeopleActive(
    @"convo-bar-edit-people-active.png");
LazyStaticImage kConvoBarAddPhotos(
    @"convo-bar-add-photos.png");
LazyStaticImage kConvoBarAddPhotosActive(
    @"convo-bar-add-photos-active.png");
LazyStaticImage kConvoBarUseCamera(
    @"convo-bar-use-camera.png");
LazyStaticImage kConvoBarUseCameraActive(
    @"convo-bar-use-camera-active.png");

LazyStaticImage kConvoMuteConvo(
    @"convo-mute-convo.png");
LazyStaticImage kConvoMuteConvoActive(
    @"convo-mute-convo-active.png");
LazyStaticImage kConvoRemoveConvo(
    @"convo-remove-convo.png");
LazyStaticImage kConvoRemoveConvoActive(
    @"convo-remove-convo-active.png");
LazyStaticImage kConvoUnmuteConvo(
    @"convo-unmute-convo.png");
LazyStaticImage kConvoUnmuteConvoActive(
    @"convo-unmute-convo-active.png");

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

LazyStaticCTFont kCommentFont = {
  kProximaNovaRegular, 16,
};
LazyStaticUIFont kConvoNavbarButtonUIFont = {
  kProximaNovaBold, 15,
};
LazyStaticUIFont kConvoNavbarDrawerButtonUIFont = {
  kProximaNovaRegular, 12
};

LazyStaticHexColor kCommentTextColor = { "#000000" };
LazyStaticHexColor kConvoNavbarButtonColor = { "#ffffffff" };
LazyStaticHexColor kConvoNavbarButtonActiveColor = { "#ffffff7f" };
LazyStaticHexColor kConvoNavbarButtonDisabledColor = { "#ffffff7f" };
LazyStaticHexColor kMessageDrawerBackgroundColor = { "#2f2e2e" };
LazyStaticHexColor kMessageDrawerTopButtonColor = { "#cfcbcb" };
LazyStaticHexColor kMessageDrawerTopButtonActiveColor = { "#cfcbcb7f" };
LazyStaticHexColor kMessageDrawerButtonColor = { "#9f9c9c" };
LazyStaticHexColor kMessageDrawerButtonActiveColor = { "#9f9c9c7f" };

LazyStaticDict kCommentAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)kCommentFont.get(),
        kCTForegroundColorAttributeName,
        (__bridge id)kCommentTextColor.get().CGColor);
  }
};

UIButton* NewConversationNavbarDrawerButton(
    NSString* title, UIImage* image, UIImage* active,
    bool top_row, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.titleLabel.font = kConvoNavbarDrawerButtonUIFont;
  [b setTitle:title
     forState:UIControlStateNormal];
  if (top_row) {
    [b setTitleColor:kMessageDrawerTopButtonColor.get()
            forState:UIControlStateNormal];
    [b setTitleColor:kMessageDrawerTopButtonActiveColor.get()
            forState:UIControlStateHighlighted];
  } else {
    [b setTitleColor:kMessageDrawerButtonColor.get()
            forState:UIControlStateNormal];
    [b setTitleColor:kMessageDrawerButtonActiveColor.get()
            forState:UIControlStateHighlighted];
  }
  b.titleEdgeInsets = UIEdgeInsetsMake(kMessageDrawerButtonTitleTopMargin, 0, 0, 0);
  [b setBackgroundImage:image
               forState:UIControlStateNormal];
  [b setBackgroundImage:active
               forState:UIControlStateHighlighted];
  [b sizeToFit];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

UIButton* NewConversationNavbarActionButton(
    NSString* title, UIImage* bg_image, UIImage* bg_active,
    float width, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.showsTouchWhenHighlighted = NO;
  b.frameSize = CGSizeMake(width, bg_image.size.height);

  b.titleLabel.font = kConvoNavbarButtonUIFont.get();
  [b setTitle:title forState:UIControlStateNormal];
  [b setTitleColor:kConvoNavbarButtonColor.get()
          forState:UIControlStateNormal];
  [b setTitleColor:kConvoNavbarButtonActiveColor.get()
          forState:UIControlStateHighlighted];
  [b setTitleColor:kConvoNavbarButtonDisabledColor.get()
          forState:UIControlStateDisabled];
  if (bg_image) {
    [b setBackgroundImage:bg_image forState:UIControlStateNormal];
  }
  if (bg_active) {
    [b setBackgroundImage:bg_active forState:UIControlStateHighlighted];
  }

  if (target && selector) {
    [b addTarget:target
          action:selector
       forControlEvents:UIControlEventTouchUpInside];
  } else {
    b.enabled = NO;
  }
  return b;
}

UIButton* NewConversationNavbarIconButton(
    UIImage* fg_normal, UIImage* fg_active,
    UIImage* bg_normal, UIImage* bg_active,
    float width, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.frameSize = CGSizeMake(width, kNavbarButtonHeight);

  if (bg_normal) {
    b.contentEdgeInsets = UIEdgeInsetsMake(
        (b.frameHeight - bg_normal.size.height), 0, 0, 0);
  }

  const float x = (b.frameWidth - fg_normal.size.width) / 2;
  const float y = b.frameHeight - fg_normal.size.height;
  [b setImage:fg_normal forState:UIControlStateNormal];
  b.imageEdgeInsets = UIEdgeInsetsMake(0, x, y, x);
  if (fg_active) {
    [b setImage:fg_active forState:UIControlStateHighlighted];
  }
  if (bg_normal) {
    [b setBackgroundImage:bg_normal
                 forState:UIControlStateNormal];
    [b setBackgroundImage:bg_normal
                 forState:UIControlStateDisabled];
  }
  if (bg_active) {
    [b setBackgroundImage:bg_active
                 forState:UIControlStateHighlighted];
  }
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

UIButton* NewConversationNavbarTextButton(
    NSString* title, UIImage* bg_normal, UIImage* bg_active,
    float width, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  DCHECK_EQ(bg_normal.size.height, bg_active.size.height);
  b.frameSize = CGSizeMake(width, bg_normal.size.height);

  b.titleLabel.font = kConvoNavbarButtonUIFont.get();
  [b setTitle:title forState:UIControlStateNormal];
  [b setTitleColor:kConvoNavbarButtonColor
          forState:UIControlStateNormal];
  [b setTitleColor:kConvoNavbarButtonActiveColor
          forState:UIControlStateHighlighted];
  [b setTitleColor:kConvoNavbarButtonDisabledColor
          forState:UIControlStateDisabled];

  [b setBackgroundImage:bg_normal
               forState:UIControlStateNormal];
  [b setBackgroundImage:bg_active
               forState:UIControlStateHighlighted];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

UIButton* NewConversationNavbarAdd(id target, SEL selector) {
  return NewConversationNavbarIconButton(
      kConvoBarIconAdd, NULL,
      kConvoBarButtonGrey, kConvoBarButtonGreyActive, 32, target, selector);
}

UIButton* NewConversationNavbarExit(bool background, id target, SEL selector) {
  return NewConversationNavbarIconButton(
      kConvoBarIconExit, NULL,
      kConvoBarButtonGrey, kConvoBarButtonGreyActive, 32, target, selector);
}

UIButton* NewConversationNavbarExport(id target, SEL selector) {
  return NewConversationNavbarActionButton(
      @"Export", kActionBarButtonGreyMiddle, kActionBarButtonGreyMiddleActive,
      kNavbarActionWidth, target, selector);
}

UIButton* NewConversationNavbarSend(id target, SEL selector) {
  return NewConversationNavbarTextButton(
      @"Send", kConvoBarButtonSend, kConvoBarButtonSendActive,
      60, target, selector);
}

UIButton* NewConversationNavbarShare(id target, SEL selector) {
  return NewConversationNavbarActionButton(
      @"Forward", kActionBarButtonGreyRight, kActionBarButtonGreyRightActive,
      kNavbarActionWidth, target, selector);
}

UIButton* NewConversationNavbarUnshare(id target, SEL selector) {
  return NewConversationNavbarActionButton(
      @"Unshare", kActionBarButtonRedLeft, kActionBarButtonRedLeftActive,
      kNavbarActionWidth, target, selector);
}

}  // namespace

@implementation ConversationNavbar

- (id)initWithEnv:(id<ConversationNavbarEnv>)env {
  if (self = [super init]) {
    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleTopMargin;

    env_ = env;

    navbar_state_ = CONVO_NAVBAR_MESSAGE;

    UIToolbar* bg_toolbar = [UIToolbar new];
    bg_toolbar.barStyle = UIBarStyleBlack;
    bg_toolbar.translucent = YES;
    background_ = bg_toolbar;
    background_.autoresizesSubviews = YES;
    [self addSubview:background_];

    top_drawer_ = [UIView new];
    top_drawer_.clipsToBounds = YES;
    top_drawer_.autoresizesSubviews = YES;
    top_drawer_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    top_drawer_.frameHeight = 0;
    top_drawer_.backgroundColor = kMessageDrawerBackgroundColor;
    [self addSubview:top_drawer_];

    action_tray_ = [UIView new];
    action_tray_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    [self addSubview:action_tray_];

    export_ = NewConversationNavbarExport(env_, @selector(navbarExport:));
    [action_tray_ addSubview:export_];

    share_ = NewConversationNavbarShare(env_, @selector(navbarShare:));
    [action_tray_ addSubview:share_];

    unshare_ = NewConversationNavbarUnshare(env_, @selector(navbarUnshare:));
    [action_tray_ addSubview:unshare_];

    UIView* const kActionTrayOrder[] = {
      unshare_, export_, share_,
    };
    kActionTrayOrder[0].frameLeft = kNavbarActionLeftMargin;
    kActionTrayOrder[0].frameTop = kNavbarActionTopMargin;
    for (int i = 1; i < ARRAYSIZE(kActionTrayOrder); ++i) {
      kActionTrayOrder[i].frameLeft = kActionTrayOrder[i - 1].frameRight;
      kActionTrayOrder[i].frameTop = kActionTrayOrder[i - 1].frameTop;
    }

    message_tray_ = [UIView new];
    message_tray_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    [self addSubview:message_tray_];

    text_container_ =
        [[UIImageView alloc] initWithImage:kConvoBarTextField];
    text_container_.userInteractionEnabled = YES;
    [message_tray_ addSubview:text_container_];
    text_spacing_ = kMinHeight - text_container_.frameHeight;

    text_view_ = [TextView new];
    text_view_.contentInset = UIEdgeInsetsMake(0, 6, 0, 6);
    text_view_.delegate = self;
    text_view_.keyboardAppearance = UIKeyboardAppearanceAlert;
    [text_view_ setAttributes:kCommentAttributes];
    [message_tray_ addSubview:text_view_];

    add_ = NewConversationNavbarAdd(self, @selector(showBottomDrawer));
    [message_tray_ addSubview:add_];

    exit_ = NewConversationNavbarExit(false, self, @selector(hideBottomDrawer));
    [message_tray_ addSubview:exit_];

    send_ = NewConversationNavbarSend(env_, @selector(navbarSend:));
    send_.enabled = NO;
    [message_tray_ addSubview:send_];

    bottom_drawer_ = [UIView new];
    bottom_drawer_.clipsToBounds = YES;
    bottom_drawer_.autoresizesSubviews = YES;
    bottom_drawer_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    bottom_drawer_.frameHeight = 0;
    [self addSubview:bottom_drawer_];

    use_camera_ = NewConversationNavbarDrawerButton(
        @"Use Camera", kConvoBarUseCamera, kConvoBarUseCameraActive,
        true, env_, @selector(navbarUseCamera:));
    [bottom_drawer_ addSubview:use_camera_];

    add_people_ = NewConversationNavbarDrawerButton(
        @"Add People", kConvoBarAddPeople, kConvoBarAddPeopleActive,
        true, env_, @selector(navbarAddPeople:));
    [bottom_drawer_ addSubview:add_people_];

    add_photos_ = NewConversationNavbarDrawerButton(
        @"Add Photos", kConvoBarAddPhotos, kConvoBarAddPhotosActive,
        true, env_, @selector(navbarAddPhotos:));
    [bottom_drawer_ addSubview:add_photos_];

    self.replyToPhoto = NULL;
    self.frame = CGRectMake(0, -kMinHeight, 0, kMinHeight);
    top_drawer_.frameTop = 0;
  }

  return self;
}

- (void)configureFromViewpoint:(const ViewpointHandle&)vh {
  [remove_ removeFromSuperview];
  [mute_ removeFromSuperview];

  remove_ = NewConversationNavbarDrawerButton(
      @"Remove Convo", kConvoRemoveConvo, kConvoRemoveConvoActive,
      false, env_, @selector(navbarRemoveConvo:));
  if (vh->label_muted()) {
    mute_ = NewConversationNavbarDrawerButton(
        @"Unmute Convo", kConvoUnmuteConvo, kConvoUnmuteConvoActive,
        false, env_, @selector(navbarUnmuteConvo:));
  } else {
    mute_ = NewConversationNavbarDrawerButton(
        @"Mute Convo", kConvoMuteConvo, kConvoMuteConvoActive,
        false, env_, @selector(navbarMuteConvo:));
  }

  [top_drawer_ addSubview:remove_];
  [top_drawer_ addSubview:mute_];

  const float button_width = self.boundsWidth / 3;
  const float button_spacing = button_width / 3;
  remove_.frameWidth = button_width;
  remove_.frameLeft = button_spacing;
  mute_.frameWidth = button_width;
  mute_.frameLeft = remove_.frameRight + button_spacing;
}

- (BOOL)becomeFirstResponder {
  return [text_view_ becomeFirstResponder];
}

- (CGRect)visibleFrame {
  CGRect f = self.frame;
  f.origin.y = self.superview.frame.size.height - f.size.height;

  switch (navbar_state_) {
    case CONVO_NAVBAR_MESSAGE:
      break;
    case CONVO_NAVBAR_MESSAGE_ACTIVE:
      f.origin.y = keyboard_frame_.origin.y - f.size.height;
      break;
    case CONVO_NAVBAR_ACTION:
      break;
    case CONVO_NAVBAR_BOTTOM_DRAWER:
      f.origin.y -= kMessageDrawerHeight;
      break;
    case CONVO_NAVBAR_TOP_DRAWER:
      break;
  }

  return f;
}

- (CGRect)hiddenFrame {
  CGRect f = self.frame;
  f.origin.y += self.superview.frame.size.height - f.size.height;
  return f;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  [self layoutMessageTray:f];
}

- (UIView*)hitTest:(CGPoint)point
         withEvent:(UIEvent*)event {
  // If the message drawer is visible, we specifically must hittest
  // for the drawer action buttons as they fall outside the navbar's
  // frame.
  if (navbar_state_ == CONVO_NAVBAR_TOP_DRAWER) {
    if ([remove_ hitTest:[remove_ convertPoint:point fromView:self] withEvent:event]) {
      return remove_;
    } else if ([mute_ hitTest:[mute_ convertPoint:point fromView:self] withEvent:event]) {
      return mute_;
    }
  } else if (navbar_state_ == CONVO_NAVBAR_BOTTOM_DRAWER) {
    if ([use_camera_ hitTest:[use_camera_ convertPoint:point fromView:self] withEvent:event]) {
      return use_camera_;
    } else if ([add_photos_ hitTest:[add_photos_ convertPoint:point fromView:self] withEvent:event]) {
      return add_photos_;
    } else if ([add_people_ hitTest:[add_people_ convertPoint:point fromView:self] withEvent:event]) {
      return add_people_;
    }
  }
  return [super hitTest:point withEvent:event];
}

- (void)layoutMessageTray:(CGRect)f {
  const float activation_fraction = self.activationFraction;

  float action_alpha = 0;
  float action_top = action_tray_.frameHeight;
  float message_alpha = 1;
  float message_top = 0;
  bool show_top_drawer = false;
  bool show_bottom_drawer = false;

  switch (navbar_state_) {
    case CONVO_NAVBAR_MESSAGE:
      break;
    case CONVO_NAVBAR_MESSAGE_ACTIVE:
      break;
    case CONVO_NAVBAR_ACTION:
      action_alpha = 1;
      action_top = 0;
      message_alpha = 0;
      message_top = message_tray_.frameHeight;
      break;
    case CONVO_NAVBAR_BOTTOM_DRAWER:
      show_bottom_drawer = true;
      break;
    case CONVO_NAVBAR_TOP_DRAWER:
      show_top_drawer = true;
      break;
  }

  action_tray_.alpha = action_alpha;
  action_tray_.frameTop = action_top;

  message_tray_.alpha = message_alpha;
  message_tray_.frameTop = message_top;

  bottom_drawer_.frameHeight = show_bottom_drawer ? kMessageDrawerHeight : 0;
  bottom_drawer_.frameTop = self.frameHeight;

  {
    CGRect f = self.bounds;
    f.size.height += bottom_drawer_.frameHeight;
    if (!CGRectEqualToRect(background_.frame, f)) {
      background_.frame = f;
    }
  }

  if (!show_top_drawer) {
    top_drawer_.frame = CGRectMake(0, 0, self.frameWidth, 0);
  }

  add_.hidden = show_bottom_drawer ? YES : NO;
  add_.frameBottom = self.frameHeight - kBottomMargin;
  add_.frameLeft = kButtonMargin;

  send_.frameLeft = self.frameWidth - send_.frameWidth - kRightMargin;
  send_.frameBottom = self.frameHeight - kBottomMargin;

  exit_.hidden = show_bottom_drawer ? NO : YES;
  exit_.frameBottom = self.frameHeight - kBottomMargin;
  exit_.frameLeft = kButtonMargin;

  if (reply_to_photo_) {
    reply_to_photo_.frame =
        CGRectMake(int(LinearInterp<float>(
                           activation_fraction, 0, 1,
                           self.boundsWidth, self.boundsWidth - 4 - kReplyToThumbnailDim)),
                   -kReplyToThumbnailDim - 2,
                   kReplyToThumbnailDim, kReplyToThumbnailDim);
  }

  const float text_left = std::max(add_.frameRight + kButtonMargin, exit_.frameRight);
  const float text_height = std::max(kConvoBarTextField.get().size.height,
                                     self.frameHeight - text_spacing_);
  text_container_.frame =
      CGRectMake(text_left, self.frameHeight - kBottomMargin - text_height,
                 send_.frameLeft - text_left - kButtonMargin, text_height);
  text_view_.frame = text_container_.frame;

  const float button_width = self.boundsWidth / 3;
  use_camera_.frameWidth = button_width;
  add_photos_.frameWidth = button_width;
  add_people_.frameWidth = button_width;
  add_photos_.frameLeft = use_camera_.frameRight;
  add_people_.frameLeft = add_photos_.frameRight;

  [self adjustContentInset];
}

- (float)activationFraction {
  float activation_fraction = 0.0;
  if (keyboard_frame_.origin.y > 0) {
    if (keyboard_frame_.origin.y != self.superview.frame.size.height) {
      activation_fraction =
          (self.superview.frameHeight - self.frameBottom) /
          (self.superview.frameHeight - keyboard_frame_.origin.y);
    } else {
      // This will always be the case when an external keyboard is
      // present and the on-screen keyboard doesn't display. The
      // on-screen keyboard frame stays located just off the screen
      // below full screen height.
      activation_fraction = 1;
    }
  } else if (navbar_state_ == CONVO_NAVBAR_BOTTOM_DRAWER) {
    activation_fraction =
        (self.superview.frameHeight - self.frameBottom) / kMessageDrawerHeight;
  }

  return activation_fraction;
}

// Adjust the text content inset so that the text is vertically
// centered if it is smaller than the text frame.
- (void)adjustContentInset {
  if (text_view_.contentHeight < text_view_.frameHeight) {
    text_view_.contentInsetTop =
        floorf((text_view_.frameHeight - text_view_.contentHeight) / 2);
  } else {
    text_view_.contentInsetTop = 0;
  }
}

- (void)willMoveToSuperview:(UIView*)new_superview {
  if (!new_superview) {
    keyboard_did_show_.Clear();
    keyboard_did_hide_.Clear();
    keyboard_will_show_.Clear();
    keyboard_will_hide_.Clear();
    return;
  }

  if (!keyboard_did_show_.get()) {
    keyboard_did_show_.Init(
        UIKeyboardDidShowNotification,
        ^(NSNotification* n) {
          keyboard_ = text_view_.inputAccessoryView.superview;
        });
  }
  if (!keyboard_did_hide_.get()) {
    keyboard_did_hide_.Init(
        UIKeyboardDidHideNotification,
        ^(NSNotification* n) {
          keyboard_.hidden = NO;
          keyboard_ = NULL;
        });
  }
  if (!keyboard_will_show_.get()) {
    keyboard_will_show_.Init(
        UIKeyboardWillShowNotification,
        ^(NSNotification* n) {
          const Dict d(n.userInfo);
          keyboard_window_frame_ =
              d.find_value(UIKeyboardFrameEndUserInfoKey).rect_value();
          // Convert the keyboard frame (in window coordinates) to the
          // superview's coordinates. This is necessary if the superview is
          // rotated.
          keyboard_frame_ =
              [self.superview convertRect:keyboard_window_frame_
                                 fromView:self.window];

          // Only process the will show notification if the comment input
          // field is the first responder and the keyboard is not already
          // visible.
          if (!keyboard_ && text_view_.isFirstResponder) {
            const double duration =
                d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
            const int curve =
                d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
            const int options =
                (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;
            BeginIgnoringInteractionEvents();
            [UIView animateWithDuration:duration
                                  delay:0
                                options:options
                             animations:^{
                [self setNavbarState:CONVO_NAVBAR_MESSAGE_ACTIVE animated:false];
              }
                             completion:^(BOOL finished) {
                EndIgnoringInteractionEvents();
              }];
          }
        });
  }
  if (!keyboard_will_hide_.get()) {
    keyboard_will_hide_.Init(
        UIKeyboardWillHideNotification,
        ^(NSNotification* n) {
          keyboard_frame_ = CGRectZero;
          keyboard_window_frame_ = CGRectZero;

          if (keyboard_) {
            const Dict d(n.userInfo);
            const double duration =
                d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
            const int curve =
                d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
            const int options =
                (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;
            BeginIgnoringInteractionEvents();
            [UIView animateWithDuration:duration
                                  delay:0
                                options:options
                             animations:^{
                ConversationNavbarState state =
                    navbar_state_ != CONVO_NAVBAR_MESSAGE_ACTIVE ?
                    navbar_state_ : CONVO_NAVBAR_MESSAGE;
                [self setNavbarState:state animated:false];
              }
                            completion:^(BOOL finished) {
                EndIgnoringInteractionEvents();
              }];
          }
        });
  }
}

- (BOOL)textViewShouldBeginEditing:(TextView*)text_view {
  return !IsIgnoringInteractionEvents();
}

- (void)textViewDidChange:(TextView*)text_view {
  const float max_height =
      (keyboard_frame_.origin.y > 0 ?
       keyboard_frame_.origin.y : self.superview.frameHeight);
  const float height =
      std::min(max_height,
               std::max(kMinHeight, text_view_.contentHeight + kExtraTextHeight));
  send_.enabled = text_view_.hasText;

  CGRect f = self.frame;
  const float bottom = CGRectGetMaxY(f);
  f.size.height = height;
  f.origin.y = bottom - f.size.height;

  if (!CGRectEqualToRect(self.frame, f)) {
    self.frame = f;
  } else {
    [self adjustContentInset];
  }

  changed_.Run();
}

- (bool)enabled {
  return text_view_.editable;
}

- (void)setEnabled:(bool)value {
  if (value == self.enabled) {
    return;
  }
  text_view_.editable = value;
  add_.enabled = value;
  export_.enabled = value;
  exit_.enabled = value;
  share_.enabled = value;
  unshare_.enabled = value;
  send_.enabled = text_view_.hasText && value;

  [add_ setBackgroundImage:value ? kConvoBarButtonGrey : kConvoBarButtonUnavailable
                  forState:UIControlStateNormal];
  [send_ setBackgroundImage:value ? kConvoBarButtonSend : kConvoBarButtonUnavailable
                   forState:UIControlStateNormal];
  text_container_.image = value ? kConvoBarTextField : kConvoBarTextFieldUnavailable;
  [self setPlaceholderText:value ? @"Add Message…" : @""];
}

- (void)show {
  self.frame = self.visibleFrame;
}

- (void)hide {
  self.frame = self.hiddenFrame;
}

- (void)setNavbarState:(ConversationNavbarState)new_state
              animated:(bool)animated {
  // Special case in event the keyboard is up and user clicks '+'
  // button. We rely on the keyboard_will_hide_ callback to set
  // the navbar frame within the keyboard animation.
  if (text_view_.isFirstResponder &&
      new_state != CONVO_NAVBAR_MESSAGE_ACTIVE) {
    navbar_state_ = new_state;
    [text_view_ resignFirstResponder];
    return;
  }

  ConversationNavbarState old_state = navbar_state_;
  navbar_state_ = new_state;

  if (animated) {
    BeginIgnoringInteractionEvents();
    [UIView animateWithDuration:kDuration
                          delay:0
                        options:UIViewAnimationOptionCurveEaseOut
                     animations:^{
        self.frame = self.visibleFrame;
        [self notifyNavbarReconfiguration:new_state fromState:old_state];
      }
                     completion:^(BOOL finished) {
        EndIgnoringInteractionEvents();
      }];
  } else {
    self.frame = self.visibleFrame;
    [self notifyNavbarReconfiguration:new_state fromState:old_state];
  }
}

- (void)notifyNavbarReconfiguration:(ConversationNavbarState)new_state
                          fromState:(ConversationNavbarState)old_state {
  // Send env messages about navbar reconfigurations.
  if ((old_state == CONVO_NAVBAR_BOTTOM_DRAWER ||
       old_state == CONVO_NAVBAR_TOP_DRAWER) &&
      (new_state != CONVO_NAVBAR_BOTTOM_DRAWER &&
       new_state != CONVO_NAVBAR_TOP_DRAWER)) {
    [env_ navbarHideDrawer];
  } else if (new_state == CONVO_NAVBAR_BOTTOM_DRAWER ||
             new_state == CONVO_NAVBAR_TOP_DRAWER) {
    [env_ navbarShowDrawer];
  }
  if (new_state == CONVO_NAVBAR_MESSAGE_ACTIVE &&
      old_state != new_state) {
    [env_ navbarBeginMessage];
  } else if (old_state == CONVO_NAVBAR_MESSAGE_ACTIVE &&
             old_state != new_state) {
    [env_ navbarEndMessage];
  }
}

- (void)showBottomDrawer {
  self.text = @"";
  self.replyToPhoto = NULL;
  [self setNavbarState:CONVO_NAVBAR_BOTTOM_DRAWER animated:true];
}

- (void)hideBottomDrawer {
  [self setNavbarState:CONVO_NAVBAR_MESSAGE animated:true];
}

- (void)showActionTray {
  [self setNavbarState:CONVO_NAVBAR_ACTION animated:true];
}

- (void)showMessageTray {
  [self setNavbarState:CONVO_NAVBAR_MESSAGE animated:true];
}

- (void)showNotificationGlow {
  self.backgroundColor = UIStyle::kNotificationGlowColor;

  [UIView animateWithDuration:kNotificationFadeSeconds
                   animations:^{
      self.backgroundColor = MakeUIColor(0, 0, 0, 0);
    }];
}

- (bool)actionTray {
  return navbar_state_ == CONVO_NAVBAR_ACTION;
}

- (bool)keyboardActive {
  return keyboard_frame_.size.width != 0 &&
      keyboard_frame_.size.height != 0;
}

- (CallbackSet*)changed {
  return &changed_;
}

- (float)contentInset {
  return self.superview.frameHeight - self.frameTop - top_drawer_.frameTop;
}

- (bool)topDrawerOpen {
  return navbar_state_ == CONVO_NAVBAR_TOP_DRAWER;
}

- (UIPanGestureRecognizer*)pan {
  return pan_;
}

- (void)setPan:(UIPanGestureRecognizer*)p {
  if (pan_ == p) {
    return;
  }
  if (pan_) {
    [pan_ removeTarget:self action:NULL];
  }
  pan_ = p;
  if (pan_) {
    [pan_ addTarget:self action:@selector(panned)];
  }
}

- (void)setPan:(UIPanGestureRecognizer*)p
    withOffset:(float)offset {
  if (navbar_state_ != CONVO_NAVBAR_MESSAGE) {
    return;
  }
  self.pan = p;
  navbar_state_ = CONVO_NAVBAR_TOP_DRAWER;
  pan_multiple_ = kDrawerLatchMultiple;
  relative_pan_y_ = self.frameTop + top_drawer_.frameTop -
                    [pan_ locationInView:self.superview].y + offset;
}

- (void)setPlaceholderText:(NSString*)text {
  text_view_.delegate = NULL;
  text_view_.placeholderAttrText = NewAttrString(
      ToString(text), kCommentFont, [UIColor lightGrayColor].CGColor);
  text_view_.delegate = self;
}

- (NSString*)text {
  return text_view_.editableText;
}

- (void)setText:(NSString*)text {
  if (ToSlice(self.text) == ToSlice(text)) {
    return;
  }
  text_view_.editableText = text;
  [self textViewDidChange:text_view_];
}

- (PhotoView*)replyToPhoto {
  return (PhotoView*)[reply_to_photo_ viewWithTag:kReplyToTag];
}

- (void)setReplyToPhoto:(PhotoView*)p {
  if (reply_to_photo_) {
    // If the keyboard is active, animate the photo with a duration;
    // otherwise animate with 0 duration.
    UIView* old_reply_to_photo = reply_to_photo_;
    [UIView animateWithDuration:self.keyboardActive ? 0.3 : 0
                          delay:0
                        options:UIViewAnimationOptionCurveEaseOut
                     animations:^{
        old_reply_to_photo.alpha = 0;
      }
                     completion:^(BOOL finished) {
        [old_reply_to_photo removeFromSuperview];
      }];
    reply_to_photo_ = NULL;
  }
  if (p) {
    reply_to_photo_ = NewReplyToShadow(p);
    reply_to_photo_.autoresizesSubviews = YES;
    p.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    p.tag = kReplyToTag;
    // The shadow path cannot be animated easily, so just remove it. It's just
    // an optimization.
    reply_to_photo_.layer.shadowPath = NULL;
    [self addSubview:reply_to_photo_];
    [self setPlaceholderText:@"Comment on Photo…"];

    // If the keyboard is active, animate the photo immediately.
    if (self.keyboardActive) {
      [UIView animateWithDuration:0.3
                       animations:^{
          reply_to_photo_.frame =
              CGRectMake(self.boundsWidth - 4 - kReplyToThumbnailDim,
                         -kReplyToThumbnailDim - 2,
                         kReplyToThumbnailDim, kReplyToThumbnailDim);
        }];
    }
  } else {
    [self setPlaceholderText:@"Add Message…"];
  }
}

- (void)panned {
  switch (pan_.state) {
    case UIGestureRecognizerStateBegan:
      // Pin the autocorrect view to the keyboard while the keyboard is being
      // dragged.
      if (keyboard_) {
        [text_view_ pinAutocorrectToKeyboard];
      } else if (navbar_state_ == CONVO_NAVBAR_TOP_DRAWER) {
        pan_multiple_ = 1;
        relative_pan_y_ = self.frameTop + top_drawer_.frameTop - [pan_ locationInView:self.superview].y;
      }
      break;
    case UIGestureRecognizerStateChanged: {
      const CGPoint p = [pan_ locationInView:self.superview];
      // Animate within a zero-duration block to prevent any implicit animation
      // on the keyboard frame from doing something else.
      [UIView animateWithDuration:0.0
                       animations:^{
          if (keyboard_) {
            const float min_y =
                CGRectGetMinY(keyboard_frame_) - self.frameHeight;
            const float max_y =
                CGRectGetMaxY(keyboard_frame_) - self.frameHeight;
            self.frameTop = std::min(std::max(p.y, min_y), max_y);
            keyboard_.frameTop = CGRectGetMaxY(
                [self.superview convertRect:self.frame toView:self.window]);
          } else {
            // If we're pulling the top drawer, it moves in direct
            // accordance with the delta from the touch location where it
            // was engaged.
            if (navbar_state_ == CONVO_NAVBAR_TOP_DRAWER) {
              const float min_y = self.frameTop - kMessageDrawerHeight * pan_multiple_;
              const float max_y = self.frameTop;
              // Divide by two to make pulling up the top drawer feel "stickier".
              const float y =
                  (std::min(std::max(p.y + relative_pan_y_, min_y), max_y) - self.frameTop);
              top_drawer_.frame = CGRectMake(0, y / pan_multiple_, self.frameWidth, -y / pan_multiple_);
            } else {
              // Otherwise, we're operating the bottom drawer. It
              // moves only when the touch location is at the top of
              // the drawer.
              const float min_y =
                  self.superview.frameHeight - kMessageDrawerHeight - self.frameHeight;
              const float max_y =
                  self.superview.frameHeight - self.frameHeight;
              self.frameTop = std::min(std::max(p.y, min_y), max_y);
            }
          }
        }];
      break;
    }
    case UIGestureRecognizerStateEnded:
      if (keyboard_) {
        if (keyboard_.frame.origin.y <= keyboard_window_frame_.origin.y) {
          return;
        }
      }
      relative_pan_y_ = 0;
      if ([pan_ velocityInView:self.window].y >= 0) {
        [UIView animateWithDuration:kDuration
                              delay:0
                            options:UIViewAnimationOptionCurveEaseOut
                         animations:^{
            if (keyboard_) {
              keyboard_.frame = CGRectOffset(
                  keyboard_window_frame_, 0, keyboard_window_frame_.size.height);
              keyboard_frame_ = CGRectZero;
              keyboard_window_frame_ = CGRectZero;
              navbar_state_ = CONVO_NAVBAR_MESSAGE;
              self.frame = self.visibleFrame;
              [env_ navbarEndMessage];
            } else if (navbar_state_ == CONVO_NAVBAR_TOP_DRAWER) {
              if (top_drawer_.frameTop > -kMessageDrawerHeight) {
                top_drawer_.frame = CGRectMake(0, 0, self.frameWidth, 0);
                [self setNavbarState:CONVO_NAVBAR_MESSAGE animated:false];
              } else {
                top_drawer_.frame = CGRectMake(0, -kMessageDrawerHeight, self.frameWidth, kMessageDrawerHeight);
                [self setNavbarState:CONVO_NAVBAR_TOP_DRAWER animated:false];
              }
            } else {
              const float open_y =
                  self.superview.frameHeight - kMessageDrawerHeight - self.frameHeight;
              if (self.frameTop > open_y + kDrawerLatchMargin) {
                [self setNavbarState:CONVO_NAVBAR_MESSAGE animated:false];
              } else {
                [self setNavbarState:CONVO_NAVBAR_BOTTOM_DRAWER animated:false];
              }
            }
          }
                         completion:^(BOOL finished) {
            // Animate within a zero-duration block to prevent any animation of
            // the keyboard.
            if (keyboard_) {
              [UIView animateWithDuration:0.0
                               animations:^{
                  [text_view_ resignFirstResponder];
                }];
              keyboard_.hidden = YES;
            }
          }];
      } else {
        [UIView animateWithDuration:kDuration
                              delay:0
                            options:UIViewAnimationOptionCurveEaseOut
                         animations:^{
            if (keyboard_) {
              keyboard_.frame = keyboard_window_frame_;
              [self setNavbarState:CONVO_NAVBAR_MESSAGE_ACTIVE animated:false];
            } else if (navbar_state_ == CONVO_NAVBAR_TOP_DRAWER) {
              if (top_drawer_.frameTop > -kMessageDrawerHeight) {
                top_drawer_.frame = CGRectMake(0, 0, self.frameWidth, 0);
                [self setNavbarState:CONVO_NAVBAR_MESSAGE animated:false];
              } else {
                top_drawer_.frame = CGRectMake(0, -kMessageDrawerHeight, self.frameWidth, kMessageDrawerHeight);
                [self setNavbarState:CONVO_NAVBAR_TOP_DRAWER animated:false];
              }
            } else {
              const float close_y =
                  self.superview.frameHeight - self.frameHeight;
              if (self.frameTop > close_y - kDrawerLatchMargin) {
                [self setNavbarState:CONVO_NAVBAR_MESSAGE animated:false];
              } else {
                [self setNavbarState:CONVO_NAVBAR_BOTTOM_DRAWER animated:false];
              }
            }
          }
                        completion:^(BOOL finished) {
            if (keyboard_) {
              [text_view_ pinAutocorrectToWindow];
            }
          }];
      }
      break;
    case UIGestureRecognizerStateCancelled:
    default:
      if (keyboard_) {
        [text_view_ pinAutocorrectToWindow];
      }
      break;
  }
}

@end  // ConversationNavbar
