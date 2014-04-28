// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault.
//
// Android-specific implementations.

#ifdef OS_ANDROID

#ifndef VIEWFINDER_COMPAT_ANDROID_H
#define VIEWFINDER_COMPAT_ANDROID_H

#import <iostream>
#import <string>
#import <time64.h>

// Source: http://src.chromium.org/svn/trunk/src/base/os_compat_android.cc
// Android has only timegm64() and no timegm().
// We replicate the behaviour of timegm() when the result overflows time_t.
time_t timegm(struct tm* const t);

#endif // VIEWFINDER_COMPAT_ANDROID_H

#endif // OS_ANDROID
