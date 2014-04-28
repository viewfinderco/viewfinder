// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Appearance.h"
#import "AttrStringUtils.h"
#import "ScopedRef.h"
#import "ValueUtils.h"
#import "Vector.h"

namespace {

NSMutableAttributedString* AttrLineBreak(
    NSMutableAttributedString* s, CTLineBreakMode mode) {
  CTParagraphStyleSetting settings[] = {
    { kCTParagraphStyleSpecifierLineBreakMode, sizeof(mode), &mode },
  };
  ScopedRef<CTParagraphStyleRef> paragraph(
      CTParagraphStyleCreate(settings, ARRAYSIZE(settings)));
  [s addAttribute:(__bridge NSString*)kCTParagraphStyleAttributeName
            value:(__bridge id)paragraph.get()
            range:NSMakeRange(0, s.length)];
  return s;
}

Vector4f Blend(const Vector4f& a, const Vector4f& b, float t) {
  return a + (b - a) * t;
}

}  // namespace

NSMutableAttributedString* NewAttrString(
    const string& str, CTFontRef font, CGColorRef color) {
  const Dict attrs(kCTFontAttributeName, (__bridge id)font,
                   kCTForegroundColorAttributeName, (__bridge id)color);
  return NewAttrString(str, attrs);
}

NSMutableAttributedString* NewAttrString(
    const string& str, UIFont* font, UIColor* color) {
  const Dict attrs(NSFontAttributeName, font,
                   NSForegroundColorAttributeName, color);
  return NewAttrString(str, attrs);
}

NSMutableAttributedString* NewAttrString(const string& str, const Dict& attr_dict) {
  return [[NSMutableAttributedString alloc] initWithString:NewNSString(str)
                                                attributes:attr_dict];
}

NSMutableAttributedString* AttrCenterAlignment(NSMutableAttributedString* s) {
  CTTextAlignment alignment = kCTCenterTextAlignment;
  CTParagraphStyleSetting settings[] = {
    { kCTParagraphStyleSpecifierAlignment, sizeof(alignment), &alignment },
  };
  ScopedRef<CTParagraphStyleRef> paragraph(
      CTParagraphStyleCreate(settings, ARRAYSIZE(settings)));
  [s addAttribute:(__bridge NSString*)kCTParagraphStyleAttributeName
            value:(__bridge id)paragraph.get()
            range:NSMakeRange(0, s.length)];
  return s;
}

NSMutableAttributedString* AttrTruncateHead(NSMutableAttributedString* s) {
  return AttrLineBreak(s, kCTLineBreakByTruncatingHead);
}

NSMutableAttributedString* AttrTruncateMiddle(NSMutableAttributedString* s) {
  return AttrLineBreak(s, kCTLineBreakByTruncatingMiddle);
}

NSMutableAttributedString* AttrTruncateTail(NSMutableAttributedString* s) {
  return AttrLineBreak(s, kCTLineBreakByTruncatingTail);
}

NSMutableAttributedString* AttrForegroundColor(
    NSMutableAttributedString* s, CGColorRef color) {
  [s addAttribute:(__bridge NSString*)kCTForegroundColorAttributeName
            value:(__bridge id)color
            range:NSMakeRange(0, s.length)];
  return s;
}

NSMutableAttributedString* AttrUIForegroundColor(
    NSMutableAttributedString* s, UIColor* color) {
  [s addAttribute:NSForegroundColorAttributeName
            value:color
            range:NSMakeRange(0, s.length)];
  return s;
}

NSMutableAttributedString* AttrBlendForegroundColor(
    NSMutableAttributedString* s, CGColorRef color, float blend_ratio) {
  // PERFORMANCE NOTE: In case this shows up in profiler, it might be worth
  // looking into mutating the string while enumerating over its properties
  // instead.

  // Creates a new attributed string from the original with all foreground
  // colors replaced by a blended combination of existing foreground color
  // and "color", weighted by "blend_ratio".
  NSMutableAttributedString* blended_str = [NSMutableAttributedString new];
  for (int i = 0; i < s.length; ) {
    NSRange range;
    CGColorRef orig_color = (__bridge CGColorRef)
        [s attribute:(NSString*)kCTForegroundColorAttributeName atIndex:i effectiveRange:&range];
    NSAttributedString* substr = [s attributedSubstringFromRange:range];
    NSMutableAttributedString* new_str = [[NSMutableAttributedString alloc]
                                             initWithAttributedString:substr];
    CGColorRef blended_color =
        MakeUIColor(Blend(Vector4f(orig_color), Vector4f(color), blend_ratio)).CGColor;
    [new_str addAttribute:(NSString*)kCTForegroundColorAttributeName
                    value:(__bridge id)blended_color
                    range:NSMakeRange(0, range.length)];
    [blended_str appendAttributedString:new_str];
    i += range.length;
  }
  return blended_str;
}

NSMutableAttributedString* AttrKern(
    NSMutableAttributedString* s, float value) {
  [s addAttribute:(__bridge NSString*)kCTKernAttributeName
            value:[NSNumber numberWithFloat:value]
            range:NSMakeRange(0, s.length)];
  return s;
}

NSMutableAttributedString* AttrUIKern(
    NSMutableAttributedString* s, float value) {
  [s addAttribute:NSKernAttributeName
            value:[NSNumber numberWithFloat:value]
            range:NSMakeRange(0, s.length)];
  return s;
}

void AppendAttrString(NSMutableAttributedString* attr_str,
                      const string& str, CTFontRef font, CGColorRef color) {
  [attr_str appendAttributedString:NewAttrString(str, font, color)];
}

void AppendAttrString(NSMutableAttributedString* attr_str,
                      const string& str, UIFont* font, UIColor* color) {
  [attr_str appendAttributedString:NewAttrString(str, font, color)];
}

void AppendAttrString(NSMutableAttributedString* attr_str,
                      const string& str, const Dict& attrs) {
  [attr_str appendAttributedString:
              [[NSMutableAttributedString alloc]
                initWithString:NewNSString(str) attributes:attrs]];
}

void AppendAttrString(NSMutableAttributedString* attr_str,
                      NSString* str, const Dict& attrs) {
  [attr_str appendAttributedString:
              [[NSMutableAttributedString alloc]
                initWithString:str attributes:attrs]];
}

void AttrStringMetrics(NSAttributedString* attr_str,
                       float* ascent, float* descent, float* leading) {
  if (!ascent && !descent && !leading) {
    return;
  }
  float dummy;
  if (!ascent) ascent = &dummy;
  if (!descent) descent = &dummy;
  if (!leading) leading = &dummy;

  ScopedRef<CTLineRef> line(
      CTLineCreateWithAttributedString(
          (__bridge CFAttributedStringRef)attr_str));
  if (!line.get()) {
    *ascent = 0;
    *descent = 0;
    *leading = 0;
    return;
  }
  CTLineGetTypographicBounds(line, ascent, descent, leading);
}

CGSize AttrStringSize(NSAttributedString* attr_str, const CGSize& constraint) {
  ScopedRef<CTFramesetterRef> framesetter(
      CTFramesetterCreateWithAttributedString(
          (__bridge CFAttributedStringRef)attr_str));
  if (!framesetter.get()) {
    return CGSizeZero;
  }

  CFRange fit_range;
  const CGSize suggested_size = CTFramesetterSuggestFrameSizeWithConstraints(
      framesetter, CFRangeMake(0, 0), NULL, constraint, &fit_range);
  // Round the width and height up to the next integer. On iOS 5, failure to do
  // this causes strings to display the truncation ellipses incorrectly.
  return CGSizeMake(ceil(suggested_size.width), ceil(suggested_size.height));
}

void ApplySearchFilter(RE2* search_filter,
                       const string& str,
                       NSMutableAttributedString* attr_str,
                       const Dict& bold_attrs) {
  Slice s(str);
  Slice p;
  while (RE2::FindAndConsume(&s, *search_filter, &p)) {
    // NSMutableAttributedString expects the range to correspond to character
    // positions, not byte positions. So use the match to determine what
    // character position to start at and how many characters the match is.
    // TODO(ben): this is incorrect; it should be utf16 codepoints.
    const int pos = utfnlen(str.data(), p.data() - str.data());
    const int len = utfnlen(p);
    CHECK_LT(pos, attr_str.length);
    CHECK_LE(pos + len, attr_str.length);
    [attr_str addAttributes:bold_attrs
                      range:NSMakeRange(pos, len)];
  }
}
