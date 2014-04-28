// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import "BadgeView.h"
#import "PhotoPickerView.h"
#import "SummaryToolbar.h"
#import "UIView+geometry.h"

@implementation PhotoPickerView

@synthesize env = env_;
@synthesize singlePhotoSelection = single_photo_selection_;
@synthesize summary = summary_;

- (id)initWithState:(UIAppState*)state
singlePhotoSelection:(bool)single_photo_selection {
  if (self = [super initWithState:state]) {
    need_rebuild_ = true;
    single_photo_selection_ = single_photo_selection;

    summary_ = [[FullEventSummaryView alloc]
                 initWithState:state_
                      withType:SUMMARY_PHOTO_PICKER];
    summary_.singlePhotoSelection = single_photo_selection_;
    [self addSubview:summary_];

    __weak PhotoPickerView* weak_self = self;

    toolbar_ = [[SummaryToolbar alloc] initWithTarget:weak_self];
    [toolbar_ showPhotoPickerItems:false
                   singleSelection:single_photo_selection_];
    summary_.toolbar = toolbar_;
    [self addSubview:toolbar_];

    summary_.modalCallback->Add(^(bool modal) {
        [weak_self updateToolbar:modal];
      });
    summary_.selectionCallback->Add(^{
        [weak_self updateTitle];
      });
    summary_.searchCallback->Add(^{
        [weak_self updateTitle];
      });
    summary_.toolbarCallback->Add(^(bool hidden) {
        if (hidden) {
          [weak_self hideToolbar];
        } else {
          [weak_self showToolbar];
        }
      });

    [self updateTitle];
  }
  return self;
}

- (void)layoutSubviews {
  [super layoutSubviews];

  toolbar_.frame = CGRectMake(
      0, toolbar_top_, self.frameWidth,
      toolbar_.intrinsicHeight + state_->status_bar_height());

  summary_.frame = self.bounds;
  summary_.toolbarBottom = toolbar_.frameBottom;
  [summary_ updateScrollView];
  [summary_ layoutSubviews];

  if (need_rebuild_) {
    need_rebuild_ = false;
    [summary_ rebuild];
  }
}

- (void)updateTitle {
  if (summary_.searching) {
    toolbar_.title = summary_.searchTitle;
  } else if (single_photo_selection_) {
    toolbar_.title = @"Select Photo";
  } else {
    toolbar_.title = @"Select Photos";
  }

  if (summary_.numSelected > 0) {
    if (single_photo_selection_) {
      toolbar_.pickerBadge.text = @" ";
    } else {
      toolbar_.pickerBadge.text = Format("%d", summary_.numSelected);
    }
  } else {
    toolbar_.pickerBadge.text = NULL;
  }
}

- (void)updateToolbar:(bool)modal {
  if (modal) {
    [toolbar_ showSearchInboxItems:true];
    toolbar_.exitItem.customView.hidden =
        (summary_.viewfinder.mode == VF_JUMP_SCROLLING);
  } else {
    [toolbar_ showPhotoPickerItems:true
                   singleSelection:single_photo_selection_];
  }
}

- (void)hideToolbar {
  toolbar_top_ = -(toolbar_.frameHeight + 1);
  [self layoutSubviews];
}

- (void)showToolbar {
  toolbar_top_ = 0;
  [self layoutSubviews];
}

// Pass through exit if summary is in search mode. Otherwise,
// invoke conversation picker exit.
- (void)toolbarCancel {
  if (summary_.isModal) {
    [summary_ navbarExit];
  } else {
    [env_ photoPickerExit];
  }
}

- (void)toolbarDone {
  [env_ photoPickerAddPhotos:SelectionSetToVec(summary_.selection)];
}

- (void)toolbarExit {
  [summary_ navbarExit];
}

@end  // PhotoPickerView
