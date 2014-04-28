// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>
#import "ValueUtils.h"

@class BadgeView;

@interface SummaryToolbar : UINavigationBar {
 @private
  __weak id target_;
  UINavigationBar* transparent_bar_;
  UINavigationItem* contact_trapdoors_;
  UINavigationItem* convo_picker_;
  UINavigationItem* inbox_;
  UINavigationItem* photo_picker_;
  UINavigationItem* profile_;
  UINavigationItem* search_inbox_;

  BadgeView* inbox_badge_;
  BadgeView* picker_badge_;
  BadgeView* single_picker_badge_;
  BadgeView* profile_badge_;

  // For conversation layout controller.
  UINavigationItem* convo_;
  UINavigationItem* edit_convo_;
  UINavigationItem* search_convo_;
  UINavigationItem* start_convo_;
  UINavigationItem* edit_convo_photos_;

  UIBarButtonItem* back_item_;
  UIBarButtonItem* cancel_item_;
  UIBarButtonItem* compose_item_;
  UIBarButtonItem* done_item_;
  UIBarButtonItem* edit_item_;
  UIBarButtonItem* exit_item_;
  UIBarButtonItem* inbox_item_;
  UIBarButtonItem* profile_item_;
  UIBarButtonItem* no_space_item_;
  UIBarButtonItem* flex_space_item_;
}

@property (nonatomic, readonly) UIBarButtonItem* cancelItem;
@property (nonatomic, readonly) UIBarButtonItem* composeItem;
@property (nonatomic, readonly) UIBarButtonItem* doneItem;
@property (nonatomic, readonly) UIBarButtonItem* editItem;
@property (nonatomic, readonly) UIBarButtonItem* exitItem;
@property (nonatomic, readonly) UIBarButtonItem* inboxItem;
@property (nonatomic, readonly) UIBarButtonItem* profileItem;

@property (nonatomic, readonly) BadgeView* inboxBadge;
@property (nonatomic, readonly) BadgeView* pickerBadge;
@property (nonatomic, readonly) BadgeView* profileBadge;
@property (nonatomic, readonly) float intrinsicHeight;

- (id)initWithTarget:(id)target;
- (void)setTitle:(NSString*)title;
- (void)showContactTrapdoorsItems:(bool)animated;
- (void)showConvoPickerItems:(bool)animated;
- (void)showInboxItems:(bool)animated;
- (void)showPhotoPickerItems:(bool)animated
             singleSelection:(bool)single_selection;
- (void)showProfileItems:(bool)animated;
- (void)showSearchInboxItems:(bool)animated;

// For conversation layout controller.
- (void)showConvoItems:(bool)animated
             withTitle:(NSString*)title;
- (void)showSearchConvoItems:(bool)animated;
- (void)showEditConvoItems:(bool)animated
                 withTitle:(NSString*)title
           withDoneEnabled:(bool)done_enabled;
- (void)showEditConvoPhotosItems:(bool)animated;
- (void)showStartConvoItems:(bool)animated
                  withTitle:(NSString*)title;

@end  // SummaryToolbar

// local variables:
// mode: objc
// end:
