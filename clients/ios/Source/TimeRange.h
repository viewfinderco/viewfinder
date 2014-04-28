// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_TIME_RANGE_H
#define VIEWFINDER_TIME_RANGE_H

#include <time.h>
#include "WallTime.h"

string FormatOuterTimeRange(float time_scale, WallTime st, WallTime et, bool ascending = true);
string FormatInnerTimeRange(float time_scale, WallTime st, WallTime et, bool ascending = true);
WallTime GetCurrentOuterTime(float time_scale, WallTime ts);
WallTime GetCurrentInnerTime(float time_scale, WallTime ts);
WallTime GetNextOuterTime(float time_scale, WallTime ts);
WallTime GetNextInnerTime(float time_scale, WallTime ts);

#endif // VIEWFINDER_TIME_RANGE_H
