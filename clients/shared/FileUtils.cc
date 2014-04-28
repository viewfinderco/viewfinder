// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <dirent.h>
#import <errno.h>
#import <fcntl.h>
#import <sys/stat.h>
#import <unistd.h>
#import <google/protobuf/message_lite.h>
#import "FileUtils.h"
#import "Logging.h"

int FileCreate(const string& path, bool exclude_from_backup) {
  const int new_fd = open(path.c_str(), O_CREAT|O_WRONLY, 0644);
  if (new_fd < 0) {
    VLOG("open failed: %s: %d (%s)", path, errno, strerror(errno));
    return -1;
  }
  if (exclude_from_backup) {
    FileExcludeFromBackup(path);
  }
  return new_fd;
}

bool FileExists(const string& path) {
  struct stat s;
  if (stat(path.c_str(), &s) < 0) {
    return false;
  }
  return s.st_mode & S_IFREG;
}

int64_t FileSize(const string& path) {
  struct stat s;
  if (stat(path.c_str(), &s) < 0) {
    if (errno != ENOENT) {
      VLOG("stat failed: %s: %d (%s)", path, errno, strerror(errno));
    }
    return -1;
  }
  return s.st_size;
}

int64_t FileSize(int fd) {
  struct stat s;
  if (fstat(fd, &s) < 0) {
    VLOG("fstat failed: fd %d: %d (%s)", fd, errno, strerror(errno));
    return -1;
  }
  return s.st_size;
}

bool FileRename(const string& old_path, const string& new_path) {
  if (rename(old_path.c_str(), new_path.c_str()) < 0) {
    VLOG("rename failed: %s -> %s: %d (%s)",
         old_path, new_path, errno, strerror(errno));
    return false;
  }
  return true;
}

bool FileRemove(const string& path) {
  if (unlink(path.c_str()) < 0) {
    if (errno != ENOENT) {
      VLOG("remove failed: %s: %d (%s)", path, errno, strerror(errno));
    }
    return false;
  }
  return true;
}

bool DirCreate(const string& path, int mode, bool exclude_from_backup) {
  if (mkdir(path.c_str(), mode) < 0) {
    if (errno != EEXIST) {
      VLOG("mkdir failed: %s: %d (%s)", path, errno, strerror(errno));
      return false;
    }
    return true;
  }
  if (exclude_from_backup) {
    FileExcludeFromBackup(path, true);
  }
  return true;
}

bool DirExists(const string& path) {
  struct stat s;
  if (stat(path.c_str(), &s) < 0) {
    return false;
  }
  return s.st_mode & S_IFDIR;
}

bool DirRemove(const string& path, bool recursive, int* files, int* dirs) {
  if (recursive) {
    DIR* dir = opendir(path.c_str());
    if (!dir) {
      return false;
    }
    struct dirent* r = NULL;
    while ((r = readdir(dir)) != 0) {
      const string name(r->d_name);
      if (name == "." || name == "..") {
        continue;
      }
      const string subpath(path + "/" + name);
      struct stat s;
      if (lstat(subpath.c_str(), &s) < 0) {
        continue;
      }
      if (s.st_mode & S_IFDIR) {
        if (!DirRemove(subpath, true, files, dirs)) {
          break;
        }
      } else {
        if (!FileRemove(subpath)) {
          break;
        }
        if (files) {
          *files += 1;
        }
      }
    }
    closedir(dir);
  }

  if (rmdir(path.c_str()) < 0) {
    LOG("rmdir failed: %s: %d (%s)", path, errno, strerror(errno));
    return false;
  }
  if (dirs) {
    *dirs += 1;
  }
  return true;
}

bool DirList(const string& path, vector<string>* files) {
  DIR* dir = opendir(path.c_str());
  if (!dir) {
    return false;
  }
  struct dirent* r = NULL;
  while ((r = readdir(dir))  != 0) {
    const string name(r->d_name);
    if (name == "." || name == "..") {
      continue;
    }
    files->push_back(name);
  }
  closedir(dir);
  return true;
}

bool WriteStringToFD(int fd, const Slice& str, bool silent) {
  const char* p = str.data();
  int n = str.size();
  while (n > 0) {
    ssize_t res = write(fd, p, n);
    if (res < 0) {
      if (!silent) {
        LOG("write failed: %d (%s)", errno, strerror(errno));
      }
      break;
    }
    p += res;
    n -= res;
  }
  return (n == 0);
}

bool WriteStringToFile(const string& path, const Slice& str,
                       bool exclude_from_backup) {
  const string tmp_path(path + ".tmp");
  int fd = FileCreate(tmp_path, exclude_from_backup);
  if (fd < 0) {
    LOG("open failed: %s: %d (%s)", tmp_path, errno, strerror(errno));
    return false;
  }
  const bool res = WriteStringToFD(fd, str);
  close(fd);
  if (!res) {
    FileRemove(tmp_path);
    return false;
  }
  return FileRename(tmp_path, path);
}

bool WriteProtoToFile(
    const string& path, const google::protobuf::MessageLite& message,
    bool exclude_from_backup) {
  return WriteStringToFile(
      path, message.SerializeAsString(), exclude_from_backup);
}

bool ReadFileToString(const string& path, string* str) {
  int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) {
    // LOG("open failed: %s: %d (%s)", path, errno, strerror(errno));
    return false;
  }
  struct stat s;
  if (fstat(fd, &s) < 0) {
    LOG("stat failed: %s: %d (%s)", path, errno, strerror(errno));
    return false;
  }

  int n = s.st_size;
  str->resize(n);
  char* p = &(*str)[0];

  while (n > 0) {
    ssize_t res = read(fd, p, n);
    if (res < 0) {
      LOG("read failed: %s: %d (%s)", path, errno, strerror(errno));
      break;
    }
    p += res;
    n -= res;
  }
  close(fd);
  return n == 0;
}

string ReadFileToString(const string& path) {
  string s;
  if (!ReadFileToString(path, &s)) {
    return string();
  }
  return s;
}

bool ReadFileToProto(
    const string& path, google::protobuf::MessageLite* message) {
  string s;
  if (!ReadFileToString(path, &s)) {
    return false;
  }
  return message->ParseFromString(s);
}
