// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_FILE_UTILS_H
#define VIEWFINDER_FILE_UTILS_H

#import "Utils.h"

namespace google {
namespace protobuf {
class MessageLite;
}  // namespace protobuf
}  // namespace google

int FileCreate(const string& path, bool exclude_from_backup = true);
bool FileExists(const string& path);
int64_t FileSize(const string& path);
int64_t FileSize(int fd);
bool FileRename(const string& old_path, const string& new_path);
bool FileRemove(const string& path);
void FileExcludeFromBackup(const string& path, bool is_dir = false);
// Creates the given directory.  Returns true if the directory was created or
// already existed, otherwise VLOGs a warning and returns false.
bool DirCreate(const string& path, int mode = 0755,
               bool exclude_from_backup = true);
bool DirExists(const string& path);
bool DirRemove(const string& path, bool recursive = false,
               int* files = NULL, int* dirs = NULL);
bool DirList(const string& path, vector<string>* files);
void DirExcludeFromBackup(const string& path, bool recursive = false);
bool WriteStringToFD(int fd, const Slice& str, bool silent = false);
bool WriteStringToFile(const string& path, const Slice& str,
                       bool exclude_from_backup = true);
bool WriteProtoToFile(const string& path,
                      const google::protobuf::MessageLite& message,
                      bool exclude_from_backup = true);
#ifdef __OBJC__
bool WriteDataToFile(const string& path, NSData* data,
                     bool exclude_from_backup = true);
#endif  // __OBJC__
bool ReadFileToString(const string& path, string* str);
string ReadFileToString(const string& path);
bool ReadFileToProto(const string& path, google::protobuf::MessageLite* message);
#ifdef __OBJC__
NSData* ReadFileToData(const string& path);
#endif  // __OBJC__

#endif // VIEWFINDER_FILE_UTILS_H
