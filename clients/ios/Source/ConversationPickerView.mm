// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import "ConversationPickerView.h"
#import "ConversationSummaryView.h"
#import "SummaryToolbar.h"
#import "UIView+geometry.h"

@implementation ConversationPickerView

@synthesize env = env_;

- (id)initWithState:(UIAppState*)state {
  if (self = [super initWithState:state]) {
    need_rebuild_ = true;

    summary_ = [[ConversationSummaryView alloc]
                       initWithState:state_ withType:SUMMARY_CONVERSATION_PICKER];
    [self addSubview:summary_];

    __weak ConversationPickerView* weak_self = self;

    toolbar_ = [[SummaryToolbar alloc] initWithTarget:weak_self];
    [toolbar_ showConvoPickerItems:false];
    [self addSubview:toolbar_];

    summary_.modalCallback->Add(^(bool modal) {
        [weak_self updateToolbar:modal];
      });
    summary_.toolbarCallback->Add(^(bool hidden) {
        if (hidden) {
          [weak_self hideToolbar];
        } else {
          [weak_self showToolbar];
        }
      });
    summary_.viewpointCallback->Add(^(int64_t viewpoint_id, PhotoView* photo_view) {
        [env_ conversationPickerSelection:viewpoint_id];
      });
  }
  return self;
}

- (void)layoutSubviews {
  [super layoutSubviews];

  toolbar_.frame = CGRectMake(
      0, 0, self.frameWidth,
      toolbar_.intrinsicHeight + state_->status_bar_height());

  summary_.frame = self.bounds;
  summary_.toolbarBottom = toolbar_.frameBottom;
  [summary_ updateScrollView];
  [summary_ layoutSubviews];

  if (need_rebuild_) {
    [summary_ rebuild];
  }
}

- (void)updateToolbar:(bool)modal {
  if (modal) {
    [toolbar_ showSearchInboxItems:true];
    toolbar_.exitItem.customView.hidden =
        (summary_.viewfinder.mode == VF_JUMP_SCROLLING);
  } else {
    [toolbar_ showConvoPickerItems:true];
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
    [env_ conversationPickerExit];
  }
}

- (void)toolbarExit {
  [summary_ navbarExit];
}

@end  // ConversationPickerView
