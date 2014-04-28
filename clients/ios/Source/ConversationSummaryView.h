// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import "InboxCardRowView.h"
#import "SearchableSummaryView.h"

class UIAppState;

@interface ConversationSummaryView :
    SearchableSummaryView<InboxCardRowEnv> {
 @private
  UIImageView* placeholder_;
}

- (id)initWithState:(UIAppState*)state withType:(SummaryType)type;

@end  // ConversationSummaryView

// local variables:
// mode: objc
// end:
