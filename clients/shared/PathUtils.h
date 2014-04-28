// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_PATH_UTILS_H
#define VIEWFINDER_PATH_UTILS_H

#import "Utils.h"

#ifdef OS_ANDROID
void InitApplicationPath(const string& dir);
# else // !OS_ANDROID
string MainBundlePath(const string &filename);
#endif // !OS_ANDROID

string JoinPath(const Slice& a, const Slice& b);
string HomeDir();
string LibraryPath();
string LibraryDir();
string LoggingDir();
string LoggingQueueDir();
string TmpDir();

#endif // VIEWFINDER_PATH_UTILS_H
