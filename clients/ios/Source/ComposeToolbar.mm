// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <QuartzCore/CAMediaTimingFunction.h>
#import "Appearance.h"
#import "AttrStringUtils.h"
#import "ComposeToolbar.h"
#import "Logging.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kToolbarHeight = 44;

LazyStaticGeneratedImage kTransparent1x1 = {^{
    return MakeSolidColorImage(MakeUIColor(0, 0, 0, 0));
  }
};
LazyStaticGeneratedImage kiOS6Background1x1 = {^{
    return MakeSolidColorImage(MakeUIColor(0.9804, 0.9686, 0.9686, 1.0));
  }
};

LazyStaticHexColor kDoneButtonColor = { "#2070aa" };
LazyStaticHexColor kToolbarButtonColor = { "#3f3e3e" };
LazyStaticHexColor kSendButtonGreyColor = { "#9f9c9c" };
LazyStaticHexColor kSendButtonGreenColor = { "#00804b" };

LazyStaticUIFont kSendButtonFont = {
  kProximaNovaSemibold, 21
};

LazyStaticUIFont kSendButtonNumPhotosFont = {
  kProximaNovaRegular, 12
};

LazyStaticUIFont kToolbarButtonFont = {
  kProximaNovaRegular, 17
};

UIBarButtonItem* NewToolbarItem(NSString* title, UIColor* color, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.titleLabel.font = kToolbarButtonFont;
  [b setTitleColor:color ? color : kToolbarButtonColor
          forState:UIControlStateNormal];
  [b setTitle:title
     forState:UIControlStateNormal];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  return [[UIBarButtonItem alloc] initWithCustomView:b];
}

}  // namespace

@implementation ComposeToolbar

- (id)initWithTarget:(id)target {
  if (self = [super init]) {
    target_ = target;
    self.autoresizesSubviews = YES;
    self.barStyle = UIBarStyleDefault;
    self.frameHeight = self.intrinsicHeight;
    self.frameWidth = 0;
    [self setBackgroundImage:kIOSVersion >= "7.0" ? NULL : kiOS6Background1x1
               forBarMetrics:UIBarMetricsDefault];
    self.shadowImage = NULL;

    // The ComposeToolbar is composed of two UINavigationBars. One is empty but
    // provides the translucent background, the other contains the items and
    // has a completely transparent background. This is necessary in order for
    // the kCATransitionFade animation to work properly without causing the
    // background to fade to non-existence and then back in.
    transparent_bar_ = [UINavigationBar new];
    transparent_bar_.autoresizesSubviews = YES;
    transparent_bar_.barStyle = UIBarStyleBlack;
    transparent_bar_.frameHeight = self.intrinsicHeight;
    transparent_bar_.frameWidth = 0;
    [transparent_bar_ setBackgroundImage:kTransparent1x1
                           forBarMetrics:UIBarMetricsDefault];
    transparent_bar_.shadowImage = NULL;
    [self addSubview:transparent_bar_];
  }
  return self;
}

- (UIView*)hitTest:(CGPoint)point
         withEvent:(UIEvent*)event {
  // Only allow the event to go to UIButton subviews.
  UIView* v = [super hitTest:point withEvent:event];
  if ([v isKindOfClass:[UIButton class]]) {
    return v;
  }
  return NULL;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  transparent_bar_.frame = self.bounds;
}

- (UIBarButtonItem*)cancelItem {
  if (!cancel_item_) {
    cancel_item_ = NewToolbarItem(@"Cancel", NULL, target_, @selector(toolbarCancel));
  }
  return cancel_item_;
}

- (UIBarButtonItem*)doneItem {
  if (!done_item_) {
    done_item_ = NewToolbarItem(@"Done", kDoneButtonColor, target_, @selector(toolbarDone));
  }
  return done_item_;
}

- (UIBarButtonItem*)sendItem {
  if (!send_item_) {
    send_button_ = [UIButton buttonWithType:UIButtonTypeCustom];
    [send_button_ addTarget:target_
                     action:@selector(toolbarSend)
           forControlEvents:UIControlEventTouchUpInside];
    send_item_ = [[UIBarButtonItem alloc] initWithCustomView:send_button_];
  }
  return send_item_;
}

- (UIBarButtonItem*)noSpaceItem {
  if (!no_space_item_) {
    no_space_item_ =
      [[UIBarButtonItem alloc]
        initWithBarButtonSystemItem:UIBarButtonSystemItemFixedSpace
                             target:NULL
                             action:NULL];
    // These values are experimentally determined to match up the left/right edge
    // of the back/edit buttons with the summary inbox / event cards.
    if (kSDKVersion >= "7" && kIOSVersion >= "7") {
      no_space_item_.width = -9;
    } else {
      no_space_item_.width = 2;
    }
  }
  return no_space_item_;
}

- (UIBarButtonItem*)flexSpaceItem {
  if (!flex_space_item_) {
    flex_space_item_ =
      [[UIBarButtonItem alloc]
        initWithBarButtonSystemItem:UIBarButtonSystemItemFlexibleSpace
                             target:NULL
                             action:NULL];
  }
  return flex_space_item_;
}

- (float)intrinsicHeight {
  return kToolbarHeight;
}

- (void)addTransitionAnimation:(NSString*)type
                   withSubtype:(NSString*)subtype {
  CATransition *transition = [CATransition animation];
  transition.duration = 0.300;
  transition.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseInEaseOut];
  transition.type = type;
  transition.subtype = subtype;
  [transparent_bar_.layer addAnimation:transition forKey:nil];
}

- (void)showComposeItems:(bool)animated
               numPhotos:(int)num_photos {
  if (!compose_) {
    compose_ = [[UINavigationItem alloc] initWithTitle:@""];
    compose_.leftBarButtonItems = Array(self.noSpaceItem, self.cancelItem, self.flexSpaceItem);
    compose_.rightBarButtonItems = Array(self.noSpaceItem, self.sendItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != compose_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(compose_) animated:NO];
  }
  // Update the title button with the number of photos.
  NSMutableAttributedString* attr_title =
      NewAttrString(Format("%d photo%s", num_photos, Pluralize(num_photos)),
                    kSendButtonNumPhotosFont, kSendButtonGreyColor);
  AppendAttrString(attr_title, "  Send", kSendButtonFont,
                   num_photos > 0 ? kSendButtonGreenColor : kSendButtonGreyColor);
  [send_button_ setAttributedTitle:attr_title
                        forState:UIControlStateNormal];
  [send_button_ sizeToFit];
}

- (void)showAddPeopleItems:(bool)animated {
  if (!add_people_) {
    add_people_ = [[UINavigationItem alloc] initWithTitle:@"Add People"];
    add_people_.leftBarButtonItems = Array(self.noSpaceItem, self.cancelItem, self.flexSpaceItem);
    add_people_.rightBarButtonItems = Array(self.noSpaceItem, self.doneItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != add_people_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(add_people_) animated:NO];
  }
}

- (void)showAddTitleItems:(bool)animated {
  if (!add_title_) {
    add_title_ = [[UINavigationItem alloc] initWithTitle:@"Add Title"];
    add_title_.leftBarButtonItems = Array(self.noSpaceItem, self.cancelItem, self.flexSpaceItem);
    add_title_.rightBarButtonItems = Array(self.noSpaceItem, self.doneItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != add_title_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(add_title_) animated:NO];
  }
}

@end  // ComposeToolbar
