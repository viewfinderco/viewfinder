// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <QuartzCore/CAMediaTimingFunction.h>
#import "Appearance.h"
#import "BadgeView.h"
#import "Logging.h"
#import "SummaryToolbar.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kToolbarHeight = 44;
const float kToolbarButtonWidth = 44;
const float kToolbarButtonHeight = 30;

LazyStaticImage kSummaryToolbarIconBackarrow(
    @"title-bar-icon-backarrow.png");
LazyStaticImage kSummaryToolbarIconCompose(
    @"title-bar-icon-compose.png");
LazyStaticImage kSummaryToolbarIconExit(
    @"title-bar-icon-x.png");
LazyStaticImage kSummaryToolbarIconProfile(
    @"title-bar-icon-profile.png");
LazyStaticImage kSummaryToolbarIconX(
    @"title-bar-icon-x.png");
LazyStaticImage kSummaryToolbarWordmark(@"title-bar-wordmark.png");

LazyStaticGeneratedImage kTransparent1x1 = {^{
    return MakeSolidColorImage(MakeUIColor(0, 0, 0, 0));
  }
};

LazyStaticHexColor kSummaryToolbarButtonColor = { "#3f3e3e" };
LazyStaticHexColor kSummaryToolbarButtonDisabledColor = { "#9f9c9c" };

LazyStaticHexColor kButtonTitleColor = { "#ffffff" };
LazyStaticHexColor kButtonTitleActiveColor = { "#c9c7c7" };
LazyStaticHexColor kSummaryToolbarTitleColor = { "#ffffff" };

LazyStaticUIFont kSummaryToolbarButtonFont = {
  kProximaNovaSemibold, 16
};

LazyStaticUIFont kSummaryToolbarButtonBoldFont = {
  kProximaNovaBold, 16
};

LazyStaticCTFont kSummaryToolbarTitleFont = {
  kProximaNovaSemibold, 21
};

LazyStaticDict kSummaryToolbarTitleAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)kSummaryToolbarTitleFont.get(),
        kCTForegroundColorAttributeName,
        (id)kSummaryToolbarTitleColor.get().CGColor);
  }
};

UIBarButtonItem* NewSummaryToolbarItem(
    UIImage* fg_normal, NSString* title, UIFont* font, UIColor* normal_color,
    UIColor* active_color, float width, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.frameSize = CGSizeMake(width, kToolbarButtonHeight);
  if (fg_normal) {
    [b setImage:fg_normal
       forState:UIControlStateNormal];
  } else if (title) {
    b.titleLabel.font = font;
    [b setTitleColor:normal_color
            forState:UIControlStateNormal];
    [b setTitleColor:active_color
            forState:UIControlStateHighlighted];
    [b setTitle:title
       forState:UIControlStateNormal];
  }
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return [[UIBarButtonItem alloc] initWithCustomView:b];
}

UIBarButtonItem* NewSummaryToolbarIconButton(UIImage* icon, id target, SEL selector) {
  return NewSummaryToolbarItem(
      icon, NULL, NULL, kButtonTitleColor, kButtonTitleActiveColor,
      kToolbarButtonWidth, target, selector);
}

UIBarButtonItem* NewSummaryToolbarTextButton(const string& str, id target, SEL selector) {
  return NewSummaryToolbarItem(
      NULL, NewNSString(str), kSummaryToolbarButtonFont,
      kButtonTitleColor, kButtonTitleActiveColor, 60, target, selector);
}

UIBarButtonItem* NewSummaryToolbarTextButtonBold(const string& str, id target, SEL selector) {
  return NewSummaryToolbarItem(
      NULL, NewNSString(str), kSummaryToolbarButtonBoldFont,
      kButtonTitleColor, kButtonTitleActiveColor, 60, target, selector);
}

}  // namespace

@implementation SummaryToolbar

@synthesize inboxBadge = inbox_badge_;
@synthesize profileBadge = profile_badge_;

- (id)initWithTarget:(id)target {
  if (self = [super init]) {
    target_ = target;
    self.autoresizesSubviews = YES;
    self.barStyle = UIBarStyleBlack;
    self.frameHeight = self.intrinsicHeight;
    self.frameWidth = 0;
    [self setBackgroundImage:NULL
               forBarMetrics:UIBarMetricsDefault];
    self.shadowImage = NULL;

    // The SummaryToolbar is composed of two UINavigationBars. One is empty but
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
    transparent_bar_.titleTextAttributes = kSummaryToolbarTitleAttributes;
    [self addSubview:transparent_bar_];

    inbox_badge_ = UIStyle::NewBadgeOrange();
    inbox_badge_.position = CGPointMake(0.60, -0.25);  // upper-right corner
    inbox_badge_.layer.zPosition = 1;

    picker_badge_ = UIStyle::NewBadgeBlue();
    picker_badge_.position = CGPointMake(0.70, -0.20);  // upper-right corner
    picker_badge_.layer.zPosition = 1;

    single_picker_badge_ = UIStyle::NewBadgeBlueCheckmark();
    single_picker_badge_.position = CGPointMake(0.70, -0.20);  // upper-right corner
    single_picker_badge_.layer.zPosition = 1;

    profile_badge_ = UIStyle::NewBadgeOrange();
    profile_badge_.position = CGPointMake(0.60, -0.25);  // upper-right corner
    profile_badge_.layer.zPosition = 1;
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

- (UIBarButtonItem*)backItem {
  if (!back_item_) {
    back_item_ = NewSummaryToolbarIconButton(
        kSummaryToolbarIconBackarrow, target_, @selector(toolbarBack));
  }
  return back_item_;
}

- (UIBarButtonItem*)cancelItem {
  if (!cancel_item_) {
    cancel_item_ = NewSummaryToolbarTextButton(
        "Cancel", target_, @selector(toolbarCancel));
  }
  return cancel_item_;
}

- (UIBarButtonItem*)composeItem {
  if (!compose_item_) {
    compose_item_ = NewSummaryToolbarIconButton(
        kSummaryToolbarIconCompose, target_, @selector(toolbarCompose));
  }
  return compose_item_;
}

- (UIBarButtonItem*)doneItem {
  if (!done_item_) {
    done_item_ = NewSummaryToolbarTextButtonBold(
        "Done", target_, @selector(toolbarDone));
  }
  return done_item_;
}

- (UIBarButtonItem*)editItem {
  if (!edit_item_) {
    edit_item_ = NewSummaryToolbarTextButton(
        "Select", target_, @selector(toolbarEdit));
  }
  return edit_item_;
}

- (UIBarButtonItem*)exitItem {
  if (!exit_item_) {
    exit_item_ = NewSummaryToolbarIconButton(
        kSummaryToolbarIconExit, target_, @selector(toolbarExit));
  }
  return exit_item_;
}

- (UIBarButtonItem*)inboxItem {
  if (!inbox_item_) {
    inbox_item_ = NewSummaryToolbarIconButton(
        kSummaryToolbarIconBackarrow, target_, @selector(toolbarInbox));
  }
  return inbox_item_;
}

- (UIBarButtonItem*)profileItem {
  if (!profile_item_) {
    profile_item_ = NewSummaryToolbarIconButton(
        kSummaryToolbarIconProfile, target_, @selector(toolbarProfile));
    [profile_item_.customView addSubview:profile_badge_];
  }
  return profile_item_;
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

- (BadgeView*)pickerBadge {
  if (picker_badge_.superview) {
    return picker_badge_;
  }
  return single_picker_badge_;
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

- (void)setTitle:(NSString*)title {
  transparent_bar_.topItem.title = title;
}

- (void)showContactTrapdoorsItems:(bool)animated {
  if (!contact_trapdoors_) {
    contact_trapdoors_ = [[UINavigationItem alloc] initWithTitle:@""];
    contact_trapdoors_.leftBarButtonItems = Array(self.noSpaceItem, self.backItem, self.flexSpaceItem);
    contact_trapdoors_.rightBarButtonItems = NULL;
  }
  if (transparent_bar_.topItem != contact_trapdoors_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(contact_trapdoors_) animated:NO];
  }
}

- (void)showConvoPickerItems:(bool)animated {
  if (!convo_picker_) {
    convo_picker_ = [[UINavigationItem alloc] initWithTitle:@"Select Conversation"];
    convo_picker_.leftBarButtonItems = Array(self.noSpaceItem, self.cancelItem, self.flexSpaceItem);
    convo_picker_.rightBarButtonItems = Array(self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != convo_picker_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(convo_picker_) animated:NO];
  }
}

- (void)showInboxItems:(bool)animated {
  if (!inbox_) {
    inbox_ = [[UINavigationItem alloc] initWithTitle:@"Viewfinder"];
    inbox_.titleView = [[UIImageView alloc] initWithImage:kSummaryToolbarWordmark];
    inbox_.leftBarButtonItems = Array(self.noSpaceItem, self.profileItem, self.flexSpaceItem);
    inbox_.rightBarButtonItems = Array(self.noSpaceItem, self.composeItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != inbox_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(inbox_) animated:NO];
  }
}

- (void)showPhotoPickerItems:(bool)animated
             singleSelection:(bool)single_selection {
  if (!photo_picker_) {
    photo_picker_ = [[UINavigationItem alloc] initWithTitle:@""];
    photo_picker_.leftBarButtonItems = Array(self.noSpaceItem, self.cancelItem, self.flexSpaceItem);
    photo_picker_.rightBarButtonItems = Array(self.noSpaceItem, self.doneItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != photo_picker_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(photo_picker_) animated:NO];
    if (single_selection) {
      [self.doneItem.customView addSubview:single_picker_badge_];
      [picker_badge_ removeFromSuperview];
    } else {
      [self.doneItem.customView addSubview:picker_badge_];
      [single_picker_badge_ removeFromSuperview];
    }
  }
}

- (void)showProfileItems:(bool)animated {
  if (!profile_) {
    profile_ = [[UINavigationItem alloc] initWithTitle:@"Account"];
    profile_.leftBarButtonItems = Array(self.noSpaceItem, self.inboxItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != profile_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(profile_) animated:NO];
    [self.inboxItem.customView addSubview:inbox_badge_];
  }
}

- (void)showSearchInboxItems:(bool)animated {
  if (!search_inbox_) {
    search_inbox_ = [[UINavigationItem alloc] initWithTitle:@"Viewfinder"];
    search_inbox_.titleView = [[UIImageView alloc] initWithImage:kSummaryToolbarWordmark];
    search_inbox_.leftBarButtonItems = Array(self.noSpaceItem, self.exitItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != search_inbox_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(search_inbox_) animated:NO];
  }
}

- (void)showConvoItems:(bool)animated
             withTitle:(NSString*)title {
  if (!convo_) {
    convo_ = [[UINavigationItem alloc] initWithTitle:title];
    convo_.leftBarButtonItems = Array(self.noSpaceItem, self.inboxItem, self.flexSpaceItem);
    convo_.rightBarButtonItems = Array(self.noSpaceItem, self.editItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != convo_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(convo_) animated:NO];
    [self.inboxItem.customView addSubview:inbox_badge_];
  }
  convo_.title = title;
}

- (void)showSearchConvoItems:(bool)animated {
  if (!search_convo_) {
    search_convo_ = [[UINavigationItem alloc] initWithTitle:@"Conversation"];
    search_convo_.leftBarButtonItems = Array(self.noSpaceItem, self.exitItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != search_convo_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(search_convo_) animated:NO];
  }
}

- (void)showEditConvoItems:(bool)animated
                 withTitle:(NSString*)title
           withDoneEnabled:(bool)done_enabled {
  if (!edit_convo_) {
    edit_convo_ = [[UINavigationItem alloc] initWithTitle:title];
    edit_convo_.leftBarButtonItems = Array(self.noSpaceItem, self.cancelItem, self.flexSpaceItem);
    edit_convo_.rightBarButtonItems = Array(self.noSpaceItem, self.doneItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != edit_convo_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(edit_convo_) animated:NO];
  }
  self.doneItem.enabled = done_enabled ? YES : NO;
  [picker_badge_ removeFromSuperview];
  [single_picker_badge_ removeFromSuperview];
  edit_convo_.title = title;
}

- (void)showEditConvoPhotosItems:(bool)animated {
  if (!edit_convo_photos_) {
    edit_convo_photos_ = [[UINavigationItem alloc] initWithTitle:@"Select Photos"];
    edit_convo_photos_.hidesBackButton = YES;
    edit_convo_photos_.rightBarButtonItems = Array(self.noSpaceItem, self.cancelItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != edit_convo_photos_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(edit_convo_photos_) animated:NO];
  }
}

- (void)showStartConvoItems:(bool)animated
                  withTitle:(NSString*)title {
  if (!start_convo_) {
    start_convo_ = [[UINavigationItem alloc] initWithTitle:title];
    start_convo_.leftBarButtonItems = Array(self.noSpaceItem, self.cancelItem, self.flexSpaceItem);
  }
  if (transparent_bar_.topItem != start_convo_) {
    if (animated) {
      [self addTransitionAnimation:kCATransitionFade withSubtype:NULL];
    }
    [transparent_bar_ setItems:Array(start_convo_) animated:NO];
  }
  start_convo_.title = title;
}

@end  // SummaryToolbar
