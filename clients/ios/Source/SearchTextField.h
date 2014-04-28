// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import <UIKit/UITextField.h>
#import <UIKit/UIView.h>
#import "ScopedNotification.h"

@class SearchTextField;
@class UIActivityIndicatorView;

@protocol SearchTextFieldDelegate <NSObject>
- (void)searchFieldDidChange:(SearchTextField*)field;
@optional
- (void)searchFieldDidBeginEditing:(SearchTextField*)field;
- (void)searchFieldDidEndEditing:(SearchTextField*)field;
- (bool)searchFieldShouldReturn:(SearchTextField*)field;
- (BOOL)searchField:(SearchTextField*)field
    shouldChangeCharactersInRange:(NSRange)range
    replacementString:(NSString*)string;
@end  // SearchTextFieldDelegate

@interface SearchTextField : UIView<UITextFieldDelegate> {
 @private
  __weak id<SearchTextFieldDelegate> delegate_;
  UIView* search_background_;
  UITextField* search_field_;
  UIButton* search_cancel_;
  UIImageView* search_icon_;
  UIActivityIndicatorView* spinner_;
  float cancel_button_padding_;
  ScopedNotification change_notification_;
}

+ (int)defaultHeight;

- (void)updateSearchFieldSize;
- (void)select;
- (void)deselect;
- (void)cancelSearch;
- (void)showSpinner;
- (void)hideSpinner;
- (void)showCancelButton;
- (void)hideCancelButton;
- (void)fadeCancelButton:(float)keyboard_top min:(float)min_y max:(float)max_y;

@property (weak, nonatomic) id<SearchTextFieldDelegate> delegate;
@property (nonatomic) UITextField* searchField;
// Spacing between text field and cancel button, to allow room for the alphabetic index in the table view.
@property (nonatomic) float cancelButtonPadding;
@property (readonly, nonatomic) NSString* text;

@end  // SearchTextField
