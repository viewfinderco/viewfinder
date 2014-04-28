// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <QuartzCore/CAAnimation.h>
#import <UIKit/UILabel.h>
#import <UIKit/UITextField.h>
#import "CALayer+geometry.h"
#import "Logging.h"
#import "ScopedPtr.h"
#import "StringUtils.h"
#import "TokenizedTextView.h"
#import "UIScrollView+visibleBounds.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kShortDuration = 0.1;

// Color schemes for contact and viewpoint cells.
// Outer array is type (see enum in TokenizedTextView.h)
// Second array is selection state.
// Inner array is one of k{Background,Text}Color.
const int kUnselectedColors = 0;
const int kSelectedColors = 1;

const int kBackgroundColor = 0;
const int kBorderColor = 1;
const int kTextColor = 2;

LazyStaticHexColor kColorScheme[4][2][3] = {
  // User himself.
  { { { "#ece9e9" },
      { "#cfcbcb" },
      { "#3f3e3e" }, },
    { { "#bfbbbb" },
      { "#9f9c9c" },
      { "#3f3e3e" }, }, },
  // Newly added users.
  { { { "#c7dbea" },
      { "#2070aa" },
      { "#3f3e3e" }, },
    { { "#2070aa" },
      { "#2070aa" },
      { "#ffffff" }, }, },
  // Previously-existing users.
  { { { "#ece9e9" },
      { "#cfcbcb" },
      { "#3f3e3e" }, },
    { { "#bfbbbb" },
      { "#9f9c9c" },
      { "#3f3e3e" }, }, },
  // Search tokens.
  { { { "#dfdbdb" },
      { "#dfdbdb" },
      { "#3f3e3e" }, },
    { { "#2070aa" },
      { "#2070aa" },
      { "#ffffff" }, }, },
};

LazyStaticImage kFollowerTokenEmailInvite(@"followers-token-email-invite.png");
LazyStaticImage kFollowerTokenEmailInviteSelected(@"followers-token-email-invite-selected.png");
LazyStaticImage kFollowerTokenSMSInvite(@"followers-token-sms-invite.png");
LazyStaticImage kFollowerTokenSMSInviteSelected(@"followers-token-sms-invite-selected.png");

}  // namespace

TextViewToken::~TextViewToken() {
}

@interface TokenizedTextView (internal)

- (void)deselect:(UITextField*)text_field;

@end  // TokenizedTextView (internal)

@interface TokenCellView : UIView {
  ScopedPtr<const TextViewToken> token_;
  const TokenizedTextViewOptions* options_;
  UILabel* label_;
  UIImageView* invite_;
  UIImageView* remove_;
  CGSize label_desired_size_;
  bool selected_;
}

@property (nonatomic) bool selected;
@property (nonatomic, readonly) const TextViewToken& token;
@property (nonatomic, readonly) UIImage* inviteImage;
@property (nonatomic, readonly) UIImage* removeImage;

// Takes ownership of token.
- (id)initWithToken:(const TextViewToken*)token
       withMaxWidth:(float)max_width
        withOptions:(const TokenizedTextViewOptions&)options;

@end  // TokenCellView

@implementation TokenCellView

- (const TextViewToken&)token {
  return *token_;
}

- (id)initWithToken:(const TextViewToken*)token
       withMaxWidth:(float)max_width
        withOptions:(const TokenizedTextViewOptions&)options {
  if (self = [super init]) {
    token_.reset(token);
    options_ = &options;

    self.layer.cornerRadius = options_->token_corner_radius;
    self.layer.borderWidth = 0.5;

    label_ = [UILabel new];
    label_.clipsToBounds = NO;
    label_.backgroundColor = [UIColor clearColor];
    label_.font = token_->colors() == TextViewToken::SELF ? options.bold_font : options.font;
    label_.text = NewNSString(token_->text());
    label_.lineBreakMode = NSLineBreakByTruncatingTail;
    [label_ sizeToFit];
    label_desired_size_ = label_.frameSize;
    label_desired_size_.height = options.font.lineHeight * options_->emoji_extra_height_factor;
    label_.frameSize = label_desired_size_;
    [self addSubview:label_];

    // Add an invite image if prospective is not NONE.
    if (token_->prospective() != TextViewToken::NONE) {
      [self addProspectiveInviteImage];
    }
    // Add remove image if removable.
    if (token_->removable()) {
      [self addRemoveImage];
    }

    self.frameSize = [self desiredSize];
    // Enforce maximum width by shortening label width.
    if (self.frameWidth > max_width) {
      const float diff = self.frameWidth - max_width;
      self.frameWidth = max_width;
      label_.frameWidth -= diff;
    }

    [self setColors];
  }
  return self;
}

- (bool)isTouchForRemove:(UITouch*)touch {
  const CGPoint p = [touch locationInView:remove_];
  return CGRectContainsPoint(remove_.bounds, p);
}

- (UIImage*)inviteImage {
  if (token_->prospective() == TextViewToken::SMS) {
    return selected_ ? kFollowerTokenSMSInviteSelected : kFollowerTokenSMSInvite;
  } else {
    DCHECK_EQ(token_->prospective(), TextViewToken::EMAIL);
    return selected_ ? kFollowerTokenEmailInviteSelected : kFollowerTokenEmailInvite;
  }
}

- (UIImage*)removeImage {
  return token_->remove_image(selected_);
}

- (void)addProspectiveInviteImage {
  invite_ = [[UIImageView alloc] initWithImage:self.inviteImage];
  [self addSubview:invite_];
}

- (void)addRemoveImage {
  remove_ = [[UIImageView alloc] initWithImage:self.removeImage];
  [self addSubview:remove_];
}

- (CGSize)desiredSize {
  CGSize s = label_desired_size_;
  s.height += options_->top_inset_y + options_->bottom_inset_y;

  if (invite_) {
    s.width += invite_.frameWidth;
  } else {
    s.width += options_->inset_x;
  }
  if (remove_) {
    s.width += remove_.frameWidth;
  } else {
    s.width += options_->inset_x;
  }

  return s;
}

- (void)setColors {
  self.backgroundColor = kColorScheme[token_->colors()][selected_][kBackgroundColor];
  self.layer.borderColor = kColorScheme[token_->colors()][selected_][kBorderColor];
  label_.textColor = kColorScheme[token_->colors()][selected_][kTextColor];
  if (invite_) {
    invite_.image = self.inviteImage;
  }
  if (remove_) {
    remove_.image = self.removeImage;
  }
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  ScopedDisableCAActions disable_actions;
  if (!options_) {
    // This method may be called in the superclass constructor before options_ is set;
    // we can bail out at this point and it will be called again later.
    return;
  }
  label_.frameTop = options_->top_inset_y;
  label_.frameLeft = options_->inset_x;
  if (invite_) {
    label_.frameLeft = invite_.frameRight;
  }
  if (remove_) {
    label_.frameWidth = std::min(label_desired_size_.width,
                                 f.size.width - label_.frameLeft - remove_.frameWidth);
    remove_.frameLeft = label_.frameRight;
  } else {
    label_.frameWidth = std::min(label_desired_size_.width,
                                 f.size.width - label_.frameLeft - options_->inset_x);
  }
}

- (bool)selected {
  return selected_;
}

- (void)setSelected:(bool)v {
  if (selected_ == v) {
    return;
  }
  selected_ = v;
  [self setColors];
}

@end  // TokenCellView

@implementation TokenizedTextField

@synthesize disablePaste = disable_paste_;
@synthesize showFullTable = show_full_table_;
@synthesize showPlaceholder = show_placeholder_;

- (id)initWithParent:(TokenizedTextView*)parent {
  if (self = [super init]) {
    parent_ = parent;
    selected_token_ = -1;
    disable_paste_ = true;
    show_placeholder_ = true;

    self.autoresizingMask =
        UIViewAutoresizingFlexibleWidth;
    self.backgroundColor = [UIColor whiteColor];
    self.textColor = [UIColor blackColor];
    self.borderStyle = UITextBorderStyleNone;
    self.autocorrectionType = UITextAutocorrectionTypeNo;
    self.autocapitalizationType = UITextAutocapitalizationTypeNone;
    self.returnKeyType = UIReturnKeyDefault;
    self.enablesReturnKeyAutomatically = NO;
    self.clearButtonMode = UITextFieldViewModeNever;
  }
  return self;
}

- (void)deleteBackward {
  if ([self.text length] == 0) {
    [parent_ deleteBackward];
  } else {
    [super deleteBackward];
  }
}

- (BOOL)canPerformAction:(SEL)action withSender:(id)sender {
  if (selected_token_ >= 0) {
    return NO;
  }
  const Slice s(ToSlice(self.text));
  if ((s.empty()) &&
      (action == @selector(select:) ||
       action == @selector(selectAll:) ||
       action == @selector(copy:) ||
       action == @selector(cut:) ||
       action == @selector(delete:) ||
       (disable_paste_ && action == @selector(paste:)))) {
    return NO;
  }
  return [super canPerformAction:action withSender:sender];
}

- (void)touchesBegan:(NSSet*)touches withEvent:(UIEvent*)event {
  UITouch* touch = [touches anyObject];

  if ([touch.view isKindOfClass:[TokenCellView class]]) {
    [parent_ touchesBegan:touches withEvent:event];
    return;
  }
  if (selected_token_ >= 0) {
    [parent_ deselect:self];
    return;
  }
  [super touchesBegan:touches withEvent:event];
}

- (CGRect)textRectForBounds:(CGRect)bounds {
  CGRect r = bounds;
  r.origin.x += cursor_.x;
  // This method may be called in the superclass constructor before parent_ is set.
  r.origin.y += cursor_.y + (parent_ ? parent_.options.text_top_inset_y : 0);
  r.size.width -= cursor_.x;
  if (self.rightView) {
    r.size.width -= [self rightViewRectForBounds:bounds].size.width;
  }
  return r;
}

- (CGRect)editingRectForBounds:(CGRect)bounds {
  return [self textRectForBounds:bounds];
}

- (CGRect)placeholderRectForBounds:(CGRect)bounds {
  if (show_placeholder_) {
    return [self textRectForBounds:bounds];
  } else {
    return CGRectZero;
  }
}

- (CGRect)leftViewRectForBounds:(CGRect)bounds {
  if (self.leftView) {
    bounds.size = self.leftView.frameSize;
  }
  return bounds;
}

- (CGRect)rightViewRectForBounds:(CGRect)bounds {
  if (self.rightView) {
    bounds.origin.x = bounds.size.width - self.rightView.frameWidth;
    bounds.origin.y = bounds.size.height - self.rightView.frameHeight;
    bounds.size = self.rightView.bounds.size;
  }
  return bounds;
}

- (CGPoint*)cursor {
  return &cursor_;
}

- (int)selectedToken {
  return selected_token_;
}

- (void)setSelectedToken:(int)v {
  if (selected_token_ == v) {
    return;
  }
  selected_token_ = v;
  [self setNeedsLayout];
}

- (bool)isEditing {
  return self.isFirstResponder || self.showFullTable;
}

@end  // TokenizedTextField


@interface TokenizedTextScrollView : UIScrollView {
}

@end  // TokenizedTextScrollView

@implementation TokenizedTextScrollView

- (BOOL)touchesShouldCancelInContentView:(UIView*)view {
  return YES;
}

@end  // TokenizedTextScrollView


@implementation TokenizedTextView

@synthesize options = options_;
@synthesize field = field_;
@synthesize delegate = delegate_;
@synthesize editingFieldHeight = editing_field_height_;

- (id)initWithDelegate:(id<TokenizedTextViewDelegate>)delegate
           withOptions:(const TokenizedTextViewOptions&)options {
  if (self = [super init]) {
    self.autoresizesSubviews = YES;

    delegate_ = delegate;
    options_ = options;
    min_height_ = options.min_height;
    line_height_ = [options.font lineHeight] * options_.emoji_extra_height_factor;

    scroll_view_ = [TokenizedTextScrollView new];
    scroll_view_.autoresizesSubviews = YES;
    scroll_view_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    scroll_view_.canCancelContentTouches = YES;
    scroll_view_.delaysContentTouches = NO;
    scroll_view_.scrollsToTop = NO;
    //scroll_view_.frameHeight = std::max(min_height_, line_height_ + options_.margin_y + options_.top_inset_y);
    [self addSubview:scroll_view_];

    field_ = [[TokenizedTextField alloc] initWithParent:self];
    field_.autocorrectionType = UITextAutocorrectionTypeNo;
    field_.autocapitalizationType = UITextAutocapitalizationTypeNone;
    field_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    // contentVerticalAlignment defaults to center in iOS 7 and top in older versions.
    // The rect returned by textRectForBounds is adjusted based on this field.
    field_.contentVerticalAlignment = UIControlContentVerticalAlignmentTop;
    field_.delegate = self;
    field_.font = options_.font;
    field_.keyboardAppearance = UIKeyboardAppearanceAlert;
    field_.text = @"";
    field_.disablePaste = false;
    [scroll_view_ addSubview:field_];

    __weak TokenizedTextView* weak_self = self;
    change_notification_.Init(
        UITextFieldTextDidChangeNotification,
        field_,
        ^(NSNotification* n) {
          [weak_self.delegate tokenizedTextViewChangedText:weak_self];
        });

  }
  return self;
}

- (void)willMoveToSuperview:(UIView*)new_superview {
  if (new_superview) {
    keyboard_will_show_.Init(
        UIKeyboardWillShowNotification,
        ^(NSNotification* n) {
          const Dict d(n.userInfo);
          const double duration =
              d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve =
              d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
          [UIView animateWithDuration:duration
                                delay:0
                              options:curve|UIViewAnimationOptionBeginFromCurrentState
                           animations:^{
              [self updateHeight:duration];
            }
         completion:NULL];
        });
    keyboard_will_hide_.Init(
        UIKeyboardWillHideNotification,
        ^(NSNotification* n) {
          const Dict d(n.userInfo);
          const double duration =
              d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve =
              d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
          [UIView animateWithDuration:duration
                                delay:0
                              options:curve|UIViewAnimationOptionBeginFromCurrentState
                           animations:^{
              [self updateHeight:duration];
            }
         completion:NULL];
        });
  } else {
    keyboard_will_show_.Clear();
    keyboard_will_hide_.Clear();
  }
}

- (void)addToken:(const TextViewToken*)token {
  // We don't use the right view when computing space available for
  // tokens as any tokens which would exceed 60% of the width wrap to
  // next line. So we'll never been close on a line with the right view.
  const float max_width = self.frameWidth - options_.inset_x -
                          (field_.leftView ? field_.leftView.frameWidth - 4 : options_.padding_x * 2);
  tokens_.push_back([[TokenCellView alloc] initWithToken:token
                                            withMaxWidth:max_width
                                             withOptions:options_]);
  [delegate_ tokenizedTextViewChangedTokens:self];
  [field_ addSubview:tokens_.back()];
  [self setNeedsLayout];
}

- (int)numTokens {
  return tokens_.size();
}

- (const TextViewToken&)getToken:(int)i {
  return tokens_[i].token;
}

- (void)removeToken:(int)i {
  [tokens_[i] removeFromSuperview];
  tokens_.erase(tokens_.begin() + i);
}

- (void)layoutSubviews {
  [self updateHeight:0];
  [super layoutSubviews];
}

- (void)touchesBegan:(NSSet*)touches withEvent:(UIEvent*)event {
  UITouch* touch = [touches anyObject];
  if ([touch.view isKindOfClass:[TokenCellView class]]) {
    if (field_.selectedToken >= 0) {
      tokens_[field_.selectedToken].selected = false;
    }
    for (int i = 0; i < tokens_.size(); ++i) {
      if (tokens_[i] == touch.view) {
        if ([tokens_[i] isTouchForRemove:touch]) {
          field_.selectedToken = i;
          tokens_[i].selected = true;
          [self removeSelectedToken];
          return;
        }
        if (tokens_[i].token.frozen() || field_.selectedToken == i) {
          field_.selectedToken = -1;
          return;
        }
        field_.selectedToken = i;
        tokens_[i].selected = true;
        return;
      }
    }
  }
  [super touchesBegan:touches withEvent:event];
}

- (void)deleteBackward {
  // Text entry when there is a selected contact. If this is a deletion, delete the token.
  // If this is new text deselect the token.
  if (field_.selectedToken >= 0) {
    [self removeSelectedToken];
    [self clearText];

    if (!tokens_.empty()) {
      [self updateHeight:kShortDuration];
    }
  } else if (!tokens_.empty()) {
    // Select the last contact, but only if it was not populated from
    // an existing viewpoint.
    const int index = tokens_.size() - 1;
    if (!tokens_[index].token.frozen()) {
      field_.selectedToken = index;
      tokens_[index].selected = true;
      [self setNeedsLayout];
    }
  }
}

- (BOOL)textField:(UITextField*)text_field
shouldChangeCharactersInRange:(NSRange)range
replacementString:(NSString*)string {
  if (field_.selectedToken >= 0) {
    tokens_[field_.selectedToken].selected = false;
    field_.selectedToken = -1;
  }

  return YES;
}

- (void)removeSelectedToken {
  const int token_index = field_.selectedToken;
  if (token_index == -1 || tokens_[token_index].token.frozen()) {
    return;
  }
  tokens_[token_index].selected = false;
  field_.selectedToken = -1;
  [delegate_ tokenizedTextViewQueryRemoveToken:self
                                         token:tokens_[token_index].token
                                  withCallback:^{
      [self removeToken:token_index];
      [delegate_ tokenizedTextViewChangedTokens:self];
      [self updateHeight:kShortDuration];
    }];
}

- (void)pauseEditing {
  field_.textColor = [UIColor lightGrayColor];
  field_.delegate = NULL;
}

- (void)resumeEditing {
  field_.textColor = [UIColor blackColor];
  [field_ becomeFirstResponder];
  field_.delegate = self;
}

- (bool)canEndEditing {
  return [delegate_ tokenizedTextViewShouldEndEditing:self];
}

- (void)clearText {
  field_.text = @"";
}

- (BOOL)textFieldShouldClear:(UITextField*)text_field {
  field_.selectedToken = -1;
  bool update_height = false;
  for (int i = 0; i < tokens_.size(); ++i) {
    if (tokens_[i].token.colors() != TextViewToken::NEW) {
      continue;
    }
    [tokens_[i] removeFromSuperview];
    tokens_.erase(tokens_.begin() + i);
    [delegate_ tokenizedTextViewChangedTokens:self];
    --i;
    update_height = true;
  }
  return YES;
}

- (BOOL)textFieldShouldBeginEditing:(UITextField*)text_field {
  return [delegate_ tokenizedTextViewShouldBeginEditing:self];
}

- (void)textFieldDidBeginEditing:(UITextField*)text_field {
  field_.textColor = [UIColor blackColor];
  [self updateHeight:kShortDuration];
  [delegate_ tokenizedTextViewDidBeginEditing:self];
}

- (void)textFieldDidEndEditing:(UITextField*)text_field {
  field_.textColor = [UIColor lightGrayColor];
  [self updateHeight:kShortDuration];
  [delegate_ tokenizedTextViewDidEndEditing:self];
}

- (BOOL)textFieldShouldReturn:(UITextField*)text_field {
  [delegate_ tokenizedTextViewShouldReturn:self];
  return NO;
}

- (float)layoutToField {
  const float x_min = field_.leftView ? field_.leftView.frame.size.width - 4 : options_.margin_x * 2;
  const float x_max = std::min<float>(320, self.bounds.size.width) - options_.margin_x;
  const float line_size = line_height_ + options_.top_inset_y + options_.bottom_inset_y;
  const float y_step = line_size + options_.padding_y;
  CGPoint* cursor = field_.cursor;
  cursor->x = x_min;
  cursor->y = options_.margin_y;

  for (int i = 0; i < tokens_.size(); ++i) {
    TokenCellView* token = tokens_[i];
    CGRect f = CGRectZero;
    f.size = token.desiredSize;
    if (cursor->x > x_min &&
        cursor->x + f.size.width >= x_max) {
      cursor->x = x_min;
      cursor->y += y_step;
    }

    f.origin.x = cursor->x;
    f.origin.y = cursor->y;
    if (CGRectGetMaxX(f) >= x_max) {
      f.size.width = x_max - f.origin.x;
    }

    token.frame = f;

    cursor->x += f.size.width + options_.padding_x;
  }

  // If we're currently editing, make sure we have enough room for text entry,
  // starting a new line if necessary.
  // TODO(pmattis): Take into account rightViewRectForBounds. Start a new
  // line if the current line starts at >= 60% of the available width.
  if (field_.isEditing &&
      cursor->x > x_min &&
      x_max - cursor->x < options_.text_wrap_width) {
    cursor->x = x_min;
    cursor->y += y_step;
  }

  return cursor->y + line_size + options_.margin_y;
}

- (void)updateHeight:(float)duration {
  CGRect frame = field_.frame;
  frame.size.height = std::max(min_height_, [self layoutToField]);
  CGRect scroll_frame = frame;
  scroll_frame.origin.y = 0;

  const Slice text(ToSlice(field_.text));
  editing_field_height_ = scroll_frame.size.height;
  if ((field_.isFirstResponder && !text.empty()) ||
      field_.showFullTable) {
    editing_field_height_ = std::min(
        editing_field_height_,
        line_height_ * 2 + options_.margin_y + options_.top_inset_y + options_.bottom_inset_y);
    // Disable scrolling while we're editing text.
    scroll_view_.scrollEnabled = NO;
  } else {
    // Enable scrolling when we're not editing text.
    scroll_view_.scrollEnabled = YES;
  }

  [UIView animateWithDuration:duration
                        delay:0
                      options:UIViewAnimationOptionBeginFromCurrentState
                   animations:^{
      // TODO(pmattis): The scroll content offset gets set incorrectly below if
      // the scroll offset is not currently at the farthest position. I have
      // not been able to figure out why. Grrr.
      field_.frame = frame;
      scroll_view_.contentSize = frame.size;
      scroll_view_.contentOffset = CGPointMake(
          0, frame.size.height - scroll_frame.size.height);
      scroll_view_.frame = scroll_frame;

      // Only update our height (and notify our delegate) if it is actually
      // changing.
      if (self.frameHeight != scroll_view_.frameBottom) {
        self.frameHeight = scroll_view_.frameBottom;
        if ([delegate_ respondsToSelector:@selector(tokenizedTextViewChangedSize:)]) {
          [delegate_ tokenizedTextViewChangedSize:self];
        }
      }
    }
                   completion:NULL];
}

- (void)deselect:(UITextField*)text_field {
  if (text_field == field_) {
    if (field_.selectedToken >= 0) {
      tokens_[field_.selectedToken].selected = false;
      field_.selectedToken = -1;
      [self setNeedsLayout];
    }
  }
}

- (void)dealloc {
  field_.delegate = NULL;
}

@end  // TokenizedTextView
