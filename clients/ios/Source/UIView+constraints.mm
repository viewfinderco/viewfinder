// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import "Logging.h"
#import "UIView+constraints.h"

ConstraintAttribute::ConstraintAttribute(UIView* view, NSLayoutAttribute attribute)
    : view_(view),
      attribute_(attribute),
      multiplier_(1),
      constant_(0) {
}

ConstraintAttribute::ConstraintAttribute(float constant)
    : view_(NULL),
      attribute_(NSLayoutAttributeNotAnAttribute),
      multiplier_(1),
      constant_(constant) {
}

EqualityConstraint ConstraintAttribute::operator==(const ConstraintAttribute& other) const {
  EqualityConstraint constraint(*this);
  constraint.AddAttribute(other);
  return constraint;
}

RelationConstraint ConstraintAttribute::operator<=(const ConstraintAttribute& other) const {
  return RelationConstraint(*this, other, NSLayoutRelationLessThanOrEqual);
}

RelationConstraint ConstraintAttribute::operator>=(const ConstraintAttribute& other) const {
  return RelationConstraint(*this, other, NSLayoutRelationGreaterThanOrEqual);
}

ConstraintAttribute ConstraintAttribute::operator*(float multiplier) const {
  ConstraintAttribute new_attr = *this;
  new_attr.multiplier_ *= multiplier;
  return new_attr;
}

ConstraintAttribute ConstraintAttribute::operator+(float constant) const {
  ConstraintAttribute new_attr = *this;
  new_attr.constant_ += constant;
  return new_attr;
}

ConstraintAttribute ConstraintAttribute::operator-(float constant) const {
  return *this + (-constant);
}

RelationConstraint::RelationConstraint(const ConstraintAttribute& attr1,
                                       const ConstraintAttribute& attr2,
                                       NSLayoutRelation relation)
    : attr1_(attr1),
      attr2_(attr2),
      relation_(relation) {
    CHECK_EQ(attr1_.multiplier_, 1.0);
    CHECK_EQ(attr1_.constant_, 0.0);
}

RelationConstraint::operator NSArray*() const {
  NSLayoutConstraint* constraint =
      [NSLayoutConstraint constraintWithItem:attr1_.view_
                                   attribute:attr1_.attribute_
                                   relatedBy:relation_
                                      toItem:attr2_.view_
                                   attribute:attr2_.attribute_
                                  multiplier:attr2_.multiplier_
                                    constant:attr2_.constant_];

  return @[constraint];
}

EqualityConstraint::EqualityConstraint(const ConstraintAttribute& attr)
    : base_attr_(attr) {
  CHECK_EQ(base_attr_.multiplier_, 1.0);
  CHECK_EQ(base_attr_.constant_, 0.0);
}

void EqualityConstraint::AddAttribute(const ConstraintAttribute& attr) {
  attrs_.push_back(attr);
}

EqualityConstraint EqualityConstraint::operator==(const ConstraintAttribute& attr) const {
  EqualityConstraint copy(*this);
  copy.AddAttribute(attr);
  return copy;
}

EqualityConstraint::operator NSArray*() const {
  NSMutableArray* array = [NSMutableArray arrayWithCapacity:attrs_.size()];
  for (auto it : attrs_) {
    [array addObject:
             [NSLayoutConstraint constraintWithItem:base_attr_.view_
                                          attribute:base_attr_.attribute_
                                          relatedBy:NSLayoutRelationEqual
                                             toItem:it.view_
                                          attribute:it.attribute_
                                         multiplier:it.multiplier_
                                           constant:it.constant_]];
  }
  return array;
}

ConstraintSequence::ConstraintSequence(NSLayoutAttribute leading_attr, NSLayoutAttribute trailing_attr,
                                       std::initializer_list<Arg> args)
  : constraints_([NSMutableArray arrayWithCapacity:4]) {
  ConstraintAttribute anchor(0);
  for (auto it : args) {
    switch (it.type) {
      case VIEW:
        if (anchor.view_) {
          // initializer_list always adds const, so cast it away on the view.
          AddConstraint(ConstraintAttribute(const_cast<UIView*>(it.view), leading_attr), anchor);
        }
        anchor = ConstraintAttribute(const_cast<UIView*>(it.view), trailing_attr);
        break;

      case CONSTANT:
        anchor.constant_ = it.constant;
        break;

      case ATTRIBUTE:
        if (anchor.view_) {
          AddConstraint(it.attribute, anchor);
        }
        anchor = it.attribute;
        break;
    }
  }
}

ConstraintSequence::~ConstraintSequence() {
}

ConstraintSequence::operator NSArray*() const {
  return constraints_;
}

void ConstraintSequence::AddConstraint(const ConstraintAttribute& attr1, const ConstraintAttribute& attr2) {
  CHECK_EQ(attr1.multiplier_, 1.0);
  CHECK_EQ(attr1.constant_, 0.0);
  [constraints_ addObject:
                  [NSLayoutConstraint constraintWithItem:attr1.view_
                                               attribute:attr1.attribute_
                                               relatedBy:NSLayoutRelationEqual
                                                  toItem:attr2.view_
                                               attribute:attr2.attribute_
                                              multiplier:attr2.multiplier_
                                                constant:attr2.constant_]];
 }

@implementation UIView (objcpp_constraints)

- (ConstraintAttribute)anchorLeft {
  return ConstraintAttribute(self, NSLayoutAttributeLeft);
}

- (ConstraintAttribute)anchorRight {
  return ConstraintAttribute(self, NSLayoutAttributeRight);
}

- (ConstraintAttribute)anchorTop {
  return ConstraintAttribute(self, NSLayoutAttributeTop);
}

- (ConstraintAttribute)anchorBottom {
  return ConstraintAttribute(self, NSLayoutAttributeBottom);
}

- (ConstraintAttribute)anchorLeading {
  return ConstraintAttribute(self, NSLayoutAttributeLeading);
}

- (ConstraintAttribute)anchorTrailing {
  return ConstraintAttribute(self, NSLayoutAttributeTrailing);
}

- (ConstraintAttribute)anchorWidth {
  return ConstraintAttribute(self, NSLayoutAttributeWidth);
}

- (ConstraintAttribute)anchorHeight {
  return ConstraintAttribute(self, NSLayoutAttributeHeight);
}

- (ConstraintAttribute)anchorCenterX {
  return ConstraintAttribute(self, NSLayoutAttributeCenterX);
}

- (ConstraintAttribute)anchorCenterY {
  return ConstraintAttribute(self, NSLayoutAttributeCenterY);
}

- (ConstraintAttribute)anchorBaseline {
  return ConstraintAttribute(self, NSLayoutAttributeBaseline);
}


@end  // UIView (objcpp_constraints)
