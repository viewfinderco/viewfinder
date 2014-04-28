// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// Note, this file has to be plain old objective-c and not objective-c++
// because the plcrash_async_image_list_*() functions are C functions but are
// not properly tagged as such (via extern "C" {}).

#import <dlfcn.h>
#import <stdio.h>
#import "CrashReporter.h"
#import "JailbreakUtils.h"
#import "PLCrashAsyncImageList.h"
#import "PLCrashAsyncMachOImage.h"

static dispatch_once_t once;
static bool has_mobile_substrate_dynamic_library;

static bool IsMobileSubstrateDynamicLibraryImage(pl_async_macho_t* image) {
  const void* addr = (const void*)image->header_addr;
  Dl_info dli;
  if (dladdr((const void*)addr, &dli)) {
    if (strstr(dli.dli_fname, "MobileSubstrate/DynamicLibraries")) {
      // printf("%s\n", dli.dli_fname);
      return true;
    }
  }
  return false;
}

static void InitHasMobileSubstrateDynamicLibrary(void* data) {
  plcrash_async_image_list_t* image_list = [PLCrashReporter sharedImageList];
  plcrash_async_image_list_set_reading(image_list, true);
  plcrash_async_image_t* image = NULL;
  while ((image = plcrash_async_image_list_next(image_list, image)) != NULL) {
    if (IsMobileSubstrateDynamicLibraryImage(&image->macho_image)) {
      has_mobile_substrate_dynamic_library = true;
      break;
    }
  }
  plcrash_async_image_list_set_reading(image_list, false);
}

bool HasMobileSubstrateDynamicLibrary(void) {
  dispatch_once_f(&once, NULL, &InitHasMobileSubstrateDynamicLibrary);
  return has_mobile_substrate_dynamic_library;
}
