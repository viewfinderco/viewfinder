// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_TESTS_TESTING_H
#define VIEWFINDER_TESTS_TESTING_H

#ifdef __OBJC__

@class UIWindow;

#endif  // __OBJC__

#ifdef TESTING

#include "Logging.h"
#include "Mutex.h"

class Testing;

// A temporary directory that a test can write to. The directory will be
// deleted when the object is destroyed.
class TestTmpDir {
 public:
  TestTmpDir();
  ~TestTmpDir();

  const string& dir() const { return dir_; }

 private:
  const string tmp_dir_;
  const string dir_;
};

class Test : public TestTmpDir {
  friend class Testing;

 public:
  virtual ~Test();

 protected:
  Test();
  virtual void SetUp();
  virtual void TearDown();

 private:
  virtual void TestBody() = 0;
  void Run();
};

class TestFactory {
 public:
  virtual ~TestFactory() { }
  virtual Test* NewTest() const = 0;
};

template <typename T>
class TestFactoryImpl : public TestFactory {
 public:
  virtual Test* NewTest() const { return new T; }
};

struct TestInfo {
  const char* test_case;
  const char* name;
  TestFactory* factory;
};

class Testing {
  friend class TestMessage;

 public:
  static const TestInfo* RegisterTest(
      const char* test_case, const char* name,
      TestFactory* factory);
#ifdef __OBJC__
  static void RunTests(UIWindow* window, void (^completion)());
#endif  // __OBJC__
  static void MarkFailure();

 private:
  static const TestInfo* current_info;
  static bool current_result;
};

#define TEST_INTERNAL(test_case, name, parent_class)                \
class test_case##_##name##_Test : public parent_class {             \
 private:                                                           \
  virtual void TestBody();                                          \
  static const TestInfo* kTestInfo;                                 \
};                                                                  \
const TestInfo* test_case##_##name##_Test::kTestInfo =              \
    Testing::RegisterTest(#test_case, #name,                        \
                 new TestFactoryImpl<test_case##_##name##_Test>);   \
void test_case##_##name##_Test::TestBody()

#define TEST(test_case, name)                           \
  TEST_INTERNAL(test_case, name, Test)
#define TEST_F(test_fixture, name)                      \
  TEST_INTERNAL(test_fixture, name, test_fixture)

class TestMessage : public LogMessage {
 public:
  TestMessage(const char* file_line)
      : LogMessage(file_line, false, false) {
    stream() << Testing::current_info->test_case
             << "." << Testing::current_info->name
             << ": ";
  }
  ~TestMessage() {
    Testing::MarkFailure();
  }
};

#define NON_FATAL_FAILURE()                             \
  TestMessage(LOG_FILE_LINE).stream()
#define FATAL_FAILURE()                                 \
  return LogStreamVoidify() & NON_FATAL_FAILURE()

#define EXPECT_OP(name, op, val1, val2)                         \
  if (string* _result =                                         \
      Check##name##Impl(                                        \
             GetReferenceableValue(val1),                       \
             GetReferenceableValue(val2),                       \
             #val1 " " #op " " #val2))                          \
    NON_FATAL_FAILURE() << "expectation failed: " << *_result

#define EXPECT_EQ(val1, val2) EXPECT_OP(_EQ, ==, val1, val2)
#define EXPECT_NE(val1, val2) EXPECT_OP(_NE, !=, val1, val2)
#define EXPECT_LE(val1, val2) EXPECT_OP(_LE, <=, val1, val2)
#define EXPECT_LT(val1, val2) EXPECT_OP(_LT, < , val1, val2)
#define EXPECT_GE(val1, val2) EXPECT_OP(_GE, >=, val1, val2)
#define EXPECT_GT(val1, val2) EXPECT_OP(_GT, > , val1, val2)
#define EXPECT(cond)                            \
  (cond) ? (void) 0 :                           \
  LogStreamVoidify() & NON_FATAL_FAILURE()      \
  << "expectation failed: " << #cond

#define ASSERT_OP(name, op, val1, val2)                   \
  if (string* _result =                                   \
         Check##name##Impl(                               \
             GetReferenceableValue(val1),                 \
             GetReferenceableValue(val2),                 \
             #val1 " " #op " " #val2))                    \
    FATAL_FAILURE() << "assertion failed: " << *_result

#define ASSERT_EQ(val1, val2) ASSERT_OP(_EQ, ==, val1, val2)
#define ASSERT_NE(val1, val2) ASSERT_OP(_NE, !=, val1, val2)
#define ASSERT_LE(val1, val2) ASSERT_OP(_LE, <=, val1, val2)
#define ASSERT_LT(val1, val2) ASSERT_OP(_LT, < , val1, val2)
#define ASSERT_GE(val1, val2) ASSERT_OP(_GE, >=, val1, val2)
#define ASSERT_GT(val1, val2) ASSERT_OP(_GT, > , val1, val2)
#define ASSERT(cond)                                     \
  if (!(cond))                                           \
    return LogStreamVoidify() & NON_FATAL_FAILURE()      \
        << "assertion failed: " << #cond

#else  // TESTING

class Testing {
 public:
#ifdef __OBJC__
  static void RunTests(UIWindow* window, void (^completion)()) {
    completion();
  }
#endif  // __OBJC__
};

#endif // TESTING

#endif // VIEWFINDER_TESTING_H
