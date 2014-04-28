// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "LayoutUtils.h"
#import "TextView.h"
#import "TitleRowView.h"

@interface ConversationActivityRowView : TitleRowView<TextViewDelegate> {
 @protected
  ActivityHandle activity_;
  TextView* activity_text_;
  UIView* thread_;
  NSString* orig_text_;
  NSRange orig_editable_range_;
  float top_margin_;
  float bottom_margin_;
}

+ (float)suggestedHeight:(NSAttributedString*)text
               textWidth:(float)text_width;

- (id)initWithActivity:(const ActivityHandle&)activity
                  text:(NSAttributedString*)text
             textWidth:(float)text_width
             topMargin:(float)top_margin
          bottomMargin:(float)bottom_margin
            leftMargin:(float)left_margin
            threadType:(ActivityThreadType)thread_type
               comment:(const NSRange&)comment_range;

@end  // ConversationActivityRowView

// local variables:
// mode: objc
// end:
