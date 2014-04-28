// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "OutlinedLabel.h"

@implementation OutlinedLabel

- (void)drawTextInRect:(CGRect)rect {
  UIColor* text_color = self.textColor;
  UIColor* shadow_color = self.shadowColor;

  CGContextRef c = UIGraphicsGetCurrentContext();
  CGContextSetLineWidth(c, 1);
  CGContextSetLineJoin(c, kCGLineJoinRound);

  CGContextSetTextDrawingMode(c, kCGTextStroke);
  self.shadowColor = nil;
  self.textColor = shadow_color;
  [super drawTextInRect:rect];

  CGContextSetTextDrawingMode(c, kCGTextFill);
  self.textColor = text_color;
  [super drawTextInRect:rect];

  self.shadowColor = shadow_color;

}
@end  // OutlinedLabel
