// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "CheckmarkBadge.h"
#import "RowView.h"

class UIAppState;

@interface FullEventRowView : RowView {
 @private
  UIAppState* state_;
  EventHandle evh_;
  DBHandle db_;
  CheckmarkBadge* badge_;
  bool enabled_;
}

@property (nonatomic, readonly) EventHandle event;

- (id)initWithState:(UIAppState*)state
          withEvent:(const EventHandle&)evh
          withWidth:(float)width
             withDB:(const DBHandle&)db;

+ (float)getEventHeightWithState:(UIAppState*)state
                       withEvent:(const Event&)ev
                       withWidth:(float)width
                          withDB:(const DBHandle&)db;

@end  // FullEventRowView

// local variables:
// mode: objc
// end:
