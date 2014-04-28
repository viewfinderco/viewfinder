// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <UIKit/UITableView.h>
#import <UIKit/UITextField.h>
#import <UIKit/UITextInput.h>
#import <UIKit/UIView.h>
#import "ScopedNotification.h"
#import "Utils.h"

@class TokenCellView;
@class TokenizedTextField;
@class TokenizedTextScrollView;
@class TokenizedTextView;

struct TokenizedTextViewOptions {
  // Font used for both text entry and token cells.
  UIFont* font;
  // Font used for bolded tokens.
  UIFont* bold_font;

  // Minimum height for the whole field.
  float min_height;

  // Space between tokens/text and the view bounds.
  float margin_x;
  float margin_y;

  // Space between adjacent tokens.
  float padding_x;
  float padding_y;

  // Space within the token cells.
  float inset_x;
  float top_inset_y;
  float bottom_inset_y;

  // Position of the text entry field within the view.
  float text_top_inset_y;

  // Radius of rounded corners on token cells.
  float token_corner_radius;

  // Multiplier of line height to account for emoji.
  // Empirically determined to be 1.35; smaller values should only be used when emoji are not expected.
  float emoji_extra_height_factor;

  // Wrap to the next line unless there is this much room for text entry.
  float text_wrap_width;
};

class TextViewToken {
 public:
  // TODO(ben): Refactor this into the subclasses.
  enum TokenColorScheme {
    // Follower token colors.
    SELF,
    NEW,
    EXISTING,
    // Search token colors.
    SEARCH,
  };
  enum TokenProspectiveType {
    NONE,
    EMAIL,
    SMS,
  };

  virtual ~TextViewToken();

  virtual const string& text() const = 0;
  virtual TokenColorScheme colors() const = 0;
  virtual TokenProspectiveType prospective() const = 0;
  virtual bool frozen() const = 0;
  virtual bool removable() const = 0;
  virtual UIImage* remove_image(bool selected) const = 0;
};

typedef void (^RemoveTokenCallback)();
typedef void (^CreateTokensCallback)(const vector<const TextViewToken*>&);

@interface TokenizedTextField : UITextField<UIKeyInput> {
  __weak TokenizedTextView* parent_;
  const TokenizedTextViewOptions* options_;
  int selected_token_;
  bool disable_paste_;
  bool show_full_table_;
  bool show_placeholder_;
  CGPoint cursor_;
}

@property (nonatomic, readonly) CGPoint* cursor;
@property (nonatomic) int selectedToken;
@property (nonatomic) bool disablePaste;
@property (nonatomic) bool showFullTable;
@property (nonatomic) bool showPlaceholder;
@property (nonatomic, readonly) bool isEditing;

@end  // TokenizedTextField

@protocol TokenizedTextViewDelegate <NSObject>

- (BOOL)tokenizedTextViewShouldBeginEditing:(TokenizedTextView*)view;
- (void)tokenizedTextViewDidBeginEditing:(TokenizedTextView*)view;
- (BOOL)tokenizedTextViewShouldEndEditing:(TokenizedTextView*)view;
- (void)tokenizedTextViewDidEndEditing:(TokenizedTextView*)view;
- (void)tokenizedTextViewChangedTokens:(TokenizedTextView*)view;
- (void)tokenizedTextViewQueryRemoveToken:(TokenizedTextView*)view
                                    token:(const TextViewToken&)token
                             withCallback:(RemoveTokenCallback)done;
- (bool)tokenizedTextViewShouldReturn:(TokenizedTextView*)view;
// Returns the bounds that the view can use to display autocomplete suggestions.
- (CGRect)tokenizedTextViewVisibleBounds:(TokenizedTextView*)view;
- (void)tokenizedTextViewChangedText:(TokenizedTextView*)view;

@optional
- (void)tokenizedTextViewChangedSize:(TokenizedTextView*)view;

@end  // TokenizedTextViewDelegate

@interface TokenizedTextView : UIView<UITextFieldDelegate> {
 @private
  __weak id<TokenizedTextViewDelegate> delegate_;
  TokenizedTextViewOptions options_;
  float min_height_;
  float line_height_;
  float editing_field_height_;
  TokenizedTextScrollView* scroll_view_;
  TokenizedTextField* field_;
  vector<TokenCellView*> tokens_;
  ScopedNotification keyboard_will_show_;
  ScopedNotification keyboard_will_hide_;
  ScopedNotification change_notification_;
}

@property (readonly, nonatomic) const TokenizedTextViewOptions& options;
@property (readonly, nonatomic) TokenizedTextField* field;
@property (nonatomic, weak) id<TokenizedTextViewDelegate> delegate;
@property (readonly, nonatomic) float editingFieldHeight;

- (id)initWithDelegate:(id<TokenizedTextViewDelegate>)delegate
           withOptions:(const TokenizedTextViewOptions&)options;

// Takes ownership of token.
- (void)addToken:(const TextViewToken*)token;
- (int)numTokens;
- (const TextViewToken&)getToken:(int)i;
- (void)removeToken:(int)i;
- (void)pauseEditing;
- (void)resumeEditing;
- (bool)canEndEditing;
// Sets the text field to the appropriate "empty" value (which is not necessarily an empty string).
- (void)clearText;
- (void)deleteBackward;

@end  // TokenizedTextView

// local variables:
// mode: objc
// end:
