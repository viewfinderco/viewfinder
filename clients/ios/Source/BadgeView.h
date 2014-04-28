// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

@interface BadgeView : UIImageView {
 @private
  UILabel* text_;
  CGPoint position_;
}

@property (nonatomic) NSString* text;
@property (nonatomic) CGPoint position;

- (id)initWithImage:(UIImage*)image
               font:(UIFont*)font
              color:(UIColor*)color;

@end  // BadgeView

// local variables:
// mode: objc
// end:
