// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_UTILS_ANDROID_H
#define VIEWFINDER_UTILS_ANDROID_H

#include <functional>
#include <jni.h>

extern string app_version;
extern std::function<int64_t ()> free_disk_space;
extern std::function<int64_t ()> total_disk_space;

void InitDispatch(JavaVM* jvm);

#endif // VIEWFINDER_UTILS_ANDROID_H
