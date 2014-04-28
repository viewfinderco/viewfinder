// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

@interface ExpandyMenu : UIButton {
 @private
  bool expanded_;
  int selected_item_;
  UIView* title_;
  NSArray* labels_;
  NSArray* dividers_;
}

- (id)initWithPoint:(CGPoint)point
              title:(UIView*)title
        buttonNames:(NSArray*)buttonNames;

@property (nonatomic,assign) int selectedItem;
@property (strong,nonatomic,readonly) NSArray* labels;

@end  // ExpandyMenu

// local variables:
// mode: objc
// end:
