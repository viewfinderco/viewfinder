// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>
#import "ValueUtils.h"

@interface ComposeToolbar : UINavigationBar {
 @private
  __weak id target_;
  UINavigationBar* transparent_bar_;
  UINavigationItem* add_people_;
  UINavigationItem* add_title_;
  UINavigationItem* compose_;

  UIButton* send_button_;

  UIBarButtonItem* cancel_item_;
  UIBarButtonItem* done_item_;
  UIBarButtonItem* flex_space_item_;
  UIBarButtonItem* no_space_item_;
  UIBarButtonItem* send_item_;
}

@property (nonatomic, readonly) UIBarButtonItem* cancelItem;
@property (nonatomic, readonly) UIBarButtonItem* doneItem;
@property (nonatomic, readonly) UIBarButtonItem* sendItem;
@property (nonatomic, readonly) float intrinsicHeight;

- (id)initWithTarget:(id)target;
- (void)showAddPeopleItems:(bool)animated;
- (void)showAddTitleItems:(bool)animated;
- (void)showComposeItems:(bool)animated numPhotos:(int)num_photos;

@end  // ComposeToolbar

// local variables:
// mode: objc
// end:
