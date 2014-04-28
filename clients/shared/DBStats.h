// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_DB_STATS_H
#define VIEWFINDER_DB_STATS_H

#import "DB.h"

class AppState;

class DBStats {
 public:
  DBStats(AppState* state);
  ~DBStats() {}

  // Compute statistics over database information.
  void ComputeStats();

 private:
  void ComputeViewpointStats();
  void ComputeEventStats();

 private:
  AppState* state_;
};

#endif  // VIEWFINDER_DB_STATS_H

// local variables:
// mode: c++
// end:
