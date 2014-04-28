// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "Testing.h"
#import "Vector.h"

namespace {

template <typename VectorT>
void TestVectorZeroConstructor() {
  VectorT v;
  for (int i = 0; i < v.size(); i++) {
    EXPECT_EQ(v(i), 0);
  }
}

template <typename VectorT>
void TestVectorFillConstructor() {
  VectorT v(42);
  for (int i = 0; i < v.size(); i++) {
    EXPECT_EQ(v(i), 42);
  }
}

template <typename VectorT>
void TestVectorArrayConstructor() {
  const int N = VectorT::size();
  float vals[N];
  for (int i = 0; i < N; i++) {
    vals[i] = N - i;
  }
  VectorT v(vals);
  for (int i = 0; i < v.size(); i++) {
    EXPECT_EQ(v(i), vals[i]);
  }
}

template <typename VectorT>
void TestVectorCopyConstructor() {
  VectorT v1;
  for (int i = 0; i < v1.size(); i++) {
    v1(i) = i;
  }
  VectorT v2(v1);
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), v2(i));
  }
}

template <typename VectorT>
void TestVectorConstructor() {
  TestVectorZeroConstructor<VectorT>();
  TestVectorFillConstructor<VectorT>();
  TestVectorArrayConstructor<VectorT>();
  TestVectorCopyConstructor<VectorT>();
}

template <typename VectorT>
void TestVectorIterators() {
  const int N = VectorT::size();
  VectorT v;
  for (int i = 0; i < N; i++) {
    v(i) = i;
  }
  int i = 0;
  for (typename VectorT::iterator iter(v.begin());
       iter != v.end();
       ++iter) {
    EXPECT_EQ(*iter, i);
    ++i;
  }
  const VectorT& const_v = v;
  i = 0;
  for (typename VectorT::const_iterator iter(const_v.begin());
       iter != const_v.end();
       ++iter) {
    EXPECT_EQ(*iter, i);
    ++i;
  }
}

template <typename VectorT>
void TestVectorMethods() {
  const int N = VectorT::size();
  VectorT v;
  float length_squared = 0;
  float sum = 0;
  for (int i = 0; i < N; i++) {
    v(i) = i;
    length_squared += i * i;
    sum += v(i);
  }
  EXPECT_EQ(v.length_squared(), length_squared);
  EXPECT_EQ(v.dot(v), length_squared);
}

template <typename VectorT>
void TestVectorOperators() {
  VectorT v1;

  // Vector-scalar operations
  v1 += 10;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), 10);
  }
  v1 -= 1;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), 9);
  }
  v1 *= 2;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), 18);
  }
  v1 /= 3;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), 6);
  }

  // Vector-vector operations
  VectorT v2;
  for (int i = 0; i < v2.size(); i++) {
    v2(i) = i + 1;
  }
  v1 += v2;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), 7 + i);
  }
  v1 -= v2;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), 6);
  }
  v1 *= v2;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), 6 * (i + 1));
  }
  v1 /= v2;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), 6);
  }

  // Assignment operator
  v1 = v2;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), (i + 1));
  }
  // Negation operator
  v1 = -v1;
  for (int i = 0; i < v1.size(); i++) {
    EXPECT_EQ(v1(i), -(i + 1));
  }
}

TEST(VectorTest, Constructor) {
  TestVectorConstructor<Vector2f>();
  TestVectorConstructor<Vector3f>();
  TestVectorConstructor<Vector4f>();
}

TEST(VectorTest, Iterators) {
  TestVectorIterators<Vector2f>();
  TestVectorIterators<Vector3f>();
  TestVectorIterators<Vector4f>();
}

TEST(VectorTest, Methods) {
  TestVectorMethods<Vector2f>();
  TestVectorMethods<Vector3f>();
  TestVectorMethods<Vector4f>();
}

TEST(VectorTest, Operators) {
  TestVectorOperators<Vector2f>();
  TestVectorOperators<Vector3f>();
  TestVectorOperators<Vector4f>();
}

}  // namespace

#endif // TESTING
