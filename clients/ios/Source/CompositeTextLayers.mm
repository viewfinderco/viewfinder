// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "Appearance.h"
#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "CompositeTextLayers.h"
#import "Logging.h"
#import "ScopedRef.h"
#import "StringUtils.h"
#import "UIStyle.h"
#import "ValueUtils.h"

#undef SHOW_SUMMARY_WEIGHTS

namespace {

// Sizes in points.
// TODO(spencer): remove this hard-coded value and instead compute
// something appropriate from the fonts being used.
const float kLeading = 16;
const CGSize kShadowOffset = { 0.5, 0.5 };
const float kShadowRadius = 0.5;

const float kActivityTitleBaseline = 14.5;
const float kActivityTimeBaseline = 28;

const float kInboxCardUnviewedTopMargin = 4;
const float kInboxCardTitleBaseline = 24;
const float kInboxCardContribBaseline = 44;
const float kInboxCardTitleAscent = 10.4;

LazyStaticCTFont kInboxCardTitleFont = {
  kProximaNovaRegular, 20
};
LazyStaticCTFont kInboxCardContribFont = {
  kProximaNovaRegular, 12
};
LazyStaticCTFont kInboxCardContribNewFont = {
  kProximaNovaBold, 12
};
LazyStaticCTFont kInboxCardInfoFont = {
  kProximaNovaRegular, 12
};

LazyStaticHexColor kInboxCardTitleColor = { "#3f3e3eff" };
LazyStaticHexColor kInboxCardContribColor = { "#3f3e3eff" };
LazyStaticHexColor kInboxCardContribNewColor = { "#3f3e3eff" };
LazyStaticHexColor kInboxCardInfoColor = { "#9f9c9cff" };

const float kEventCardTitleBaseline = 23;
const float kEventCardDateBaseline = 37;

LazyStaticCTFont kEventCardTitleFont = {
  kProximaNovaBold, 12
};
LazyStaticCTFont kEventCardDateFont = {
  kProximaNovaRegularItalic, 12
};

LazyStaticHexColor kEventCardTitleColor = { "#3f3e3e" };
LazyStaticHexColor kEventCardDateColor = { "#9f9c9c" };

const float kFullEventCardTitleBaseline = 21;
const float kFullEventCardDateSpacing = 16;

LazyStaticCTFont kFullEventCardTitleFont = {
  kProximaNovaRegular, 15
};
LazyStaticCTFont kFullEventCardDateFont = {
  kProximaNovaRegular, 15
};

LazyStaticHexColor kFullEventCardTitleColor = { "#dfdbdb" };
LazyStaticHexColor kFullEventCardDateColor = { "#dfdbdb" };

// The metrics (ascent, descent, leading) are the same (0) for all empty
// attributed strings, regardless of the font and color.
LazyStaticAttributedString kEmptyAttrString = {^{
    return [[NSAttributedString alloc] initWithString:@""];
  }
};

}  // namespace

@interface TextLayer (internal)
- (void)blendForegroundColor:(CGColorRef)color blendRatio:(float)t;
@end  // TextLayer

@interface ColoredTextLayer : TextLayer {
 @private
  NSAttributedString* orig_str_;
}

@end  // ColoredTextLayer

@implementation ColoredTextLayer

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[ColoredTextLayer class]]) {
      ColoredTextLayer* other = (ColoredTextLayer*)layer;
      orig_str_ = other->orig_str_;
    }
  }
  return self;
}

- (void)setAttrStr:(NSAttributedString*)attr_str {
  [super setAttrStr:attr_str];
  orig_str_ = NULL;
}

- (void)blendForegroundColor:(CGColorRef)color
                  blendRatio:(float)t {
  if (t == 0) {
    if (orig_str_) {
      [super setAttrStr:orig_str_];
      orig_str_ = NULL;
    }
    return;
  }
  if (!orig_str_) {
    orig_str_ = self.attrStr;
  }
  [super setAttrStr:AttrBlendForegroundColor([orig_str_ mutableCopy], color, t)];
}

@end  // ColoredTextLayer

// A CALayer subclass which provides a masking window onto a
// TextLayer. The layer is auto-sized to fit the text layer.
// The text layer can be positioned internally for effect, such
// as in the case of the transition text blending.
@interface MaskedTextLayer : CALayer {
 @private
  ColoredTextLayer* text_;
}

@property (nonatomic, readonly) ColoredTextLayer* text;

@end  // MaskedTextLayer

@implementation MaskedTextLayer

@synthesize text = text_;

- (id)initWithText:(NSMutableAttributedString*)attr_str
      withMaxWidth:(float)max_width {
  if (self = [super init]) {
    text_ = [ColoredTextLayer new];
    text_.maxWidth = max_width;
    text_.attrStr = attr_str;
    text_.anchorPoint = CGPointMake(0, 0);

    self.masksToBounds = YES;
    // self.backgroundColor = MakeUIColor(0, 0, 1, 0.2).CGColor;
    self.bounds = text_.bounds;

    [self addSublayer:text_];
    text_.frame = self.bounds;
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[MaskedTextLayer class]]) {
      MaskedTextLayer* other = (MaskedTextLayer*)layer;
      text_ = other->text_;
    }
  }
  return self;
}

@end  // MaskedTextLayer


@implementation TransitionTextLayer

@synthesize ascent = max_ascent_;
@synthesize descent = max_descent_;
@synthesize leading = max_leading_;

- (id)initWithText:(NSAttributedString*)text
            toText:(NSAttributedString*)to_text {
  if (self = [super init]) {
    self.contentsScale = [UIScreen mainScreen].scale;
    self.rasterizationScale = [UIScreen mainScreen].scale;
    transition_ = 0;
    max_width_ = CGFLOAT_MAX;
    slide_left_ = 0;
    slide_layer_ = [CALayer new];
    [self addSublayer:slide_layer_];
    self.anchorPoint = CGPointMake(0, 0);
    text_ = text;
    to_text_ = to_text;
    blend_ratio_ = 0;
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[TransitionTextLayer class]]) {
      TransitionTextLayer* other = (TransitionTextLayer*)layer;
      transition_ = other->transition_;
      max_width_ = other->max_width_;
      slide_left_ = other->slide_left_;
      slide_layer_ = other->slide_layer_;
      text_ = other->text_;
      to_text_ = other->to_text_;
      text_layer_ = other->text_layer_;
      to_text_layer_ = other->to_text_layer_;
      max_ascent_ = other->max_ascent_;
      max_descent_ = other->max_descent_;
      max_leading_ = other->max_leading_;
      max_height_ = other->max_height_;
      diffs_ = other->diffs_;
      blend_ratio_ = other->blend_ratio_;
    }
  }
  return self;
}

- (void)initDiffText {
  vector<DiffOp> diff;
  const string from_str(text_ ? ToString(text_.string) : string());
  const string to_str(to_text_ ? ToString(to_text_.string) : string());
  DiffStrings(from_str, to_str, &diff, DIFF_UTF16);

  // Loop over the diffs, creating a MaskedTextLayer for each diff op.
  for (int i = 0; i < diff.size(); ++i) {
    const DiffOp& op = diff[i];
    NSMutableAttributedString* attr_str = [NSMutableAttributedString new];

    // Use attributes from original string.
    if (op.type == DiffOp::MATCH || op.type == DiffOp::DELETE) {
      NSRange range = NSMakeRange(op.offset, op.length);
      CHECK_LT(range.location, text_.length);
      CHECK_LE(range.location + range.length, text_.length);
      [attr_str appendAttributedString:[text_ attributedSubstringFromRange:range]];
    } else {
      // Otherwise, from "to" string.
      NSRange range = NSMakeRange(op.offset, op.length);
      CHECK_LT(range.location, to_text_.length);
      CHECK_LE(range.location + range.length, to_text_.length);
      [attr_str appendAttributedString:[to_text_ attributedSubstringFromRange:range]];
    }

    MaskedTextLayer* layer = [[MaskedTextLayer alloc]
                               initWithText:attr_str
                               withMaxWidth:max_width_ - slide_left_];

    max_ascent_ = std::max<float>(max_ascent_, layer.text.ascent);
    max_descent_ = std::max<float>(max_descent_, layer.text.descent);
    max_leading_ = std::max<float>(max_leading_, layer.text.leading);
    max_height_ = std::max<float>(max_height_, layer.bounds.size.height);
    [slide_layer_ addSublayer:layer];
    diffs_.push_back(DiffLayer(op, layer));
  }
}

// Optimized version of full diff-text. Only creates a text layer for
// the to-text.
- (void)initToText {
  CHECK_EQ(transition_, 1);
  to_text_layer_ = [ColoredTextLayer new];
  to_text_layer_.maxWidth = max_width_ - slide_left_;
  to_text_layer_.attrStr = to_text_;
  to_text_layer_.anchorPoint = CGPointMake(0, 0);
  max_ascent_ = to_text_layer_.ascent;
  max_descent_ = to_text_layer_.descent;
  max_leading_ = to_text_layer_.leading;
  max_height_ = to_text_layer_.bounds.size.height;
  [slide_layer_ addSublayer:to_text_layer_];
  self.bounds = to_text_layer_.bounds;
}

// Optimized version of full diff-text. Only creates a text layer for
// the text.
- (void)initText {
  CHECK_EQ(transition_, 0);
  text_layer_ = [ColoredTextLayer new];
  text_layer_.maxWidth = max_width_ - slide_left_;
  text_layer_.attrStr = text_;
  text_layer_.anchorPoint = CGPointMake(0, 0);
  max_ascent_ = text_layer_.ascent;
  max_descent_ = text_layer_.descent;
  max_leading_ = text_layer_.leading;
  max_height_ = text_layer_.bounds.size.height;
  [slide_layer_ addSublayer:text_layer_];
  self.bounds = text_layer_.bounds;
}

- (float)baseline {
  return max_height_ - max_descent_;
}

- (float)lineHeight {
  return self.leading + self.ascent + self.descent;
}

- (float)transition {
  return transition_;
}

- (void)setTransition:(float)t {
  transition_ = t;
  if (transition_ == 1 || transition_ == 0) {
    while (!diffs_.empty()) {
      [diffs_.back().layer removeFromSuperlayer];
      diffs_.pop_back();
    }
    if (transition_ == 1) {
      if (text_layer_) {
        [text_layer_ removeFromSuperlayer];
        text_layer_ = NULL;
      }
      if (!to_text_layer_) {
        [self initToText];
      }
    } else {
      DCHECK_EQ(transition_, 0);
      if (to_text_layer_) {
        [to_text_layer_ removeFromSuperlayer];
        to_text_layer_ = NULL;
      }
      if (!text_layer_) {
        [self initText];
      }
    }
    return;
  }

  if (to_text_layer_) {
    [to_text_layer_ removeFromSuperlayer];
    to_text_layer_ = NULL;
  }
  if (text_layer_) {
    [text_layer_ removeFromSuperlayer];
    text_layer_ = NULL;
  }
  if (diffs_.empty()) {
    [self initDiffText];
  }

  float x = 0;
  for (int i = 0; i < diffs_.size(); ++i) {
    const DiffLayer& diff = diffs_[i];
    const float width = diff.layer.text.bounds.size.width;
    const float y_offset = (max_height_ - max_descent_) - (diff.layer.frame.size.height - diff.layer.text.descent);
    float offset = 0;
    switch (diff.op.type) {
      case DiffOp::MATCH:
        diff.layer.frame = MakeIntegralRect(
            x, y_offset, width, diff.layer.frame.size.height);
        break;
      case DiffOp::INSERT:
        diff.layer.frame = MakeIntegralRect(
            x, y_offset, width * t, diff.layer.frame.size.height);
        diff.layer.hidden = (t == 0) ? YES : NO;
        offset = -(1 - t) * width;
        break;
      case DiffOp::DELETE:
        diff.layer.frame = MakeIntegralRect(
            x, y_offset, width * (1 - t), diff.layer.frame.size.height);
        diff.layer.hidden = (t == 1) ? YES : NO;
        offset = -t * width;
        break;
      default:
        CHECK(false) << "unrecognized diff type";
    }

    diff.layer.text.position = MakeIntegralPoint(offset, 0);
    x += width + offset;
  }
  self.bounds = MakeIntegralRect(0, 0, x, max_height_);
}

- (float)maxWidth {
  return max_width_;
}

- (void)setMaxWidth:(float)w {
  max_width_ = w;
  // If already initialized, remove existing layers and reinitialize.
  if (to_text_layer_ != NULL) {
    [to_text_layer_ removeFromSuperlayer];
    [self initToText];
  } else if (text_layer_ != NULL) {
    [text_layer_ removeFromSuperlayer];
    [self initText];
  } else if (!diffs_.empty()) {
    while (!diffs_.empty()) {
      [diffs_.back().layer removeFromSuperlayer];
      diffs_.pop_back();
    }
    [self initDiffText];
  }
}

- (float)slideLeft {
  return slide_left_;
}

- (void)setSlideLeft:(float)sl {
  if (slide_left_ == sl) {
    return;
  }
  slide_left_ = sl;

  // Shift the slide layer.
  slide_layer_.frameLeft = slide_left_;

  // Reset max width so it is computed in light of this new value
  // for the slide left property.
  self.maxWidth = max_width_;
}

- (void)clearShadow {
  for (int i = 0; i < diffs_.size(); ++i) {
    CALayer* text = diffs_[i].layer.text;
    text.shadowRadius = 0;
    text.shadowOpacity = 0;
    text.shouldRasterize = NO;
  }
}

- (void)setShadowWithColor:(CGColorRef)color {
  for (int i = 0; i < diffs_.size(); ++i) {
    CALayer* text = diffs_[i].layer.text;
    text.shadowOffset = kShadowOffset;
    text.shadowColor = color;
    text.shadowRadius = kShadowRadius;
    text.shadowOpacity = 1;
    text.shouldRasterize = YES;
  }
}

- (void)blendForegroundColor:(const Vector4f&)c
                  blendRatio:(float)t {
  if (blend_ratio_ == t) {
    return;
  }
  blend_ratio_ = t;
  UIColor* ui_color = MakeUIColor(c);

  if (to_text_layer_) {
    [to_text_layer_ blendForegroundColor:ui_color.CGColor blendRatio:t];
    return;
  }
  if (text_layer_) {
    [text_layer_ blendForegroundColor:ui_color.CGColor blendRatio:t];
    return;
  }
  for (int i = 0; i < diffs_.size(); ++i) {
    [diffs_[i].layer.text blendForegroundColor:ui_color.CGColor blendRatio:t];
  }
}

@end  // TransitionTextLayer


@implementation CompositeTextLayer

- (id)init {
  if (self = [super init]) {
    self.contentsScale = [UIScreen mainScreen].scale;
    self.rasterizationScale = [UIScreen mainScreen].scale;

    transition_ = -1;
    max_width_ = CGFLOAT_MAX;
    slide_left_ = 0;
    text_width_ = 0;
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[CompositeTextLayer class]]) {
      CompositeTextLayer* other = (CompositeTextLayer*)layer;
      layers_ = other->layers_;
      text_width_ = other->text_width_;
      transition_ = other->transition_;
      max_width_ = other->max_width_;
      slide_left_ = other->slide_left_;
    }
  }
  return self;
}

- (float)transition {
  return transition_;
}

- (void)setTransition:(float)t {
  if (transition_ == t) {
    return;
  }
  transition_ = t;

  for (int i = 0; i < layers_.size(); ++i) {
    layers_[i].transition = transition_;
  }
}

- (float)maxWidth {
  return max_width_;
}

- (void)setMaxWidth:(float)w {
  if (max_width_ == w) {
    return;
  }
  max_width_ = w;

  for (int i = 0; i < layers_.size(); ++i) {
    layers_[i].maxWidth = max_width_;
  }
}

- (float)slideLeft {
  return slide_left_;
}

- (void)setSlideLeft:(float)sl {
  if (slide_left_ == sl) {
    return;
  }
  slide_left_ = sl;

  // Default implementation shifts all transition text layers.
  for (int i = 0; i < layers_.size(); ++i) {
    layers_[i].slideLeft = slide_left_;
  }
}

- (void)clearShadow {
  for (int i = 0; i < layers_.size(); ++i) {
    [layers_[i] clearShadow];
  }
}

- (void)setShadowWithColor:(const Vector4f&)color {
  UIColor* ui_color = MakeUIColor(color);
  for (int i = 0; i < layers_.size(); ++i) {
    [layers_[i] setShadowWithColor:ui_color.CGColor];
  }
}

- (void)blendForegroundColor:(const Vector4f&)c
                  blendRatio:(float)t {
  // Set foreground color for all child layers.
  for (int i = 0; i < layers_.size(); ++i) {
    [layers_[i] blendForegroundColor:c blendRatio:t];
  }
}

@synthesize textWidth = text_width_;

@end  // CompositeTextLayer


@implementation EpisodeTextLayer

- (id)initWithEpisode:(const EpisodeHandle&)episode
     withContributors:(bool)with_contribs
       withPhotoCount:(int)photo_count
                atNow:(WallTime)now {
  if (self = [super init]) {
    UIColor* color = UIStyle::kTitleTextColor;

    location_ = [[TransitionTextLayer alloc]
                  initWithText:AttrTruncateTail(
                      NewAttrString(episode->FormatLocation(false), UIStyle::kTitleFont, color.CGColor))
                        toText:AttrTruncateTail(
                            NewAttrString(episode->FormatLocation(true), UIStyle::kTitleFont, color.CGColor))];
    [self addSublayer:location_];
    layers_.push_back(location_);

    string full_info_str = FormatRelativeTime(episode->timestamp(), now);
    if (photo_count > 0) {
      full_info_str += Format("%s%s %s", kSpaceSymbol, kPhotoSymbol, LocalizedNumberFormat(photo_count));
    }
    string short_info_str = Format("  %s", FormatRelativeTime(episode->timestamp(), now));

    if (with_contribs) {
      const string full_contributor = episode->FormatContributor(false);
      if (!full_contributor.empty()) {
        full_info_str = Format("%s%s%s %s", full_info_str, kSpaceSymbol,
                               kUserSymbol, full_contributor);
        short_info_str = Format("%s, %s", short_info_str, episode->FormatContributor(true));
      }
    }

    full_info_ = [[TransitionTextLayer alloc]
                   initWithText:AttrTruncateTail(
                       NewAttrString(full_info_str, UIStyle::kSubtitleFont, color.CGColor))
                         toText:kEmptyAttrString];
    [self addSublayer:full_info_];
    layers_.push_back(full_info_);

    short_info_ = [[TransitionTextLayer alloc]
                    initWithText:kEmptyAttrString
                          toText:NewAttrString(short_info_str, UIStyle::kSubtitleFont, color.CGColor)];
    [self addSublayer:short_info_];
    layers_.push_back(short_info_);
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[EpisodeTextLayer class]]) {
      EpisodeTextLayer* other = (EpisodeTextLayer*)layer;
      location_ = other->location_;
      full_info_ = other->full_info_;
      short_info_ = other->short_info_;
    }
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  text_width_ = 0;
  float y = kLeading;

  full_info_.position = MakeIntegralPoint(0, y - full_info_.baseline);
  text_width_ = full_info_.bounds.size.width;

  y += kLeading;
  location_.position = MakeIntegralPoint(0, y - location_.baseline);
  short_info_.position = MakeIntegralPoint(
      location_.frame.origin.x + location_.frame.size.width,
      y - short_info_.baseline);
  text_width_ = std::max<float>(text_width_, (location_.bounds.size.width +
                                              short_info_.bounds.size.width));

  // Set position so as to move the vertical center of location to the origin.
  [super setFrame:MakeIntegralRect(
        f.origin.x, f.origin.y - (y - location_.ascent / 2),
        text_width_, y)];
}

@end  // EpisodeTextLayer


@implementation ActivityTextLayer

- (id)initWithActivity:(const ActivityHandle&)activity
       withActivityRow:(const ViewpointSummaryMetadata::ActivityRow*)activity_row
        isContinuation:(bool)is_continuation {
  if (self = [super init]) {
    Vector4f default_color = UIStyle::kConversationTitleColor;
    // In the case of a continuation, we want the default color to fade out to 0 alpha.
    if (is_continuation) {
      default_color(3) = 0.0;
    }
    UIColor* color = MakeUIColor(default_color);

    const string info_str = is_continuation ? "" : activity->FormatName(false);
    const string activity_str = activity->FormatContent(activity_row, true);
    const string short_info_str = Format("%s: %s", activity->FormatName(true), activity_str);
    info_ = [[TransitionTextLayer alloc]
                    initWithText:AttrTruncateTail(
                        NewAttrString(info_str, UIStyle::kConversationTitleFont, color.CGColor))
                          toText:AttrTruncateTail(
                              NewAttrString(short_info_str, UIStyle::kConversationTitleFont, color.CGColor))];
    [self addSublayer:info_];
    layers_.push_back(info_);

    NSAttributedString* time_attr_str = NewAttrString(
        Format("%s", activity->FormatTimestamp(false)),
        UIStyle::kConversationTimeFont,
        UIStyle::kConversationTimeColor);

    time_ = [[TransitionTextLayer alloc]
                    initWithText:(is_continuation ? kEmptyAttrString : time_attr_str)
                          toText:kEmptyAttrString];
    [self addSublayer:time_];
    layers_.push_back(time_);

    NSMutableAttributedString* short_time_attr_str = NewAttrString(
        Format("%s%d %s", kSpaceSymbol, kTimeSymbol, activity->FormatTimestamp(false)),
        UIStyle::kConversationTimeFont,
        UIStyle::kConversationTimeColor);
    short_info_ = [[TransitionTextLayer alloc]
                    initWithText:kEmptyAttrString
                          toText:short_time_attr_str];
    [self addSublayer:short_info_];
    layers_.push_back(short_info_);
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[ActivityTextLayer class]]) {
      ActivityTextLayer* other = (ActivityTextLayer*)layer;
      info_ = other->info_;
      time_ = other->time_;
      short_info_ = other->short_info_;
    }
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  float y = kActivityTitleBaseline;

  info_.position = MakeIntegralPoint(0, y - info_.baseline);
  text_width_ = info_.bounds.size.width;

  short_info_.position = MakeIntegralPoint(info_.frameRight, y - short_info_.baseline);
  text_width_ += short_info_.bounds.size.width;

  time_.position = MakeIntegralPoint(0, kActivityTimeBaseline - time_.baseline);
  text_width_ = std::max(text_width_, time_.bounds.size.width);

  // Set position so as to move the vertical center of location to the origin.
  [super setFrame:MakeIntegralRect(
        f.origin.x, f.origin.y - (y - info_.ascent / 2),
        text_width_, y)];
}

@end  // ActivityTextLayer


@implementation EventTextLayer

- (id)initWithEvent:(const Event&)event
         withWeight:(float)weight
      locationFirst:(bool)location_first {
  if (self = [super init]) {
    UIColor* color = UIStyle::kTitleTextColor;
    location_first_ = location_first;

#ifdef SHOW_SUMMARY_WEIGHTS
    const string full_loc_str = Format("%s (%.3f)", event.FormatTitle(false), weight);
    const string short_loc_str = Format("%s (%.3f)", event.FormatTitle(true), weight);
#else
    const string full_loc_str = event.FormatTitle(false);
    const string short_loc_str = event.FormatTitle(true);
#endif  // SHOW_SUMMARY_WEIGHTS

    location_ = [[TransitionTextLayer alloc]
                    initWithText:AttrTruncateTail(
                        NewAttrString(full_loc_str, UIStyle::kTitleFont, color.CGColor))
                          toText:AttrTruncateTail(
                              NewAttrString(short_loc_str, UIStyle::kTitleFont, color.CGColor))];
    [self addSublayer:location_];
    layers_.push_back(location_);

    string full_info_str = Format("%s%s%s %s", event.FormatTimestamp(false),
                                  kSpaceSymbol, kPhotoSymbol, event.FormatPhotoCount());

    NSMutableAttributedString* short_info_attr_str = [NSMutableAttributedString new];
    [short_info_attr_str appendAttributedString:NewAttrString(
          Format("  %s", event.FormatTimestamp(true)), UIStyle::kTimeagoFont, color.CGColor)];

    if (event.contributors_size() > 0) {
      full_info_str = Format("%s%s%s %s", full_info_str, kSpaceSymbol, kUserSymbol,
                             event.FormatContributors(false));
      [short_info_attr_str appendAttributedString:NewAttrString(
            Format(", %s", event.FormatContributors(true)),
            UIStyle::kSubtitleFont, color.CGColor)];
    }

    full_info_ = [[TransitionTextLayer alloc]
                     initWithText:AttrTruncateTail(
                         NewAttrString(full_info_str, UIStyle::kSubtitleFont, color.CGColor))
                           toText:kEmptyAttrString];
    [self addSublayer:full_info_];
    layers_.push_back(full_info_);

    short_info_ = [[TransitionTextLayer alloc]
                     initWithText:kEmptyAttrString
                           toText:short_info_attr_str];
    [self addSublayer:short_info_];
    layers_.push_back(short_info_);
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  return (self = [super initWithLayer:layer]);
}

- (void)setFrame:(CGRect)f {
  text_width_ = 0;
  float y = kLeading;

  if (location_first_) {
    location_.position = MakeIntegralPoint(0, y - location_.baseline);
    short_info_.position = MakeIntegralPoint(
        location_.frame.origin.x + location_.frame.size.width,
        y - short_info_.baseline);
    text_width_ = location_.bounds.size.width + short_info_.bounds.size.width;

    y += kLeading;
    full_info_.position = MakeIntegralPoint(0, y - full_info_.baseline);
    text_width_ = std::max<float>(text_width_, full_info_.bounds.size.width);

    // Set position so as to move the vertical center of location to the origin.
    [super setFrame:MakeIntegralRect(
          f.origin.x, f.origin.y - (kLeading - location_.ascent / 2),
          text_width_, y)];
  } else {
    full_info_.position = MakeIntegralPoint(0, y - full_info_.baseline);
    text_width_ = full_info_.bounds.size.width;

    y += kLeading;
    location_.position = MakeIntegralPoint(0, y - location_.baseline);
    short_info_.position = MakeIntegralPoint(
        location_.frame.origin.x + location_.frame.size.width,
        y - short_info_.baseline);
    text_width_ = std::max<float>(text_width_, (location_.bounds.size.width +
                                                short_info_.bounds.size.width));

    // Set position so as to move the vertical center of location to the origin.
    [super setFrame:MakeIntegralRect(
          f.origin.x, f.origin.y - (y - location_.ascent / 2),
          text_width_, y)];
  }
}

@end  // EventTextLayer


@implementation EventCardTextLayer

- (id)initWithEvent:(const Event&)event
         withWeight:(float)weight {
  if (self = [super init]) {
#ifdef SHOW_SUMMARY_WEIGHTS
    const string full_loc_str = Format("%s (%.3f)", event.FormatLocation(false), weight);
    const string short_loc_str = Format("%s (%.3f)", event.FormatLocation(true), weight);
#else
    const string full_loc_str = event.FormatLocation(false);
    const string short_loc_str = event.FormatLocation(true);
#endif  // SHOW_SUMMARY_WEIGHTS

    CTFontRef font = kEventCardTitleFont;
    UIColor* color = kEventCardTitleColor;
    title_ = [[TransitionTextLayer alloc]
                    initWithText:AttrTruncateTail(NewAttrString(full_loc_str, font, color.CGColor))
                          toText:NewAttrString(short_loc_str, font, color.CGColor)];
    [self addSublayer:title_];
    layers_.push_back(title_);

    font = kEventCardDateFont;
    color = kEventCardDateColor;
    date_ = [[TransitionTextLayer alloc]
                     initWithText:AttrTruncateTail(NewAttrString(event.FormatTimeRange(false), font, color.CGColor))
                           toText:NewAttrString(event.FormatTimeRange(true), font, color.CGColor)];
    [self addSublayer:date_];
    layers_.push_back(date_);
  }

  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[EventCardTextLayer class]]) {
      EventCardTextLayer* other = (EventCardTextLayer*)layer;
      title_ = other->title_;
      date_ = other->date_;
    }
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  float y = kEventCardTitleBaseline;
  title_.position = MakeIntegralPoint(0, y - title_.baseline);

  y = kEventCardDateBaseline;
  date_.position = MakeIntegralPoint(0, y - date_.baseline);

  text_width_ = std::max<float>(title_.bounds.size.width, date_.bounds.size.width);

  [super setFrame:MakeIntegralRect(
        f.origin.x, f.origin.y - (kEventCardTitleBaseline - title_.ascent / 2),
        text_width_, y)];
}

@end  // EventCardTextLayer


@implementation FullEventCardTextLayer

- (id)initWithEvent:(const Event&)event
         withWeight:(float)weight {
  if (self = [super init]) {
#ifdef SHOW_SUMMARY_WEIGHTS
    const string loc_str = Format("%s (%.3f)", event.FormatLocation(true, false), weight);
#else
    const string loc_str = event.FormatLocation(true, false);
#endif  // SHOW_SUMMARY_WEIGHTS

    CTFontRef font = kFullEventCardTitleFont;
    UIColor* color = kFullEventCardTitleColor;
    title_ = [[TransitionTextLayer alloc]
                    initWithText:AttrTruncateTail(NewAttrString(loc_str, font, color.CGColor))
                          toText:AttrTruncateTail(NewAttrString(loc_str, font, color.CGColor))];
    [self addSublayer:title_];
    layers_.push_back(title_);

    font = kFullEventCardDateFont;
    color = kFullEventCardDateColor;
    date_ = [[TransitionTextLayer alloc]
                     initWithText:NewAttrString(event.FormatTimestamp(false), font, color.CGColor)
                           toText:kEmptyAttrString];
    [self addSublayer:date_];
    layers_.push_back(date_);
  }

  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[EventCardTextLayer class]]) {
      FullEventCardTextLayer* other = (FullEventCardTextLayer*)layer;
      title_ = other->title_;
      date_ = other->date_;
    }
  }
  return self;
}

- (void)setTransition:(float)t {
  [super setTransition:t];
  // Always hide date if we've started transition.
  // TODO(spencer): come up with something better looking.
  date_.hidden = t > 0;
}

- (void)setMaxWidth:(float)w {
  if (max_width_ == w) {
    return;
  }
  max_width_ = w;

  // Split available space between title and date. Leave title with
  // kFullEventCardDateSpacing pts.
  const float date_transition = date_.transition;
  date_.transition = 0;
  title_.maxWidth = w - (date_.bounds.size.width + kFullEventCardDateSpacing);
  date_.transition = date_transition;

  // Ensure date remains right justified.
  date_.position = MakeIntegralPoint(
      std::min<float>(w, self.frameWidth) - date_.bounds.size.width, date_.position.y);
}

- (void)setSlideLeft:(float)sl {
  if (slide_left_ == sl) {
    return;
  }
  slide_left_ = sl;

  // Only the title slides.
  title_.slideLeft = slide_left_;
}

- (void)setFrame:(CGRect)f {
  float y = kFullEventCardTitleBaseline;
  const float baseline = std::max(title_.baseline, date_.baseline);
  title_.position = MakeIntegralPoint(0, y - baseline);
  date_.position = MakeIntegralPoint(
      std::min<float>(max_width_, f.size.width) - date_.bounds.size.width, y - baseline);

  text_width_ = date_.frameRight;

  const float ascent = std::max(title_.ascent, date_.ascent);
  [super setFrame:MakeIntegralRect(
        f.origin.x, f.origin.y - (kFullEventCardTitleBaseline - ascent / 2),
        text_width_, y)];
}

@end  // FullEventCardTextLayer


@implementation InboxCardTextLayer

- (id)initWithTrapdoor:(const Trapdoor&)trapdoor
         withViewpoint:(const ViewpointHandle&)vh
            withWeight:(float)weight {
  if (self = [super init]) {
    UIColor* to_color = UIStyle::kTitleTextColor;

    top_margin_ = trapdoor.unviewed_content() ? kInboxCardUnviewedTopMargin : 0;

    // Title.
#ifdef SHOW_SUMMARY_WEIGHTS
    const string title_str = Format("%s (%.3f)", vh->FormatTitle(false, true), weight);
    const string short_title_str = Format("%s (%.3f)", vh->FormatTitle(true, true), weight);
#else
    const string title_str = vh->FormatTitle(false, true);
    const string short_title_str = vh->FormatTitle(true, true);
#endif  // SHOW_SUMMARY_WEIGHTS
    title_ = [[TransitionTextLayer alloc]
                     initWithText:AttrTruncateTail(NewAttrString(title_str, kInboxCardTitleFont,
                                                                 kInboxCardTitleColor.get().CGColor))
                           toText:kEmptyAttrString];
    [self addSublayer:title_];
    layers_.push_back(title_);

    // Short title (smaller font size).
    short_title_ = [[TransitionTextLayer alloc]
                     initWithText:kEmptyAttrString
                           toText:AttrTruncateTail(
                               NewAttrString(short_title_str, UIStyle::kTitleFont, to_color.CGColor))];
    [self addSublayer:short_title_];
    layers_.push_back(short_title_);

    time_ = [[TransitionTextLayer alloc]
                     initWithText:NewAttrString(trapdoor.FormatTimeAgo(), kInboxCardInfoFont,
                                                kInboxCardInfoColor.get().CGColor)
                           toText:kEmptyAttrString];
    [self addSublayer:time_];
    layers_.push_back(time_);

    // Info string (to be combined with short title).
    const string info_str = Format("  %s, %s", trapdoor.FormatContributors(true), trapdoor.FormatTimeAgo());
    short_info_ = [[TransitionTextLayer alloc]
                     initWithText:kEmptyAttrString
                           toText:AttrTruncateTail(
                               NewAttrString(info_str, UIStyle::kSubtitleFont, to_color.CGColor))];
    [self addSublayer:short_info_];
    layers_.push_back(short_info_);

    // Compute the contributors string.
    string new_contrib = trapdoor.FormatContributors(
         false, DayContributor::UNVIEWED_CONTENT);
    string old_contrib = trapdoor.FormatContributors(
        false, (DayContributor::VIEWED_CONTENT | DayContributor::NO_CONTENT));

    if (!new_contrib.empty() && !old_contrib.empty()) {
      new_contrib += ", ";
    }
    NSMutableAttributedString* contrib_attr_str = [NSMutableAttributedString new];
    if (!new_contrib.empty()) {
      [contrib_attr_str appendAttributedString:NewAttrString(
            new_contrib, kInboxCardContribNewFont, kInboxCardContribNewColor.get().CGColor)];
    }
    if (!old_contrib.empty()) {
      [contrib_attr_str appendAttributedString:NewAttrString(
            old_contrib, kInboxCardContribFont, kInboxCardContribColor.get().CGColor)];
    }
    contrib_attr_str = AttrTruncateTail(contrib_attr_str);

    contrib_ = [[TransitionTextLayer alloc]
                     initWithText:contrib_attr_str
                           toText:kEmptyAttrString];
    [self addSublayer:contrib_];
    layers_.push_back(contrib_);
  }

  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[InboxCardTextLayer class]]) {
      InboxCardTextLayer* other = (InboxCardTextLayer*)layer;
      title_ = other->title_;
      short_title_ = other->short_title_;
      short_info_ = other->short_info_;
      contrib_ = other->contrib_;
      time_ = other->time_;
    }
  }
  return self;
}

// Override setMaxWidth to set max width on short_title_ layer to account
// for the size of short_info_.
- (void)setMaxWidth:(float)w {
  if (max_width_ == w) {
    return;
  }
  [super setMaxWidth:w];

  title_.maxWidth = max_width_ - time_.frame.size.width;

  // Set the transition for short info to 1 to guarantee text is computed.
  const float orig_transition = short_info_.transition;
  short_info_.transition = 1;
  short_title_.maxWidth = max_width_ - short_info_.frame.size.width;
  short_info_.transition = orig_transition;
}

- (void)setSlideLeft:(float)sl {
  if (slide_left_ == sl) {
    return;
  }
  slide_left_ = sl;

  // Only the title and contrib slide.
  title_.slideLeft = slide_left_;
  contrib_.slideLeft = slide_left_;
}

- (void)setFrame:(CGRect)f {
  text_width_ = 0;

  float y = top_margin_ + kInboxCardTitleBaseline;
  title_.position = MakeIntegralPoint(0, y - title_.baseline);
  time_.position =
      MakeIntegralPoint(title_.frameRight + 8, y - time_.baseline);
  text_width_ = time_.frameRight;

  y = top_margin_ + kInboxCardContribBaseline;
  contrib_.position = MakeIntegralPoint(0, y - contrib_.baseline);
  short_title_.position = MakeIntegralPoint(contrib_.frameRight, y - short_title_.baseline);
  short_info_.position = MakeIntegralPoint(short_title_.frameRight, y - short_info_.baseline);
  text_width_ = std::max<float>(text_width_, short_info_.frameRight);

  // Set position so as to move the vertical center of contrib to the origin.
  [super setFrame:MakeIntegralRect(
        f.origin.x, f.origin.y - (kInboxCardContribBaseline - kInboxCardTitleAscent / 2),
        text_width_, y)];
}

@end  // InboxCardTextLayer
