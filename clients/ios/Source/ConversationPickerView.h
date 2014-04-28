// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>
#import "ModalView.h"

class UIAppState;
@class ConversationSummaryView;
@class SummaryToolbar;

@protocol ConversationPickerEnv
@optional
- (void)conversationPickerSelection:(int64_t)viewpoint_id;
- (void)conversationPickerExit;
@end  // ConversationPickerEnv

@interface ConversationPickerView : ModalView {
 @private
  __weak id<ConversationPickerEnv> env_;
  bool need_rebuild_;
  float toolbar_top_;
  ConversationSummaryView* summary_;
  SummaryToolbar* toolbar_;
}

@property (nonatomic, weak) id<ConversationPickerEnv> env;

- (id)initWithState:(UIAppState*)state;

@end  // ConversationPickerView

// local variables:
// mode: objc
// end:
