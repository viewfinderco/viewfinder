// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <Foundation/Foundation.h>
#import "Defines.h"
#import "FileUtils.h"
#import "Format.h"
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "PathUtils.h"
#import "StringUtils.h"

namespace {

string StripHomeDirPrefix(const Slice& s) {
  Slice h([NSHomeDirectory() UTF8String]);
  CHECK(s.starts_with(h));
  return s.substr(h.size() + 1).ToString();
}

string GetDirPath(NSSearchPathDirectory dir) {
  NSArray* dirs = NSSearchPathForDirectoriesInDomains(
      dir, NSUserDomainMask, YES);
  if (dirs.count == 0) {
    return string();
  }
  return StripHomeDirPrefix([[dirs objectAtIndex:0] UTF8String]);
}

string TmpPath() {
  return "tmp";
}

class HomeDir : public string {
 public:
  HomeDir() {
    string dir = ToString(NSHomeDirectory());
    const string clean_slate_dir = JoinPath(JoinPath(dir, TmpPath()), "CleanSlate");

#ifdef CLEAN_SLATE_VERSION
    dir = clean_slate_dir;
    DirCreate(dir);

    vector<string> filenames;
    DirList(dir, &filenames);

#ifdef CLEAN_SLATE_RESTORE_VERSION
    const string save_subdir = ToString(CLEAN_SLATE_RESTORE_VERSION);
#else  // !CLEAN_SLATE_RESTORE_VERSION
    const string save_subdir = ToString(CLEAN_SLATE_VERSION);
#endif // !CLEAN_SLATE_RESTORE_VERSION

    // List out all of the existing files/directories in "CleanSlate". Remove any
    // that do not match the current version.
    for (int i = 0; i < filenames.size(); ++i) {
      if (filenames[i] != save_subdir) {
        DirRemove(JoinPath(dir, filenames[i]), true);
      }
    }

    const string dest_dir = JoinPath(dir, ToString(CLEAN_SLATE_VERSION));

#ifdef CLEAN_SLATE_RESTORE_VERSION
    {
      const string restore_dir = JoinPath(dir, ToString(CLEAN_SLATE_RESTORE_VERSION));
      NSFileManager* fm = [NSFileManager defaultManager];
      NSError* error;
      if (![fm copyItemAtPath:NewNSString(restore_dir)
                       toPath:NewNSString(dest_dir)
                        error:&error]) {
        DIE("unable to copy %s to %s: %s", restore_dir, dest_dir, error);
      }
    }
#endif // !CLEAN_SLATE_RESTORE_VERSION

    dir = dest_dir;
    DirCreate(dir);
    DirCreate(JoinPath(dir, LibraryPath()));
    DirCreate(JoinPath(dir, TmpPath()));
#else  // !CLEAN_SLATE_VERSION
    DirRemove(clean_slate_dir, true);
#endif // !CLEAN_SLATE_VERSION

    assign(dir);
  }
};

LazyStaticPtr<HomeDir> kHomeDir;

}  // namespace

string MainBundlePath(const string &filename) {
  NSString* name = [NSString stringWithUTF8String:filename.c_str()];
  NSString* path = [[NSBundle mainBundle] pathForResource:name ofType:nil];
  return ToString(path);
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
  return *kHomeDir;
}

string LibraryPath() {
  return GetDirPath(NSLibraryDirectory);
}

string LibraryDir() {
  return JoinPath(*kHomeDir, LibraryPath());
}

string LoggingDir() {
  return JoinPath(LibraryDir(), "Logs");
}

string LoggingQueueDir() {
  return JoinPath(LoggingDir(), "Queue");
}

string TmpDir() {
  return JoinPath(*kHomeDir, TmpPath());
}
