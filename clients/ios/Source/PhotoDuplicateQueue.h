// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_PHOTO_DUPLICATE_QUEUE_H
#define VIEWFINDER_PHOTO_DUPLICATE_QUEUE_H

#import "BackgroundManager.h"
#import "Mutex.h"

class UIAppState;

class PhotoDuplicateQueue {
 public:
  PhotoDuplicateQueue(UIAppState* state);
  ~PhotoDuplicateQueue();

  // Process the queue of potentially duplicate photos.
  void MaybeProcess();

  // Blocks until all background potential duplicate processing has completed.
  // Only public for tests.
  void Drain();

 private:
  void MaybeProcessLocked();

 private:
  UIAppState* const state_;
  Mutex mu_;
  bool inflight_;
  BackgroundTask bg_task_;
};

#endif  // VIEWFINDER_PHOTO_DUPLICATE_QUEUE_H

// local variables:
// mode: c++
// end:
