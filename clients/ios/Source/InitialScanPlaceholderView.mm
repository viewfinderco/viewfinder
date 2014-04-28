// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Appearance.h"
#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "InitialScanPlaceholderView.h"
#import "Logging.h"
#import "TextLayer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

LazyStaticHexColor kInitialScanColor = { "#ffffff" };

LazyStaticCTFont kInitialScanTitleFont = {
  kProximaNovaBold, 17
};

LazyStaticCTFont kInitialScanCaptionFont = {
  kProximaNovaRegular, 12
};

}  // namespace

UIView* NewInitialScanPlaceholder() {
  UIView* v = [UIView new];

  UIActivityIndicatorView* activity_indicator =
      [[UIActivityIndicatorView alloc]
        initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleWhiteLarge];
  activity_indicator.color = kInitialScanColor;
  [activity_indicator startAnimating];
  [v addSubview:activity_indicator];

  NSMutableAttributedString* str = NewAttrString(
      "Organizing Photos\n", kInitialScanTitleFont, kInitialScanColor);
  AppendAttrString(str, "Sit tight, this should take only\na few more moments",
                   kInitialScanCaptionFont, kInitialScanColor);

  TextLayer* text = [TextLayer new];
  text.anchorPoint = CGPointMake(0, 0);
  text.attrStr  = AttrCenterAlignment(str);
  text.frameTop = activity_indicator.frameBottom + 12;
  [v.layer addSublayer:text];

  // Make the parent view large enough to hold both the activity indicator and
  // the text.
  v.frameWidth = std::max(activity_indicator.frameWidth, text.frameWidth);
  v.frameHeight = text.frameBottom;

  // Center both the activity indicator and text horizontally within the parent
  // view.
  activity_indicator.frameLeft = (v.frameWidth - activity_indicator.frameWidth) / 2;
  text.frameLeft = (v.frameWidth - text.frameWidth) / 2;

  return v;
}

// local variables:
// mode: objc
// end:
