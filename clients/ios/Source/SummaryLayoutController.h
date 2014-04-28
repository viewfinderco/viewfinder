// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "ConversationSummaryView.h"
#import "Dashboard.h"
#import "LayoutController.h"
#import "SummaryToolbar.h"
#import "UIAppState.h"
#import "Utils.h"

enum SummaryPage {
  PAGE_PROFILE = 0,
  PAGE_INBOX,
  PAGE_MAX,
};

@class TextLayer;

@interface SummaryLayoutController
    : LayoutController<DashboardEnv,
                       UIScrollViewDelegate> {
 @private
  SummaryPage summary_page_;
  Dashboard* dashboard_;
  ConversationSummaryView* inbox_;
  ScopedPtr<LayoutTransitionState> transition_;
  bool refreshing_;
  bool need_rebuild_;
  SummaryToolbar* toolbar_;
  bool toolbar_offscreen_;
  int view_state_;
  bool prompted_for_contacts_;
  bool registered_for_push_notifications_;
}

- (id)initWithState:(UIAppState*)state;
- (void)setCurrentView:(int)page animated:(BOOL)animated;
- (void)updateToolbar:(bool)animated modal:(bool)modal;

// See note in LayoutController.h about requirement for
// nonatomic specifier.
@property (nonatomic) SummaryPage summaryPage;
@property (nonatomic) ControllerState controllerState;
@property (nonatomic, readonly) Dashboard* dashboard;
@property (nonatomic, readonly) ConversationSummaryView* inbox;

@end  // SummaryLayoutController

// local variables:
// mode: objc
// end:
