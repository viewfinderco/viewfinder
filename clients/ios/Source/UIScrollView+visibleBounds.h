// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <UIKit/UIScrollView.h>

// Adds a "visibleBounds" property to UIScrollView.  By default it is identical to the regular bounds,
// but in e.g. ConversationScrollView it excludes the area under the keyboard.
@interface UIScrollView (visibleBounds)

- (CGRect)visibleBounds;

@end  // UIScrollView (visibleBounds)
