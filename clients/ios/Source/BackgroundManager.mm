// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AsyncState.h"
#import "BackgroundManager.h"
#import "Logging.h"
#import "UIAppState.h"

namespace {

const double kMinBackoffSecs = 30.0;
const double kMaxBackoffSecs = 6000.0;

}  // unnamed namespace


BackgroundTask::BackgroundTask()
    : task_(UIBackgroundTaskInvalid) {
}

BackgroundTask::~BackgroundTask() {
  Stop();
}

double BackgroundTask::Start() {
  UIApplication* a = [UIApplication sharedApplication];
  if (valid()) {
    return a.backgroundTimeRemaining;
  }
  // backgroundTimeRemaining is not well-defined before a background task has started.
  task_ = [a beginBackgroundTaskWithExpirationHandler:^{
      LOG("background: %d: cancelling task: %.0f",
          task_, a.backgroundTimeRemaining);
      Stop(false);
    }];
  if (a.backgroundTimeRemaining < 30) {
    LOG("background: insufficient time remaining: %f",
        a.backgroundTimeRemaining);
    Stop(false);
    return 0;
  }
  double remaining = std::min<double>(600, a.backgroundTimeRemaining);
  if (valid() && a.applicationState != UIApplicationStateActive) {
    LOG("background: %d: starting task: %d",
        task_, a.applicationState);
  }
  return remaining;
}

void BackgroundTask::Stop(bool verbose) {
  if (valid()) {
    UIApplication* a = [UIApplication sharedApplication];
    if (verbose && a.applicationState != UIApplicationStateActive) {
      LOG("background: %d: stopping task: %d: %.0f", task_,
          a.applicationState, std::min<double>(600, a.backgroundTimeRemaining));
    }
    [a endBackgroundTask:task_];
    task_ = UIBackgroundTaskInvalid;
  }
}

void BackgroundTask::Dispatch(void (^callback)()) {
  BackgroundTask* task = new BackgroundTask;
  task->Start();
  dispatch_low_priority(^{
      callback();
      task->Stop();
      delete task;
    });
}


@implementation BackgroundManager

- (id)initWithState:(UIAppState*)state
          withBlock:(BackgroundBlock)block {
  if (self = [super init]) {
    state_ = state;
    block_ = block;
    timestamp_ = 0;
  }
  return self;
}

- (void)resetBackoff {
  //  LOG("background mgr: resetting backoff");
  backoff_secs_ = kMinBackoffSecs;
  timestamp_ = WallTime_Now();
  if (timer_) {
    [timer_ invalidate];
    timer_ = NULL;
  }
}

- (void)startWithKeepAlive:(bool)keep_alive {
  const double remaining = bg_task_.Start();
  const double delay =
      std::max<double>(0, backoff_secs_ - (WallTime_Now() - timestamp_));
  //  LOG("background mgr: keep alive: %d, remaining: %.0fs, "
  //      "backoff: %.0fs, delay: %.0fs",
  //      keep_alive, remaining, backoff_secs_, delay);

  // Don't keep background task active if we're not supposed to
  // keep alive and either there's been no backoff reset or the
  // delay for the next query exceeds the remaining processing time.
  if (!keep_alive && (timestamp_ == 0 || remaining < delay)) {
    bg_task_.Stop();
  } else if (timestamp_ != 0) {
    //    LOG("background mgr: setting block timeout for %.0fs", delay);
    if (!timer_) {
      timer_ = [NSTimer scheduledTimerWithTimeInterval:delay
                                                target:self
                                              selector:@selector(runBlock)
                                              userInfo:NULL
                                               repeats:NO];
    }
  }
}

- (void)runBlock {
  //  LOG("background mgr: running block");
  timer_ = NULL;
  backoff_secs_ = std::min<double>(kMaxBackoffSecs, backoff_secs_ * 4);
  timestamp_ = WallTime_Now();
  block_();
}

@end  // BackgroundManager

// local variables:
// mode: c++
// end:
