// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Callback.h"

@class UIButton;
@class UIControl;

@interface ControlDelegate : NSObject {
 @private
  CallbackSet callbacks_;
}

@property (nonatomic, readonly) CallbackSet* callbacks;

+ (ControlDelegate*)delegateWithControl:(UIControl*)control;

@end  // ControlDelegate

// TODO(ben): make this a category on UIControl.
void AddButtonCallback(UIButton* b, void (^callback)());
