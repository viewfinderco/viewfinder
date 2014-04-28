// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import "PhotoSelection.h"

class UIAppState;

void ShowExportDialog(UIAppState* state, const PhotoSelectionVec& selection, void (^done)(bool completed));
