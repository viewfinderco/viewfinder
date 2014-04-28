// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "ConversationActivityRowView.h"

@class CheckmarkBadge;

@interface ShareActivityRowView : ConversationActivityRowView {
}

+ (float)suggestedHeight:(NSAttributedString*)text
               textWidth:(float)text_width;

- (id)initWithActivity:(const ActivityHandle&)activity
       withActivityRow:(const ViewpointSummaryMetadata::ActivityRow*)activity_row
                  text:(NSAttributedString*)text
             textWidth:(float)text_width
             topMargin:(float)top_margin
          bottomMargin:(float)bottom_margin
            leftMargin:(float)left_margin
            threadType:(ActivityThreadType)thread_type
               comment:(const NSRange&)comment_range;

@end  // ShareActivityRowView

// local variables:
// mode: objc
// end:
