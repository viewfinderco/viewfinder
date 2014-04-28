// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "CheckmarkBadge.h"
#import "LayoutUtils.h"
#import "RowView.h"

class UIAppState;

@interface EventRowView : RowView {
 @private
  UIAppState* state_;
  EventHandle evh_;
  float width_;
  float height_;
  DBHandle db_;
  UIImageView* convo_badge_;
  CheckmarkBadge* badge_;
}

@property (nonatomic, readonly) EventHandle event;
@property (nonatomic) bool selected;

- (id)initWithState:(UIAppState*)state
          withEvent:(const EventHandle&)evh
          withWidth:(float)width
             withDB:(const DBHandle&)db;

+ (float)getEventHeightWithState:(UIAppState*)state
                       withEvent:(const Event&)ev
                       withWidth:(float)width
                          withDB:(const DBHandle&)db;

@end  // EventRowView

// local variables:
// mode: objc
// end:
