// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_UI_STYLE_H
#define VIEWFINDER_UI_STYLE_H

#import <CoreText/CoreText.h>
#import <UIKit/UIKit.h>
#import "Appearance.h"
#import "ScopedRef.h"
#import "ValueUtils.h"
#import "Vector.h"

@class BadgeView;

// UIStyle provides access to fonts and colors used consistently
// throughout the application.
class UIStyle {
 public:
  static void Init();

  // UI elements.
  static BadgeView* NewBadgeBlue();
  static BadgeView* NewBadgeBlueCheckmark();
  static BadgeView* NewBadgeOrange();
  static UIButton* NewEditButton(id target, SEL selector);
  static UIButton* NewBigButtonGrey(NSString* title, id target, SEL selector);
  static UIButton* NewSignupButtonGreen(NSString* title, UIFont* font, id target, SEL selector);
  static UIButton* NewSignupButtonGrey(NSString* title, UIFont* font, id target, SEL selector);
  static UIButton* NewCameraToggle(id target, SEL selector);
  static UIBarButtonItem* NewToolbarAddContact(id target, SEL selector);
  static UIBarButtonItem* NewToolbarBack(id target, SEL selector);
  static UIBarButtonItem* NewToolbarCancel(id target, SEL selector);
  static UIBarButtonItem* NewToolbarCompose(id target, SEL selector);
  static UIBarButtonItem* NewToolbarGreenButton(
      NSString* title, id target, SEL selector);
  static UIView* NewContactsTitleView(NSString* title_str);

  static void InitLeftBarButton(UIBarButtonItem* item);
  static void InitRightBarButton(UIBarButtonItem* item);

  // Fonts.
  static LazyStaticUIFont kBadgeUIFont;
  static LazyStaticUIFont kContactsButtonUIFont;
  static LazyStaticUIFont kContactsCellUIFont;
  static LazyStaticUIFont kContactsCellDetailUIFont;
  static LazyStaticCTFont kContactsHeaderFont;
  static LazyStaticCTFont kContactsListLabelFont;
  static LazyStaticUIFont kContactsListLabelUIFont;
  static LazyStaticCTFont kContactsListBoldLabelFont;
  static LazyStaticUIFont kContactsListBoldLabelUIFont;
  static LazyStaticCTFont kContactsListItalicFont;
  static LazyStaticCTFont kContactsListSublabelFont;
  static LazyStaticCTFont kContactsListBoldSublabelFont;
  static LazyStaticUIFont kContactsListButtonUIFont;
  static LazyStaticUIFont kContactsListSectionUIFont;
  static LazyStaticUIFont kContactsSubtitleUIFont;
  static LazyStaticCTFont kConversationCaptionFont;
  static LazyStaticCTFont kConversationMessageFont;
  static LazyStaticCTFont kConversationSharePhotosFont;
  static LazyStaticCTFont kConversationTimeFont;
  static LazyStaticCTFont kConversationTitleFont;
  static LazyStaticCTFont kConversationUpdateFont;
  static LazyStaticCTFont kFollowerGroupBoldLabelFont;
  static LazyStaticCTFont kFollowerGroupSublabelFont;
  static LazyStaticCTFont kFollowerGroupItalicSublabelFont;
  static LazyStaticCTFont kTitleFont;
  static LazyStaticUIFont kTitleUIFont;
  static LazyStaticCTFont kSmallTitleFont;
  static LazyStaticCTFont kSubtitleFont;
  static LazyStaticUIFont kSubtitleUIFont;
  static LazyStaticCTFont kTimeagoFont;
  static LazyStaticCTFont kHeadingFont;
  static LazyStaticUIFont kHeadingUIFont;
  static LazyStaticUIFont kLoginSignupButtonUIFont;
  static LazyStaticUIFont kLoginSignupEntryUIFont;
  static LazyStaticUIFont kSettingsCellUIFont;
  static LazyStaticUIFont kSettingsCellDetailUIFont;
  static LazyStaticCTFont kSettingsFooterFont;
  static LazyStaticCTFont kSettingsFooterBoldFont;
  static LazyStaticCTFont kSettingsHeaderFont;
  static LazyStaticUIFont kShareLabelUIFont;
  static LazyStaticUIFont kShareBoldLabelUIFont;
  static LazyStaticUIFont kShareSublabelUIFont;
  static LazyStaticUIFont kShareBoldSublabelUIFont;
  static LazyStaticUIFont kSummaryTitleUIFont;

  // Images.
  static LazyStaticImage kBadgeAllSelected;
  static LazyStaticImage kBadgeAllUnselected;
  static LazyStaticImage kBadgeDisconnected;
  static LazyStaticImage kBadgeEmpty;
  static LazyStaticImage kBadgeEmptyBlue;
  static LazyStaticImage kBadgeEmptyBlueCheckmark;
  static LazyStaticImage kBadgeSelected;
  static LazyStaticImage kBadgeUnselected;
  static LazyStaticImage kCameraAutofocus0;
  static LazyStaticImage kCameraAutofocus1;
  static LazyStaticImage kCameraAutofocusSmall0;
  static LazyStaticImage kCameraAutofocusSmall1;
  static LazyStaticImage kCameraFlash;
  static LazyStaticImage kCameraToggle;
  static LazyStaticImage kCheckmark;
  static LazyStaticImage kContactsCellBackground1;
  static LazyStaticImage kContactsListButton;
  static LazyStaticImage kContactsListButtonActive;
  static LazyStaticImage kContactsListSearch;
  static LazyStaticImage kContactsListSectionHeader;
  static LazyStaticGeneratedImage kConvoHeaderCap;
  static LazyStaticImage kConvoEditIconGrey;
  static LazyStaticImage kConvoEditIconWhite;
  static LazyStaticImage kCornerBottomLeft;
  static LazyStaticImage kCornerBottomRight;
  static LazyStaticImage kCornerTopLeft;
  static LazyStaticImage kCornerTopRight;
  static LazyStaticGeneratedImage kDeleteHighlightedBackground;
  static LazyStaticGeneratedImage kDeleteNormalBackground;
  static LazyStaticImage kDismissDialog;
  static LazyStaticImage kDoorBgGradient;
  static LazyStaticImage kDoorMorePhotos;
  static LazyStaticImage kDoorNewActivity;
  static LazyStaticImage kDoorNewActivityTop;
  static LazyStaticImage kDoorNewActivityBottom;
  static LazyStaticImage kDoorPendingActivity;
  static LazyStaticImage kDoorPendingActivityTop;
  static LazyStaticImage kDoorPendingActivityBottom;
  static LazyStaticImage kIconAddressBook;
  static LazyStaticImage kIconFacebook;
  static LazyStaticImage kIconGmail;
  static LazyStaticImage kIconBigCheckmark;
  static LazyStaticImage kIconBigError;
  static LazyStaticImage kIconBigRefresh;
  static LazyStaticImage kSpacer;
  static LazyStaticImage kTallButtonBlueActive;
  static LazyStaticImage kTallButtonBlue;
  static LazyStaticImage kTallButtonGreenActive;
  static LazyStaticImage kTallButtonGreen;
  static LazyStaticImage kTallButtonGreyActive;
  static LazyStaticImage kTallButtonGrey;
  static LazyStaticImage kTallButtonRedActive;
  static LazyStaticImage kTallButtonRed;
  static LazyStaticGeneratedImage kThumbnailShadow;
  static LazyStaticGeneratedImage kTransparent1x1;

  // Colors.
  static LazyStaticHexColor kBuyColor;
  static LazyStaticHexColor kContactsCellTextColor;
  static LazyStaticHexColor kContactsCellDetailTextColor;
  static LazyStaticHexColor kConversationCaptionColor;
  static LazyStaticHexColor kConversationMessageColor;
  static LazyStaticHexColor kConversationSharePhotosColor;
  static LazyStaticHexColor kConversationTimeColor;
  static LazyStaticHexColor kConversationTitleColor;
  static LazyStaticHexColor kConversationContentColor;
  static LazyStaticHexColor kConversationOddRowColor;
  static LazyStaticHexColor kConversationEvenRowColor;
  static LazyStaticHexColor kConversationShareBackgroundColor;
  static LazyStaticHexColor kConversationThreadColor;
  static LazyStaticHexColor kConversationUpdateColor;
  static LazyStaticHexColor kConversationUpdateRowColor;
  static LazyStaticHexColor kContactsListBoldTextColor;
  static LazyStaticHexColor kContactsListIndexBackgroundColor;
  static LazyStaticHexColor kContactsListNormalTextColor;
  static LazyStaticHexColor kContactsListSearchBackgroundColor;
  static LazyStaticHexColor kContactsListSearchTextColor;
  static LazyStaticHexColor kContactsListSectionTextColor;
  static LazyStaticHexColor kContactsListSeparatorColor;
  static LazyStaticHexColor kEventTitleTextColor;
  static LazyStaticHexColor kEventTitleTextShadowColor;
  static LazyStaticHexColor kEpisodeTitleBackgroundColor;
  static LazyStaticHexColor kFullEventTitleBackgroundColor;
  static LazyStaticHexColor kLightOrangeColor;
  static LazyStaticHexColor kLinkColor;
  static LazyStaticRgbColor kImportantColor;
  static LazyStaticHexColor kMinTitleTextColor;
  static LazyStaticHexColor kNotificationGlowColor;
  static LazyStaticHexColor kOverlayColor;
  static LazyStaticHexColor kOverlayBorderColor;
  static LazyStaticRgbColor kPendingActivityColor;
  static LazyStaticHexColor kSettingsBackgroundColor;
  static LazyStaticHexColor kSettingsSwitchOffColor;
  static LazyStaticHexColor kSettingsSwitchOnColor;
  static LazyStaticHexColor kSettingsTextColor;
  static LazyStaticHexColor kSettingsTextFooterColor;
  static LazyStaticHexColor kSettingsTextHeaderColor;
  static LazyStaticHexColor kSettingsTextSelectedColor;
  static LazyStaticRgbColor kShadowColor;
  static LazyStaticHexColor kTitleTextColor;
  static LazyStaticHexColor kTutorialTextColor;
  static LazyStaticRgbColor kUnviewedActivityColor;

  // Attribute dictionaries.
  static LazyStaticDict kContactsListItalicBoldAttributes;
  static LazyStaticDict kContactsListItalicNormalAttributes;
  static LazyStaticDict kContactsListLabelBoldAttributes;
  static LazyStaticDict kContactsListLabelNormalAttributes;
  static LazyStaticDict kContactsListSublabelBoldAttributes;
  static LazyStaticDict kContactsListSublabelNormalAttributes;
  static LazyStaticDict kContactsSelectorNormalAttributes;
  static LazyStaticDict kContactsSelectorHighlightedAttributes;
  static LazyStaticDict kFollowerGroupLabelBoldAttributes;
  static LazyStaticDict kFollowerGroupSublabelNormalAttributes;
  static LazyStaticDict kFollowerGroupSublabelItalicNormalAttributes;
  static LazyStaticDict kLinkAttributes;

  // Constants.
  static const float& kDividerSize;
  static const float& kGutterSpacing;
  // Number of seconds after which an activity will be marked as fully viewed.
  static const float kUnviewedFadeSeconds;
};

#endif  // VIEWFINDER_UI_STYLE_H

// local variables:
// mode: c++
// end:
