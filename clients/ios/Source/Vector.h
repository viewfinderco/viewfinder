// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_VECTOR_H
#define VIEWFINDER_VECTOR_H

#include <CoreGraphics/CGGeometry.h>
#include <CoreGraphics/CGColor.h>
#include <GLKit/GLKVector2.h>
#include <GLKit/GLKVector3.h>
#include <GLKit/GLKVector4.h>
#include "Logging.h"
#include "Utils.h"

const double kPi = 3.14159265358979323846;

template <typename DerivedT, typename VectorT, int N>
class VectorBase {
 public:
  enum {
    SIZE = N,
  };

  typedef float* iterator;
  typedef const float* const_iterator;

 public:
  explicit VectorBase(const VectorT& v)
      : v_(v) {
  }

  iterator data() { return &v_.v[0]; }
  const_iterator data() const { return &v_.v[0]; }
  iterator begin() { return &v_.v[0]; }
  const_iterator begin() const { return &v_.v[0]; }
  iterator end() { return &v_.v[N]; }
  const_iterator end() const { return &v_.v[N]; }

  VectorT& glk_vector() { return v_; }
  const VectorT& glk_vector() const { return v_; }

  float& operator()(int i) { return v_.v[i]; }
  const float& operator()(int i) const { return v_.v[i]; }

  static int size() { return SIZE; }

  DerivedT& fill(float val) {
    return (derived() = DerivedT(val));
  }
  DerivedT& zero() {
    return fill(0);
  }

  bool equal(const DerivedT& x,
             float threshold = std::numeric_limits<float>::epsilon() * 32) const {
    for (int i = 0; i < N; i++) {
      if (fabs(v_.v[i] - x.v_.v[i]) > threshold) {
        return false;
      }
    }
    return true;
  }

  // Assignment operators.
  DerivedT& operator+=(const VectorBase& x) {
    return (derived() = derived() + x.derived());
  }
  DerivedT& operator-=(const VectorBase& x) {
    return (derived() = derived() - x.derived());
  }
  DerivedT& operator*=(const VectorBase& x) {
    return (derived() = derived() * x.derived());
  }
  DerivedT& operator/=(const VectorBase& x) {
    return (derived() = derived() / x.derived());
  }
  DerivedT& operator+=(float val) {
    return (derived() = derived() + val);
  }
  DerivedT& operator-=(float val) {
    return (derived() = derived() - val);
  }
  DerivedT& operator*=(float val) {
    return (derived() = derived() * val);
  }
  DerivedT& operator/=(float val) {
    return (derived() = derived() / val);
  }

 private:
  DerivedT& derived() { return *static_cast<DerivedT*>(this); }
  const DerivedT& derived() const { return *static_cast<const DerivedT*>(this); }

 protected:
  VectorT v_;
};

class Vector2f : public VectorBase<Vector2f, GLKVector2, 2> {
  typedef VectorBase<Vector2f, GLKVector2, 2> VectorBaseT;

 public:
  explicit Vector2f(float v = 0)
      : VectorBaseT(GLKVector2Make(v, v)) {
  }
  explicit Vector2f(const float v[2])
      : VectorBaseT(GLKVector2Make(v[0], v[1])) {
  }
  Vector2f(float x, float y)
      : VectorBaseT(GLKVector2Make(x, y)) {
  }
  Vector2f(const Vector2f& x)
      : VectorBaseT(x.v_) {
  }
  Vector2f(const CGPoint& p)
      : VectorBaseT(GLKVector2Make(p.x, p.y)) {
  }
  explicit Vector2f(const GLKVector2& x)
      : VectorBaseT(x) {
  }

  float& x() { return v_.v[0]; }
  const float& x() const { return v_.v[0]; }
  float& y() { return v_.v[1]; }
  const float& y() const { return v_.v[1]; }

  float length() const {
    return GLKVector2Length(v_);
  }
  float length_squared() const {
    return dot(*this);
  }
  float dot(const Vector2f& x) const {
    return GLKVector2DotProduct(v_, x.v_);
  }
  Vector2f& normalize() {
    v_ = GLKVector2Normalize(v_);
    return *this;
  }
  CGPoint ToCGPoint() const {
    return CGPointMake(x(), y());
  }

  // Negation operator.
  Vector2f operator-() const {
    return Vector2f(GLKVector2Negate(v_));
  }

  // Vector-vector operators.
  Vector2f operator+(const Vector2f& b) const {
    return Vector2f(GLKVector2Add(v_, b.v_));
  }
  Vector2f operator-(const Vector2f& b) const {
    return Vector2f(GLKVector2Subtract(v_, b.v_));
  }
  Vector2f operator*(const Vector2f& b) const {
    return Vector2f(GLKVector2Multiply(v_, b.v_));
  }
  Vector2f operator/(const Vector2f& b) const {
    return Vector2f(GLKVector2Divide(v_, b.v_));
  }

  // Vector-scalar operators.
  Vector2f operator+(float val) const {
    return Vector2f(GLKVector2AddScalar(v_, val));
  }
  Vector2f operator-(float val) const {
    return Vector2f(GLKVector2SubtractScalar(v_, val));
  }
  Vector2f operator*(float val) const {
    return Vector2f(GLKVector2MultiplyScalar(v_, val));
  }
  Vector2f operator/(float val) const {
    return Vector2f(GLKVector2DivideScalar(v_, val));
  }
};

class Vector3f : public VectorBase<Vector3f, GLKVector3, 3> {
  typedef VectorBase<Vector3f, GLKVector3, 3> VectorBaseT;

 public:
  explicit Vector3f(float v = 0)
      : VectorBaseT(GLKVector3Make(v, v, v)) {
  }
  explicit Vector3f(const float v[3])
      : VectorBaseT(GLKVector3Make(v[0], v[1], v[2])) {
  }
  Vector3f(float x, float y, float z)
      : VectorBaseT(GLKVector3Make(x, y, z)) {
  }
  Vector3f(const Vector3f& x)
      : VectorBaseT(x.v_) {
  }
  Vector3f(const CGPoint& p)
      : VectorBaseT(GLKVector3Make(p.x, p.y, 0)) {
  }
  explicit Vector3f(const GLKVector3& x)
      : VectorBaseT(x) {
  }

  float& x() { return v_.v[0]; }
  const float& x() const { return v_.v[0]; }
  float& y() { return v_.v[1]; }
  const float& y() const { return v_.v[1]; }
  float& z() { return v_.v[2]; }
  const float& z() const { return v_.v[2]; }

  float length() const {
    return GLKVector3Length(v_);
  }
  float length_squared() const {
    return dot(*this);
  }
  float dot(const Vector3f& x) const {
    return GLKVector3DotProduct(v_, x.v_);
  }
  Vector3f cross(const Vector3f& x) const {
    return Vector3f(GLKVector3CrossProduct(v_, x.v_));
  }
  Vector3f& normalize() {
    v_ = GLKVector3Normalize(v_);
    return *this;
  }

  // Negation operator.
  Vector3f operator-() const {
    return Vector3f(GLKVector3Negate(v_));
  }

  // Vector-vector operators.
  Vector3f operator+(const Vector3f& b) const {
    return Vector3f(GLKVector3Add(v_, b.v_));
  }
  Vector3f operator-(const Vector3f& b) const {
    return Vector3f(GLKVector3Subtract(v_, b.v_));
  }
  Vector3f operator*(const Vector3f& b) const {
    return Vector3f(GLKVector3Multiply(v_, b.v_));
  }
  Vector3f operator/(const Vector3f& b) const {
    return Vector3f(GLKVector3Divide(v_, b.v_));
  }

  // Vector-scalar operators.
  Vector3f operator+(float val) const {
    return Vector3f(GLKVector3AddScalar(v_, val));
  }
  Vector3f operator-(float val) const {
    return Vector3f(GLKVector3SubtractScalar(v_, val));
  }
  Vector3f operator*(float val) const {
    return Vector3f(GLKVector3MultiplyScalar(v_, val));
  }
  Vector3f operator/(float val) const {
    return Vector3f(GLKVector3DivideScalar(v_, val));
  }
};

class Vector4f : public VectorBase<Vector4f, GLKVector4, 4>  {
  typedef VectorBase<Vector4f, GLKVector4, 4> VectorBaseT;

 public:
  explicit Vector4f(float v = 0)
      : VectorBaseT(GLKVector4Make(v, v, v, v)) {
  }
  explicit Vector4f(const float v[4])
      : VectorBaseT(GLKVector4Make(v[0], v[1], v[2], v[3])) {
  }
  Vector4f(float x, float y, float z, float w)
      : VectorBaseT(GLKVector4Make(x, y, z, w)) {
  }
  Vector4f(const Vector4f& x)
      : VectorBaseT(x.v_) {
  }
  Vector4f(const Vector2f& p)
      : VectorBase(GLKVector4Make(p.x(), p.y(), 0, 1)) {
  }
  Vector4f(const Vector3f& p)
      : VectorBase(GLKVector4Make(p.x(), p.y(), p.z(), 1)) {
  }
  Vector4f(const CGPoint& p)
      : VectorBaseT(GLKVector4Make(p.x, p.y, 0, 1)) {
  }
  explicit Vector4f(const GLKVector4& x)
      : VectorBaseT(x) {
  }
  // Only valid for color spaces with 4 values (incl. alpha).
  explicit Vector4f(CGColorRef c)
      : VectorBaseT(GLKVector4Make(0, 0, 0, 0)) {
    DCHECK_EQ(CGColorGetNumberOfComponents(c), 4);
    const CGFloat* comps = CGColorGetComponents(c);
    for (int i = 0; i < CGColorGetNumberOfComponents(c); ++i) {
      v_.v[i] = comps[i];
    }
  }

  float& x() { return v_.v[0]; }
  const float& x() const { return v_.v[0]; }
  float& y() { return v_.v[1]; }
  const float& y() const { return v_.v[1]; }
  float& z() { return v_.v[2]; }
  const float& z() const { return v_.v[2]; }
  float& w() { return v_.v[3]; }
  const float& w() const { return v_.v[3]; }

  float length() const {
    return GLKVector4Length(v_);
  }
  float length_squared() const {
    return dot(*this);
  }
  float dot(const Vector4f& x) const {
    return GLKVector4DotProduct(v_, x.v_);
  }
  Vector4f cross(const Vector4f& x) const {
    return Vector4f(GLKVector4CrossProduct(v_, x.v_));
  }
  Vector4f& normalize() {
    v_ = GLKVector4Normalize(v_);
    return *this;
  }

  // Negation operator.
  Vector4f operator-() const {
    return Vector4f(GLKVector4Negate(v_));
  }

  // Vector-vector operators.
  Vector4f operator+(const Vector4f& b) const {
    return Vector4f(GLKVector4Add(v_, b.v_));
  }
  Vector4f operator-(const Vector4f& b) const {
    return Vector4f(GLKVector4Subtract(v_, b.v_));
  }
  Vector4f operator*(const Vector4f& b) const {
    return Vector4f(GLKVector4Multiply(v_, b.v_));
  }
  Vector4f operator/(const Vector4f& b) const {
    return Vector4f(GLKVector4Divide(v_, b.v_));
  }

  // Vector-scalar operators.
  Vector4f operator+(float val) const {
    return Vector4f(GLKVector4AddScalar(v_, val));
  }
  Vector4f operator-(float val) const {
    return Vector4f(GLKVector4SubtractScalar(v_, val));
  }
  Vector4f operator*(float val) const {
    return Vector4f(GLKVector4MultiplyScalar(v_, val));
  }
  Vector4f operator/(float val) const {
    return Vector4f(GLKVector4DivideScalar(v_, val));
  }
};

template <typename DerivedT, typename VectorT, int N>
ostream& operator<<(ostream& os, const VectorBase<DerivedT,VectorT,N> &v) {
  os << '[' << v(0);
  for (int i = 1; i <N; i++) {
    os << ',' << v(i);
  }
  os << ']';
  return os;
}

#endif  // VIEWFINDER_VECTOR_H
