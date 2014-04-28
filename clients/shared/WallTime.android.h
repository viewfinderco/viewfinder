// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_WALLTIME_ANDROID_H
#define VIEWFINDER_WALLTIME_ANDROID_H

#import <functional>
#import <string>
#import <jni.h>

extern std::function<jlong (jlong)> time_zone_offset;
extern std::function<string ()> time_zone_name;

#endif  // VIEWFINDER_WALLTIME_ANDROID_H
