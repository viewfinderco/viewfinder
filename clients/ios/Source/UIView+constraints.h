// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

// Objective-C++ wrappers around iOS 6 constraint-based layout.
//
// General usage: Make a constraint by comparing anchor attributes of two views,
// then pass the result to the addConstraints: method of their common superview.
// [self addConstraints:label_.anchorRight == field_.anchorLeft];
// [self addConstraints:field_.anchorWidth >= 120];
//
// Equality constraints can be chained:
// [self addConstraints:label_.anchorBaseline == field_.anchorBaseline == button_.anchorBaseline];
//
// Simple arithmetic (multiplication and additon/subtraction) is allowed on the right hand side only:
// [self addConstraints:a.anchorLeft == b.anchorRight + 8];
// [self addConstraints:view.anchorHeight == view.anchorWidth * 2];
//
// For a sequence of end-to-end constraints, use the sequence interfaces TopToBottom and LeftToRight:
// [self addConstraints:LeftToRight(self.anchorLeft, kMargin, label_, kMargin, field_, self.anchorRight)];
//
// The sequence interfaces accept arbitrary anchors (normally used only at the beginning or end of a sequence),
// views, and numbers (for spacing).
//
// Note that when using constraints, you should set translatesAutoresizingMaskIntoConstraints = NO on the
// affected views.

#import <vector>
#import <UIKit/UIView.h>

class EqualityConstraint;
class RelationConstraint;

class ConstraintAttribute {
  friend class ConstraintSequence;
  friend class EqualityConstraint;
  friend class RelationConstraint;

 public:
  ConstraintAttribute(UIView* view, NSLayoutAttribute attribute);

  // Implicit constructor.
  ConstraintAttribute(float constant);

  EqualityConstraint operator==(const ConstraintAttribute& other) const;
  RelationConstraint operator<=(const ConstraintAttribute& other) const;
  RelationConstraint operator>=(const ConstraintAttribute& other) const;

  ConstraintAttribute operator*(float multiplier) const;
  ConstraintAttribute operator+(float constant) const;
  ConstraintAttribute operator-(float constant) const;

 private:
  UIView* view_;
  NSLayoutAttribute attribute_;
  float multiplier_;
  float constant_;
};

class RelationConstraint {
 public:
  RelationConstraint(const ConstraintAttribute& attr1, const ConstraintAttribute& attr2, NSLayoutRelation relation);

  operator NSArray*() const;

 private:
  ConstraintAttribute attr1_;
  ConstraintAttribute attr2_;
  NSLayoutRelation relation_;
};

class EqualityConstraint {
 public:
  explicit EqualityConstraint(const ConstraintAttribute& attr);

  void AddAttribute(const ConstraintAttribute& attr);

  EqualityConstraint operator==(const ConstraintAttribute& other) const;

  operator NSArray*() const;

 private:
  ConstraintAttribute base_attr_;
  std::vector<ConstraintAttribute> attrs_;
};

class ConstraintSequence {
 public:
  enum ArgType {
    VIEW,
    CONSTANT,
    ATTRIBUTE,
  };
  struct Arg {
    Arg(UIView* v)
        : type(VIEW),
          view(v),
          constant(0),
          attribute(0) {
    }
    Arg(float c)
        : type(CONSTANT),
          view(NULL),
          constant(c),
          attribute(0) {
    }
    Arg(ConstraintAttribute a)
        : type(ATTRIBUTE),
          view(NULL),
          constant(0),
          attribute(a) {
    }

    const ArgType type;
    const UIView* view;
    const float constant;
    const ConstraintAttribute attribute;
  };

  ConstraintSequence(NSLayoutAttribute leading_attr, NSLayoutAttribute trailing_attr, std::initializer_list<Arg> args);
  virtual ~ConstraintSequence();

  operator NSArray*() const;

 private:
  void AddConstraint(const ConstraintAttribute& attr1, const ConstraintAttribute& attr2);

  NSMutableArray* constraints_;
};

template<typename... Args> ConstraintSequence TopToBottom(Args... args) {
  return ConstraintSequence(NSLayoutAttributeTop, NSLayoutAttributeBottom, {args...});
}

template<typename... Args> ConstraintSequence LeftToRight(Args... args) {
  return ConstraintSequence(NSLayoutAttributeLeft, NSLayoutAttributeRight, {args...});
}

// i18n-aware horizontal layout: left-to-right or right-to-left depending on the current locale's writing direction.
template<typename... Args> ConstraintSequence LeadingToTrailing(Args... args) {
  return ConstraintSequence(NSLayoutAttributeLeading, NSLayoutAttributeTrailing, {args...});
}


@interface UIView (objcpp_constraints)

- (ConstraintAttribute)anchorLeft;
- (ConstraintAttribute)anchorRight;
- (ConstraintAttribute)anchorTop;
- (ConstraintAttribute)anchorBottom;
- (ConstraintAttribute)anchorLeading;
- (ConstraintAttribute)anchorTrailing;
- (ConstraintAttribute)anchorWidth;
- (ConstraintAttribute)anchorHeight;
- (ConstraintAttribute)anchorCenterX;
- (ConstraintAttribute)anchorCenterY;
- (ConstraintAttribute)anchorBaseline;

@end  // UIView (objcpp_constraints)
