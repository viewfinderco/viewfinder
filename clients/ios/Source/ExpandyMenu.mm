// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "ExpandyMenu.h"
#import "Logging.h"

@implementation ExpandyMenu

@synthesize labels = labels_;
@dynamic selectedItem;

- (id)initWithPoint:(CGPoint)point
              title:(UIView*)title
        buttonNames:(NSArray*)button_names {
  if ((self = [super initWithFrame:CGRectZero])) {
    title.backgroundColor = [UIColor clearColor];
    [self addSubview:title];
    title_ = title;

    UIFont* kFont = kTranslucentFont;
    title.frame = CGRectMake(
        kTranslucentInsets.left, kTranslucentInsets.top,
        title.frame.size.width * kFont.lineHeight / title.frame.size.height,
        kFont.lineHeight);
    self.frame = CGRectMake(
        point.x, point.y, 0,
        kFont.lineHeight + kTranslucentInsets.top + kTranslucentInsets.bottom);
    self.backgroundColor = [UIColor clearColor];

    NSMutableArray* labels =
        [[NSMutableArray alloc] initWithCapacity:button_names.count];
    int index = 0;
    for (NSString* button_name in button_names) {
      UILabel* label = [UILabel new];
      label.text = button_name;
      label.font = kFont;
      label.textColor = [UIColor blackColor];
      label.backgroundColor = [UIColor clearColor];
      label.textAlignment = NSTextAlignmentCenter;
      [label sizeToFit];
      [self addSubview:label];
      [labels addObject:label];
      index += 1;
    }
    labels_ = labels;

    NSMutableArray* dividers =
        [[NSMutableArray alloc] initWithCapacity:labels_.count - 1];
    for (int i = 1; i < labels_.count; ++i) {
      UILabel* label = [labels_ objectAtIndex:i];
      CALayer* divider = [CALayer layer];
      divider.opacity = 0;
      divider.backgroundColor = kTranslucentBorderColor;
      divider.frame = CGRectMake(
          0, 0, kTranslucentBorderWidth, self.frame.size.height);
      [label.layer addSublayer:divider];
      [dividers addObject:divider];
    }
    dividers_ = dividers;

    [self addTarget:self
             action:@selector(chooseLabel:forEvent:)
          forControlEvents:UIControlEventTouchUpInside];

    self.layer.backgroundColor = kTranslucentBackgroundColor;
    InitTranslucentLayer(self.layer);

    expanded_ = YES;
    [self setSelectedItem:0];
  }
  return self;
}

- (void)chooseLabel:(id)sender
           forEvent:(UIEvent*)event {
  if (!expanded_) {
    expanded_ = YES;

    [UIView animateWithDuration:0.15
                     animations:^{
        for (CALayer* divider in dividers_) {
          divider.opacity = 1;
        }
        int x = int(CGRectGetMaxX(title_.frame));
        for (UILabel* label in labels_) {
          CGSize size = [label sizeThatFits:label.frame.size];
          label.frame = CGRectMake(
              x, 0,
              size.width + kTranslucentInsets.left + kTranslucentInsets.right,
              self.frame.size.height);
          x += label.frame.size.width;
        }
        self.frame = CGRectMake(
            self.frame.origin.x, self.frame.origin.y,
            x, self.frame.size.height);
      }];
  } else {
    int index = selected_item_;
    for (int i = 0; i < labels_.count; ++i) {
      UILabel* label = [labels_ objectAtIndex:i];
      if ([label pointInside:[[[event allTouches] anyObject] locationInView:label]
                   withEvent:event]) {
        index = i;
        break;
      }
    }

    [UIView animateWithDuration:0.15
                     animations:^{
        for (CALayer* divider in dividers_) {
          divider.opacity = 0;
        }
        [self setSelectedItem:index];
      }];
  }
}

- (int)selectedItem {
  return selected_item_;
}

- (void)setSelectedItem:(int)selected_item {
  if (selected_item >= labels_.count) {
    // Invalid selection.
    return;
  }

  UILabel* selected_label = [labels_ objectAtIndex:selected_item];
  CGSize selected_size = [selected_label sizeThatFits:selected_label.frame.size];

  CGRect selected_frame = CGRectMake(
      int(CGRectGetMaxX(title_.frame)), 0,
      selected_size.width + kTranslucentInsets.left + kTranslucentInsets.right,
      self.frame.size.height);
  CGRect left_frame = CGRectMake(
      selected_frame.origin.x, 0, 0, self.frame.size.height);
  CGRect right_frame = CGRectMake(
      CGRectGetMaxX(selected_frame), 0, 0, self.frame.size.height);
  self.frame = CGRectMake(
      self.frame.origin.x, self.frame.origin.y,
      CGRectGetMaxX(selected_frame), self.frame.size.height);

  int index = 0;
  for (UILabel* label in labels_) {
    if (index < selected_item) {
      label.frame = left_frame;
    } else if (index > selected_item) {
      label.frame = right_frame;
    } else if (index == selected_item) {
      label.frame = selected_frame;
    }
    index += 1;
  }

  expanded_ = NO;

  if (selected_item_ != selected_item) {
    selected_item_ = selected_item;
    [self sendActionsForControlEvents:UIControlEventValueChanged];
  }
}

@end  // ExpandyMenu
