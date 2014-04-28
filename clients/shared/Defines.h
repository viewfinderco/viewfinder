// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_DEFINES_H
#define VIEWFINDER_DEFINES_H

// Only include DeveloperDefines.h if this is not an ad-hoc/app-store build.
#ifdef DEVELOPMENT
  #ifndef FLYMAKE
    #import "DeveloperDefines.h"
  #endif  // !FLYMAKE
#else   // !DEVELOPMENT
#define PRODUCTION
#endif  // !DEVELOPMENT

#endif // VIEWFINDER_DEFINES_H
