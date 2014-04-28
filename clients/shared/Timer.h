// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_TIMER_H
#define VIEWFINDER_TIMER_H

#include <algorithm>
#include "Logging.h"
#include "WallTime.h"

using std::min;

class WallTimer {
 public:
  WallTimer()
      : total_time_(0),
        start_time_(WallTime_Now()) {
  }

  void Reset() {
    total_time_ = 0;
    start_time_ = 0;
  }

  void Start() {
    start_time_ = WallTime_Now();
  }

  void Restart() {
    total_time_ = 0;
    Start();
  }

  void Stop() {
    if (start_time_ > 0) {
      total_time_ += WallTime_Now() - start_time_;
      start_time_ = 0;
    }
  }

  WallTime Get() const {
    WallTime r = total_time_;
    if (start_time_ > 0) {
      r += WallTime_Now() - start_time_;
    }
    return r;
  }

  double Milliseconds() const {
    return 1000 * Get();
  }

 private:
  WallTime total_time_;
  WallTime start_time_;
};

class ScopedTimer {
 public:
  ScopedTimer(const string& n)
      : name_(n) {
    timer_.Start();
  }
  ~ScopedTimer() {
    LOG("%s: %0.3f sec", name_.c_str(), timer_.Get());
  }

 private:
  const string name_;
  WallTimer timer_;
};

class AverageTimer {
 public:
  AverageTimer(int n)
      : size_(n),
        count_(0),
        average_(0.0) {
  }

  void SetSize(int n) {
    size_ = n;
    int new_count = min(count_, size_);
    if (new_count > 0) {
      average_ = (average_ * count_) / new_count;
    }
    count_ = new_count;
  }

  void Add(WallTime value) {
    if (count_ < size_) {
      ++count_;
    }
    average_ = (average_ * (count_ - 1) + value) / count_;
  }

  WallTime Get() const {
    return average_;
  }

  double Milliseconds() const {
    return 1000 * Get();
  }

 private:
  int size_;
  int count_;
  WallTime average_;
};

#endif // VIEWFINDER_TIMER_H
