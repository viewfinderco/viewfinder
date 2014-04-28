// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_BACKGROUND_MANAGER_H
#define VIEWFINDER_BACKGROUND_MANAGER_H

#import <UIKit/UIKit.h>
#import "WallTime.h"

class UIAppState;

class BackgroundTask {
 public:
  BackgroundTask();
  ~BackgroundTask();

  // Returns the number of seconds remaining for background processing.
  double Start();
  void Stop(bool verbose = true);

  bool valid() const { return task_ != UIBackgroundTaskInvalid; }

  // Runs the given block on the low-priority queue as a background task
  // (so the process will not be suspended while it is running).
  static void Dispatch(void (^callback)());

 private:
  UIBackgroundTaskIdentifier task_;
};

typedef void (^BackgroundBlock)(void);

@interface BackgroundManager : NSObject {
 @private
  UIAppState* state_;
  BackgroundBlock block_;
  BackgroundTask bg_task_;
  NSTimer* timer_;
  double backoff_secs_;
  WallTime timestamp_;
}

- (id)initWithState:(UIAppState*)state
          withBlock:(BackgroundBlock)block;

- (void)resetBackoff;
// True if the background manager should stay alive to enable the
// application as much time as it can have to finish processing.
- (void)startWithKeepAlive:(bool)keep_alive;

@end  // BackgroundManager

#endif  // VIEWFINDER_BACKGROUND_MANAGER_H
