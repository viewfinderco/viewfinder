// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import <list>
#import <re2/re2.h>
#import "FileUtils.h"
#import "InteractiveTestController.h"
#import "MBProgressHUD.h"
#import "PathUtils.h"
#import "ScopedPtr.h"
#import "TestDefines.h"
#import "Testing.h"

namespace {

#ifndef TEST_VERBOSE
#define TEST_VERBOSE false
#endif // TEST_VERBOSE

#ifndef TEST_ONLY
#define TEST_ONLY false
#endif // TEST_ONLY

#ifndef TEST_SELECTION
#define TEST_SELECTION ""
#endif // TEST_SELECTION

#ifndef TEST_EXCLUSION
#define TEST_EXCLUSION "#"
#endif // TEST_EXCLUSION

#ifndef TEST_REPEAT
#define TEST_REPEAT  1
#endif // TEST_REPEAT

#ifndef TEST_INTERACTIVE
#define TEST_INTERACTIVE 0
#endif // TEST_INTERACTIVE

// Set kVerbose to true to have disable buffering of log messages.
const bool kVerbose = TEST_VERBOSE;
// Set kStopAfterTests to true to stop the program after tests have run. Useful
// during development when running the actual app is not desirable.
const bool kStopAfterTests = TEST_ONLY;
// Set kTestRepeate to specify how many times to repeat the tests. Useful for
// tracking down a test that fails sporadically.
const int kTestRepeat = TEST_REPEAT;
// Set kTestInteractive to true to go into an interactive testing interface when tests
// are complete instead of launching the app.
const int kTestInteractive = TEST_INTERACTIVE;
// A regular expression matched against the <test-case>.<test-name>
// string. Only matching tests are allowed to run. The empty string allows all
// tests to run.
#if (TARGET_IPHONE_SIMULATOR)
const string kTestsToRun = TEST_SELECTION;
const string kTestsToSkip = TEST_EXCLUSION;
#else  // !(TARGET_IPHONE_SIMULATOR)
const string kTestsToRun = "#";
const string kTestsToSkip = "";
#endif // !(TARGET_IPHONE_SIMULATOR)

// Abuse emoji to get colors in log output.  These characters get
// replaced by color versions on apple platforms.
const string kGreenCheck = "\u2705";
const string kRedX = "\u274c";

typedef std::list<const TestInfo*> TestInfoList;
TestInfoList* tests;

}  // namespace

@interface TestingViewController : UIViewController {
 @private
  MBProgressHUD* hud_;
}

@property (nonatomic) float progress;
@property (nonatomic) NSString* status;
@property (nonatomic) NSString* testId;
@property (nonatomic, readonly) MBProgressHUD* hud;

@end  // TestingViewController

@implementation TestingViewController

@synthesize hud = hud_;

- (void)loadView {
  self.view = [UIView new];
  self.view.backgroundColor = [UIColor blackColor];
}

- (void)viewDidAppear:(BOOL)animated {
  hud_ = [[MBProgressHUD alloc] initWithWindow:self.view.window];
  hud_.labelText = @"Running tests";
  hud_.mode = MBProgressHUDModeDeterminate;
  hud_.removeFromSuperViewOnHide = YES;
  [self.view.window addSubview:hud_];
  [hud_ show:YES];
  [super viewWillAppear:animated];
}

- (void)viewWillDisappear:(BOOL)animated {
  [hud_ hide:YES afterDelay:1];
  [super viewWillDisappear:animated];
}

- (void)setProgress:(float)p {
  hud_.progress = p;
}

- (float)progress {
  return hud_.progress;
}

- (void)setStatus:(NSString*)s {
  hud_.labelText = s;
}

- (NSString*)status {
  return hud_.labelText;
}

- (void)setTestId:(NSString*)s {
  hud_.detailsLabelText = s;
}

- (NSString*)testId {
  return hud_.detailsLabelText;
}

@end  // TestingViewController

TestTmpDir::TestTmpDir()
    : tmp_dir_(JoinPath(ToString(NSHomeDirectory()), "tmp")),
      dir_(JoinPath(tmp_dir_, "Test")) {
  DirCreate(tmp_dir_);
  // Stupidly, sometimes DirCreate() fails the first time with a "file exists"
  // error, even though we removed it on the previous line. Just loop trying to
  // create the directory.
  do {
    DirRemove(dir_, true);
  } while (!DirCreate(dir_));
}

TestTmpDir::~TestTmpDir() {
  DirRemove(dir_, true);
}

Test::Test() {
}

Test::~Test() {
}

void Test::Run() {
  SetUp();
  TestBody();
  TearDown();
}

void Test::SetUp() {
}

void Test::TearDown() {
}

const TestInfo* Testing::current_info;
bool Testing::current_result;

const TestInfo* Testing::RegisterTest(
    const char* test_case, const char* name, TestFactory* factory) {
  TestInfo* info = new TestInfo;
  info->test_case = test_case;
  info->name = name;
  info->factory = factory;
  if (!tests) {
    tests = new TestInfoList;
  }
  tests->push_back(info);
  return info;
}

void Testing::RunTests(UIWindow* window, void (^completion)()) {
  LOG("running tests...");

  if (kTestInteractive) {
    completion = ^{
      window.rootViewController = [InteractiveTestController new];
    };
  }

  if (kTestsToRun == "#") {
    completion();
    return;
  }

  TestingViewController* testing_controller = [TestingViewController new];
  window.rootViewController = testing_controller;

  dispatch_low_priority(^{
      int num_passed = 0;
      int num_failed = 0;
      int num_skipped = 0;

      if (tests) {
        RE2 match_re(kTestsToRun);
        RE2 skip_re(kTestsToSkip);
        const int count = tests->size() * kTestRepeat;
        for (int i = 0; i < kTestRepeat && !num_failed; ++i) {
          for (TestInfoList::iterator iter(tests->begin());
               iter != tests->end();
               ++iter) {
            @autoreleasepool {
              current_info = *iter;
              const string test_id(
                  Format("%s.%s", current_info->test_case, current_info->name));
              const string display_test_id(
                  Format("%s\n%s", current_info->test_case, current_info->name));
              const string status(
                  Format("%d passed, %d failed, %d skipped",
                         num_passed, num_failed, num_skipped));
              dispatch_main(^{
                  testing_controller.progress =
                      float(num_skipped + num_failed + num_passed) / count;
                  testing_controller.status = NewNSString(status);
                  testing_controller.testId = NewNSString(display_test_id);
                });

              if (!RE2::PartialMatch(test_id, match_re) ||
                  RE2::PartialMatch(test_id, skip_re)) {
                ++num_skipped;
              } else {
                {
                  ScopedPtr<ScopedLogSink> sink(
                      kVerbose ? NULL : new ScopedLogSink);
                  ScopedPtr<Test> test(current_info->factory->NewTest());
                  current_result = true;
                  test->Run();
                  if (sink.get() && !current_result) {
                    std::cerr << sink->output();
                  }
                }
                if (current_result) {
                  LOG("test: %s: PASS %s", test_id, kGreenCheck);
                  ++num_passed;
                } else {
                  LOG("test: %s: FAIL %s", test_id, kRedX);
                  ++num_failed;
                  if (i > 0) {
                    break;
                  }
                }
              }
              current_info = NULL;
            }
          }
        }
      }

      const string& icon = num_failed ? kRedX : kGreenCheck;
      LOG("test: %d passed, %d failed, %d skipped %s",
          num_passed, num_failed, num_skipped, icon);
      if (num_failed > 0 || kStopAfterTests) {
        exit(0);
      }

      dispatch_main(^{
          completion();

          testing_controller.progress = 1;
          testing_controller.status =
              Format("%d passed, %d failed, %d skipped",
                     num_passed, num_failed, num_skipped);
          testing_controller.testId = @"";
          [window addSubview:testing_controller.hud];
        });
    });
}

void Testing::MarkFailure() {
  current_result = false;
}

#endif // TESTING

// local variables:
// mode: c++
// end:
