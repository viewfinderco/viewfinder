// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_CONVERSATION_UTILS_H
#define VIEWFINDER_CONVERSATION_UTILS_H

#import <UIKit/UIKit.h>
#import "DB.h"
#import "PhotoSelection.h"

class UIAppState;

typedef void (^DoneCallback)(bool finished);

// Removes the conversations from the inbox.
void RemoveConversations(
    UIAppState* state, CGRect from_rect, UIView* in_view,
    const vector<int64_t>& viewpoint_ids, DoneCallback done);

// Mutes the conversations. Specify "mute" as true to mute and as
// false to unmute.
void MuteConversations(
    UIAppState* state, CGRect from_rect, UIView* in_view,
    const vector<int64_t>& viewpoint_ids, bool mute, DoneCallback done);

#endif  // VIEWFINDER_CONVERSATION_UTILS_H

// local variables:
// mode: objc
// end:
