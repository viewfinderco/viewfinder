// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault.

#import "FileUtils.h"
#import "Format.h"
#import "Logging.h"
#import "PathUtils.h"
#import "StringUtils.h"

namespace {

string TmpPath() {
  return "tmp";
}

class AppDir : public string {
 public:
  AppDir(const string& dir) {
    DirCreate(dir);
    DirCreate(JoinPath(dir, LibraryPath()));
    DirCreate(JoinPath(dir, TmpPath()));
    assign(dir);
  }
};

AppDir* kAppDir = NULL;

}  // namespace

void InitApplicationPath(const string& dir) {
  if (kAppDir == NULL) {
    kAppDir = new AppDir(dir);
  }
}

string JoinPath(const Slice& a, const Slice& b) {
  if (b.empty()) {
    return a.ToString();
  }
  if (!a.ends_with("/")) {
    return Format("%s/%s", a, b);
  }
  return Format("%s%s", a, b);
}

string HomeDir() {
  return *kAppDir;
}

string LibraryPath() {
  return "Library";
}

string LibraryDir() {
  return JoinPath(*kAppDir, LibraryPath());
}

string LoggingDir() {
  return JoinPath(LibraryDir(), "Logs");
}

string LoggingQueueDir() {
  return JoinPath(LoggingDir(), "Queue");
}

string TmpDir() {
  return JoinPath(*kAppDir, TmpPath());
}
