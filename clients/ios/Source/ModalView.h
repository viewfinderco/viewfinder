// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import <UIKit/UIKit.h>

class UIAppState;

// ModalView presents contents decorated with a modal frame.
// Contents should be added via calls to addModalSubview instead
// of using the UIKit subview manipulation routines directly.
@interface ModalView : UIView {
 @protected
  UIAppState* state_;
  UIView* first_responder_;
  bool shown_from_rect_;
  CGPoint show_position_;
}

- (id)initWithState:(UIAppState*)state;
- (void)show;
- (void)showFromRect:(CGRect)rect;
- (void)hide:(bool)remove;

@end  // ModalView

// local variables:
// mode: objc
// end:
