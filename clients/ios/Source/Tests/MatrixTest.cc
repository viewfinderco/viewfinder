// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "Matrix.h"
#import "Testing.h"

namespace {

template <typename MatrixT>
void TestMatrixIdentityConstructor() {
  const int N = MatrixT::DIM;
  MatrixT m;
  for (int r = 0; r < N; r++) {
    for (int c = 0; c < N; c++) {
      EXPECT_EQ(m(r, c), (r == c));
    }
  }
}

template <typename MatrixT>
void TestMatrixArrayConstructor() {
  const int N = MatrixT::DIM;
  float d1[N * N];
  for (int i = 0; i < N * N; i++) {
    d1[i] = N * N - i;
  }
  MatrixT m(d1);
  for (int r = 0; r < N; r++) {
    for (int c = 0; c < N; c++) {
      EXPECT_EQ(m(r, c), (N * N - c * N - r));
    }
  }
}

template <typename MatrixT>
void TestMatrixConstructor() {
  TestMatrixIdentityConstructor<MatrixT>();
  TestMatrixArrayConstructor<MatrixT>();
}

template <typename MatrixT>
void TestMatrixIterators() {
  const int N = MatrixT::DIM;
  MatrixT m;
  for (int r = 0; r < N; r++) {
    for (int c = 0; c < N; c++) {
      m(r, c) = c * N + r;
    }
  }
  int i = 0;
  for (typename MatrixT::iterator iter(m.begin());
       iter != m.end();
       ++iter) {
    EXPECT_EQ(*iter, i);
    ++i;
  }
  const MatrixT& const_m = m;
  i = 0;
  for (typename MatrixT::const_iterator iter(const_m.begin());
       iter != const_m.end();
       ++iter) {
    EXPECT_EQ(*iter, i);
    ++i;
  }
}

template <typename MatrixT, typename VectorT>
void TestMatrixTransform(
    const MatrixT& m, const VectorT& a, const VectorT& b) {
  const VectorT v = m * a;
  EXPECT(v.equal(b));
}

TEST(MatrixTest, Constructors) {
  TestMatrixConstructor<Matrix3f>();
  TestMatrixConstructor<Matrix4f>();
}

TEST(MatrixTest, Iterators) {
  TestMatrixIterators<Matrix3f>();
  TestMatrixIterators<Matrix4f>();
}

TEST(MatrixTest, Identity) {
  Matrix4f m(2);
  EXPECT_EQ(&m, &m.identity());
  for (int r = 0; r < 4; r++) {
    for (int c = 0; c < 4; c++) {
      EXPECT_EQ(m(r, c), (r == c));
    }
  }
}

TEST(MatrixTest, Translate) {
  Matrix4f m;
  m.translate(1, 2, 3);
  TestMatrixTransform(m, Vector4f(1, 1, 1, 1), Vector4f(2, 3, 4, 1));

  Matrix4f t;
  t.translate(1, 0, 0);
  t.translate(0, 2, 0);
  t.translate(0, 0, 3);
  EXPECT(m.equal(t));
}

TEST(MatrixTest, Scale) {
  Matrix4f m;
  m.scale(1, 2, 3);
  TestMatrixTransform(m, Vector4f(1, 1, 1, 1), Vector4f(1, 2, 3, 1));

  Matrix4f t;
  t.scale(1, 1, 1);
  t.scale(1, 2, 1);
  t.scale(1, 1, 3);
  EXPECT(m.equal(t));
}

TEST(MatrixTest, Rotate) {
  Matrix4f m;
  m.identity().rotate(kPi, 1, 0, 0);
  TestMatrixTransform(m, Vector4f(0, 1, 0, 1), Vector4f(0, -1, 0, 1));
  TestMatrixTransform(m, Vector4f(0, 0, 1, 1), Vector4f(0, 0, -1, 1));
  m.identity().rotate(kPi, 0, 1, 0);
  TestMatrixTransform(m, Vector4f(1, 0, 0, 1), Vector4f(-1, 0, 0, 1));
  TestMatrixTransform(m, Vector4f(0, 0, 1, 1), Vector4f(0, 0, -1, 1));
  m.identity().rotate(kPi, 0, 0, 1);
  TestMatrixTransform(m, Vector4f(1, 0, 0, 1), Vector4f(-1, 0, 0, 1));
  TestMatrixTransform(m, Vector4f(0, 1, 0, 1), Vector4f(0, -1, 0, 1));
}

TEST(MatrixTest, Transpose) {
  Matrix4f m;
  for (int r = 0; r < 4; r++) {
    for (int c = 0; c < 4; c++) {
      m(r, c) = r * 4 + c;
    }
  }
  m.transpose();
  for (int r = 0; r < 4; r++) {
    for (int c = 0; c < 4; c++) {
      EXPECT_EQ(m(r, c), (c * 4 + r));
    }
  }
}

TEST(MatrixTest, Ortho) {
  Matrix4f m;
  m.ortho(-1, 1, -1, 1, 1, -1);
  Matrix4f e;
  EXPECT(m.equal(e));
}

TEST(MatrixTest, Frustum) {
  Matrix4f m;
  m.frustum(-1, 1, -1, 1, 1, -1);
  Matrix4f e;
  e(2, 2) = 0;
  e(2, 3) = -1;
  e(3, 2) = -1;
  e(3, 3) = 0;
  EXPECT(m.equal(e));
}

TEST(MatrixTest, LookAt) {
  Matrix4f m;
  m.look_at(Vector3f(0, 0, 0),
            Vector3f(0, 0, -1),
            Vector3f(0, 1, 0));
  Matrix4f e;
  EXPECT(m.equal(e));
}

TEST(MatrixTest, Operators) {
  Matrix4f m;

  // Matrix-matrix operations
  m = Matrix4f() + Matrix4f();
  for (int r = 0; r < 4; r++) {
    for (int c = 0; c < 4; c++) {
      EXPECT_EQ(m(r, c), 2 * (r == c));
    }
  }
  m = Matrix4f() - Matrix4f();
  for (int r = 0; r < 4; r++) {
    for (int c = 0; c < 4; c++) {
      EXPECT_EQ(m(r, c), 0);
    }
  }
}

}  // namespace

#endif  // TESTING
