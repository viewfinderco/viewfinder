// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_JAILBREAK_UTILS_H
#define VIEWFINDER_JAILBREAK_UTILS_H

#if __cplusplus
extern "C" {
#endif

// Is the MobileSubstrate library mapped into our address space? Presence of
// the MobileSubstrate library is a good indication that not only are we
// running on a jailbroken phone, but there is a package present which is
// injecting code into our process (e.g. TypeStatus).
bool HasMobileSubstrateDynamicLibrary(void);

#if __cplusplus
}  // extern "C"
#endif

#endif // VIEWFINDER_JAILBREAK_UTILS_H
