// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_PHOTO_UTILS_H
#define VIEWFINDER_PHOTO_UTILS_H

#import "DB.h"
#import "PhotoSelection.h"

class UIAppState;

typedef void (^FilterCallback)();

// Returns true if any photos were filtered from the selection. Otherwise,
// returns false if all selected photos have proper unshare permissions.
bool FilterUnshareSelection(
    UIAppState* state, PhotoSelectionSet* selection,
    FilterCallback filter_callback, DBHandle snapshot);

#endif  // VIEWFINDER_PHOTO_UTILS_H

// local variables:
// mode: objc
// end:
