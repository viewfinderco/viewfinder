// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_MATRIX_H
#define VIEWFINDER_MATRIX_H

#include <CoreGraphics/CGAffineTransform.h>
#include <GLKit/GLKMatrix3.h>
#include <GLKit/GLKMatrix4.h>
#include <QuartzCore/CATransform3D.h>
#include "Vector.h"

template <typename DerivedT, typename MatrixT, int N>
class MatrixBase {
 public:
  enum {
    DIM = N,
    SIZE = N * N,
  };

  typedef float* iterator;
  typedef const float* const_iterator;

 public:
  explicit MatrixBase(const MatrixT& m)
      : m_(m) {
  }

  iterator data() { return &m_.m[0]; }
  const_iterator data() const { return &m_.m[0]; }
  iterator begin() { return &m_.m[0]; }
  const_iterator begin() const { return &m_.m[0]; }
  iterator end() { return &m_.m[N * N]; }
  const_iterator end() const { return &m_.m[N * N]; }

  MatrixT& glk_matrix() { return m_; }
  const MatrixT& glk_matrix() const { return m_; }

  float& operator()(int row, int col) { return m_.m[col * N + row]; }
  const float& operator()(int row, int col) const { return m_.m[col * N + row]; }

  static int size() { return SIZE; }

  DerivedT& fill(float val) {
    return (derived() = DerivedT(val));
  }
  DerivedT& zero() {
    return fill(0);
  }

  bool equal(const DerivedT& x,
             float threshold = std::numeric_limits<float>::epsilon() * 32) const {
    for (int r = 0; r < N; r++) {
      for (int c = 0; c < N; c++) {
        if (fabs((*this)(r, c) - x(r, c)) > threshold) {
          return false;
        }
      }
    }
    return true;
  }

  // Assignment operators.
  DerivedT& operator+=(const MatrixBase& x) {
    return (derived() = derived() + x.derived());
  }
  DerivedT& operator-=(const MatrixBase& x) {
    return (derived() = derived() - x.derived());
  }
  DerivedT& operator*=(const MatrixBase& x) {
    return (derived() = derived() * x.derived());
  }

 private:
  DerivedT& derived() { return *static_cast<DerivedT*>(this); }
  const DerivedT& derived() const { return *static_cast<const DerivedT*>(this); }

 protected:
  MatrixT m_;
};

class Matrix3f : public MatrixBase<Matrix3f, GLKMatrix3, 3> {
  typedef MatrixBase<Matrix3f, GLKMatrix3, 3> MatrixBaseT;

 public:
  Matrix3f()
      : MatrixBaseT(GLKMatrix3Identity) {
  }
  explicit Matrix3f(float v)
      : MatrixBaseT(GLKMatrix3Make(v, v, v,
                                   v, v, v,
                                   v, v, v)) {
  }
  explicit Matrix3f(const float v[9])
      : MatrixBaseT(GLKMatrix3Make(v[0], v[1], v[2],
                                   v[3], v[4], v[5],
                                   v[6], v[7], v[8])) {
  }
  // TODO(pmattis): Is this correct?
  explicit Matrix3f(const CGAffineTransform& t)
      : MatrixBaseT(GLKMatrix3Make(t.a, t.c, t.tx,
                                   t.b, t.d, t.ty,
                                     0,   0,    1)) {
  }
  Matrix3f(float m00, float m01, float m02,
           float m10, float m11, float m12,
           float m20, float m21, float m22)
      : MatrixBaseT(GLKMatrix3Make(m00, m01, m02,
                                   m10, m11, m12,
                                   m20, m21, m22)) {
  }
  Matrix3f(const Matrix3f& x)
      : MatrixBaseT(x.m_) {
  }
  explicit Matrix3f(const GLKMatrix3& x)
      : MatrixBaseT(x) {
  }

  Matrix3f& identity() {
    m_ = GLKMatrix3Identity;
    return *this;
  }
  Matrix3f& transpose() {
    m_ = GLKMatrix3Transpose(m_);
    return *this;
  }
  Matrix3f& invert(bool* invertible) {
    m_ = GLKMatrix3Invert(m_, invertible);
    return *this;
  }

  Matrix3f& scale(float x, float y, float z) {
    *this *= Matrix3f(GLKMatrix3MakeScale(x, y, z));
    return *this;
  }
  Matrix3f& scale(const Vector3f& s) {
    return scale(s.x(), s.y(), s.z());
  }

  // Matrix-matrix operators..
  Matrix3f operator*(const Matrix3f& b) const {
    return Matrix3f(GLKMatrix3Multiply(m_, b.m_));
  }
  Matrix3f operator+(const Matrix3f& b) const {
    return Matrix3f(GLKMatrix3Add(m_, b.m_));
  }
  Matrix3f operator-(const Matrix3f& b) const {
    return Matrix3f(GLKMatrix3Subtract(m_, b.m_));
  }

  // Matrix-vector multiplication.
  Vector3f operator*(const Vector3f& b) const {
    return Vector3f(GLKMatrix3MultiplyVector3(m_, b.glk_vector()));
  }
};

class Matrix4f : public MatrixBase<Matrix4f, GLKMatrix4, 4> {
  typedef MatrixBase<Matrix4f, GLKMatrix4, 4> MatrixBaseT;

 public:
  Matrix4f()
      : MatrixBaseT(GLKMatrix4Identity) {
  }
  explicit Matrix4f(float v)
      : MatrixBaseT(GLKMatrix4Make(v, v, v, v,
                                   v, v, v, v,
                                   v, v, v, v,
                                   v, v, v, v)) {
  }
  explicit Matrix4f(const float v[16])
      : MatrixBaseT(GLKMatrix4Make(v[0], v[1], v[2], v[3],
                                   v[4], v[5], v[6], v[7],
                                   v[8], v[9], v[10], v[11],
                                   v[12], v[13], v[14], v[15])) {
  }
  // TODO(pmattis): Is this correct?
  explicit Matrix4f(const CGAffineTransform& t)
      : MatrixBaseT(GLKMatrix4Make(t.a, t.c, 0, t.tx,
                                   t.b, t.d, 0, t.ty,
                                   0, 0, 1, 0,
                                   0, 0, 0, 1)) {
  }
  // TODO(pmattis): Is this correct?
  explicit Matrix4f(const CATransform3D& t)
      : MatrixBaseT(GLKMatrix4Make(t.m11, t.m12, t.m13, t.m14,
                                   t.m21, t.m22, t.m23, t.m24,
                                   t.m31, t.m32, t.m33, t.m34,
                                   t.m41, t.m42, t.m43, t.m44)) {
  }
  Matrix4f(const Matrix4f& x)
      : MatrixBaseT(x.m_) {
  }
  explicit Matrix4f(const GLKMatrix4& x)
      : MatrixBaseT(x) {
  }

  Matrix4f& identity() {
    m_ = GLKMatrix4Identity;
    return *this;
  }
  Matrix4f& transpose() {
    m_ = GLKMatrix4Transpose(m_);
    return *this;
  }
  Matrix4f& invert(bool* invertible) {
    m_ = GLKMatrix4Invert(m_, invertible);
    return *this;
  }

  Matrix4f& translate(float x, float y, float z) {
    *this *= Matrix4f(GLKMatrix4MakeTranslation(x, y, z));
    return *this;
  }
  Matrix4f& translate(const Vector3f& t) {
    return translate(t.x(), t.y(), t.z());
  }

  Matrix4f& scale(float x, float y, float z) {
    *this *= Matrix4f(GLKMatrix4MakeScale(x, y, z));
    return *this;
  }
  Matrix4f& scale(const Vector3f& s) {
    return scale(s.x(), s.y(), s.z());
  }

  Matrix4f& rotate(float radians, float x, float y, float z) {
    *this *= Matrix4f(GLKMatrix4MakeRotation(radians, x, y, z));
    return *this;
  }
  Matrix4f& rotate(float radians, const Vector3f& axis) {
    return rotate(radians, axis.x(), axis.y(), axis.z());
  }

  Matrix4f& ortho(float left, float right,
                  float bottom, float top,
                  float near, float far) {
    *this *= Matrix4f(GLKMatrix4MakeOrtho(left, right, bottom, top, near, far));
    return *this;
  }

  Matrix4f& frustum(float left, float right,
                    float bottom, float top,
                    float near, float far) {
    *this *= Matrix4f(GLKMatrix4MakeFrustum(left, right, bottom, top, near, far));
    return *this;
  }

  Matrix4f& look_at(const Vector3f& eye,
                    const Vector3f& center,
                    const Vector3f& up) {
    *this *= Matrix4f(GLKMatrix4MakeLookAt(eye.x(), eye.y(), eye.z(),
                                           center.x(), center.y(), center.z(),
                                           up.x(), up.y(), up.z()));
    return *this;
  }

  // Matrix-matrix operators.
  Matrix4f operator*(const Matrix4f& b) const {
    // NOTE(pmattis): We intentially reverse the natural order of the
    // multiplication in order to get composition of transforms to be
    // expected. That is:
    //
    //   Matrix4f m;
    //   m.rotate(kPi / 2, 0, 0, 1);
    //   m.translate(1, 0, 0);
    //
    // Should perform a rotation and then a translation.
    return Matrix4f(GLKMatrix4Multiply(b.m_, m_));
  }
  Matrix4f operator+(const Matrix4f& b) const {
    return Matrix4f(GLKMatrix4Add(m_, b.m_));
  }
  Matrix4f operator-(const Matrix4f& b) const {
    return Matrix4f(GLKMatrix4Subtract(m_, b.m_));
  }

  // Matrix-vector multiplication.
  Vector3f operator*(const Vector3f& b) const {
    return Vector3f(GLKMatrix4MultiplyVector3(m_, b.glk_vector()));
  }
  Vector4f operator*(const Vector4f& b) const {
    return Vector4f(GLKMatrix4MultiplyVector4(m_, b.glk_vector()));
  }
};

template <typename DerivedT, typename MatrixT, int N>
ostream& operator<<(ostream& os, const MatrixBase<DerivedT,MatrixT,N> &m) {
  for (int r = 0; r < N; r++) {
    os << '|' << m(0, r);
    for (int c = 1; c < N; c++) {
      os << ',' << m(c, r);
    }
    os << "|\n";
  }
  return os;
}

#endif  // VIEWFINDER_MATRIX_H
