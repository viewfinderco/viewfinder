// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "AttrStringUtils.h"
#import "BadgeView.h"
#import "Logging.h"
#import "STLUtils.h"
#import "UIStyle.h"
#import "UIView+geometry.h"
#import "ValueUtils.h"

namespace {

const float kConversationCornerRadius = 6.5;
const float kThumbnailDim = 40;
const float kThumbnailCorner = 2;
const float kEditButtonWidth = 56;
const float kEditButtonHeight = 28;
const float kEditButtonMargin = 8;
const float kEditButtonCornerRadius = 3;

const Vector4f kViewfinderOrangeRgb = ParseStaticRgbColor("#f89113");
const Vector4f kViewfinderBlueRgb = ParseStaticRgbColor("#1f13f8");
const Vector4f kShadowRgb = ParseStaticRgbColor("#2b2320cc");

LazyStaticHexColor kBigButtonColor = { "#faf7f7" };
LazyStaticHexColor kBigButtonShadowColor = { "#0000003f" };
LazyStaticHexColor kEditButtonColor = { "#ffffff" };
LazyStaticHexColor kEditButtonBackgroundColor = { "#00000033" };
LazyStaticHexColor kSignupButtonColor = { "#ffffff" };
LazyStaticHexColor kToolbarButtonColor = { "#3f3e3e" };
LazyStaticHexColor kToolbarButtonGreenColor = { "#00804b" };

float mutable_divider_size;
float mutable_gutter_spacing;

LazyStaticImage kBigButtonGrey(
    @"big_button_grey.png", UIEdgeInsetsMake(19, 4, 20, 5));
LazyStaticImage kBigButtonGreyPressed(
    @"big_button_grey_pressed.png", UIEdgeInsetsMake(19, 4, 20, 5));
LazyStaticImage kSignupButtonGreen(
    @"signup-button-green.png", UIEdgeInsetsMake(19, 4, 20, 5));
LazyStaticImage kSignupButtonGreenPressed(
    @"signup-button-green-pressed.png", UIEdgeInsetsMake(19, 4, 20, 5));
LazyStaticImage kSignupButtonGrey(
    @"signup-button-grey.png", UIEdgeInsetsMake(19, 4, 20, 5));
LazyStaticImage kSignupButtonGreyPressed(
    @"signup-button-grey-pressed.png", UIEdgeInsetsMake(19, 4, 20, 5));
LazyStaticImage kToolbarAddContact(
    @"title-bar-icon-addcontact-dark.png");
LazyStaticImage kToolbarBack(
    @"title-bar-icon-backarrow-dark.png");
LazyStaticImage kToolbarCompose(
    @"title-bar-icon-compose-dark.png");

LazyStaticGeneratedImage kEditButtonBackground = {^{
    const float width = kEditButtonWidth + kEditButtonMargin * 2;
    const float height = kEditButtonHeight + kEditButtonMargin * 2;
    UIGraphicsBeginImageContextWithOptions(CGSizeMake(width, height), NO, 0);
    CGContextRef context = UIGraphicsGetCurrentContext();

    const CGRect rect = CGRectMake(kEditButtonMargin, kEditButtonMargin,
                                   kEditButtonWidth, kEditButtonHeight);
    CGContextClearRect(context, rect);

    UIBezierPath* path =
    [UIBezierPath bezierPathWithRoundedRect:rect
                               cornerRadius:kEditButtonCornerRadius];
    CGContextAddPath(context, path.CGPath);
    CGContextSetFillColorWithColor(context, kEditButtonBackgroundColor.get().CGColor);
    CGContextFillPath(context);

    UIImage* image = UIGraphicsGetImageFromCurrentImageContext();
    UIGraphicsEndImageContext();
    return image;
  }
};

LazyStaticUIFont kBigButtonUIFont = {
  kProximaNovaBold, 20
};
LazyStaticUIFont kToolbarButtonSmallUIFont = {
  kProximaNovaRegular, 17
};
LazyStaticUIFont kToolbarButtonLargeUIFont = {
  kProximaNovaSemibold, 21
};
LazyStaticUIFont kEditButtonFont = {
  kProximaNovaSemibold, 16
};

UIImage* MakeThumbnailShadow(
    int width, int height, int border, float corner_radius,
    CGSize offset, float blur, const Vector4f& color) {
  const int image_width = width + border * 2;
  const int image_height = height + border * 2;

  UIGraphicsBeginImageContextWithOptions(
      CGSizeMake(image_width, image_height), NO, 0);
  CGContextRef context = UIGraphicsGetCurrentContext();

  UIColor* c = MakeUIColor(color);
  CGContextSetFillColorWithColor(context, c.CGColor);
  CGContextSetShadowWithColor(context, offset, blur, c.CGColor);

  const CGRect r = CGRectMake(border, border, width, height);
  UIBezierPath* path =
      [UIBezierPath bezierPathWithRoundedRect:r
                                 cornerRadius:corner_radius];
  CGContextAddPath(context, path.CGPath);
  CGContextFillPath(context);

  UIImage* image = UIGraphicsGetImageFromCurrentImageContext();
  UIGraphicsEndImageContext();
  return image;
}

UIImage* GradientImage(
    int height, bool opaque, const Array& colors,
    const vector<CGFloat>& locations) {
  CHECK_EQ(colors.size(), locations.size());

  UIGraphicsBeginImageContextWithOptions(CGSizeMake(1, height), opaque, 0);
  CGContextRef context = UIGraphicsGetCurrentContext();

  ScopedRef<CGColorSpaceRef> colorspace(CGColorSpaceCreateDeviceRGB());
  ScopedRef<CGGradientRef> gradient(
      CGGradientCreateWithColors(colorspace, colors, &locations[0]));
  CGContextDrawLinearGradient(
      context, gradient, CGPointMake(0, height - 0.5), CGPointMake(0, 0),
      kCGGradientDrawsBeforeStartLocation | kCGGradientDrawsAfterEndLocation);

  UIImage* image = UIGraphicsGetImageFromCurrentImageContext();
  UIGraphicsEndImageContext();
  return image;
}

// This mimics the red gradient background found on builtin iOS delete buttons
// (which is unfortunately not available to programmers).
UIImage* DeleteNormalBackground(int height) {
  return GradientImage(
      height, true,
      Array(MakeUIColor(0.667, 0.15, 0.152, 1.0).CGColor,
            MakeUIColor(0.841, 0.566, 0.566, 1.0).CGColor,
            MakeUIColor(0.75, 0.341, 0.345, 1.0).CGColor,
            MakeUIColor(0.592, 0.0, 0.0, 1.0).CGColor,
            MakeUIColor(0.592, 0.0, 0.0, 1.0).CGColor),
      L(0.0, 1.0, 0.582, 0.418, 0.346));
}

// This mimics the red gradient background (highlighted) found on builtin iOS
// delete buttons (which is unfortunately not available to programmers).
UIImage* DeleteHighlightedBackground(int height) {
  return GradientImage(
      height, true,
      Array(MakeUIColor(0.467, 0.009, 0.005, 1.0).CGColor,
            MakeUIColor(0.754, 0.562, 0.562, 1.0).CGColor,
            MakeUIColor(0.543, 0.212, 0.212, 1.0).CGColor,
            MakeUIColor(0.5, 0.153, 0.152, 1.0).CGColor,
            MakeUIColor(0.388, 0.004, 0.0, 1.0).CGColor),
      L(0.0, 1.0, 0.715, 0.513, 0.445));
}

UIImage* ConversationHeaderCap(UIColor* color, float corner_radius) {
  const float width = corner_radius * 2 + 1;
  const float height = corner_radius;
  UIGraphicsBeginImageContextWithOptions(CGSizeMake(width, height), NO, 0);
  CGContextRef context = UIGraphicsGetCurrentContext();

  const CGRect rect = CGRectMake(0, 0, width, height * 2);
  CGContextSetRGBFillColor(context, 0, 0, 0, 0);
  CGContextFillRect(context, rect);

  UIBezierPath* path =
      [UIBezierPath bezierPathWithRoundedRect:rect
                                 cornerRadius:corner_radius];
  CGContextAddPath(context, path.CGPath);
  CGContextSetFillColorWithColor(context, color.CGColor);
  CGContextFillPath(context);

  UIImage* image = UIGraphicsGetImageFromCurrentImageContext();
  UIGraphicsEndImageContext();
  return [image resizableImageWithCapInsets:
                  UIEdgeInsetsMake(0, corner_radius, 0, corner_radius)];
}

UIButton* NewTranslucentButton(
    UIImage* image, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  [b setImage:image
     forState:UIControlStateNormal];
  [b setImage:image
     forState:UIControlStateHighlighted];
  [b setBackgroundImage:MakeSolidColorImage(kTranslucentBackgroundColor)
               forState:UIControlStateNormal];
  [b setBackgroundImage:MakeSolidColorImage(kTranslucentHighlightedColor)
               forState:UIControlStateHighlighted];
  b.imageView.contentMode = UIViewContentModeScaleAspectFit;
  b.contentEdgeInsets = kTranslucentInsets;
  const int image_height = [kTranslucentFont lineHeight];
  b.frame = CGRectMake(
      0, 0,
      image.size.width * image_height / image.size.height +
      kTranslucentInsets.left + kTranslucentInsets.right,
      image_height + kTranslucentInsets.top + kTranslucentInsets.bottom);
  InitTranslucentLayer(b.layer);
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

UIBarButtonItem* NewToolbarItem(
    UIImage* image, UIImage* active, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.showsTouchWhenHighlighted = NO;
  b.frameSize = CGSizeMake(56, 44);
  [b setImage:image
     forState:UIControlStateNormal];
  if (active) {
    [b setImage:active
       forState:UIControlStateHighlighted];
  }
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return [[UIBarButtonItem alloc] initWithCustomView:b];
}

UIBarButtonItem* NewToolbarTitleItem(
    NSString* title, UIFont* font, UIColor* color,
    float width, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.frameSize = CGSizeMake(width, 44);
  b.titleLabel.font = font;
  [b setTitle:title
     forState:UIControlStateNormal];
  [b setTitleColor:color
          forState:UIControlStateNormal];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return [[UIBarButtonItem alloc] initWithCustomView:b];
}

UIButton* NewBigButton(
    NSString* title, UIColor* color, UIColor* shadow_color,
    UIImage* bg_normal, UIImage* bg_active,
    id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.contentEdgeInsets = UIEdgeInsetsMake(10, 13, 10, 13);
  b.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
  b.titleLabel.font = kBigButtonUIFont;
  b.titleLabel.shadowOffset = CGSizeMake(0, -1);
  [b setTitle:title
     forState:UIControlStateNormal];
  [b setTitleColor:color
          forState:UIControlStateNormal];
  if (shadow_color) {
    [b setTitleShadowColor:shadow_color
                  forState:UIControlStateNormal];
  }
  [b setBackgroundImage:bg_normal
               forState:UIControlStateNormal];
  [b setBackgroundImage:bg_active
               forState:UIControlStateHighlighted];
  if (target) {
    [b addTarget:target
          action:selector
       forControlEvents:UIControlEventTouchUpInside];
  }
  [b sizeToFit];
  b.frameHeight = bg_normal.size.height;
  return b;
}

UIButton* NewSignupButton(
    NSString* title, UIFont* font, UIColor* color,
    UIImage* bg_normal, UIImage* bg_active,
    id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.contentEdgeInsets = UIEdgeInsetsMake(10, 13, 10, 13);
  b.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
  b.titleLabel.font = font;
  [b setTitle:title
     forState:UIControlStateNormal];
  [b setTitleColor:color
          forState:UIControlStateNormal];
  [b setBackgroundImage:bg_normal
               forState:UIControlStateNormal];
  [b setBackgroundImage:bg_active
               forState:UIControlStateHighlighted];
  if (target) {
    [b addTarget:target
          action:selector
       forControlEvents:UIControlEventTouchUpInside];
  }
  [b sizeToFit];
  b.frameHeight = bg_normal.size.height;
  return b;
}

}  // unnamed namespace


LazyStaticUIFont UIStyle::kBadgeUIFont = {
  kProximaNovaBold, 10
};
LazyStaticUIFont UIStyle::kContactsButtonUIFont = {
  kProximaNovaBold, 16
};
LazyStaticUIFont UIStyle::kContactsCellUIFont = {
  kProximaNovaRegular, 16.66667
};
LazyStaticUIFont UIStyle::kContactsCellDetailUIFont = {
  kProximaNovaRegular, 12
};
LazyStaticCTFont UIStyle::kContactsHeaderFont = {
  kProximaNovaRegular, 17
};
LazyStaticCTFont UIStyle::kContactsListLabelFont = {
  kProximaNovaRegular, 18
};
LazyStaticUIFont UIStyle::kContactsListLabelUIFont = {
  kProximaNovaRegular, 18
};
LazyStaticCTFont UIStyle::kContactsListBoldLabelFont = {
  kProximaNovaBold, 18
};
LazyStaticUIFont UIStyle::kContactsListBoldLabelUIFont = {
  kProximaNovaBold, 18
};
LazyStaticCTFont UIStyle::kContactsListItalicFont = {
  kProximaNovaRegularItalic, 15
};
LazyStaticCTFont UIStyle::kContactsListSublabelFont = {
  kProximaNovaRegular, 12
};
LazyStaticCTFont UIStyle::kContactsListBoldSublabelFont = {
  kProximaNovaBold, 12
};
LazyStaticUIFont UIStyle::kContactsListButtonUIFont = {
  kProximaNovaBold, 14
};
LazyStaticUIFont UIStyle::kContactsListSectionUIFont = {
  kProximaNovaBold, 14
};
LazyStaticUIFont UIStyle::kContactsSubtitleUIFont = {
  kProximaNovaBold, 10
};
LazyStaticCTFont UIStyle::kConversationCaptionFont = {
  kProximaNovaRegular, 12,
};
LazyStaticCTFont UIStyle::kConversationMessageFont = {
  kProximaNovaRegular, 15,
};
LazyStaticCTFont UIStyle::kConversationSharePhotosFont = {
  kProximaNovaBold, 15,
};
LazyStaticCTFont UIStyle::kConversationTimeFont = {
  kProximaNovaRegularItalic, 12,
};
LazyStaticCTFont UIStyle::kConversationTitleFont = {
  kProximaNovaBold, 12,
};
LazyStaticCTFont UIStyle::kConversationUpdateFont = {
  kProximaNovaBold, 12,
};
LazyStaticCTFont UIStyle::kFollowerGroupBoldLabelFont = {
  kProximaNovaBold, 16
};
LazyStaticCTFont UIStyle::kFollowerGroupSublabelFont = {
  kProximaNovaRegular, 12
};
LazyStaticCTFont UIStyle::kFollowerGroupItalicSublabelFont = {
  kProximaNovaRegularItalic, 12
};
LazyStaticCTFont UIStyle::kTitleFont = {
  kProximaNovaBold, 12.84
};
LazyStaticUIFont UIStyle::kTitleUIFont = {
  kProximaNovaBold, 12.84
};
LazyStaticCTFont UIStyle::kSmallTitleFont = {
  kProximaNovaBold, 11.415
};
LazyStaticCTFont UIStyle::kSubtitleFont = {
  kProximaNovaRegular, 11.415
};
LazyStaticUIFont UIStyle::kSubtitleUIFont = {
  kProximaNovaRegular, 11.415
};
LazyStaticCTFont UIStyle::kTimeagoFont = {
  kProximaNovaRegularItalic, 11.415
};
LazyStaticCTFont UIStyle::kHeadingFont = {
  kProximaNovaRegular, 29
};
LazyStaticUIFont UIStyle::kHeadingUIFont = {
  kProximaNovaRegular, 29
};
LazyStaticUIFont UIStyle::kLoginSignupButtonUIFont = {
  kProximaNovaBold, 17
};
LazyStaticUIFont UIStyle::kLoginSignupEntryUIFont = {
  kProximaNovaRegular, 15
};
LazyStaticUIFont UIStyle::kSettingsCellUIFont = {
  kProximaNovaRegular, 17
};
LazyStaticUIFont UIStyle::kSettingsCellDetailUIFont = {
  kProximaNovaRegular, 12
};
LazyStaticCTFont UIStyle::kSettingsFooterFont = {
  kProximaNovaRegular, 13
};
LazyStaticCTFont UIStyle::kSettingsFooterBoldFont = {
  kProximaNovaBold, 13
};
LazyStaticCTFont UIStyle::kSettingsHeaderFont = {
  kProximaNovaBold, 17
};
LazyStaticUIFont UIStyle::kShareLabelUIFont = {
  kProximaNovaRegular, 14
};
LazyStaticUIFont UIStyle::kShareBoldLabelUIFont = {
  kProximaNovaBold, 14
};
LazyStaticUIFont UIStyle::kShareSublabelUIFont = {
  kProximaNovaRegular, 12
};
LazyStaticUIFont UIStyle::kShareBoldSublabelUIFont = {
  kProximaNovaBold, 12
};
LazyStaticUIFont UIStyle::kSummaryTitleUIFont = {
  kProximaNovaBold, 18
};

LazyStaticImage UIStyle::kBadgeAllSelected(
    @"badge-all-selected.png");
LazyStaticImage UIStyle::kBadgeAllUnselected(
    @"badge-all-unselected.png");
LazyStaticImage UIStyle::kBadgeDisconnected(
    @"badge-disconnected.png");
LazyStaticImage UIStyle::kBadgeEmpty(
    @"badge-empty.png", UIEdgeInsetsMake(0, 11, 0, 11));
LazyStaticImage UIStyle::kBadgeEmptyBlue(
    @"badge-empty-blue.png", UIEdgeInsetsMake(0, 11, 0, 11));
LazyStaticImage UIStyle::kBadgeEmptyBlueCheckmark(
    @"badge-empty-blue-checkmark.png", UIEdgeInsetsMake(0, 11, 0, 11));
LazyStaticImage UIStyle::kBadgeSelected(
    @"badge-selected.png");
LazyStaticImage UIStyle::kBadgeUnselected(
    @"badge-unselected.png");
LazyStaticImage UIStyle::kCameraAutofocus0(
    @"camera-autofocus0.png");
LazyStaticImage UIStyle::kCameraAutofocus1(
    @"camera-autofocus1.png");
LazyStaticImage UIStyle::kCameraAutofocusSmall0(
    @"camera-autofocus-small0.png");
LazyStaticImage UIStyle::kCameraAutofocusSmall1(
    @"camera-autofocus-small1.png");
LazyStaticImage UIStyle::kCameraFlash(
    @"camera-flash.png");
LazyStaticImage UIStyle::kCameraToggle(
    @"camera-toggle.png");
LazyStaticImage UIStyle::kCheckmark(
    @"checkmark.png");
LazyStaticImage UIStyle::kContactsCellBackground1(
    @"contacts-cell-background1.png", UIEdgeInsetsMake(3, 3, 3, 3));
LazyStaticImage UIStyle::kContactsListSearch(
    @"contacts-list-search.png");
LazyStaticImage UIStyle::kContactsListSectionHeader(
    @"contacts-list-section-header.png");
LazyStaticGeneratedImage UIStyle::kConvoHeaderCap = {^{
    return ConversationHeaderCap(
        [UIColor whiteColor], kConversationCornerRadius);
  }
};
LazyStaticImage UIStyle::kConvoEditIconGrey(
    @"convo-icon-edit-grey.png");
LazyStaticImage UIStyle::kConvoEditIconWhite(
    @"convo-icon-edit-white.png");
LazyStaticImage UIStyle::kCornerBottomLeft(
    @"corner-bottom-left.png");
LazyStaticImage UIStyle::kCornerBottomRight(
    @"corner-bottom-right.png");
LazyStaticImage UIStyle::kCornerTopLeft(
    @"corner-top-left.png");
LazyStaticImage UIStyle::kCornerTopRight(
    @"corner-top-right.png");
LazyStaticGeneratedImage UIStyle::kDeleteHighlightedBackground = {^{
    return DeleteHighlightedBackground(44);
  }
};
LazyStaticGeneratedImage UIStyle::kDeleteNormalBackground = {^{
    return DeleteNormalBackground(44);
  }
};
LazyStaticImage UIStyle::kDoorBgGradient(
    @"door-bg-gradient.png");
LazyStaticImage UIStyle::kDoorMorePhotos(
    @"door-more-photos.png");
LazyStaticImage UIStyle::kDoorNewActivity(
    @"door-new-activity.png");
LazyStaticImage UIStyle::kDoorNewActivityTop(
    @"door-new-activity-top.png");
LazyStaticImage UIStyle::kDoorNewActivityBottom(
    @"door-new-activity-bottom.png");
LazyStaticImage UIStyle::kDoorPendingActivity(
    @"door-pending-activity.png");
LazyStaticImage UIStyle::kDoorPendingActivityTop(
    @"door-pending-activity-top.png");
LazyStaticImage UIStyle::kDoorPendingActivityBottom(
    @"door-pending-activity-bottom.png");
LazyStaticImage UIStyle::kIconAddressBook(
    @"icon-address-book.png");
LazyStaticImage UIStyle::kIconFacebook(
    @"icon-facebook.png");
LazyStaticImage UIStyle::kIconGmail(
    @"icon-gmail.png");
LazyStaticImage UIStyle::kIconBigCheckmark(
    @"icon-big-checkmark.png");
LazyStaticImage UIStyle::kIconBigError(
    @"icon-big-error.png");
LazyStaticImage UIStyle::kIconBigRefresh(
    @"icon-big-refresh.png");
LazyStaticImage UIStyle::kSpacer(
    @"spacer.png");
LazyStaticImage UIStyle::kTallButtonBlueActive(
    @"tall-button-blue-active.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage UIStyle::kTallButtonBlue(
    @"tall-button-blue.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage UIStyle::kTallButtonGreenActive(
    @"tall-button-green-active.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage UIStyle::kTallButtonGreen(
    @"tall-button-green.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage UIStyle::kTallButtonGreyActive(
    @"tall-button-grey-active.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage UIStyle::kTallButtonGrey(
    @"tall-button-grey.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage UIStyle::kTallButtonRedActive(
    @"tall-button-red-active.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage UIStyle::kTallButtonRed(
    @"tall-button-red.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticGeneratedImage UIStyle::kThumbnailShadow = {^{
    return MakeThumbnailShadow(
        kThumbnailDim, kThumbnailDim, 5, kThumbnailCorner,
        CGSizeMake(1, 1), 1, kShadowRgb); }
};
LazyStaticGeneratedImage UIStyle::kTransparent1x1 = {^{
    return MakeSolidColorImage(MakeUIColor(0, 0, 0, 0));
  }
};
LazyStaticHexColor UIStyle::kBuyColor = { "#96bbe5" };
LazyStaticHexColor UIStyle::kContactsCellTextColor = { "#423733" };
LazyStaticHexColor UIStyle::kContactsCellDetailTextColor = { "#786d6a" };
LazyStaticHexColor UIStyle::kConversationCaptionColor = { "#9f9c9c" };
LazyStaticHexColor UIStyle::kConversationMessageColor = { "#3f3e3e" };
LazyStaticHexColor UIStyle::kConversationSharePhotosColor = { "#ffffff" };
LazyStaticHexColor UIStyle::kConversationTimeColor = { "#9f9c9c" };
LazyStaticHexColor UIStyle::kConversationTitleColor = { "#3f3e3e" };
LazyStaticHexColor UIStyle::kConversationContentColor = { "#201c19" };
LazyStaticHexColor UIStyle::kConversationOddRowColor = { "#f9f9f9" };
LazyStaticHexColor UIStyle::kConversationEvenRowColor = { "#ffffff" };
LazyStaticHexColor UIStyle::kConversationShareBackgroundColor = { "#7f7c7c" };
LazyStaticHexColor UIStyle::kConversationThreadColor = { "#cfcbcb" };
LazyStaticHexColor UIStyle::kConversationUpdateColor = { "#ffffff" };
LazyStaticHexColor UIStyle::kConversationUpdateRowColor = { "#bab3b1" };
LazyStaticHexColor UIStyle::kContactsListBoldTextColor = { "#3f3e3e" };
LazyStaticHexColor UIStyle::kContactsListIndexBackgroundColor = { "#e7e4e1bf" };
LazyStaticHexColor UIStyle::kContactsListNormalTextColor = { "#9f9c9c" };
LazyStaticHexColor UIStyle::kContactsListSearchBackgroundColor = { "#ece9e9" };
LazyStaticHexColor UIStyle::kContactsListSearchTextColor = { "#3d3431" };
LazyStaticHexColor UIStyle::kContactsListSectionTextColor = { "#ada4a1" };
LazyStaticHexColor UIStyle::kContactsListSeparatorColor = { "#ada4a1" };
LazyStaticHexColor UIStyle::kEventTitleTextColor = { "#514643" };
LazyStaticHexColor UIStyle::kEventTitleTextShadowColor = { "#ffffff" };
LazyStaticHexColor UIStyle::kEpisodeTitleBackgroundColor = { "#514643" };
LazyStaticHexColor UIStyle::kFullEventTitleBackgroundColor = { "#514643" };
LazyStaticHexColor UIStyle::kLightOrangeColor = { "#f89113bf" };
LazyStaticHexColor UIStyle::kLinkColor = { "#0044dd" };
LazyStaticRgbColor UIStyle::kImportantColor = { kViewfinderOrangeRgb };
LazyStaticHexColor UIStyle::kMinTitleTextColor = { "#bfbfbf" };
LazyStaticHexColor UIStyle::kNotificationGlowColor = { "#f891137f" };
LazyStaticHexColor UIStyle::kOverlayColor = { "#000000bf" };
LazyStaticHexColor UIStyle::kOverlayBorderColor = { "#f89113bf" };
LazyStaticRgbColor UIStyle::kPendingActivityColor = { kViewfinderBlueRgb };
LazyStaticHexColor UIStyle::kSettingsBackgroundColor = { "#faf7f7" };
LazyStaticHexColor UIStyle::kSettingsSwitchOffColor = { "#bab3b1" };
LazyStaticHexColor UIStyle::kSettingsSwitchOnColor = { "#fa9214" };
LazyStaticHexColor UIStyle::kSettingsTextColor = { "#3f3e3e" };
LazyStaticHexColor UIStyle::kSettingsTextFooterColor = { "#786d6a" };
LazyStaticHexColor UIStyle::kSettingsTextHeaderColor = { "#645956" };
LazyStaticHexColor UIStyle::kSettingsTextSelectedColor = { "#ffffff" };
LazyStaticRgbColor UIStyle::kShadowColor = { kShadowRgb };
LazyStaticHexColor UIStyle::kTitleTextColor = { "#ffffff" };
LazyStaticHexColor UIStyle::kTutorialTextColor = { "#ffffff" };
LazyStaticRgbColor UIStyle::kUnviewedActivityColor = { kViewfinderOrangeRgb };

LazyStaticDict UIStyle::kContactsListItalicBoldAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)UIStyle::kContactsListItalicFont.get(),
        kCTForegroundColorAttributeName,
        (id)UIStyle::kContactsListBoldTextColor.get().CGColor);
  }
};
LazyStaticDict UIStyle::kContactsListItalicNormalAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)UIStyle::kContactsListItalicFont.get(),
        kCTForegroundColorAttributeName,
        (id)UIStyle::kContactsListNormalTextColor.get().CGColor);
  }
};
LazyStaticDict UIStyle::kContactsListLabelBoldAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)UIStyle::kContactsListBoldLabelFont.get(),
        kCTForegroundColorAttributeName,
        (id)UIStyle::kContactsListBoldTextColor.get().CGColor);
  }
};
LazyStaticDict UIStyle::kContactsListLabelNormalAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)UIStyle::kContactsListLabelFont.get(),
        kCTForegroundColorAttributeName,
        (id)UIStyle::kContactsListNormalTextColor.get().CGColor);
  }
};
LazyStaticDict UIStyle::kContactsListSublabelBoldAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)UIStyle::kContactsListBoldSublabelFont.get(),
        kCTForegroundColorAttributeName,
        (id)UIStyle::kContactsListBoldTextColor.get().CGColor);
  }
};
LazyStaticDict UIStyle::kContactsListSublabelNormalAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)UIStyle::kContactsListSublabelFont.get(),
        kCTForegroundColorAttributeName,
        (id)UIStyle::kContactsListNormalTextColor.get().CGColor);
  }
};
LazyStaticDict UIStyle::kContactsSelectorNormalAttributes = {^{
    return Dict(
        UITextAttributeFont, UIStyle::kContactsListButtonUIFont.get(),
        UITextAttributeTextColor, [UIColor darkGrayColor],
        UITextAttributeTextShadowColor, [UIColor whiteColor],
        UITextAttributeTextShadowOffset, UIOffsetMake(0, -0.5));
  }
};
LazyStaticDict UIStyle::kContactsSelectorHighlightedAttributes = {^{
    return Dict(
        UITextAttributeFont, UIStyle::kContactsListButtonUIFont.get(),
        UITextAttributeTextColor, [UIColor whiteColor],
        UITextAttributeTextShadowColor, [UIColor darkGrayColor],
        UITextAttributeTextShadowOffset, UIOffsetMake(0, 0.5));
  }
};
LazyStaticDict UIStyle::kFollowerGroupLabelBoldAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)UIStyle::kFollowerGroupBoldLabelFont.get(),
        kCTForegroundColorAttributeName,
        (id)UIStyle::kContactsListBoldTextColor.get().CGColor);
  }
};
LazyStaticDict UIStyle::kFollowerGroupSublabelNormalAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)UIStyle::kFollowerGroupSublabelFont.get(),
        kCTForegroundColorAttributeName,
        (id)UIStyle::kContactsListNormalTextColor.get().CGColor);
  }
};
LazyStaticDict UIStyle::kFollowerGroupSublabelItalicNormalAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)UIStyle::kFollowerGroupItalicSublabelFont.get(),
        kCTForegroundColorAttributeName,
        (id)UIStyle::kContactsListNormalTextColor.get().CGColor);
  }
};
LazyStaticDict UIStyle::kLinkAttributes = {^{
    return Dict(
        kCTUnderlineStyleAttributeName, YES,
        kCTForegroundColorAttributeName,
        (id)UIStyle::kLinkColor.get().CGColor);
  }
};

const float& UIStyle::kDividerSize = mutable_divider_size;
const float& UIStyle::kGutterSpacing = mutable_gutter_spacing;
const float UIStyle::kUnviewedFadeSeconds = 5;


void UIStyle::Init() {
  // 0.5 on retina displays, 1 on non-retina displays.
  mutable_divider_size = 1 / [UIScreen mainScreen].scale;
  // 1 on retina displays, 2 on non-retina displays.
  mutable_gutter_spacing = 1 / [UIScreen mainScreen].scale;

  [[UINavigationBar appearance]
    setTitleTextAttributes:
      Dict(UITextAttributeTextColor,
           kEventTitleTextColor.get(),
           UITextAttributeTextShadowColor,
           kEventTitleTextShadowColor.get(),
           UITextAttributeTextShadowOffset,
           UIOffsetMake(0, 0.5))];
  [[UINavigationBar appearance]
    setBackgroundImage:MakeSolidColorImage(kSettingsBackgroundColor)
         forBarMetrics:UIBarMetricsDefault];
  if (kSDKVersion < "7" || kIOSVersion < "7") {
    [[UIBarButtonItem appearanceWhenContainedIn:[UINavigationBar class], NULL]
     setTintColor:MakeUIColor(0.7, 0.7, 0.7, 1)];
  }
}

BadgeView* UIStyle::NewBadgeBlue() {
  return [[BadgeView alloc]
           initWithImage:kBadgeEmptyBlue
                    font:kBadgeUIFont
                   color:[UIColor whiteColor]];
}

BadgeView* UIStyle::NewBadgeBlueCheckmark() {
  return [[BadgeView alloc]
           initWithImage:kBadgeEmptyBlueCheckmark
                    font:kBadgeUIFont
                   color:[UIColor whiteColor]];
}

BadgeView* UIStyle::NewBadgeOrange() {
  return [[BadgeView alloc]
           initWithImage:kBadgeEmpty
                    font:kBadgeUIFont
                   color:[UIColor whiteColor]];
}

UIButton* UIStyle::NewEditButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  [b setImage:UIStyle::kConvoEditIconWhite forState:UIControlStateNormal];
  b.titleLabel.font = kEditButtonFont.get();
  b.titleEdgeInsets = UIEdgeInsetsMake(0, -16, 0, 8);
  [b setTitle:@"Edit" forState:UIControlStateNormal];
  [b setTitleColor:kEditButtonColor forState:UIControlStateNormal];
  [b setBackgroundImage:kEditButtonBackground forState:UIControlStateNormal];
  b.frameSize = kEditButtonBackground.get().size;
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

UIButton* UIStyle::NewBigButtonGrey(NSString* title, id target, SEL selector) {
  return NewBigButton(
      title, kBigButtonColor, kBigButtonShadowColor,
      kBigButtonGrey, kBigButtonGreyPressed,
      target, selector);
}

UIButton* UIStyle::NewSignupButtonGreen(NSString* title, UIFont* font, id target, SEL selector) {
  return NewSignupButton(
      title, font, kSignupButtonColor, kSignupButtonGreen,
      kSignupButtonGreenPressed, target, selector);
}

UIButton* UIStyle::NewSignupButtonGrey(NSString* title, UIFont* font, id target, SEL selector) {
  return NewSignupButton(
      title, font, kSignupButtonColor, kSignupButtonGrey,
      kSignupButtonGreyPressed, target, selector);
}

UIButton* UIStyle::NewCameraToggle(id target, SEL selector) {
  return NewTranslucentButton(kCameraToggle, target, selector);
}

UIBarButtonItem* UIStyle::NewToolbarAddContact(id target, SEL selector) {
  return NewToolbarItem(kToolbarAddContact, NULL, target, selector);
}

UIBarButtonItem* UIStyle::NewToolbarBack(id target, SEL selector) {
  return NewToolbarItem(kToolbarBack, NULL, target, selector);
}

UIBarButtonItem* UIStyle::NewToolbarCancel(id target, SEL selector) {
  return NewToolbarTitleItem(
      @"Cancel", kToolbarButtonSmallUIFont, kToolbarButtonColor,
      60, target, selector);
}

UIBarButtonItem* UIStyle::NewToolbarCompose(id target, SEL selector) {
  return NewToolbarItem(kToolbarCompose, NULL, target, selector);
}

UIBarButtonItem* UIStyle::NewToolbarGreenButton(
    NSString* title, id target, SEL selector) {
  return NewToolbarTitleItem(
      title, kToolbarButtonLargeUIFont, kToolbarButtonGreenColor,
      60, target, selector);
}

UIView* UIStyle::NewContactsTitleView(NSString* title_str) {
  UILabel* title = [UILabel new];
  title.backgroundColor = [UIColor clearColor];
  title.font = UIStyle::kSummaryTitleUIFont;
  title.shadowColor = UIStyle::kEventTitleTextShadowColor;
  title.shadowOffset = CGSizeMake(0, 1);
  title.text = title_str;
  title.textAlignment = NSTextAlignmentCenter;
  title.textColor = UIStyle::kEventTitleTextColor;
  [title sizeToFit];
  return title;
}

void UIStyle::InitLeftBarButton(UIBarButtonItem* item) {
  if (kSDKVersion >= "7" && kIOSVersion >= "7" && item.customView) {
    // Adjust for the different inset for left/right bar button items on iOS 7.
    item.customView.layer.sublayerTransform =
        CATransform3DMakeTranslation(-11, 0, 0);
  }
}

void UIStyle::InitRightBarButton(UIBarButtonItem* item) {
  if (kSDKVersion >= "7" && kIOSVersion >= "7" && item.customView) {
    // Adjust for the different inset for left/right bar button items on iOS 7.
    item.customView.layer.sublayerTransform =
        CATransform3DMakeTranslation(11, 0, 0);
  }
}

// local variables:
// mode: c++
// end:
