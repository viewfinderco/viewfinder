// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// Utility functions for creating attributed strings and setting common attributes.
//
// IMPORTANT: There are two sets of string attributes, one used by CoreText (including our TextLayer),
// and one used by UIKit (e.g. UILabel.attributedText).  The functions in this file mostly use
// the CoreText attributes and so are not suitable for use with UIKit.

#ifndef VIEWFINDER_ATTR_STRING_UTILS_H
#define VIEWFINDER_ATTR_STRING_UTILS_H

#import <CoreText/CoreText.h>
#import <Foundation/Foundation.h>
#import <re2/re2.h>
#import "Utils.h"
#import "ValueUtils.h"

// Create a new mutable attributed string.  CoreText only.
NSMutableAttributedString* NewAttrString(
    const string& str, CTFontRef font, CGColorRef color);

// Create a new mutable attributed string.  UIKit only.
NSMutableAttributedString* NewAttrString(
    const string& str, UIFont* font, UIColor* color);

// Create an attributed string from an attributes dictionary (as found in UIStyle).
NSMutableAttributedString* NewAttrString(const string& str, const Dict& attr_dict);

// Add center alignment attribute to the full range of an existing attributed
// string.  CoreText only.
NSMutableAttributedString* AttrCenterAlignment(NSMutableAttributedString* s);

// Add a head truncation attribute to the full range of an existing attributed
// string.  CoreText only.
NSMutableAttributedString* AttrTruncateHead(NSMutableAttributedString* s);

// Add a middle truncation attribute to the full range of an existing
// attributed string.  CoreText only.
NSMutableAttributedString* AttrTruncateMiddle(NSMutableAttributedString* s);

// Add a tail truncation attribute to the full range of an existing attributed
// string.  CoreText only.
NSMutableAttributedString* AttrTruncateTail(NSMutableAttributedString* s);

// Adds a foreground color attribute to the full range of an existing
// attributed string.  CoreText only.
NSMutableAttributedString* AttrForegroundColor(
    NSMutableAttributedString* s, CGColorRef color);

// Adds a (UI) foreground color attribute to the full range of an existing
// attributed string. For use with attributed strings that will be displayed in
// UIViews, such as in the title of a UIButton.
NSMutableAttributedString* AttrUIForegroundColor(
    NSMutableAttributedString* s, UIColor* color);

// Blends any existing foreground color attribute with "color" based on the
// specified blend ratio.  CoreText only.
NSMutableAttributedString* AttrBlendForegroundColor(
    NSMutableAttributedString* s, CGColorRef color, float blend_ratio);

// Sets the inter-letter kerning (spacing) for the string.
NSMutableAttributedString* AttrKern(
    NSMutableAttributedString* s, float value);

// Sets the inter-letter kerning for UIKit.
NSMutableAttributedString* AttrUIKern(
    NSMutableAttributedString* s, float value);

// Append to an existing attributed string.  CoreText only.
void AppendAttrString(NSMutableAttributedString* attr_str,
                      const string& str, CTFontRef font, CGColorRef color);

// Append to an existing attributed string.  UIKit only.
void AppendAttrString(NSMutableAttributedString* attr_str,
                      const string& str, UIFont* font, UIColor* color);

// Append to an existing attributed string.
void AppendAttrString(NSMutableAttributedString* attr_str,
                      const string& str, const Dict& attrs);

void AppendAttrString(NSMutableAttributedString* attr_str,
                      NSString* str, const Dict& attrs);

// Returns the line metrics for the specified attributed string.  CoreText only.
void AttrStringMetrics(NSAttributedString* attr_str,
                       float* ascent, float* descent, float* leading);

// Return the frame size for the specified attributed string given a
// constraint.
CGSize AttrStringSize(NSAttributedString* attr_str, const CGSize& constraint);

// Applies 'bold_attrs' to the portions of 'attr_str' matching 'search_filter'.
// 'str' and 'attr_str' must have the same contents.
void ApplySearchFilter(RE2* search_filter, const string& str, NSMutableAttributedString* attr_str,
                       const Dict& bold_attrs);

#endif  // VIEWFINDER_ATTR_STRING_UTILS_H
