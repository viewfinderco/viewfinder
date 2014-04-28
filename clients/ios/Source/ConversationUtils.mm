// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "Analytics.h"
#import "Callback.h"
#import "ConversationUtils.h"
#import "CppDelegate.h"
#import "DayTable.h"
#import "PhotoSelection.h"
#import "RootViewController.h"
#import "StatusBar.h"
#import "UIAppState.h"
#import "ViewpointTable.h"

void RemoveConversations(
    UIAppState* state, CGRect from_rect, UIView* in_view,
    const vector<int64_t>& viewpoint_ids, DoneCallback done) {
  vector<int64_t> copied_viewpoint_ids = viewpoint_ids;
  CppDelegate* cpp_delegate = new CppDelegate;
  cpp_delegate->Add(
      @protocol(UIActionSheetDelegate),
      @selector(actionSheet:clickedButtonAtIndex:),
      ^(UIActionSheet* sheet, NSInteger button_index) {
        sheet.delegate = NULL;
        delete cpp_delegate;

        if (button_index != 0) {
          if (done) {
            done(false);
          }
          return;
        }

        [state->root_view_controller().statusBar
            setMessage:(copied_viewpoint_ids.size() == 1 ? @"Removing conversation" :
                        Format("Removing %d Conversation%s…",
                               copied_viewpoint_ids.size(),
                               Pluralize(copied_viewpoint_ids.size())))
            activity:true
            type:STATUS_MESSAGE_UI
            displayDuration:0.75];
        LOG("remove %d conversation%s", copied_viewpoint_ids.size(),
            Pluralize(copied_viewpoint_ids.size()));
        for (int i = 0; i < copied_viewpoint_ids.size(); ++i) {
          state->viewpoint_table()->Remove(copied_viewpoint_ids[i]);
          state->analytics()->ConversationRemove();
        }
        if (done) {
          done(true);
        }
      });

  NSString* s = viewpoint_ids.size() == 1 ? @"Remove conversation" :
                Format("Remove %d conversation%s",
                       viewpoint_ids.size(), Pluralize(viewpoint_ids.size()));
  UIActionSheet* confirm =
      [[UIActionSheet alloc] initWithTitle:s
                                  delegate:cpp_delegate->delegate()
                         cancelButtonTitle:@"Cancel"
                    destructiveButtonTitle:s
                         otherButtonTitles:NULL];
  [confirm setActionSheetStyle:UIActionSheetStyleBlackOpaque];
  [confirm showFromRect:from_rect inView:in_view animated:YES];
}

void MuteConversations(
    UIAppState* state, CGRect from_rect, UIView* in_view,
    const vector<int64_t>& viewpoint_ids, bool mute, DoneCallback done) {
  LOG("mute-%s %d conversation%s", mute ? "on" : "off",
      viewpoint_ids.size(), Pluralize(viewpoint_ids.size()));
  [state->root_view_controller().statusBar
      setMessage:mute ? @"Disabling notifications…" : @"Enabling notifications…"
      activity:true
      type:STATUS_MESSAGE_UI
      displayDuration:0.75];
  for (int i = 0; i < viewpoint_ids.size(); ++i) {
    if (mute) {
      state->analytics()->ConversationMute();
    } else {
      state->analytics()->ConversationUnmute();
    }
    state->viewpoint_table()->UpdateMutedLabel(viewpoint_ids[i], mute);
  }
  if (done) {
    done(true);
  }
}
