// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <CoreText/CTFont.h>
#import <QuartzCore/CAAnimation.h>
#import <UIKit/UIKit.h>
#import "FontSymbols.h"
#import "ValueUtils.h"
#import "Vector.h"

bool ParseRgbColor(const Slice& s, Vector4f* c);
Vector4f ParseStaticRgbColor(const Slice& s);

class LazyStaticInit {
 public:
  template <typename T>
  static void Once(dispatch_once_t* once, T* obj) {
    typedef void (*function_t)(void*);
    dispatch_once_f(once,
                    reinterpret_cast<void*>(obj),
                    reinterpret_cast<function_t>(&T::Init));
  }
};

class LazyStaticHexColor {
  friend class LazyStaticInit;

 public:
  const char* hex_;
  UIColor* color_;
  Vector4f rgba_;
  dispatch_once_t once_;

 public:
  operator CGColorRef() { return [get() CGColor]; }
  operator UIColor*() { return get(); }
  UIColor* get();
  operator const Vector4f&() { return rgba(); }
  const Vector4f& rgba() { get(); return rgba_; }

 private:
  static void Init(LazyStaticHexColor* x);
};

class LazyStaticRgbColor {
  friend class LazyStaticInit;

 public:
  Vector4f rgba_;
  UIColor* color_;
  dispatch_once_t once_;

 public:
  operator CGColorRef() { return [get() CGColor]; }
  operator UIColor*() { return get(); }
  UIColor* get();
  operator const Vector4f&() { return rgba_; }
  const Vector4f& rgba() const { return rgba_; }

 private:
  static void Init(LazyStaticRgbColor* x);
};

class LazyStaticHsbColor {
  friend class LazyStaticInit;

 public:
  Vector4f hsba_;
  UIColor* color_;
  dispatch_once_t once_;

 public:
  operator CGColorRef() { return [get() CGColor]; }
  operator UIColor*() { return get(); }
  UIColor* get();
  operator const Vector4f&() { return hsba_; }
  const Vector4f& hsba() const { return hsba_; }

 private:
  static void Init(LazyStaticHsbColor* x);
};

class LazyStaticUIFont {
  friend class LazyStaticInit;

 public:
  NSString* name_;
  float size_;
  UIFont* font_;
  dispatch_once_t once_;

 public:
  operator UIFont*() { return get(); }
  UIFont* get();

 private:
  static void Init(LazyStaticUIFont* x);
};

class LazyStaticCTFont {
  friend class LazyStaticInit;

 public:
  NSString* name_;
  float size_;
  float height_;
  CTFontRef font_;
  dispatch_once_t once_;

 public:
  operator CTFontRef() { return get(); }
  CTFontRef get();
  float height() { get(); return height_; }

 private:
  static void Init(LazyStaticCTFont* x);
};

class LazyStaticImage {
  friend class LazyStaticInit;

 public:
  explicit LazyStaticImage(NSString* name, UIEdgeInsets insets = UIEdgeInsetsZero);

  NSString* name_;
  UIEdgeInsets insets_;
  UIImage* image_;
  dispatch_once_t once_;

 public:
  operator UIImage*() { return get(); }

  UIImage* get();

 private:
  static void Init(LazyStaticImage* x);
};

class LazyStaticGeneratedImage {
  friend class LazyStaticInit;

 public:
  UIImage* (^generator_)();
  UIImage* image_;
  dispatch_once_t once_;

 public:
  operator UIImage*() { return get(); }

  UIImage* get();

 private:
  static void Init(LazyStaticGeneratedImage* x);
};

class LazyStaticAttributedString {
  friend class LazyStaticInit;

 public:
  NSAttributedString* (^generator_)();
  NSAttributedString* str_;
  dispatch_once_t once_;

 public:
  operator NSAttributedString*() { return get(); }

  NSAttributedString* get();

 private:
  static void Init(LazyStaticAttributedString* x);
};

class LazyStaticDict {
  friend class LazyStaticInit;

 public:
  Dict (^generator_)();
  Dict dict_;
  dispatch_once_t once_;

 public:
  operator NSDictionary*() { return get(); }
  operator const Dict&() { return get(); }

  const Dict& get();

 private:
  static void Init(LazyStaticDict* x);
};

extern NSString* const kHelvetica;
extern NSString* const kHelveticaBold;
extern NSString* const kHelveticaMedium;
extern NSString* const kDIN;
extern NSString* const kProximaNovaBold;
extern NSString* const kProximaNovaRegular;
extern NSString* const kProximaNovaRegularItalic;
extern NSString* const kProximaNovaSemibold;

extern LazyStaticRgbColor kTranslucentBackgroundColor;
extern LazyStaticRgbColor kTranslucentHighlightedColor;
extern LazyStaticRgbColor kTranslucentBorderColor;
extern LazyStaticUIFont kTranslucentFont;
extern const float kTranslucentBorderWidth;
extern const UIEdgeInsets kTranslucentInsets;

extern LazyStaticUIFont& kCameraMessageFont;

void InitAppearanceConstants();
void InitTranslucentLayer(CALayer* layer);
UIColor* MakeUIColor(float r, float g, float b, float a);
UIColor* MakeUIColorHSB(float h, float s, float b, float a);
UIColor* MakeUIColor(const Vector4f& rgba);
UIColor* MakeUIColorHSB(const Vector4f& hsba);
UIImage* MakeSolidColorImage(const UIColor* color);

// Make a point/rect that allows on "integral" boundaries. Note that integral
// refers to pixels, not points. On retina displays, pixel boundaries occur
// every 0.5 points.
CGPoint MakeIntegralPoint(float x, float y);
inline CGPoint MakeIntegralPoint(const CGPoint& p) {
  return MakeIntegralPoint(p.x, p.y);
}
CGRect MakeIntegralRect(float x, float y, float w, float h);
inline CGRect MakeIntegralRect(const CGRect& f) {
  return MakeIntegralRect(f.origin.x, f.origin.y, f.size.width, f.size.height);
}

CAKeyframeAnimation* NewWiggleAnimation();
CAKeyframeAnimation* NewFloatingAnimation(CGPoint p);

// local variables:
// mode: objc
// end:
