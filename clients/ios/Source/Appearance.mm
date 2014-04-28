// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "FileUtils.h"
#import "Logging.h"
#import "PathUtils.h"
#import "StringUtils.h"

namespace {

float kScreenScale = 1;

#if TARGET_IPHONE_SIMULATOR
  // #define GENERATE_1X_ASSETS
#endif  // TARGET_IPHONE_SIMULATOR

#ifdef GENERATE_1X_ASSETS

void Init1XImage(NSString* name, const UIEdgeInsets& insets) {
  if ([UIScreen mainScreen].scale != 2) {
    return;
  }
  // Init1XImage gets called from a global constructor. Dispatch to main in
  // order to have the 1X image's built after other initialization is
  // performed.
  dispatch_after_main(1, ^{
      // Load the image and apply the cap insets.
      UIImage* image = [UIImage imageNamed:name];
      if (!UIEdgeInsetsEqualToEdgeInsets(insets, UIEdgeInsetsZero)) {
        image = [image resizableImageWithCapInsets:insets];
      }
      // The image might have a fractional size due to it being an @2x image with
      // an odd dimension and cap insets specified. Round up to the next integer
      // width and height.
      const CGSize size = { ceil(image.size.width), ceil(image.size.height) };
      UIGraphicsBeginImageContextWithOptions(size, NO, 1);
      [image drawInRect:CGRectMake(0, 0, size.width, size.height)];
      UIImage* new_image = UIGraphicsGetImageFromCurrentImageContext();
      LOG("wrote image %s to file: %s", name, JoinPath(TmpDir(), ToSlice(name)));
      NSData* data;
      if (ToSlice(name).ends_with(".png")) {
        data = UIImagePNGRepresentation(new_image);
      } else {
        data = UIImageJPEGRepresentation(new_image, 0.7);
      }
      WriteDataToFile(JoinPath(TmpDir(), ToSlice(name)), data);
      UIGraphicsEndImageContext();
    });
}

#else  // !GENERATE_1X_ASSETS

void Init1XImage(NSString* name, const UIEdgeInsets& insets) {
}

#endif  // !GENERATE_1X_ASSETS

}  // namespace

NSString* const kHelvetica = @"HelveticaNeue";
NSString* const kHelveticaBold = @"HelveticaNeue-Bold";
NSString* const kHelveticaMedium = @"HelveticaNeue-Medium";
NSString* const kDIN = @"DINMittelschriftLT-Alternate";
NSString* const kProximaNovaBold = @"ProximaNova-Bold";
NSString* const kProximaNovaRegular = @"ProximaNova-Regular";
NSString* const kProximaNovaRegularItalic = @"ProximaNova-RegularIt";
NSString* const kProximaNovaSemibold = @"ProximaNova-Semibold";

LazyStaticRgbColor kTranslucentBackgroundColor = { Vector4f(1, 1, 1, 0.5) };
LazyStaticRgbColor kTranslucentHighlightedColor = { Vector4f(1, 1, 1, 0.8) };
LazyStaticRgbColor kTranslucentBorderColor = { Vector4f(0, 0, 0, 0.5) };
LazyStaticUIFont kTranslucentFont = { kHelveticaBold, 14 };
const float kTranslucentBorderWidth = 1;
const UIEdgeInsets kTranslucentInsets = UIEdgeInsetsMake(8, 12, 8, 12);

LazyStaticUIFont& kCameraMessageFont = kTranslucentFont;

UIColor* LazyStaticHexColor::get() {
  LazyStaticInit::Once(&once_, this);
  return color_;
}

void LazyStaticHexColor::Init(LazyStaticHexColor* x) {
  CHECK(ParseRgbColor(x->hex_, &x->rgba_));
  x->color_ = MakeUIColor(x->rgba_);
}

UIColor* LazyStaticRgbColor::get() {
  LazyStaticInit::Once(&once_, this);
  return color_;
}

void LazyStaticRgbColor::Init(LazyStaticRgbColor* x) {
  x->color_ = MakeUIColor(x->rgba_(0), x->rgba_(1), x->rgba_(2), x->rgba_(3));
}

UIColor* LazyStaticHsbColor::get() {
  LazyStaticInit::Once(&once_, this);
  return color_;
}

void LazyStaticHsbColor::Init(LazyStaticHsbColor* x) {
  x->color_ = MakeUIColorHSB(x->hsba_(0), x->hsba_(1), x->hsba_(2), x->hsba_(3));
}

UIFont* LazyStaticUIFont::get() {
  LazyStaticInit::Once(&once_, this);
  return font_;
}

void LazyStaticUIFont::Init(LazyStaticUIFont* x) {
  x->font_ = [UIFont fontWithName:x->name_ size:x->size_];
}

CTFontRef LazyStaticCTFont::get() {
  LazyStaticInit::Once(&once_, this);
  return font_;
}

void LazyStaticCTFont::Init(LazyStaticCTFont* x) {
  x->font_ = CTFontCreateWithName(
      (__bridge CFStringRef)x->name_,
      x->size_, NULL);
  x->height_ = CTFontGetAscent(x->font_) +
      CTFontGetDescent(x->font_) +
      CTFontGetLeading(x->font_);
}

LazyStaticImage::LazyStaticImage(NSString* name, UIEdgeInsets insets)
    : name_(name),
      insets_(insets),
      image_(NULL),
      once_(0) {
  Init1XImage(name_, insets_);
}

UIImage* LazyStaticImage::get() {
  LazyStaticInit::Once(&once_, this);
  return image_;
}

void LazyStaticImage::Init(LazyStaticImage* x) {
  x->image_ = [UIImage imageNamed:x->name_];
  DCHECK(x->image_ != NULL);
  if (!UIEdgeInsetsEqualToEdgeInsets(x->insets_, UIEdgeInsetsZero)) {
    x->image_ = [x->image_ resizableImageWithCapInsets:x->insets_];
  }
  Init1XImage(x->name_, x->insets_);
}

UIImage* LazyStaticGeneratedImage::get() {
  LazyStaticInit::Once(&once_, this);
  return image_;
}

void LazyStaticGeneratedImage::Init(LazyStaticGeneratedImage* x) {
  x->image_ = x->generator_();
  x->generator_ = NULL;
}

NSAttributedString* LazyStaticAttributedString::get() {
  LazyStaticInit::Once(&once_, this);
  return str_;
}

void LazyStaticAttributedString::Init(LazyStaticAttributedString* x) {
  x->str_ = x->generator_();
  x->generator_ = NULL;
}

const Dict& LazyStaticDict::get() {
  LazyStaticInit::Once(&once_, this);
  return dict_;
}

void LazyStaticDict::Init(LazyStaticDict* x) {
  x->dict_ = x->generator_();
  x->generator_ = NULL;
}


void InitAppearanceConstants() {
  kScreenScale = [UIScreen mainScreen].scale;
}

void InitTranslucentLayer(CALayer* layer) {
  layer.borderWidth = 1;
  layer.borderColor =
      [[UIColor colorWithWhite:0.0 alpha:0.5] CGColor];
  layer.cornerRadius = layer.frame.size.height / 2;
  layer.masksToBounds = YES;
}

UIColor* MakeUIColor(float r, float g, float b, float a) {
  return [UIColor colorWithRed:r green:g blue:b alpha:a];
}

UIColor* MakeUIColorHSB(float h, float s, float b, float a) {
  return [UIColor colorWithHue:h saturation:s brightness:b alpha:a];
}

UIColor* MakeUIColor(const Vector4f& rgba) {
  return [UIColor colorWithRed:rgba(0) green:rgba(1) blue:rgba(2) alpha:rgba(3)];
}

UIColor* MakeUIColorHSB(const Vector4f& hsba) {
  return [UIColor colorWithHue:hsba(0) saturation:hsba(1) brightness:hsba(2) alpha:hsba(3)];
}

UIImage* MakeSolidColorImage(const UIColor* color) {
  UIGraphicsBeginImageContextWithOptions(CGSizeMake(1, 1), NO, 1);
  CGContextRef context = UIGraphicsGetCurrentContext();
  CGContextSetFillColorWithColor(context, color.CGColor);
  CGContextFillRect(context, CGRectMake(0, 0, 1, 1));
  UIImage* image = UIGraphicsGetImageFromCurrentImageContext();
  UIGraphicsEndImageContext();
  return image;
}

CGPoint MakeIntegralPoint(float x, float y) {
  return CGPointMake(floorf(x * kScreenScale) / kScreenScale,
                     floorf(y * kScreenScale) / kScreenScale);
}

CGRect MakeIntegralRect(float x, float y, float w, float h) {
  return CGRectMake(floorf(x * kScreenScale) / kScreenScale,
                    floorf(y * kScreenScale) / kScreenScale,
                    ceilf(w * kScreenScale) / kScreenScale,
                    ceilf(h * kScreenScale) / kScreenScale);
}

CAKeyframeAnimation* NewWiggleAnimation() {
  CAKeyframeAnimation* a = [CAKeyframeAnimation animationWithKeyPath:@"transform"];
  a.autoreverses = YES;
  a.duration = 0.07;
  a.repeatCount = 2.0;
  a.values = Array(
      CATransform3DMakeTranslation(-5, 0, 0),
      CATransform3DMakeTranslation(5, 0, 0));
  return a;
}

CAKeyframeAnimation* NewFloatingAnimation(CGPoint p) {
  CAKeyframeAnimation* a = [CAKeyframeAnimation animationWithKeyPath:@"position.y"];

  CGMutablePathRef path = CGPathCreateMutable();
  CGPathAddArc(path, NULL, p.y, 0, 1, 0, kPi, YES);

  a.autoreverses = YES;
  a.duration = 1;
  a.repeatCount = HUGE_VALF;
  a.timeOffset = WallTime_Now();
  a.path = path;

  return a;
}

bool ParseRgbColor(const Slice& s, Vector4f* c) {
  if (s.empty()) {
    *c = Vector4f(0, 0, 0, 0);
    return false;
  }

  if (s[0] == '#') {
    char* end = const_cast<char*>(s.data() + s.size());
    const uint32_t v = strtoul(s.data() + 1, &end, 16);

    if (s.size() == 4) {
      // #rgb
      *c = Vector4f(
          (((v & 0xf00) >> 8) | ((v & 0xf00) >> 4)),
          (((v & 0xf0) >> 4) | ((v & 0xf0) << 0)),
          (((v & 0xf) >> 0) | ((v & 0xf) << 4)),
          255.0) / 255.0;
      return true;
    }

    if (s.size() == 5) {
      // #rgba
      *c = Vector4f(
          (((v & 0xf000) >> 12) | ((v & 0xf000) >> 8)),
          (((v & 0xf00) >> 8) | ((v & 0xf00) >> 4)),
          (((v & 0xf0) >> 4) | ((v & 0xf0) << 0)),
          (((v & 0xf) >> 0) | ((v & 0xf) << 4))) / 255.0;
      return true;
    }

    if (s.size() == 7) {
      // #rrggbb
      *c = Vector4f(
          ((v & 0xff0000) >> 16),
          ((v & 0x00ff00) >> 8),
          ((v & 0x0000ff) >> 0),
          255.0) / 255.0;
      return true;
    }

    if (s.size() == 9) {
      // #rrggbbaa
      *c = Vector4f(
          ((v & 0xff000000) >> 24),
          ((v & 0x00ff0000) >> 16),
          ((v & 0x0000ff00) >> 8),
          ((v & 0x000000ff) >> 0)) / 255.0;
      return true;
    }

    *c = Vector4f(0, 0, 0, 0);
    return false;
 }

  // TODO(peter): Add support, if needed, for other color specifications, such
  // as rgb(...), rgba(...), hsl(...), etc.
  *c = Vector4f(0, 0, 0, 0);
  return false;
}

Vector4f ParseStaticRgbColor(const Slice& s) {
  Vector4f c;
  CHECK(ParseRgbColor(s, &c));
  return c;
}
