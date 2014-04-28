// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_LINKIFIER_H
#define VIEWFINDER_LINKIFIER_H

#import <Foundation/Foundation.h>
#import "ValueUtils.h"

// Finds links in the specified string
NSArray* FindLinks(NSString* str, const NSRange& range);
// Apply the specified attributes to the ranges of the string specified by
// matches.
void ApplyLinkAttributes(NSMutableAttributedString* attr_str,
                         NSArray* matches, const Dict& attributes);

#endif  // VIEWFINDER_LINKIFIER_H

// local variables:
// mode: objc
// end:
