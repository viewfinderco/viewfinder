// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "Callback.h"

class UIAppState;
@class DashboardNotice;

typedef void (^DashboardCallback)();

enum DashboardNoticeType {
  // Dashboard notices are sorted on screen by their notice type.
  DASHBOARD_NOTICE_PUSH_NOTIFICATIONS,
  DASHBOARD_NOTICE_HELLO_JAILBREAKER,
  DASHBOARD_NOTICE_SYSTEM_MESSAGE,
  DASHBOARD_NOTICE_NEW_USERS,
  DASHBOARD_NOTICE_COUNT,
};

@interface DashboardNotice : UIView {
 @private
  UIAppState* state_;
  DashboardNoticeType type_;
  UIButton* activate_;
  UIButton* body_;
  UIButton* remove_;
  UIView* tray_;
  DashboardCallback tapped_;
  DashboardCallback toggled_;
  DashboardCallback updated_;
  bool expanded_;
  bool removed_;
  string identifier_;
}

@property (nonatomic, readonly) float desiredHeight;
@property (nonatomic) bool expanded;
@property (nonatomic) bool removed;
@property (nonatomic, copy) DashboardCallback tapped;
@property (nonatomic, copy) DashboardCallback toggled;
@property (nonatomic) NSString* title;
@property (nonatomic, readonly) DashboardNoticeType type;
@property (nonatomic, copy) DashboardCallback updated;
@property (nonatomic) string identifier;

@end  // DashboardNotice

DashboardNotice* NewDashboardNotice(
    UIAppState* state, DashboardNoticeType type, const string& identifier, float width);
string DashboardNoticeNeededIdentifier(UIAppState* state, DashboardNoticeType type);
void DashboardNoticeRemove(UIAppState* state, DashboardNoticeType type, const string& identifier);
void DashboardNoticeReset(UIAppState* state, DashboardNoticeType type);
void DashboardNoticeResetAll(UIAppState* state);

// local variables:
// mode: objc
// end:
