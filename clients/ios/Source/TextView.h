// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "ScopedNotification.h"
#import "TextLayer.h"

@class CAShapeLayer;
@class MagnifierView;

@class TextView;
@protocol TextViewDelegate<NSObject, UIScrollViewDelegate>
@optional
- (BOOL)textViewShouldBeginEditing:(TextView*)text_view;
- (void)textViewDidBeginEditing:(TextView*)text_view;
- (BOOL)textViewShouldEndEditing:(TextView*)text_view;
- (void)textViewDidEndEditing:(TextView*)text_view;
- (void)textViewDidChange:(TextView*)text_view;
- (bool)textViewShouldReturn:(TextView*)text_view;
@end  // TextViewDelegate

@interface TextView
    : UIScrollView<UIGestureRecognizerDelegate,
                   UIScrollViewDelegate,
                   UITextInput> {
 @private
  TextLayer* text_layer_;
  CALayer* caret_layer_;
  CALayer* drag_layer_;
  CAShapeLayer* selection_layer_;
  __weak UIView* autocorrect_view_;
  UITextLayoutDirection selection_type_;
  UILongPressGestureRecognizer* long_press_;
  UILongPressGestureRecognizer* short_press_;
  UITapGestureRecognizer* single_tap_;
  NSMutableAttributedString* attr_text_;
  NSAttributedString* placeholder_attr_text_;
  __unsafe_unretained id<TextViewDelegate> delegate_;
  __unsafe_unretained id<UITextInputDelegate> input_delegate_;
  UITextInputStringTokenizer* tokenizer_;
  bool editable_;
  bool editing_;
  NSRange editable_range_;
  NSRange marked_range_;
  NSRange selected_range_;
  NSDictionary* marked_text_style_;
  NSDictionary* link_style_;
  NSTextCheckingResult* active_link_;
  ScopedNotification menu_will_show_;
  ScopedNotification menu_will_hide_;
  UIView<UIKeyInput>* old_first_responder_;
  UIView* accessory_view_;
  MagnifierView* loupe_;
  // UITextInputTraits properties.
  UITextAutocapitalizationType autocapitalization_type_;
  UITextAutocorrectionType autocorrection_type_;
  UITextSpellCheckingType spell_checking_type_;
  UIKeyboardType keyboard_type_;
  UIKeyboardAppearance keyboard_appearance_;
  UIReturnKeyType return_key_type_;
  BOOL enables_return_key_automatically_;
  BOOL secure_text_entry_;
}

@property (nonatomic) NSAttributedString* attrText;
@property (nonatomic) NSAttributedString* placeholderAttrText;
@property (nonatomic) NSString* editableText;
@property (nonatomic, unsafe_unretained) id<TextViewDelegate> delegate;
@property (nonatomic) bool editable;
@property (nonatomic) NSRange editableRange;
@property (nonatomic) NSRange markedRange;
@property (nonatomic) NSRange selectedRange;
@property (nonatomic) NSDictionary* linkStyle;
@property (nonatomic, readonly) float contentHeight;

// Replaces the attributes for the entire attributed string and specifies the
// attributes to use for new text (even if attrText is currently empty).
- (void)setAttributes:(NSDictionary*)attrs;
- (void)pinAutocorrectToKeyboard;
- (void)pinAutocorrectToWindow;

@end  // TextView

// local variables:
// mode: objc
// end:
