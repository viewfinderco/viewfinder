// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <dirent.h>
#import <errno.h>
#import <fcntl.h>
#import <sys/stat.h>
#import <sys/xattr.h>
#import <unistd.h>
#import "FileUtils.h"
#import "Logging.h"

void FileExcludeFromBackup(const string& path, bool is_dir) {
  if (kIOSVersion == "5.0.1") {
    const char* name = "com.apple.MobileBackup";
    uint8_t value = 1;
    if (setxattr(path.c_str(), name, &value, sizeof(value), 0, 0) != 0) {
      LOG("setxattr failed: %s: %d (%s)", path, errno, strerror(errno));
    }
  } else if (kIOSVersion >= "5.1") {
    NSURL* url = [NSURL fileURLWithPath:NewNSString(path) isDirectory:is_dir];
    NSError* error = NULL;
    if (![url setResourceValue:[NSNumber numberWithBool: YES]
                        forKey:NSURLIsExcludedFromBackupKey
                         error:&error]) {
      LOG("exclude from backup failed: %s: %s", path, error);
    }
  }
}

void DirExcludeFromBackup(const string& path, bool recursive) {
  if (recursive) {
    DIR* dir = opendir(path.c_str());
    if (!dir) {
      return;
    }
    struct dirent* r = NULL;
    while ((r = readdir(dir)) != 0) {
      const string name(r->d_name, r->d_namlen);
      if (name == "." || name == "..") {
        continue;
      }
      const string subpath(path + "/" + name);
      struct stat s;
      if (lstat(subpath.c_str(), &s) < 0) {
        continue;
      }
      if (s.st_mode & S_IFDIR) {
        DirExcludeFromBackup(subpath, true);
      } else {
        FileExcludeFromBackup(subpath);
      }
    }
    closedir(dir);
  }

  FileExcludeFromBackup(path, true);
}

bool WriteDataToFile(const string& path, NSData* data,
                     bool exclude_from_backup) {
  return WriteStringToFile(
      path, Slice((const char*)data.bytes, data.length),
      exclude_from_backup);
}

NSData* ReadFileToData(const string& path) {
  int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) {
    // LOG("open failed: %s: %d (%s)", path, errno, strerror(errno));
    return NULL;
  }
  struct stat s;
  if (fstat(fd, &s) < 0) {
    LOG("stat failed: %s: %d (%s)", path, errno, strerror(errno));
    return NULL;
  }

  int n = s.st_size;
  char* p = reinterpret_cast<char*>(malloc(n));
  NSData* data = [[NSData alloc] initWithBytesNoCopy:p
                                              length:n
                                        freeWhenDone:YES];

  while (n > 0) {
    ssize_t res = read(fd, p, n);
    if (res < 0) {
      LOG("read failed: %s: %d (%s)", path, errno, strerror(errno));
      data = NULL;
      break;
    }
    p += res;
    n -= res;
  }
  close(fd);
  return data;
}
