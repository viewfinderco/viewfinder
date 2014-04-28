// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

// TODO(peter): Add support for the correction menu. See code in EGOTextView.
//
// TODO(peter): Add support for a loupe and magnifying glass for more precise
// selection. See code in EGOTextView.

#import "Appearance.h"
#import "CALayer+geometry.h"
#import "Linkifier.h"
#import "Logging.h"
#import "MagnifierView.h"
#import "TextView.h"
#import "UIView+geometry.h"

namespace {

const float kTouchRectSize = 10;
const double kCaretBlinkRate = 1.0;
const double kCaretInitialBlinkDelay = 0.6;

LazyStaticRgbColor kCaretColor = { Vector4f(0.259, 0.420, 0.949, 1) };
LazyStaticRgbColor kSelectionColor = { Vector4f(0.8, 0.867, 0.929, 1.0) };
LazyStaticImage kDragDot(@"drag-dot.png");

NSString* const kCaretBlinkAnimationKey = @"BlinkAnimation";

// Add a trailing space character so that blank lines at the end of the string
// are drawn properly.
void AddTrailingCharacter(NSMutableAttributedString* attr_str) {
  [attr_str replaceCharactersInRange:NSMakeRange(attr_str.length, 0)
                            withString:@" "];
}

}  // namespace

@interface IndexedPosition : UITextPosition {
 @private
  int index_;
}

@property (nonatomic) int index;
+ (IndexedPosition*)positionWithIndex:(int)index;

@end  // IndexedPosition

@implementation IndexedPosition

@synthesize index = index_;

+ (IndexedPosition*)positionWithIndex:(int)index {
  IndexedPosition* pos = [IndexedPosition new];
  pos.index = index;
  return pos;
}

@end  // IndexedPosition

@interface IndexedRange : UITextRange {
 @private
  NSRange range_;
}

@property (nonatomic) NSRange range;
+ (IndexedRange*)rangeWithNSRange:(NSRange)range;

@end  // IndexedRange

@implementation IndexedRange

@synthesize range = range_;

+ (IndexedRange*)rangeWithNSRange:(NSRange)r {
  if (r.location == NSNotFound) {
    return NULL;
  }
  IndexedRange* range = [IndexedRange new];
  range.range = r;
  return range;
}

- (UITextPosition*)start {
  return [IndexedPosition positionWithIndex:range_.location];
}

- (UITextPosition*)end {
  return [IndexedPosition positionWithIndex:(range_.location + range_.length)];
}

- (BOOL)isEmpty {
  return (range_.length == 0);
}

@end  // IndexedRange

@implementation TextView

// UITextInput properties.
@synthesize markedTextStyle = marked_text_style_;
@synthesize inputDelegate = input_delegate_;

// TextView properties.
@synthesize delegate = delegate_;
@synthesize linkStyle = link_style_;

- (id)init {
  if (self = [self initWithFrame:CGRectZero]) {
  }
  return self;
}

- (id)initWithFrame:(CGRect)f {
  if (self = [super initWithFrame:f]) {
    [super setDelegate:self];

    // self.backgroundColor = MakeUIColor(1, 0, 0, 0.1);
    accessory_view_ = [UIView new];

    // NOTE(peter): The marked range must correspond to [NSNotFound,0] when
    // empty. Failure to do causes autocapitalization to break because the iOS
    // keyboard asks what the marked range and sees it is [0,0] and thus always
    // uses that (empty) range to determine the autocapitalization state.
    marked_range_ = NSMakeRange(NSNotFound, 0);
    selected_range_ = NSMakeRange(0, 0);

    autocorrection_type_ = UITextAutocorrectionTypeDefault;
    autocapitalization_type_ = UITextAutocapitalizationTypeSentences;
    spell_checking_type_ = UITextSpellCheckingTypeDefault;
    return_key_type_ = UIReturnKeyDefault;
    keyboard_type_ = UIKeyboardTypeDefault;

    text_layer_ = [TextLayer new];
    text_layer_.anchorPoint = CGPointMake(0, 0);
    // text_layer_.backgroundColor = MakeUIColor(0, 0, 1, 0.1).CGColor;
    text_layer_.maxWidth = f.size.width;
    [self.layer addSublayer:text_layer_];

    attr_text_ = [NSMutableAttributedString new];
    AddTrailingCharacter(attr_text_);

    editable_ = true;

    long_press_ = [[UILongPressGestureRecognizer alloc]
                    initWithTarget:self
                            action:@selector(handleLongPress:)];
    long_press_.delegate = self;
    long_press_.minimumPressDuration = 0.5;
    [self addGestureRecognizer:long_press_];

    short_press_ = [[UILongPressGestureRecognizer alloc]
                     initWithTarget:self
                             action:@selector(handleShortPress:)];
    short_press_.delegate = self;
    short_press_.minimumPressDuration = 0;
    [self addGestureRecognizer:short_press_];

    single_tap_ = [[UITapGestureRecognizer alloc]
                    initWithTarget:self
                            action:@selector(handleSingleTap:)];
    single_tap_.delegate = self;
    [single_tap_ requireGestureRecognizerToFail:long_press_];
    [self addGestureRecognizer:single_tap_];
  }
  return self;
}

- (BOOL)conformsToProtocol:(Protocol*)protocol {
  if (protocol == @protocol(UIKeyInput)) {
    // Conforming to the UIKeyInput protocol causes the keyboard to appear. We
    // want to only conform to this protocol if the TextView is editable or if
    // the old first responder exists.
    return editable_ || old_first_responder_;
  }
  return [super conformsToProtocol:protocol];
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  text_layer_.maxWidth = f.size.width -
      self.contentInsetLeft - self.contentInsetRight;
  self.contentSize = text_layer_.frameSize;
  self.scrollEnabled = self.contentSize.height > self.frameHeight;
  self.clipsToBounds = self.scrollEnabled;
  [self delayedSelectionChanged];
}

- (void)layoutSubviews {
  [super layoutSubviews];

  // This is a hack. Auto-corrections are performed by iOS adding a view of the
  // type "UIAutocorrectInlinePrompt" to our TextView. But since it is added as
  // a subview, it will lie underneath any rows that follow. The hack is to
  // reparent this auto-correction view so that it it is a subview of the
  // keyboard window.
  //
  // Note that iOS is exceptionally tricky in its handling of the autocorrect
  // view. When a scroll view is scrolled, iOS automatically reparents the
  // autocorrect view into the scroll view so that it scrolls properly. When
  // the scrolling finishes, the autocorrect view is moved back to its old
  // location. This almost works perfectly for us, except it sometimes leaves
  // the autocorrect view visible when it shouldn't. The following lines seem
  // to take care of that, though I'm not precisely sure why they are
  // necessary.
  if (self.dragging || self.decelerating) {
    // The scroll view is currently dragging/decelerating, do nothing.
    return;
  }

  for (UIView* v in self.subviews) {
    if (![v isKindOfClass:NSClassFromString(@"UIAutocorrectInlinePrompt")]) {
      continue;
    }
    if (!CGRectIntersectsRect(v.frame, self.bounds)) {
      // The autocorrect view is not visible.
      continue;
    }
    autocorrect_view_ = v;
    [self performSelector:@selector(pinAutocorrectToWindow)
               withObject:NULL
               afterDelay:0];
  }
}

- (void)pinAutocorrectToView:(UIView*)p {
  UIView* v = autocorrect_view_;
  if (!v) {
    return;
  }
  if (v.superview == p) {
    // The autocorrect view is already pinned to the correct parent
    // view. Nothing to do.
    return;
  }
  // Correct the autocorrect frame to window device coordinates and then back
  // down to the parent view coordinates. This is necessary because the
  // autocorrect view and the new parent view might not be part of the same
  // UIWindow hierarchy.
  CGRect f = [v convertRect:v.bounds toView:NULL];
  f = [p convertRect:f fromView:NULL];
  v.frame = f;
  [p addSubview:v];
}

- (void)pinAutocorrectToKeyboard {
  if (kIOSVersion < "6.0") {
    [self pinAutocorrectToWindow];
  } else {
    [self pinAutocorrectToView:accessory_view_];
  }
}

- (void)pinAutocorrectToWindow {
  if (kIOSVersion < "6.0") {
    // iOS 5 was not nearly as fancy in its handling of the autocorrect
    // view. Don't try to reparent to the keyboard window but instead reparent
    // to to either ourselves (if scrolling is enabled) or our parent scroll
    // view.
    UIView* p = self.scrollEnabled ? self : self.parentScrollView;
    if (!p) {
      // If we don't have a parent scroll view, just leave the autocorrect as a
      // subview of self. We can't add the autocorrect to the top-level window
      // on iOS 5 because it won't be scrolled correctly and trying to track
      // when scrolling starts and doing the reparenting ourself is much too
      // difficult.
      p = self;
    }
    [self pinAutocorrectToView:p];
  } else {
    [self pinAutocorrectToView:accessory_view_.window];
  }
}

- (void)setAttributes:(NSDictionary*)attrs {
  [attr_text_ setAttributes:attrs range:NSMakeRange(0, attr_text_.length)];
  [self attrTextChanged];
}

- (NSAttributedString*)attrText {
  return [attr_text_ attributedSubstringFromRange:
                       NSMakeRange(0, attr_text_.length - 1)];
}

- (void)setAttrText:(NSAttributedString*)attr_text {
  // LOG("set attr text: '%s'", attr_text.string);
  [input_delegate_ textWillChange:self];
  attr_text_ = [attr_text mutableCopy];
  editable_range_ = NSMakeRange(0, attr_text_.length);
  AddTrailingCharacter(attr_text_);
  [input_delegate_ textDidChange:self];
  [self attrTextChanged];
}

- (NSAttributedString*)placeholderAttrText {
  return placeholder_attr_text_;
}

- (void)setPlaceholderAttrText:(NSAttributedString*)s {
  placeholder_attr_text_ = [s copy];
  [self attrTextChanged];
}

- (void)attrTextChanged {
  // LOG("attr text changed: %d: '%s'", editable_range_, attr_text_.string);

  // Linkify a copy of the attributed string, not the attributed string we're
  // editing. This is necessary so that the link attributes don't get "stuck"
  // (i.e. enabled past the end of the link) at the end of the string.
  NSArray* links = link_style_ ? [self findLinks] : NULL;
  NSAttributedString* view_text;
  if (links.count > 0) {
    NSMutableAttributedString* mutable_copy = [attr_text_ mutableCopy];
    ApplyLinkAttributes(mutable_copy, links, link_style_);
    view_text = mutable_copy;
  } else if (!self.hasText && placeholder_attr_text_) {
    NSMutableAttributedString* mutable_copy = [attr_text_ mutableCopy];
    [mutable_copy replaceCharactersInRange:editable_range_
                      withAttributedString:placeholder_attr_text_];
    view_text = mutable_copy;
  } else {
    view_text = [attr_text_ copy];
  }

  text_layer_.attrStr = view_text;
  self.contentSize = text_layer_.frameSize;
  self.scrollEnabled = self.contentSize.height > self.frameHeight;
  self.clipsToBounds = self.scrollEnabled;
  if ([delegate_ respondsToSelector:@selector(textViewDidChange:)]) {
    [delegate_ textViewDidChange:self];
  }
  [self hideMenu];
  [self selectionChanged];
}

- (NSString*)editableText {
  return [attr_text_.string substringWithRange:editable_range_];
}

- (void)setEditableText:(NSString*)text {
  // LOG("set text: %d: '%s' -> '%s'", editable_range_, attr_text_.string, text);
  [input_delegate_ textWillChange:self];
  [attr_text_ replaceCharactersInRange:editable_range_
                            withString:text];
  editable_range_.length = text.length;
  [input_delegate_ textDidChange:self];
  [self attrTextChanged];
}

- (bool)editable {
  return editable_;
}

- (void)setEditable:(bool)value {
  editable_ = value;
  if (!editable_ && [self isFirstResponder]) {
    [self resignFirstResponder];
  }
}

- (float)contentHeight {
  return text_layer_.frameHeight;
}

- (void)showMenu {
  UIMenuController* menu_controller = [UIMenuController sharedMenuController];
  CGRect target_rect = CGRectZero;
  if (selection_layer_) {
    target_rect = CGRectOffset(
        CGPathGetPathBoundingBox(selection_layer_.path),
        selection_layer_.frameLeft, selection_layer_.frameTop);
  } else if (caret_layer_) {
    target_rect = caret_layer_.frame;
  }
  [menu_controller setTargetRect:target_rect inView:self];
  [menu_controller setMenuVisible:YES animated:YES];
}

- (void)showMenuDelayed:(double)delay {
  [self cancelShowMenu];
  [self performSelector:@selector(showMenu)
             withObject:NULL
             afterDelay:delay];
}

- (void)showLoupe {
  if (!loupe_) {
    loupe_ = [[MagnifierView alloc] init];
    loupe_.viewToMagnify = self.window;
    [self.window addSubview:loupe_];
  }
}

- (void)hideLoupe {
  [loupe_ removeFromSuperview];
  loupe_ = NULL;
}

- (void)updateLoupe:(CGPoint)p {
  if (loupe_) {
    const CGRect f = [self.window convertRect:self.bounds fromView:self];
    CGPoint tx_p = [self.window convertPoint:p fromView:self];
    tx_p.y = std::min(tx_p.y, CGRectGetMaxY(f));
    loupe_.touchPoint = tx_p;
    [loupe_ setNeedsDisplay];
  }
}

- (void)cancelShowMenu {
  [NSObject cancelPreviousPerformRequestsWithTarget:self
                                           selector:@selector(showMenu)
                                             object:NULL];
}

- (bool)hideMenu {
  UIMenuController* menu_controller = [UIMenuController sharedMenuController];
  if (!menu_controller.menuVisible) {
    return false;
  }
  [menu_controller setMenuVisible:NO animated:NO];
  return true;
}

- (void)forceLongPressFail {
  long_press_.enabled = NO;
  long_press_.enabled = YES;
}

- (void)forceShortPressFail {
  short_press_.enabled = NO;
  short_press_.enabled = YES;
}

- (void)forceSingleTapFail {
  single_tap_.enabled = NO;
  single_tap_.enabled = YES;
}

- (void)forceScrollFail {
  UIScrollView* scroll_view = self.scrollEnabled ? self : [self parentScrollView];
  if (scroll_view && scroll_view.scrollEnabled) {
    scroll_view.scrollEnabled = NO;
    scroll_view.scrollEnabled = YES;
  }
}

- (void)handleLongPress:(UILongPressGestureRecognizer*)recognizer {
  if (recognizer.state == UIGestureRecognizerStateCancelled ||
      recognizer.state == UIGestureRecognizerStateFailed) {
    [self hideLoupe];  // make sure we never inadvertantly leave the loupe visible
    return;
  }
  [self cancelShowMenu];

  //  LOG("handle long press: %d", recognizer.state);
  bool became_first_responder = false;
  if (editable_ && ![self isFirstResponder]) {
    became_first_responder = true;
    [self becomeFirstResponder];
  }
  if (!editing_) {
    if (recognizer.state != UIGestureRecognizerStateBegan) {
      return;
    }
    [self forceShortPressFail];
    [self forceSingleTapFail];

    if ([self isFirstResponder]) {
      [self resignFirstResponder];
    } else if ([self becomeFirstResponder]) {
      self.selectedRange = editable_range_;
      [self showMenu];
    }
  } else {
    const CGPoint p = [recognizer locationInView:self];
    const int index = [self closestIndexToPoint:p];

    if (selection_layer_) {
      // A selection already exists. Try to extend it.
      if (recognizer.state == UIGestureRecognizerStateBegan) {
        // Which direction we try to extend the selection in depends on where
        // the gesture began.
        selection_type_ = index > (selected_range_.location + selected_range_.length / 2) ?
            UITextLayoutDirectionRight : UITextLayoutDirectionLeft;
      }

      NSRange new_selected_range = { 0, 0 };
      if (selection_type_ == UITextLayoutDirectionLeft) {
        const int end = selected_range_.location + selected_range_.length;
        const int begin = std::min<int>(index, end - 1);
        new_selected_range = NSMakeRange(begin, end - begin);
      } else {
        new_selected_range = NSMakeRange(
            selected_range_.location,
            std::max<int>(1, index - selected_range_.location));
      }

      if (!NSEqualRanges(selected_range_, new_selected_range)) {
        [self forceSingleTapFail];
        [self forceScrollFail];
        self.selectedRange = new_selected_range;
        [self scrollToVisible:[text_layer_ rectForIndex:index]
                     animated:NO];
      }
    } else {
      [self forceScrollFail];
      self.selectedRange = NSMakeRange(index, 0);
    }

    if (recognizer.state == UIGestureRecognizerStateBegan) {
      [self hideMenu];
      // Only show the loupe if the gesture was made while the text view
      // is already the first responder.
      if (!became_first_responder) {
        [self showLoupe];
      }
    } else if (recognizer.state == UIGestureRecognizerStateEnded) {
      [self showMenu];
      [self hideLoupe];
    }
    [self updateLoupe:p];
  }
}

- (void)handleShortPress:(UILongPressGestureRecognizer*)recognizer {
  //  LOG("handle short press: %d", recognizer.state);
  if (recognizer.state == UIGestureRecognizerStateCancelled ||
      recognizer.state == UIGestureRecognizerStateFailed) {
    active_link_ = NULL;
    return;
  }
  if (editable_) {
    // Only recognize short presses when the text view is not editable.
    return;
  }
  if (!editing_ && !active_link_ && selected_range_.length > 0) {
    // Only recognize short presses when there is no selection.
    return;
  }

  {
    UIScrollView* scroll_view = self.scrollEnabled ? self : [self parentScrollView];
    if (scroll_view && scroll_view.dragging) {
      // If the parent scroll is dragging, disable recognition.
      [self scrollViewWillBeginDragging:self];
      return;
    }
  }

  const CGPoint p = [recognizer locationInView:self];
  if (recognizer.state == UIGestureRecognizerStateBegan) {
    active_link_ = [self findLinkAtPoint:p];
    if (active_link_) {
      // LOG("  found link: %s", active_link_.URL);
      self.selectedRange = active_link_.range;
    } else {
      // No link found, force the gesture recognizer to fail.
      recognizer.enabled = NO;
      recognizer.enabled = YES;
    }
  } else if (active_link_) {
    selection_layer_.hidden =
        ([self linkTouchOverlap:active_link_.range point:p] <= 0);
  }
  if (recognizer.state == UIGestureRecognizerStateEnded) {
    NSTextCheckingResult* result = NULL;
    if (active_link_ && !selection_layer_.hidden) {
      result = active_link_;
    }
    active_link_ = NULL;
    self.selectedRange = NSMakeRange(0, 0);

    if (result) {
      // TODO(peter): Add special handling of various link types. For example, we
      // can display a youtube video directly within our application. We'll want
      // to make this whole mechanism a bit more general purpose at the point,
      // and call out to a block to process the URL.

      // LOG("open link: %s", result.URL);
      UIApplication* a = [UIApplication sharedApplication];
      [a openURL:result.URL];
    }
  }
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  //  LOG("handle single tap: %d", recognizer.state);
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }

  [self cancelShowMenu];

  bool became_first_responder = false;
  if (editable_ && ![self isFirstResponder]) {
    [self becomeFirstResponder];
    became_first_responder = true;
  }

  if (!editing_) {
    [self hideMenu];
    self.selectedRange = NSMakeRange(0, 0);
    return;
  }

  const CGPoint p = [recognizer locationInView:self];
  const int index = self.hasText ? [self closestWordBoundaryToPoint:p] : 0;
  const NSRange new_range = NSMakeRange(index, 0);
  const bool reselect = NSEqualRanges(selected_range_, new_range);
  self.selectedRange = NSMakeRange(index, 0);

  if (![self hideMenu] && reselect && !became_first_responder) {
    [self showMenuDelayed:0.35];
  }
}

- (void)clearSelectedRangeDelayed:(double)delay {
  dispatch_after_main(delay, ^{
      self.selectedRange = NSMakeRange(0, 0);
    });
}

- (NSArray*)findLinks {
  return FindLinks(attr_text_.string, self.editableRange);
}

- (NSTextCheckingResult*)findLinkAtPoint:(CGPoint)p {
  NSTextCheckingResult* best_result = NULL;
  float best_overlap = 0;

  for (NSTextCheckingResult* result in [self findLinks]) {
    const float overlap = [self linkTouchOverlap:result.range point:p];
    if (overlap <= best_overlap) {
      continue;
    }
    best_result = result;
    best_overlap = overlap;
  }

  return best_result;
}

- (float)linkTouchOverlap:(NSRange)range
                    point:(CGPoint)p {
  const CGRect touch_rect = CGRectInset(
      CGRectMake(p.x, p.y, 0, 0), -kTouchRectSize, -kTouchRectSize);
  const vector<CGRect> rects = [text_layer_ rectsForRange:range];
  float overlap = 0;
  for (int i = 0; i < rects.size(); ++i) {
    overlap += VisibleFraction(touch_rect, rects[i]);
  }
  return overlap;
}

// Returns the range containing the word at the specified point.
- (NSRange)characterNSRangeAtPoint:(CGPoint)point {
  return [self characterNSRangeAtIndex:[self closestIndexToPoint:point]];
}

// Returns the range containing the word at the index.
- (NSRange)characterNSRangeAtIndex:(int)index {
  IndexedRange* r = (IndexedRange*)
      [self.tokenizer rangeEnclosingPosition:[IndexedPosition positionWithIndex:index]
                             withGranularity:UITextGranularityWord
                                 inDirection:UITextStorageDirectionForward];
  if (!r) {
    return NSMakeRange(NSNotFound, 0);
  }
  return r.range;
}

// Returns the closest word boundary to the specified point.
- (NSInteger)closestWordBoundaryToPoint:(CGPoint)point {
  IndexedPosition* p = (IndexedPosition*)[self closestPositionToPoint:point];
  if (!p) {
    return editable_range_.location + editable_range_.length;
  }
  NSInteger result = p.index;
  IndexedRange* r = (IndexedRange*)
      [self.tokenizer rangeEnclosingPosition:p
                             withGranularity:UITextGranularityWord
                                 inDirection:UITextStorageDirectionForward];
  if (r) {
    if (p.index >= (r.range.location + r.range.length / 2)) {
      result = std::min(
          r.range.location + r.range.length,
          editable_range_.location + editable_range_.length);
    } else {
      result = std::max(
          r.range.location, editable_range_.location);
    }
    // LOG("closest word boundary to point: %d: %d: %d", p.index, r.range, result);
  }
  return result;
}

- (NSInteger)closestIndexToPoint:(CGPoint)point {
  return [self closestIndexToPoint:point withinRange:editable_range_];
}

- (NSInteger)closestIndexToPoint:(CGPoint)point
                     withinRange:(NSRange)range {
  point = [text_layer_ convertPoint:point fromLayer:self.layer];
  const int v = [text_layer_ closestIndexToPoint:point withinRange:range];
  // LOG("closest index to point: %.0f %d-%d: %d",
  //     point, range.location, range.length, v);
  return v;
}

- (CGRect)firstRectForNSRange:(NSRange)range {
  const vector<CGRect> rects = [text_layer_ rectsForRange:range];
  if (rects.empty()) {
    return CGRectZero;
  }
  return rects[0];
}

- (CGRect)caretRectForIndex:(int)index {
  CGRect r = [text_layer_ rectForIndex:index];
  r.origin.x -= 1;
  r.size.width = 3;
  return r;
}

- (NSArray*)selectionRectsForNSRange:(NSRange)range {
  // Ensure there are no gaps between the rects.
  const vector<CGRect> rects = [text_layer_ rectsForRange:range];
  Array array;
  for (int i = 0; i < rects.size(); ++i) {
    array.push_back(rects[i]);
  }
  return array;
}

- (NSRange)editableRange {
  return editable_range_;
}

- (void)setEditableRange:(NSRange)r {
  r = NSIntersectionRange(r, NSMakeRange(0, attr_text_.length));
  if (!NSEqualRanges(editable_range_, r)) {
    editable_range_ = r;
    [self attrTextChanged];
    [self normalizeSelectedRange];
  }
}

- (NSRange)markedRange {
  return marked_range_;
}

- (void)setMarkedRange:(NSRange)r {
  // LOG("set marked range: %d", r);
  if (!NSEqualRanges(marked_range_, r)) {
    marked_range_ = r;
    [self selectionChanged];
  }
}

- (NSRange)selectedRange {
  return selected_range_;
}

// Confine the selected range to the extents of the editable range.
- (void)normalizeSelectedRange {
  const NSRange ir = NSIntersectionRange(selected_range_, editable_range_);
  if (ir.length == 0) {
    if (selected_range_.location <= editable_range_.location) {
      self.selectedRange = NSMakeRange(editable_range_.location, 0);
    } else {
      self.selectedRange = NSMakeRange(editable_range_.location + editable_range_.length, 0);
    }
  } else {
    self.selectedRange = ir;
  }
}

- (void)setSelectedRange:(NSRange)r {
  [self setSelectedRange:r notifyDelegate:true];
}

- (void)setSelectedRange:(NSRange)r
          notifyDelegate:(bool)notify_delegate {
  if (r.location > editable_range_.location + editable_range_.length) {
    r.location = editable_range_.location + editable_range_.length;
    r.length = 0;
  } else if (r.location + r.length < editable_range_.location) {
    r.location = editable_range_.location;
    r.length = 0;
  }
  marked_range_ = NSMakeRange(NSNotFound, 0);
  if (!NSEqualRanges(selected_range_, r)) {
    if (notify_delegate) {
      [input_delegate_ selectionWillChange:self];
    }
    selected_range_ = r;
    [self selectionChanged];
    if (notify_delegate) {
      [input_delegate_ selectionDidChange:self];
    }
  }
}

- (void)cancelDelayedSelectionChanged {
  [NSObject cancelPreviousPerformRequestsWithTarget:self
                                           selector:@selector(selectionChanged)
                                             object:NULL];
}

- (void)delayedSelectionChanged {
  [self cancelDelayedSelectionChanged];
  [self performSelector:@selector(selectionChanged)
             withObject:NULL
             afterDelay:0];
}

- (void)selectionChanged {
  [self cancelDelayedSelectionChanged];

  if (!editing_ || selected_range_.length > 0) {
    [caret_layer_ removeFromSuperlayer];
    [self caretBlinkStop];
  }

  [selection_layer_ removeFromSuperlayer];
  selection_layer_ = NULL;
  [drag_layer_ removeFromSuperlayer];
  drag_layer_ = NULL;

  if (selected_range_.length == 0) {
    if (editing_) {
      if (!caret_layer_) {
        caret_layer_ = [BasicCALayer new];
        caret_layer_.backgroundColor = kCaretColor;
      }
      if (!caret_layer_.superlayer) {
        [self.layer addSublayer:caret_layer_];
      }
      caret_layer_.frame = [self caretRectForIndex:selected_range_.location];
      [caret_layer_ setNeedsDisplay];
      [self caretBlinkStart];
      [self caretScrollToVisible];
    }
    long_press_.minimumPressDuration = 0.5;
  } else {
    const vector<CGRect> rects([text_layer_ rectsForRange:selected_range_]);
    const int margin = editing_ ? 0 : 3;
    selection_layer_ = MakeShapeLayerFromRects(rects, margin, margin);
    selection_layer_.fillColor = kSelectionColor;
    selection_layer_.hidden = !editing_;
    if (editing_) {
      [self initDragLayer];
      long_press_.minimumPressDuration = 0.0;
    }
    [self.layer insertSublayer:selection_layer_ below:text_layer_];
  }
}

- (void)initDragLayer {
  drag_layer_ = [BasicCALayer new];
  [self.layer addSublayer:drag_layer_];

  UIImage* dot_image = kDragDot;
  const float dot_shadow_offset = 5;

  const CGRect begin_frame =
      [self caretRectForIndex:selected_range_.location];
  CALayer* begin_caret = [BasicCALayer new];
  begin_caret.backgroundColor = kCaretColor;
  begin_caret.frame = begin_frame;

  CALayer* begin_dot = [BasicCALayer new];
  begin_dot.anchorPoint = CGPointMake(0.5, 1.0);
  begin_dot.contents = (__bridge id)dot_image.CGImage;
  begin_dot.frameSize = dot_image.size;
  begin_dot.position = CGPointMake(
      begin_frame.origin.x + begin_frame.size.width / 2,
      begin_frame.origin.y + dot_shadow_offset);

  const CGRect end_frame =
      [self caretRectForIndex:selected_range_.location + selected_range_.length];
  CALayer* end_caret = [BasicCALayer new];
  end_caret.backgroundColor = kCaretColor;
  end_caret.frame = end_frame;

  CALayer* end_dot = [BasicCALayer new];
  end_dot.anchorPoint = CGPointMake(0.5, 0.0);
  end_dot.contents = (__bridge id)dot_image.CGImage;
  end_dot.frameSize = dot_image.size;
  end_dot.position = CGPointMake(
      end_frame.origin.x + end_frame.size.width / 2,
      end_frame.origin.y + end_frame.size.height);

  [drag_layer_ addSublayer:begin_caret];
  [drag_layer_ addSublayer:end_caret];
  [drag_layer_ addSublayer:begin_dot];
  [drag_layer_ addSublayer:end_dot];
}

- (void)caretBlinkStart {
  CAKeyframeAnimation* animation =
      [CAKeyframeAnimation animationWithKeyPath:@"opacity"];
  animation.values = Array(1, 1, 0, 0);
  animation.calculationMode = kCAAnimationCubic;
  animation.duration = kCaretBlinkRate;
  animation.beginTime = CACurrentMediaTime() + kCaretInitialBlinkDelay;
  animation.repeatCount = HUGE_VALF;
  [caret_layer_ addAnimation:animation forKey:kCaretBlinkAnimationKey];
}

- (void)caretBlinkStop {
  [caret_layer_ removeAnimationForKey:kCaretBlinkAnimationKey];
}

- (void)caretScrollToVisible {
  // Extend the frame to scroll to visible to cover a line above and below the
  // caret position.
  CGRect f = caret_layer_.frame;
  f = CGRectInset(f, 0, -f.size.height);
  [self scrollToVisible:f animated:YES];
}

- (void)scrollToVisible:(CGRect)f
               animated:(BOOL)animated {
  if (!editing_) {
    return;
  }
  UIScrollView* scroll_view = self.scrollEnabled ? self : [self parentScrollView];
  if (scroll_view) {
    // Truncate the scroll-to-rect to within our bounds.
    f.origin.x = std::max<float>(f.origin.x, 0);
    f.size.width = std::min<float>(f.size.width, text_layer_.frameWidth - f.origin.x);
    f.origin.y = std::max<float>(f.origin.y, 0);
    f.size.height = std::min<float>(f.size.height, text_layer_.frameHeight - f.origin.y);
    // Convert to the scroll-view's coordinates.
    f = [scroll_view convertRect:f fromView:self];
    [scroll_view scrollRectToVisible:f animated:animated];
  }
}

// UIResponder methods.

- (UIView*)inputAccessoryView {
  return accessory_view_;
}

- (BOOL)canBecomeFirstResponder {
  return YES;
}

- (BOOL)becomeFirstResponder {
  if ([delegate_ respondsToSelector:@selector(textViewShouldBeginEditing:)] &&
      ![delegate_ textViewShouldBeginEditing:self]) {
    return NO;
  }
  if (!editable_) {
    UIView* first_responder = [self.window findFirstResponder];
    if ([first_responder conformsToProtocol:@protocol(UIKeyInput)]) {
      old_first_responder_ = (UIView<UIKeyInput>*)first_responder;
    }
  }
  if (![super becomeFirstResponder]) {
    return NO;
  }

  // LOG("become first responder: %s", editable_ ? "editable" : "not-editable");
  if (editable_) {
    editing_ = true;
    // TODO(peter): I'd like the following to scroll the top of the text view
    // to visible and then, if necessary, scroll the caret to visible. But the
    // way [ConversationScrollView scrollRectToVisible] works the subsequent
    // scrollToVisible for the caret overrides scrolling the text view to
    // visible.
    // [self scrollToVisible:self.bounds];
    [self selectionChanged];

    if ([delegate_ respondsToSelector:@selector(textViewDidBeginEditing:)]) {
      [delegate_ textViewDidBeginEditing:self];
    }
  }

  menu_will_show_.Init(
      UIMenuControllerWillShowMenuNotification,
      ^(NSNotification* n) {
        if (!editable_) {
          selection_layer_.hidden = NO;
        }
      });
  menu_will_hide_.Init(
      UIMenuControllerWillHideMenuNotification,
      ^(NSNotification* n) {
        if (!editable_) {
          [self resignFirstResponder];
        }
      });
  return YES;
}

- (BOOL)canResignFirstResponder {
  return YES;
}

- (BOOL)resignFirstResponder {
  if ([delegate_ respondsToSelector:@selector(textViewShouldEndEditing:)] &&
      ![delegate_ textViewShouldEndEditing:self]) {
    return NO;
  }
  if (old_first_responder_) {
    UIResponder* r = old_first_responder_;
    old_first_responder_ = NULL;
    [r becomeFirstResponder];
    return NO;
  }
  if (![super resignFirstResponder]) {
    return NO;
  }
  // LOG("resign first responder: %s\n%s", editable_ ? "editing" : "not-editing");
  editing_ = false;
  if ([delegate_ respondsToSelector:@selector(textViewDidEndEditing:)]) {
    [delegate_ textViewDidEndEditing:self];
  }
  self.selectedRange = NSMakeRange(0, 0);
  [self selectionChanged];
  menu_will_show_.Clear();
  menu_will_hide_.Clear();
  UIMenuController* menu_controller = [UIMenuController sharedMenuController];
  [menu_controller setMenuVisible:NO animated:YES];
  // Just in case, move the autocorrect view back as a subview.
  [self pinAutocorrectToView:self];
  return YES;
}

- (BOOL)canPerformAction:(SEL)action
              withSender:(id)sender {
  if (action == @selector(cut:)) {
    return editing_ && selected_range_.length > 0;
  }
  if (action == @selector(copy:)) {
    return selected_range_.length > 0;
  }
  if (action == @selector(paste:)) {
    if (!editing_) {
      return NO;
    }
    UIPasteboard* board = [UIPasteboard generalPasteboard];
    return board.string.length > 0;
  }
  if (action == @selector(select:)) {
    return editing_ && selected_range_.length == 0 &&
        self.selectRange.length > 0;
  }
  if (action == @selector(selectAll:)) {
    NSRange select_all_range = self.selectAllRange;
    return editing_ && select_all_range.length > 0 &&
        !NSEqualRanges(selected_range_, select_all_range);
  }
  return [super canPerformAction:action withSender:sender];
}

- (void)copy:(id)sender {
  // LOG("copy");
  UIPasteboard* board = [UIPasteboard generalPasteboard];
  board.string = [attr_text_.string substringWithRange:selected_range_];
}

- (void)cut:(id)sender {
  // LOG("cut");
  [self copy:sender];
  [self deleteBackward];
}

- (void)paste:(id)sender {
  // LOG("paste");
  UIPasteboard* board = [UIPasteboard generalPasteboard];
  NSString* str = board.string;
  if (str) {
    [self insertText:str];
  }
}

- (void)select:(id)sender {
  // LOG("select");
  self.selectedRange = self.selectRange;
  if (selected_range_.length > 0) {
    [self showMenuDelayed:0.35];
  }
}

- (NSRange)selectRange {
  // Try to select the word forward from the current location.
  int index = selected_range_.location;
  IndexedRange* r = (IndexedRange*)
      [self.tokenizer rangeEnclosingPosition:[IndexedPosition positionWithIndex:index]
                             withGranularity:UITextGranularityWord
                                 inDirection:UITextStorageDirectionForward];
  if (r) {
    return r.range;
  }
  // ...if that failed, try to select the word backward from the current
  // location.
  r = (IndexedRange*)
      [self.tokenizer rangeEnclosingPosition:[IndexedPosition positionWithIndex:index]
                             withGranularity:UITextGranularityWord
                                 inDirection:UITextStorageDirectionBackward];
  if (r) {
    return r.range;
  }
  return NSMakeRange(NSNotFound, 0);
}

- (void)selectAll:(id)sender {
  // LOG("select all");
  self.selectedRange = self.selectAllRange;
  if (selected_range_.length > 0) {
    [self showMenuDelayed:0.35];
  }
}

- (NSRange)selectAllRange {
  NSString* str = [attr_text_.string substringWithRange:editable_range_];
  NSString* trimmed = [str stringByTrimmingCharactersInSet:
                             [NSCharacterSet whitespaceAndNewlineCharacterSet]];
  return [attr_text_.string rangeOfString:trimmed];
}

// UITextInputTraits properties.

// Proxy the UIKeyInput properties to the old_first_responder_ object. This is
// necessary so that the keyboard appearance is maintained while we're the
// first responder but not editing text.
- (UITextAutocapitalizationType)autocapitalizationType {
  if (old_first_responder_) {
    return old_first_responder_.autocapitalizationType;
  }
  return autocapitalization_type_;
}

- (void)setAutocapitalizationType:(UITextAutocapitalizationType)value {
  autocapitalization_type_ = value;
}

- (UITextAutocorrectionType)autocorrectionType {
  if (old_first_responder_) {
    return old_first_responder_.autocorrectionType;
  }
  return autocorrection_type_;
}

- (void)setAutocorrectionType:(UITextAutocorrectionType)value {
  autocorrection_type_ = value;
}

- (UITextSpellCheckingType)spellCheckingType {
  if (old_first_responder_) {
    return old_first_responder_.spellCheckingType;
  }
  return spell_checking_type_;
}

- (void)setSpellCheckingType:(UITextSpellCheckingType)value {
  spell_checking_type_ = value;
}

- (UIKeyboardType)keyboardType {
  if (old_first_responder_) {
    return old_first_responder_.keyboardType;
  }
  return keyboard_type_;
}

- (void)setKeyboardType:(UIKeyboardType)value {
  keyboard_type_ = value;
}

- (UIKeyboardAppearance)keyboardAppearance {
  if (old_first_responder_) {
    return old_first_responder_.keyboardAppearance;
  }
  return keyboard_appearance_;
}

- (void)setKeyboardAppearance:(UIKeyboardAppearance)value {
  keyboard_appearance_ = value;
}

- (UIReturnKeyType)returnKeyType {
  if (old_first_responder_) {
    return old_first_responder_.returnKeyType;
  }
  return return_key_type_;
}

- (void)setReturnKeyType:(UIReturnKeyType)value {
  return_key_type_ = value;
}

- (BOOL)enablesReturnKeyAutomatically {
  if (old_first_responder_) {
    return old_first_responder_.enablesReturnKeyAutomatically;
  }
  return enables_return_key_automatically_;
}

- (void)setEnablesReturnKeyAutomatically:(BOOL)value {
  enables_return_key_automatically_ = value;
}

- (BOOL)secureTextEntry {
  if (old_first_responder_) {
    return old_first_responder_.secureTextEntry;
  }
  return secure_text_entry_;
}

- (void)setSecureTextEntry:(BOOL)value {
  secure_text_entry_ = value;
}

// UITextInput methods.

- (id<UITextInputTokenizer>)tokenizer {
  if (!tokenizer_) {
    tokenizer_ = [[UITextInputStringTokenizer alloc] initWithTextInput:self];
  }
  return tokenizer_;
}

- (UIView*)textInputView {
  return self;
}

- (NSString*)textInRange:(UITextRange*)range {
  IndexedRange* r = (IndexedRange*)range;
  NSRange ir = NSIntersectionRange(r.range, editable_range_);
  // LOG("text in range: %d: |%s|", r.range,
  //     [attr_text_.string substringWithRange:ir]);
  return [attr_text_.string substringWithRange:ir];
}

- (void)replaceRange:(UITextRange*)range
            withText:(NSString*)text {
  IndexedRange* r = (IndexedRange*)range;
  // LOG("replace range: %d: '%s'", r.range, text);

  if ((r.range.location + r.range.length) <= selected_range_.location) {
    selected_range_.location -= (r.range.length - text.length);
  } else if (r.range.location < selected_range_.location + selected_range_.length) {
    selected_range_ = NSIntersectionRange(r.range, selected_range_);
  }

  [attr_text_ replaceCharactersInRange:r.range withString:text];
  editable_range_.length += text.length;
  editable_range_.length -= r.range.length;
  [self attrTextChanged];
}

- (UITextRange*)selectedTextRange {
  // LOG("selected text range: %d", selected_range_);
  return [IndexedRange rangeWithNSRange:selected_range_];
}

- (void)setSelectedTextRange:(UITextRange*)range {
  IndexedRange* r = (IndexedRange*)range;
  [self setSelectedRange:r.range notifyDelegate:false];
}

- (UITextRange*)markedTextRange {
  // LOG("marked text range: %d", marked_range_);
  return [IndexedRange rangeWithNSRange:marked_range_];
}

- (void)setMarkedText:(NSString*)marked_text
        selectedRange:(NSRange)selected_range {
  // LOG("set marked text: '%s': %d", marked_text, selected_range);

  if (!marked_text) {
    marked_text = @"";
  }

  if (marked_range_.location != NSNotFound) {
    [attr_text_ replaceCharactersInRange:marked_range_
                              withString:marked_text];
    editable_range_.length -= marked_range_.length;
  } else {
    [attr_text_ replaceCharactersInRange:selected_range_
                              withString:marked_text];
    marked_range_.location = selected_range_.location;
    editable_range_.length -= selected_range_.length;
  }

  editable_range_.length += marked_text.length;
  selected_range_.location += marked_range_.location;
  marked_range_.length = marked_text.length;
  [self attrTextChanged];
}

- (void)unmarkText {
  // LOG("unmark text: %d", marked_range_);
  NSRange marked_range = self.markedRange;
  if (marked_range.location == NSNotFound) {
    return;
  }
  marked_range.location = NSNotFound;
  self.markedRange = marked_range;
}

- (UITextPosition*)beginningOfDocument {
  return [IndexedPosition positionWithIndex:editable_range_.location];
}

- (UITextPosition*)endOfDocument {
  const int index = editable_range_.location + editable_range_.length;
  return [IndexedPosition positionWithIndex:index];
}

- (UITextRange*)textRangeFromPosition:(UITextPosition*)f
                           toPosition:(UITextPosition*)t {
  IndexedPosition* from = (IndexedPosition*)f;
  IndexedPosition* to = (IndexedPosition*)t;
  const NSRange range = NSMakeRange(
      std::min(from.index, to.index), abs(to.index - from.index));
  // LOG("text range from position to position: %d %d",
  //     from.index, to.index);
  return [IndexedRange rangeWithNSRange:range];
}

- (UITextPosition*)positionFromPosition:(UITextPosition*)position
                                 offset:(NSInteger)offset {
  IndexedPosition* pos = (IndexedPosition*)position;
  NSInteger end = pos.index + offset;
  // Verify position is valid in document
  if (end >= attr_text_.length || end < 0) {
    // LOG("text range from position offset (NULL): %d %d",
    //     pos.index, offset);
    return NULL;
  }
  // LOG("text range from position offset: %d %d",
  //     pos.index, offset);
  return [IndexedPosition positionWithIndex:end];
}

- (UITextPosition*)positionFromPosition:(UITextPosition*)position
                            inDirection:(UITextLayoutDirection)direction
                                 offset:(NSInteger)offset {
  IndexedPosition* pos = (IndexedPosition*)position;
  int new_index = pos.index;

  switch (direction) {
    case UITextLayoutDirectionRight:
      new_index += offset;
      break;
    case UITextLayoutDirectionLeft:
      new_index -= offset;
      break;
    case UITextLayoutDirectionUp:
    case UITextLayoutDirectionDown:
      // Unsupported
      break;
  }

  // Verify new position valid in document
  if (new_index < 0) {
    new_index = 0;
  }
  if (new_index >= attr_text_.length) {
    new_index = attr_text_.length - 1;
  }
  return [IndexedPosition positionWithIndex:new_index];
}

- (NSComparisonResult)comparePosition:(UITextPosition*)position
                           toPosition:(UITextPosition*)other {
  IndexedPosition* a = (IndexedPosition*)position;
  IndexedPosition* b = (IndexedPosition*)other;
  if (a.index == b.index) {
    return NSOrderedSame;
  } if (a.index < b.index) {
    return NSOrderedAscending;
  }
  return NSOrderedDescending;
}

- (NSInteger)offsetFromPosition:(UITextPosition*)from
                     toPosition:(UITextPosition*)to {
  IndexedPosition* f = (IndexedPosition*)from;
  IndexedPosition* t = (IndexedPosition*)to;
  return (t.index - f.index);
}

- (UITextPosition*)positionWithinRange:(UITextRange*)range
                   farthestInDirection:(UITextLayoutDirection)direction {
  // Note that this sample assumes LTR text direction
  IndexedRange* r = (IndexedRange*)range;
  int index = r.range.location;

  // For this sample, we just return the extent of the given range if the
  // given direction is "forward" in a LTR context (UITextLayoutDirectionRight
  // or UITextLayoutDirectionDown), otherwise we return just the range position
  switch (direction) {
    case UITextLayoutDirectionUp:
    case UITextLayoutDirectionLeft:
      index = r.range.location;
      break;
    case UITextLayoutDirectionRight:
    case UITextLayoutDirectionDown:
      index = r.range.location + r.range.length;
      break;
  }

  // Return text position using our UITextPosition implementation. Note that
  // position is not currently checked against document range.
  return [IndexedPosition positionWithIndex:index];
}

- (UITextRange*)characterRangeByExtendingPosition:(UITextPosition*)position
                                      inDirection:(UITextLayoutDirection)direction {
  IndexedPosition* pos = (IndexedPosition*)position;
  NSRange result = NSMakeRange(pos.index, 1);

  switch (direction) {
    case UITextLayoutDirectionUp:
    case UITextLayoutDirectionLeft:
      result = NSMakeRange(pos.index - 1, 1);
      break;
    case UITextLayoutDirectionRight:
    case UITextLayoutDirectionDown:
      result = NSMakeRange(pos.index, 1);
      break;
  }

  // Return range using our UITextRange implementation. Note that range is not
  // currently checked against document range.
  return [IndexedRange rangeWithNSRange:result];
}

- (UITextWritingDirection)baseWritingDirectionForPosition:(UITextPosition*)position
                                              inDirection:(UITextStorageDirection)direction {
  // TODO(peter): unimplemented.
  return UITextWritingDirectionLeftToRight;
}

- (void)setBaseWritingDirection:(UITextWritingDirection)writingDirection
                       forRange:(UITextRange*)range {
  // TODO(peter): unimplemented.
  // Only left to write supported for now.
}

- (CGRect)firstRectForRange:(UITextRange*)range {
  IndexedRange* r = (IndexedRange*)range;
  return [self firstRectForNSRange:r.range];
}

- (CGRect)caretRectForPosition:(UITextPosition*)position {
  IndexedPosition* pos = (IndexedPosition*)position;
  return [self caretRectForIndex:pos.index];
}

- (NSArray*)selectionRectsForRange:(UITextRange*)range {
  IndexedRange* r = (IndexedRange*)range;
  return [self selectionRectsForNSRange:r.range];
}

- (UITextPosition*)closestPositionToPoint:(CGPoint)point {
  const int index = [self closestIndexToPoint:point];
  return [IndexedPosition positionWithIndex:index];
}

- (UITextPosition*)closestPositionToPoint:(CGPoint)point
                              withinRange:(UITextRange*)range {
  IndexedRange* r = (IndexedRange*)range;
  const int index = [self closestIndexToPoint:point
                                  withinRange:r.range];
  return [IndexedPosition positionWithIndex:index];

}

- (UITextRange*)characterRangeAtPoint:(CGPoint)point {
  return [IndexedRange rangeWithNSRange:[self characterNSRangeAtPoint:point]];
}

- (NSDictionary*)textStylingAtPosition:(UITextPosition*)position
                           inDirection:(UITextStorageDirection)direction {
  IndexedPosition* pos = (IndexedPosition*)position;
  const int index = std::min<int>(
      std::max<int>(0, pos.index), attr_text_.length - 1);

  const Dict attrs([attr_text_ attributesAtIndex:index effectiveRange:NULL]);
  CTFontRef ct_font = (__bridge CTFontRef)attrs.find(kCTFontAttributeName);
  NSString* font_name = (__bridge_transfer NSString*)CTFontCopyFamilyName(ct_font);
  UIFont* font = [UIFont fontWithName:font_name size:CTFontGetSize(ct_font)];

  return Dict(UITextInputTextFontKey, font);
}

// UIKeyInput methods

- (BOOL)hasText {
  // The text always has a trailing space so that an empty last line is
  // correctly accounted for in the height of the text.
  return editable_range_.length > 0;
}

- (void)insertText:(NSString*)text {
  // LOG("insert text: %d: '%s'", selected_range_, text);
  if (ToSlice(text) == "\n" &&
      [delegate_ respondsToSelector:@selector(textViewShouldReturn:)] &&
      ![delegate_ textViewShouldReturn:self]) {
    return;
  }
  [attr_text_ replaceCharactersInRange:selected_range_
                            withString:text];
  editable_range_.length += text.length;
  editable_range_.length -= selected_range_.length;
  selected_range_.location += text.length;
  selected_range_.length = 0;
  [self attrTextChanged];
}

- (void)deleteBackward {
  // LOG("delete backward: %d", selected_range_);
  if (selected_range_.length == 0 &&
      selected_range_.location == editable_range_.location) {
    return;
  }

  if (selected_range_.length == 0) {
    // This is essentially doing "selected_range_.location -= 1;
    // selected_range_.length = 1;", but is accounting for languages with
    // composed characters (such as chinese) and properly handling emoji.
    selected_range_ = [attr_text_.string
                          rangeOfComposedCharacterSequenceAtIndex:selected_range_.location - 1];
  }
  [attr_text_ deleteCharactersInRange:selected_range_];
  editable_range_.length -= selected_range_.length;
  selected_range_.length = 0;
  [self attrTextChanged];
}

// UIGestureRecognizerDelegate methods.

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)gesture_recognizer {
  if (gesture_recognizer == long_press_) {
    if (editing_ && selected_range_.length > 0 && selection_layer_) {
      const CGPoint p = [gesture_recognizer locationInView:self];
      const int index = [self closestIndexToPoint:p];
      const int begin = selected_range_.location;
      const int end = selected_range_.location + selected_range_.length;
      return fabs(index - begin) <= 4 || fabs(index - end) <= 4;
    }
  }
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)a
shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer*)b {
  return YES;
}

// UIScrollViewDelegate methods.

- (void)scrollViewDidScroll:(UIScrollView*)scroll_view {
  // LOG("scroll view did scroll: %.0f", scroll_view.contentOffset);
}

- (void)scrollViewWillBeginDragging:(UIScrollView*)scroll_view {
  // Clear any selection if there's an active link.
  if (active_link_) {
    [self clearSelectedRangeDelayed:0.100];
  }
  [self forceLongPressFail];
  [self forceShortPressFail];
  [self forceSingleTapFail];
  [self hideMenu];
}

- (void)scrollViewDidEndDragging:(UIScrollView*)scroll_view
                  willDecelerate:(BOOL)decelerate {
  if (!decelerate) {
    [self scrollViewDidEndDecelerating:scroll_view];
  }
}

- (void)scrollViewDidEndDecelerating:(UIScrollView*)scroll_view {
  if (drag_layer_) {
    [self showMenu];
  }
}

@end  // TextView


//
//  EGOTextView.m
//
//  Created by Devin Doty on 4/18/11.
//  Copyright (C) 2011 by enormego.
//
//  Permission is hereby granted, free of charge, to any person obtaining a copy
//  of this software and associated documentation files (the "Software"), to deal
//  in the Software without restriction, including without limitation the rights
//  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
//  copies of the Software, and to permit persons to whom the Software is
//  furnished to do so, subject to the following conditions:
//
//  The above copyright notice and this permission notice shall be included in
//  all copies or substantial portions of the Software.
//
//  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
//  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
//  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
//  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
//  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
//  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
//  THE SOFTWARE.
//

/*
     File: EditableCoreTextView.m
 Abstract:
A view that illustrates how to implement and use the UITextInput protocol.

Heavily leverages an existing CoreText-based editor and merely serves
as the "glue" between the system keyboard and this editor.

  Version: 1.0

 Disclaimer: IMPORTANT:  This Apple software is supplied to you by Apple
 Inc. ("Apple") in consideration of your agreement to the following
 terms, and your use, installation, modification or redistribution of
 this Apple software constitutes acceptance of these terms.  If you do
 not agree with these terms, please do not use, install, modify or
 redistribute this Apple software.

 In consideration of your agreement to abide by the following terms, and
 subject to these terms, Apple grants you a personal, non-exclusive
 license, under Apple's copyrights in this original Apple software (the
 "Apple Software"), to use, reproduce, modify and redistribute the Apple
 Software, with or without modifications, in source and/or binary forms;
 provided that if you redistribute the Apple Software in its entirety and
 without modifications, you must retain this notice and the following
 text and disclaimers in all such redistributions of the Apple Software.
 Neither the name, trademarks, service marks or logos of Apple Inc. may
 be used to endorse or promote products derived from the Apple Software
 without specific prior written permission from Apple.  Except as
 expressly stated in this notice, no other rights or licenses, express or
 implied, are granted by Apple herein, including but not limited to any
 patent rights that may be infringed by your derivative works or by other
 works in which the Apple Software may be incorporated.

 The Apple Software is provided by Apple on an "AS IS" basis.  APPLE
 MAKES NO WARRANTIES, EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION
 THE IMPLIED WARRANTIES OF NON-INFRINGEMENT, MERCHANTABILITY AND FITNESS
 FOR A PARTICULAR PURPOSE, REGARDING THE APPLE SOFTWARE OR ITS USE AND
 OPERATION ALONE OR IN COMBINATION WITH YOUR PRODUCTS.

 IN NO EVENT SHALL APPLE BE LIABLE FOR ANY SPECIAL, INDIRECT, INCIDENTAL
 OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 INTERRUPTION) ARISING IN ANY WAY OUT OF THE USE, REPRODUCTION,
 MODIFICATION AND/OR DISTRIBUTION OF THE APPLE SOFTWARE, HOWEVER CAUSED
 AND WHETHER UNDER THEORY OF CONTRACT, TORT (INCLUDING NEGLIGENCE),
 STRICT LIABILITY OR OTHERWISE, EVEN IF APPLE HAS BEEN ADVISED OF THE
 POSSIBILITY OF SUCH DAMAGE.

 Copyright (C) 2011 Apple Inc. All Rights Reserved.

*/
