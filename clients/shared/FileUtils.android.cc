// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault

#include "FileUtils.h"

// Android does not currently support cloud backup.
void FileExcludeFromBackup(const string& path, bool is_dir) { return; }
