// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_DEBUG_UTILS_H
#define VIEWFINDER_DEBUG_UTILS_H

#include "Utils.h"

string MemStats(bool verbose);
string FileStats();
string DebugStats(bool verbose);
void   DebugStatsLoop();
void   DebugInject();

#endif // VIEWFINDER_DEBUG_UTILS_H
