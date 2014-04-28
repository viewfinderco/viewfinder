// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import "ModalView.h"
#import "Navbar.h"
#import "SummaryView.h"

class UIAppState;
@class ContactTrapdoorsSummaryView;
@class SummaryToolbar;

@protocol ContactTrapdoorsEnv
@optional
- (void)contactTrapdoorsSelection:(int64_t)viewpoint_id;
- (void)contactTrapdoorsExit;
@end  // ContactTrapdoorsEnv

@interface ContactTrapdoorsView : ModalView<NavbarEnv> {
 @private
  __weak id<ContactTrapdoorsEnv> env_;
  bool need_rebuild_;
  float toolbar_top_;
  ContactTrapdoorsSummaryView* summary_;
  SummaryToolbar* toolbar_;
}

@property (nonatomic, weak) id<ContactTrapdoorsEnv> env;
@property (nonatomic, readonly) bool empty;

- (id)initWithState:(UIAppState*)state
      withContactId:(int64_t)contact_id;

@end  // ContactTrapdoorsView

// local variables:
// mode: objc
// end:
