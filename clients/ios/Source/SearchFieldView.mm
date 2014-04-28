// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.
// Author: Spencer Kimball.

#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "Defines.h"
#import "RootViewController.h"
#import "SearchFieldView.h"
#import "SummaryLayoutController.h"
#import "TextLayer.h"
#import "UIView+constraints.h"
#import "UIView+geometry.h"

namespace {

const float kDuration = 0.3;
const float kMargin = 7;

// Space around the search field within its background.
const float kSearchFieldInsetX = 4;
const float kSearchFieldInsetY = 5.5;
const float kSearchFieldIntrinsicHeight = 44;
const float kCancelButtonWidth = 62;
const float kAutocompleteMarginX = 6;
const float kAutocompleteTextOffsetX = 10;
const float kAutocompleteTextBaselineY = 31;
const float kEmojiHeightFactor = 1.35;

LazyStaticImage kSearchBarShadow(@"search-bar-shadow.png", UIEdgeInsetsMake(0, 2, 0, 2));

LazyStaticImage kSearchBarButtonDark(@"search-bar-button-dark.png", UIEdgeInsetsMake(0, 4, 0, 4));
LazyStaticImage kSearchBarButtonDarkActive(@"search-bar-button-dark-active.png", UIEdgeInsetsMake(0, 4, 0, 4));

LazyStaticImage kSearchBarTextField(@"search-bar-text-field.png", UIEdgeInsetsMake(4, 4, 4, 4));
LazyStaticImage kSearchBarIconSearch(@"search-bar-icon-search.png");
LazyStaticImage kSearchBarTextFieldClear(@"search-bar-text-field-clear.png");

enum AutocompleteRowPosition {
  TOP,
  MIDDLE,
  BOTTOM,
  SINGLE,  // rounded corners on both top and bottom
};
LazyStaticImage kSearchKeywordsBgTop(@"search-keywords-bg-top.png", UIEdgeInsetsMake(0, 7, 0, 7));
LazyStaticImage kSearchKeywordsBgMiddle(@"search-keywords-bg-middle.png", UIEdgeInsetsMake(0, 7, 0, 7));
LazyStaticImage kSearchKeywordsBgBottom(@"search-keywords-bg-bottom.png", UIEdgeInsetsMake(0, 7, 0, 7));
LazyStaticImage kSearchKeywordsBgSingle(@"search-keywords-bg-single.png", UIEdgeInsetsMake(0, 7, 0, 7));

//LazyStaticImage kSearchKeywordsIconArrow(@"search-keywords-icon-arrow.png");
LazyStaticImage kSearchKeywordsIconLocation(@"search-keywords-icon-location.png");
LazyStaticImage kSearchKeywordsIconUser(@"search-keywords-icon-user.png");
LazyStaticImage kSearchKeywordsIconConvo(@"search-keywords-icon-convo.png");

LazyStaticUIFont kSearchBarButtonFont = { kProximaNovaSemibold, 16 };
LazyStaticHexColor kSearchBarPinnedBGColor = { "#4f4e4e" };
LazyStaticHexColor kSearchBarUnpinnedBGColor = { "#9f9c9c" };
LazyStaticHexColor kSearchBarBorderColor = { "#4f4e4e" };
LazyStaticHexColor kButtonTitleColor = { "#ffffff" };
LazyStaticHexColor kButtonTitleActiveColor = { "#c9c7c7" };

LazyStaticUIFont kSearchFieldFont = { kProximaNovaRegular, 16 };
LazyStaticHexColor kSearchFieldTextColor = { "#3f3e3e" };
LazyStaticHexColor kSearchFieldPlaceholderColor = { "#9f9c9c" };

LazyStaticImage kSearchTokenIconRemoveUser(@"search-token-icon-remove-user.png");
LazyStaticImage kSearchTokenIconRemoveUserSelected(@"search-token-icon-remove-user-selected.png");

LazyStaticUIFont kAutocompleteBoldFont = { kProximaNovaBold, 18 };
LazyStaticHexColor kAutocompleteBoldColor = { "#3f3e3e" };
LazyStaticUIFont kAutocompleteNormalFont = { kProximaNovaRegular, 18 };
LazyStaticHexColor kAutocompleteNormalColor = { "#9f9c9c" };

// Same as SummaryView kBackgroundColor
LazyStaticHexColor kAutocompleteBackgroundColor = { "#9f9c9c" };

LazyStaticDict kAutocompleteBoldAttributes = {^{
    return Dict(
        NSFontAttributeName,
        kAutocompleteBoldFont.get(),
        NSForegroundColorAttributeName,
        kAutocompleteBoldColor.get());
  }
};

LazyStaticDict kAutocompleteNormalAttributes = {^{
    return Dict(
        NSFontAttributeName,
        kAutocompleteNormalFont.get(),
        NSForegroundColorAttributeName,
        kAutocompleteNormalColor.get());
  }
};

LazyStaticDict kSearchFieldPlaceholderAttributes = {^{
    return Dict(
        NSFontAttributeName,
        kSearchFieldFont.get(),
        NSForegroundColorAttributeName,
        kSearchFieldPlaceholderColor.get());
  }
};

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

class SummaryToken : public TextViewToken {
 public:
  explicit SummaryToken(const SummaryTokenInfo& info)
      : info_(info) {
  }

  virtual const string& text() const {
    return info_.display_term;
  }

  virtual TokenColorScheme colors() const {
    return SEARCH;
  }

  virtual TokenProspectiveType prospective() const {
    return NONE;
  }

  virtual bool frozen() const {
    return false;
  }

  virtual bool removable() const {
    return true;
  }

  virtual UIImage* remove_image(bool selected) const {
    return selected ? kSearchTokenIconRemoveUserSelected : kSearchTokenIconRemoveUser;
  }

  const string& query_term() const {
    return info_.query_term;
  }

 private:
  const SummaryTokenInfo info_;
};

}  // namespace

bool SummaryTokenInfo::operator<(const SummaryTokenInfo& other) const {
  if (type != other.type) {
    return type < other.type;
  } else if (display_term != other.display_term) {
    return display_term < other.display_term;
  } else {
    return query_term < other.query_term;
  }
}

SummaryAutocompleteResults::SummaryAutocompleteResults() {
}

SummaryAutocompleteResults::~SummaryAutocompleteResults() {
}

void SummaryAutocompleteResults::Add(const SummaryTokenInfo& token, int score) {
  tokens_[token] += score;
}

void SummaryAutocompleteResults::GetSortedResults(vector<pair<int, SummaryTokenInfo> >* tokens) {
  for (auto it = tokens_.begin(); it != tokens_.end(); ++it) {
    tokens->push_back(std::make_pair(it->second, it->first));
  }
  std::sort(tokens->begin(), tokens->end(), std::greater<pair<int, SummaryTokenInfo> >());
}


@interface AutocompleteTableViewCell : UITableViewCell {
  UIImageView* background_;
  UILabel* label_;
  UIImageView* icon_;
}

- (id)initWithReuseIdentifier:(NSString*)identifier;
- (void)setTokenInfo:(const SummaryTokenInfo&)info
            filterRE:(RE2*)filter_re
            position:(AutocompleteRowPosition)position;
+ (int)rowHeight;

@end  // AutocompleteTableViewCell


@implementation AutocompleteTableViewCell

- (id)initWithReuseIdentifier:(NSString*)identifier {
  if (self = [super initWithStyle:UITableViewCellStyleDefault
                  reuseIdentifier:identifier]) {
    self.backgroundColor = [UIColor clearColor];
    self.selectionStyle = UITableViewCellSelectionStyleNone;
    self.contentView.autoresizesSubviews = YES;

    background_ = [[UIImageView alloc] initWithImage:kSearchKeywordsBgMiddle];
    background_.translatesAutoresizingMaskIntoConstraints = NO;
    [self.contentView addSubview:background_];
    [self addConstraints:LeftToRight(self.anchorLeft, kAutocompleteMarginX, background_,
                                     kAutocompleteMarginX, self.anchorRight)];

    label_ = [UILabel new];
    label_.backgroundColor = [UIColor clearColor];
    label_.translatesAutoresizingMaskIntoConstraints = NO;
    // The automatic sizing doesn't allow enough room for the extra height of emoji;
    [label_ addConstraints:label_.anchorHeight == kAutocompleteNormalFont.get().pointSize * kEmojiHeightFactor];
    [background_ addSubview:label_];
    [background_ addConstraints:label_.anchorBaseline == background_.anchorTop + kAutocompleteTextBaselineY];

    icon_ = [[UIImageView alloc] initWithImage:kSearchKeywordsIconUser];
    icon_.translatesAutoresizingMaskIntoConstraints = NO;
    // The icon sometimes loses its dimensions when it is hidden.
    [icon_ addConstraints:icon_.anchorWidth == icon_.image.size.width];
    [background_ addSubview:icon_];

    [background_ addConstraints:LeftToRight(background_.anchorLeft,
                                            kAutocompleteTextOffsetX, label_,
                                            icon_, background_.anchorRight)];
  }
  return self;
}

- (void)setMessage:(const Slice&)message {
  background_.image = kSearchKeywordsBgSingle;
  icon_.hidden = YES;
  NSMutableAttributedString* attr_str = NewAttrString(message.as_string(), kAutocompleteNormalAttributes);
  label_.attributedText = attr_str;

  [self setNeedsLayout];
}

- (void)setTokenInfo:(const SummaryTokenInfo&)info
            filterRE:(RE2*)filter_re
            position:(AutocompleteRowPosition)position {
  switch (position) {
    case TOP:
      background_.image = kSearchKeywordsBgTop;
      break;
    case MIDDLE:
      background_.image = kSearchKeywordsBgMiddle;
      break;
    case BOTTOM:
      background_.image = kSearchKeywordsBgBottom;
      break;
    case SINGLE:
      background_.image = kSearchKeywordsBgSingle;
  }

  icon_.hidden = NO;
  switch (info.type) {
    case SummaryTokenInfo::TEXT:
      icon_.hidden = YES;
      break;
    case SummaryTokenInfo::CONTACT:
      icon_.image = kSearchKeywordsIconUser;
      break;
    case SummaryTokenInfo::CONVERSATION:
      icon_.image = kSearchKeywordsIconConvo;
      break;
    case SummaryTokenInfo::LOCATION:
      icon_.image = kSearchKeywordsIconLocation;
      break;
  }

  NSMutableAttributedString* attr_str = NewAttrString(info.display_term, kAutocompleteNormalAttributes);
  if (filter_re) {
    ApplySearchFilter(filter_re, info.display_term, attr_str, kAutocompleteBoldAttributes);
  }
  label_.attributedText = attr_str;

  [self setNeedsLayout];
}

+ (int)rowHeight {
  return 44;
}

@end  // AutocompleteTableViewCell


@implementation SearchFieldView

@synthesize env = env_;
@synthesize searching = searching_;
@synthesize editing = search_field_editing_;
@synthesize searchQuery = search_query_;
@synthesize searchPlaceholder = search_placeholder_;
@synthesize pinnedBGColor = pinned_bg_color_;
@synthesize unpinnedBGColor = unpinned_bg_color_;
@synthesize borderColor = border_color_;

- (id)initWithState:(UIAppState*)state
   withSearchParent:(UIView*)search_parent {
  if (self = [super init]) {
    state_ = state;
    search_parent_ = search_parent;

    pinned_bg_color_ = kSearchBarPinnedBGColor;
    unpinned_bg_color_ = kSearchBarUnpinnedBGColor;
    border_color_ = kSearchBarBorderColor;
    self.backgroundColor = unpinned_bg_color_;

    search_bar_bottom_border_ = [UIView new];
    search_bar_bottom_border_.backgroundColor = border_color_;
    search_bar_bottom_border_.frameHeight = UIStyle::kDividerSize;
    [self addSubview:search_bar_bottom_border_];

    search_field_container_ = [UIView new];
    search_field_container_.autoresizesSubviews = YES;
    search_field_container_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    search_field_container_.frameTop = kMargin;
    [self addSubview:search_field_container_];

    search_field_background_ = [[UIImageView alloc] initWithImage:kSearchBarTextField];
    search_field_background_.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    search_field_background_.frameSize = search_field_container_.frameSize;
    [search_field_container_ addSubview:search_field_background_];

    search_field_icon_ = [[UIImageView alloc] initWithImage:kSearchBarIconSearch];
    [search_field_container_ addSubview:search_field_icon_];

    TokenizedTextViewOptions options;
    options.font = kSearchFieldFont;
    options.bold_font = kSearchFieldFont;
    options.min_height = 0;
    options.margin_x = 0;
    options.margin_y = 0;
    options.padding_x = 4;
    options.padding_y = 4;
    options.inset_x = 4;
    options.top_inset_y = 2;
    options.bottom_inset_y = 1;
    options.text_top_inset_y = 2;
    options.token_corner_radius = 2;
    options.emoji_extra_height_factor = 1.0;
    options.text_wrap_width = 50;
    search_field_ = [[TokenizedTextView alloc] initWithDelegate:self withOptions:options];
    search_field_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    search_field_.field.backgroundColor = [UIColor clearColor];
    search_field_.field.textColor = kSearchFieldTextColor;
    search_field_.frameOrigin = CGPointMake(search_field_icon_.frameRight,
                                            kSearchFieldInsetY);
    [search_field_container_ addSubview:search_field_];

    // The tokenized field is configured with narrow margins so the tap area is smaller than it looks.
    // Make up for it by making the background (including the magnifying glass icon) tappable.
    UITapGestureRecognizer* tap_recognizer = [[UITapGestureRecognizer alloc]
                                               initWithTarget:search_field_.field
                                                       action:@selector(becomeFirstResponder)];
    tap_recognizer.delegate = self;
    [search_field_container_ addGestureRecognizer:tap_recognizer];

    clear_button_ = [UIButton new];
    clear_button_.frameSize = kSearchBarTextFieldClear.get().size;
    [clear_button_ setImage:kSearchBarTextFieldClear
                   forState:UIControlStateNormal];
    [clear_button_ addTarget:self
                      action:@selector(searchBarCancel)
            forControlEvents:UIControlEventTouchUpInside];
    search_field_.field.rightView = clear_button_;
    search_field_.field.rightViewMode = UITextFieldViewModeNever;

    cancel_button_ = NewSearchBarButtonDark(@"Cancel", kCancelButtonWidth, self, @selector(searchBarCancel));
    cancel_button_.frameTop = kMargin;
    [self addSubview:cancel_button_];

    autocomplete_table_ = [UITableView new];
    autocomplete_table_.alwaysBounceVertical = YES;
    autocomplete_table_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    autocomplete_table_.backgroundColor = kAutocompleteBackgroundColor;
    autocomplete_table_.dataSource = self;
    autocomplete_table_.delegate = self;
    autocomplete_table_.hidden = YES;
    autocomplete_table_.rowHeight = [AutocompleteTableViewCell rowHeight];
    autocomplete_table_.scrollsToTop = NO;
    autocomplete_table_.separatorStyle = UITableViewCellSeparatorStyleNone;
    [search_parent_ addSubview:autocomplete_table_];

    search_bar_shadow_ = [[UIImageView alloc] initWithImage:kSearchBarShadow];
    search_bar_shadow_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    search_bar_shadow_.hidden = YES;
    [search_parent_ addSubview:search_bar_shadow_];

    autocomplete_header_ = [UIView new];
    autocomplete_header_.autoresizesSubviews = YES;
    autocomplete_header_.frameHeight = kMargin;

    autocomplete_footer_ = [UIView new];
    autocomplete_footer_.frameHeight = kMargin;
  }
  return self;
}

- (float)intrinsicHeight {
  return kSearchFieldIntrinsicHeight;
}

- (void)willMoveToSuperview:(UIView*)new_superview {
  if (!self.superview && new_superview) {
    keyboard_will_show_.Init(
        UIKeyboardWillShowNotification,
        ^(NSNotification* n) {
          const Dict d(n.userInfo);
          keyboard_frame_ = [self convertRect:d.find_value(UIKeyboardFrameEndUserInfoKey).rect_value()
                                     fromView:NULL];
          const double duration = d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve = d.find_value(UIKeyboardAnimationDurationUserInfoKey).int_value();
          [UIView animateWithDuration:duration
                                delay:0
                              options:curve|UIViewAnimationOptionBeginFromCurrentState
                           animations:^{
              [self layoutSubviews];
            }
                           completion:NULL];
        });
    keyboard_will_hide_.Init(
        UIKeyboardWillHideNotification,
        ^(NSNotification* n) {
          const Dict d(n.userInfo);
          keyboard_frame_ = CGRectZero;
          const double duration = d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve = d.find_value(UIKeyboardAnimationDurationUserInfoKey).int_value();
          [UIView animateWithDuration:duration
                                delay:0
                              options:curve|UIViewAnimationOptionBeginFromCurrentState
                           animations:^{
              [self layoutSubviews];
            }
                           completion:NULL];
        });
  } else {
    keyboard_will_show_.Clear();
    keyboard_will_hide_.Clear();
  }
}

- (void)setPinnedBGColor:(UIColor*)pinned_bg_color {
  pinned_bg_color_ = pinned_bg_color;
  if (self.searchPinned) {
    self.backgroundColor = pinned_bg_color_;
  }
}

- (void)setUnpinnedBGColor:(UIColor*)unpinned_bg_color {
  unpinned_bg_color_ = unpinned_bg_color;
  if (!self.searchPinned) {
    self.backgroundColor = unpinned_bg_color_;
  }
}

- (void)setBorderColor:(UIColor*)border_color {
  border_color_ = border_color;
  search_bar_bottom_border_.backgroundColor = border_color_;
}

- (void)setSearchPlaceholder:(NSString*)search_placeholder {
  search_placeholder_ = search_placeholder;
  search_field_.field.attributedPlaceholder = NewAttrString(
      ToString(search_placeholder_), kSearchFieldPlaceholderAttributes);
}

- (void)searchFor:(const Slice&)query {
  LOG("searching for [%s]", query);
  search_query_ = query.as_string();
  searching_ = (query.size() > 0);
  [env_ searchFieldViewDidSearch:self];
}

- (BOOL)tokenizedTextViewShouldBeginEditing:(TokenizedTextView*)field {
  return YES;
}

- (void)tokenizedTextViewDidBeginEditing:(TokenizedTextView*)field {
  search_field_editing_ = true;
  if (!self.searchPinned) {
    [self pinSearchToTop];
  }

  [self updateAutocomplete];
  autocomplete_table_.hidden = NO;
  autocomplete_table_.alpha = 0;
  [UIView animateWithDuration:kDuration
                   animations:^{
      if (!searching_) {
        [env_ searchFieldViewWillBeginSearching:self];
        self.backgroundColor = pinned_bg_color_;
      }
      autocomplete_table_.alpha = 1;
      [self layoutSubviews];
      if (!searching_) {
        [env_ searchFieldViewDidBeginSearching:self];
      }
    }
                   completion:^(BOOL finished) {
    }];
}

- (BOOL)tokenizedTextViewShouldEndEditing:(TokenizedTextView*)field {
  return YES;
}

- (void)tokenizedTextViewDidEndEditing:(TokenizedTextView*)field {
  search_field_editing_ = false;
  if (!searching_) {
    [self unpinSearch];
  }

  [UIView animateWithDuration:kDuration
                   animations:^{
      if (!searching_) {
        [env_ searchFieldViewWillEndSearching:self];
        self.backgroundColor = unpinned_bg_color_;
      }
      autocomplete_table_.alpha = 0;
      [self layoutSubviews];
      if (!searching_) {
        [env_ searchFieldViewDidEndSearching:self];
      }
    }
                   completion:^(BOOL finished) {
      autocomplete_table_.hidden = YES;
    }];

}

- (void)tokenizedTextViewChangedTokens:(TokenizedTextView*)view {
  string query;
  for (int i = 0; i < view.numTokens; i++) {
    query += static_cast<const SummaryToken&>([view getToken:i]).query_term();
    query += " ";
  }
  [self searchFor:query];
  if (view.numTokens > prev_num_tokens_) {
    // Once a token has been added, dismiss the keyboard and autocomplete.
    [view.field resignFirstResponder];
  }
  prev_num_tokens_ = view.numTokens;
  view.field.showPlaceholder = (view.numTokens == 0);
  [self updateClearButton];
}

- (void)tokenizedTextViewQueryRemoveToken:(TokenizedTextView*)view
                                    token:(const TextViewToken&)token
                             withCallback:(RemoveTokenCallback)done {
  done();
}

- (void)updateAutocomplete {
  const string text = ToString(search_field_.field.text);
  SummaryAutocompleteResults results;
  [env_ searchFieldViewPopulateAutocomplete:self results:&results forQuery:text];
  autocomplete_.clear();
  autocomplete_filter_.reset(results.release_filter_re());
  results.GetSortedResults(&autocomplete_);

  autocomplete_table_.tableHeaderView = (self.autocompleteRowCount > 0) ? autocomplete_header_ : NULL;
  autocomplete_table_.tableFooterView = (self.autocompleteRowCount > 0) ? autocomplete_footer_ : NULL;
  [autocomplete_table_ reloadData];
  [autocomplete_table_ setContentOffset:CGPointMake(0, 0) animated:YES];
}

- (int)autocompleteRowCount {
  if (autocomplete_.size() > 0) {
    return autocomplete_.size();
  } else if (search_field_.field.text.length > 0) {
    // The dummy "no results found" row.
    return 1;
  } else {
    return 0;
  }
}

- (UITableViewCell*)tableView:(UITableView*)table cellForRowAtIndexPath:(NSIndexPath*)path {
  const int row = path.row;
  static NSString* kIdentifier = @"SearchableSummaryViewCellIdentifier";

  AutocompleteTableViewCell* cell =
      [table dequeueReusableCellWithIdentifier:kIdentifier];
  if (!cell) {
    cell = [[AutocompleteTableViewCell alloc]
             initWithReuseIdentifier:kIdentifier];
  }

  if (row == 0 && autocomplete_.size() == 0) {
    [cell setMessage:"No results found"];
    return cell;
  }

  AutocompleteRowPosition position;
  if (row == 0) {
    position = (autocomplete_.size() > 1) ? TOP : SINGLE;
  } else if (row == autocomplete_.size() - 1) {
    position = BOTTOM;
  } else {
    position = MIDDLE;
  }
  [cell setTokenInfo:autocomplete_[row].second filterRE:autocomplete_filter_.get() position:position];

  return cell;
}

- (bool)tokenizedTextViewShouldReturn:(TokenizedTextView*)view {
  string text = Trim(ToString(view.field.text));
  view.field.text = @"";
  if (text.size() == 0) {
    [view.field resignFirstResponder];
  } else {
    SummaryTokenInfo token(SummaryTokenInfo::TEXT, text, text);
    [search_field_ addToken:new SummaryToken(token)];
  }
  return false;
}

- (CGRect)tokenizedTextViewVisibleBounds:(TokenizedTextView*)view {
  CGRect r = self.bounds;
  r.size.height = std::min(keyboard_frame_.origin.y, r.size.height);
  return r;
}

- (void)tokenizedTextViewChangedSize:(TokenizedTextView*)view {
  [self layoutSubviews];
}

- (void)tokenizedTextViewChangedText:(TokenizedTextView*)view {
  [self updateAutocomplete];
  [self updateClearButton];
}

- (bool)searchPinned {
  return self.superview == search_parent_;
}

- (void)pinSearchToTop {
  // Reassign the search bar's parent view while maintaining its on-screen position.
  // It will be animated into its new position later.
  orig_parent_ = self.superview;
  orig_index_ = [[orig_parent_ subviews] indexOfObject:self];
  CGRect new_frame = [search_parent_ convertRect:self.frame fromView:self.superview];
  [search_parent_ addSubview:self];
  self.frame = new_frame;
  search_bar_shadow_.hidden = NO;
}

- (void)unpinSearch {
  CGRect new_frame = [orig_parent_ convertRect:self.frame fromView:self.superview];
  [orig_parent_ insertSubview:self atIndex:orig_index_];
  self.frame = new_frame;
  search_bar_shadow_.hidden = YES;
}

- (void)updateClearButton {
  if (search_field_.numTokens == 0 &&
      search_field_.field.text.length == 0) {
    search_field_.field.rightViewMode = UITextFieldViewModeNever;
  } else {
    search_field_.field.rightViewMode = UITextFieldViewModeAlways;
  }
}

- (float)searchBarExtra {
  if (self.searchPinned && search_parent_.boundsHeight == state_->screen_height()) {
    return state_->status_bar_height();
  }
  return 0;
}

- (CGRect)searchBarFrame {
  CGRect f = self.frame;
  f.size.width = self.frameWidth;
  f.size.height = self.searchBarExtra +
      std::max(self.intrinsicHeight, search_field_.frameHeight + 10 + kMargin * 2);
  if (self.searchPinned) {
    f.origin.y = 0;
  } else {
    f.origin.y = -f.size.height;
  }
  return f;
}

- (CGRect)searchFieldContainerFrame {
  CGRect f = search_field_container_.frame;
  const float search_bar_extra = self.searchBarExtra;
  f.origin.x = kMargin;
  f.origin.y = kMargin + search_bar_extra;
  f.size.height = self.frameHeight - kMargin * 2 - search_bar_extra;
  f.size.width = self.frameWidth - kMargin - f.origin.x;
  if (search_field_editing_) {
    f.size.width -= cancel_button_.frameWidth + kMargin;
  }
  return f;
}

- (CGRect)searchFieldFrame {
  CGRect f = search_field_.frame;
  f.size.width = search_field_container_.frameWidth - search_field_.frameLeft - kSearchFieldInsetX;
  return f;
}

- (CGRect)cancelButtonFrame {
  CGRect f = cancel_button_.frame;
  f.origin.y = kMargin + self.searchBarExtra;
  if (search_field_editing_) {
    f.origin.x = self.frameWidth - kMargin - f.size.width;
  } else {
    f.origin.x = self.frameWidth;
  }
  return f;
}

- (void)layoutSubviews {
  self.frame = self.searchBarFrame;
  search_bar_bottom_border_.frameWidth = self.boundsWidth;
  search_bar_bottom_border_.frameBottom = self.boundsHeight;
  search_field_container_.frame = self.searchFieldContainerFrame;
  search_field_.frame = self.searchFieldFrame;
  cancel_button_.frame = self.cancelButtonFrame;

  [super layoutSubviews];
  [env_ searchFieldViewDidChange:self];

  CGRect search_frame = [search_parent_ convertRect:self.frame fromView:self.superview];
  search_bar_shadow_.frameTop = CGRectGetMaxY(search_frame);
  float frame_height = search_parent_.frameHeight;
  if (!CGRectIsEmpty(keyboard_frame_)) {
    frame_height = std::min(frame_height, keyboard_frame_.origin.y);
  }
  autocomplete_table_.frame = CGRectMake(
      0, CGRectGetMaxY(search_frame),
      search_parent_.frameWidth, frame_height - CGRectGetMaxY(search_frame));
}

- (NSInteger)numberOfSectionsInTableView:(UITableView*)view {
  return 1;
}

- (NSInteger)tableView:(UITableView*)table_view
 numberOfRowsInSection:(NSInteger)section {
  return self.autocompleteRowCount;
}

- (NSString*)tableView:(UITableView*)table_view
titleForHeaderInSection:(NSInteger)section {
  return NULL;
}

- (NSIndexPath*)tableView:(UITableView*)table_view
 willSelectRowAtIndexPath:(NSIndexPath*)index_path {
  if (autocomplete_.size() == 0) {
    // Don't allow selection of the no-results message.
    return NULL;
  }
  return index_path;
}

- (void)tableView:(UITableView*)table_view
didSelectRowAtIndexPath:(NSIndexPath*)index_path {
  [self selectSummaryTokenInfo:autocomplete_[index_path.row].second];
}

- (void)selectSummaryTokenInfo:(const SummaryTokenInfo&)info {
  [search_field_ addToken:new SummaryToken(info)];
  [search_field_ clearText];
  [self updateAutocomplete];
}

- (void)searchBarCancel {
  const bool was_searching = searching_;
  while (search_field_.numTokens) {
    [search_field_ removeToken:0];
  }
  [search_field_ clearText];
  [search_field_ setNeedsLayout];
  [search_field_.field resignFirstResponder];
  [UIView animateWithDuration:kDuration
                   animations:^{
      // TODO(ben): should search_field_ be sending this message itself?  There's still some more cleanup to do here.
      [self tokenizedTextViewChangedTokens:search_field_];
      [self tokenizedTextViewChangedSize:search_field_];
    }
                   completion:NULL];

  if (was_searching) {
    [self tokenizedTextViewDidEndEditing:search_field_];
  }
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)recognizer shouldReceiveTouch:(UITouch*)touch {
  // Make sure the clear button isn't being tapped.
  if ([touch.view isKindOfClass:[UIControl class]]) {
    return NO;
  }
  return YES;
}

@end  // SearchableSummaryView
