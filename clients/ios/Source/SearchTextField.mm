// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import "ContactsTableViewCell.h"
#import "MathUtils.h"
#import "SearchTextField.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kCancelButtonWidth = 62;

LazyStaticImage kSearchBarButtonDark(@"search-bar-button-dark.png", UIEdgeInsetsMake(14, 4, 14, 4));
LazyStaticImage kSearchBarButtonDarkActive(@"search-bar-button-dark-active.png", UIEdgeInsetsMake(14, 4, 14, 4));
LazyStaticImage kSearchBarTextField(@"search-bar-text-field.png", UIEdgeInsetsMake(4, 4, 4, 4));

LazyStaticUIFont kSearchBarButtonFont = { kProximaNovaSemibold, 16 };
LazyStaticUIFont kSearchFieldFont = { kProximaNovaRegular, 16 };

LazyStaticHexColor kButtonTitleColor = { "#ffffff" };
LazyStaticHexColor kButtonTitleActiveColor = { "#c9c7c7" };

UIButton* NewSearchBarButtonDark(NSString* title, float width, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  DCHECK_EQ(kSearchBarButtonDark.get().size.height, kSearchBarButtonDarkActive.get().size.height);
  b.frameSize = CGSizeMake(width, kSearchBarButtonDark.get().size.height);
  if (title) {
    b.titleLabel.font = kSearchBarButtonFont.get();
    [b setTitleColor:kButtonTitleColor
            forState:UIControlStateNormal];
    [b setTitleColor:kButtonTitleActiveColor
            forState:UIControlStateHighlighted];
    [b setTitle:title
       forState:UIControlStateNormal];

  }
  [b setBackgroundImage:kSearchBarButtonDark forState:UIControlStateNormal];
  [b setBackgroundImage:kSearchBarButtonDarkActive forState:UIControlStateHighlighted];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

}  // namespace

@implementation SearchTextField

@synthesize delegate = delegate_;
@synthesize searchField = search_field_;
@synthesize cancelButtonPadding = cancel_button_padding_;

+ (int)defaultHeight {
  return [ContactsTableViewCell rowHeight];
}

- (id)initWithFrame:(CGRect)frame {
  if (self = [super initWithFrame:frame]) {
    self.autoresizesSubviews = YES;
    self.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    self.backgroundColor =
        UIStyle::kContactsListSearchBackgroundColor;

    search_background_ =
        [[UIImageView alloc] initWithImage:kSearchBarTextField];
    search_background_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    search_background_.frameLeft = 8;
    search_background_.frameTop = 8;
    search_background_.userInteractionEnabled = YES;
    [self addSubview:search_background_];

    search_field_ = [UITextField new];
    search_field_.autocapitalizationType = UITextAutocapitalizationTypeNone;
    search_field_.autocorrectionType = UITextAutocorrectionTypeNo;
    search_field_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth;
    search_field_.clearButtonMode = UITextFieldViewModeWhileEditing;
    search_field_.delegate = self;
    search_field_.frameLeft = 11;
    search_field_.frameTop = 9;
    search_field_.frameHeight = 19;
    search_field_.font = kSearchFieldFont;
    search_field_.keyboardAppearance = UIKeyboardAppearanceLight;
    search_icon_ =
        [[UIImageView alloc]
          initWithImage:UIStyle::kContactsListSearch];
    // Provide padding on the right and bottom of the search icon in order for it
    // to properly align inside of the text field.
    search_icon_.contentMode = UIViewContentModeTopLeft;
    search_icon_.frameWidth = search_icon_.frameWidth + 7;
    search_icon_.frameHeight = search_icon_.frameHeight + 3;
    search_field_.leftView = search_icon_;
    search_field_.leftViewMode = UITextFieldViewModeAlways;
    // Add an empty input accessory view so we can grab keyboard the UIView
    // when the keyboard is shown.
    search_field_.inputAccessoryView = [UIView new];
    search_field_.placeholder = @"Search";
    search_field_.returnKeyType = UIReturnKeySearch;
    search_field_.text = @"";
    search_field_.textColor = UIStyle::kContactsListSearchTextColor;
    [search_background_ addSubview:search_field_];

    search_cancel_ = NewSearchBarButtonDark(@"Cancel", kCancelButtonWidth, self, @selector(cancelSearch));
    search_cancel_.alpha = 0;
    search_cancel_.autoresizingMask = UIViewAutoresizingFlexibleLeftMargin;
    search_cancel_.frameLeft = frame.size.width;
    [self addSubview:search_cancel_];

    __weak SearchTextField* weak_self = self;
    change_notification_.Init(
        UITextFieldTextDidChangeNotification,
        search_field_,
        ^(NSNotification* n) {
          [weak_self textChanged];
        });
  }
  return self;
}

- (void)layoutSubviews {
  search_background_.frameHeight = self.frameHeight -
      2 * search_background_.frameTop;
  search_cancel_.frameHeight = search_background_.frameHeight;
  search_cancel_.frameTop = search_background_.frameTop;
  [super layoutSubviews];
  [self updateSearchFieldSize];
}

- (void)updateSearchFieldSize {
  search_background_.frameWidth = search_cancel_.frameLeft -
      2 * search_background_.frameLeft - cancel_button_padding_;
  search_field_.frameWidth = search_background_.frameWidth -
      search_field_.frameLeft - 5;
}

- (void)select {
  [search_field_ becomeFirstResponder];
}

- (void)deselect {
  [search_field_ resignFirstResponder];
}

- (void)fadeCancelButton:(float)keyboard_top min:(float)min_y max:(float)max_y {
  search_cancel_.alpha =
      LinearInterp<float>(keyboard_top, min_y, max_y, 1, 0);
  search_cancel_.frameLeft =
      int(LinearInterp<float>(
              keyboard_top, min_y, max_y,
              self.frameWidth - search_cancel_.frameWidth -
              search_cancel_.frameTop, self.frameWidth));
}

- (void)showCancelButton {
  search_cancel_.alpha = 1;
  search_cancel_.frameLeft = self.frameWidth -
                             search_cancel_.frameWidth - search_cancel_.frameTop;
}

- (void)hideCancelButton {
  search_cancel_.alpha = 0;
  search_cancel_.frameLeft = self.frameWidth;
}

- (void)showSpinner {
  if (!spinner_) {
    spinner_ = [[UIActivityIndicatorView alloc]
                 initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleGray];
    spinner_.frame = search_icon_.frame;
  }
  search_field_.leftView = spinner_;
  [spinner_ startAnimating];
}

- (void)hideSpinner {
  [spinner_ stopAnimating];
  search_field_.leftView = search_icon_;
}

- (BOOL)textField:(UITextField*)text_field
shouldChangeCharactersInRange:(NSRange)range
replacementString:(NSString*)string {
  BOOL result = YES;
  if ([self.delegate respondsToSelector:@selector(searchField:shouldChangeCharactersInRange:replacementString:)]) {
    result = [self.delegate searchField:self
                  shouldChangeCharactersInRange:range
                        replacementString:string];
  }
  return result;
}

- (BOOL)textFieldShouldReturn:(UITextField*)text_field {
  bool should_return = true;
  if ([self.delegate respondsToSelector:@selector(searchFieldShouldReturn:)]) {
    should_return = [self.delegate searchFieldShouldReturn:self];
  }
  if (should_return) {
    // Never actually return immediately; do it ourselves so we have control over the animation.
    dispatch_after_main(0, ^{
        [search_field_ resignFirstResponder];
      });
  }
  return NO;
}

- (BOOL)textFieldShouldClear:(UITextField*)text_field {
  // We show the clear button while the field is not being edited so it can be used to cancel the search,
  // but if we return YES here iOS will activate editing mode.  Clear the text by hand instead.
  text_field.text = @"";
  [self textChanged];
  return NO;
}

- (void)textFieldDidBeginEditing:(UITextField*)text_field {
  if ([self.delegate respondsToSelector:@selector(searchFieldDidBeginEditing:)]) {
    [self.delegate searchFieldDidBeginEditing:self];
  }
}

- (void)textFieldDidEndEditing:(UITextField*)text_field {
  if ([self.delegate respondsToSelector:@selector(searchFieldDidEndEditing:)]) {
    [self.delegate searchFieldDidEndEditing:self];
  }
}

- (void)cancelSearch {
  if (!ToSlice(search_field_.text).empty()) {
    search_field_.text = @"";
    [self.delegate searchFieldDidChange:self];
  }
  // We need to resign the first responder after clearing the search field in
  // order to avoid an animation scrolling oddity.
  [search_field_ resignFirstResponder];
}

- (NSString*)text {
  return search_field_.text;
}

- (void)textChanged {
  UITextField* field = self.searchField;
  field.clearButtonMode = (field.text.length > 0) ? UITextFieldViewModeAlways : UITextFieldViewModeNever;
  [self.delegate searchFieldDidChange:self];
}

@end  // SearchTextField
