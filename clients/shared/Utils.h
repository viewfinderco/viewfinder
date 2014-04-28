// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_UTILS_H
#define VIEWFINDER_UTILS_H


#import <functional>
#import <iostream>
#import <string>
#import <vector>
#import <re2/stringpiece.h>

#ifdef OS_IOS
#import <CoreGraphics/CGGeometry.h>
#ifdef __OBJC__
#import <Foundation/NSRange.h>
#endif  // __OBJC__
#endif  // OS_IOS

using std::ostream;
using std::pair;
using std::string;
using std::vector;

// Import re2::StringPiece using the more compact name Slice.
typedef re2::StringPiece Slice;

namespace google {
namespace protobuf {
class Message;
}  // namespace protobuf
}  // namespace google

class ActivityId;
class CommentId;
class EpisodeId;
class EpisodeStats;
class Location;
class PhotoId;
class Placemark;
class ViewpointId;

struct ServerIdFormat {
  ServerIdFormat(const Slice& i)
      : id(i) {
  }
  const Slice id;
};

#define ARRAYSIZE(a)                                 \
  ((sizeof(a) / sizeof(*(a))) /                      \
   static_cast<size_t>(!(sizeof(a) % sizeof(*(a)))))

// COMPILE_ASSERT causes a compile error about msg if expr is not true.
template<bool> struct CompileAssert {};
#define COMPILE_ASSERT(expr, msg) \
  typedef CompileAssert<(bool(expr))> msg[bool(expr) ? 1 : -1]

typedef std::function<void ()> DispatchBlock;

// Returns true if the current thread is the main thread.
bool dispatch_is_main_thread();

// Runs the specified block on the main thread. If the current thread is the
// main thread, the block is run synchronously.
void dispatch_main(const DispatchBlock& block);
// Runs the specified block on the main thread. The block is always run
// asynchronously.
void dispatch_main_async(const DispatchBlock& block);

// Runs the specified block on the network queue thread.
void dispatch_network(const DispatchBlock& block);

// Runs the specified block on a background thread at high priority.
void dispatch_high_priority(const DispatchBlock& block);

// Runs the specified block on a background thread at low priority.
void dispatch_low_priority(const DispatchBlock& block);

// Runs the specified block on a background thread at background (lower than "low") priority.
void dispatch_background(const DispatchBlock& block);

// Runs the specified block on the main/network/high/low-priority/background queue
// after the the specified delay (in seconds) has elapsed.
void dispatch_after_main(double delay, const DispatchBlock& block);
void dispatch_after_network(double delay, const DispatchBlock& block);
void dispatch_after_high_priority(double delay, const DispatchBlock& block);
void dispatch_after_low_priority(double delay, const DispatchBlock& block);
void dispatch_after_background(double delay, const DispatchBlock& block);

#if defined(OS_IOS)

// Runs the specified block inside of an "@autoreleasepool { }" block.
void dispatch_autoreleasepool(const DispatchBlock& block);

#elif defined(OS_ANDROID)

// Auto release pools are ObjectiveC-ism and do not exist on Android.
inline void dispatch_autoreleasepool(const DispatchBlock& block) {
  block();
}

#endif  // defined(OS_ANDROID)

ostream& operator<<(ostream& os, const ActivityId& i);
ostream& operator<<(ostream& os, const CommentId& i);
ostream& operator<<(ostream& os, const EpisodeId& i);
ostream& operator<<(ostream& os, const EpisodeStats& s);
ostream& operator<<(ostream& os, const PhotoId& i);
ostream& operator<<(ostream& os, const ViewpointId& i);
ostream& operator<<(ostream& os, const ServerIdFormat& f);
ostream& operator<<(ostream& os, const Location& l);
ostream& operator<<(ostream& os, const Placemark& p);
ostream& operator<<(ostream& os, const google::protobuf::Message& msg);

string AppVersion();
int64_t FreeDiskSpace();
int64_t TotalDiskSpace();

#ifdef OS_IOS

extern const string kIOSVersion;
extern const string kSDKVersion;

string TaskInfo();
string HostInfo();
string BuildInfo();
string BuildRevision();
bool IsJailbroken();

ostream& operator<<(ostream& os, const CGPoint& p);
ostream& operator<<(ostream& os, const CGSize& s);
ostream& operator<<(ostream& os, const CGRect& r);

#ifdef __OBJC__

@class NSData;
@class NSString;

// An output operator for NSObject and derived classes.
ostream& operator<<(ostream& os, id obj);
ostream& operator<<(ostream& os, NSString* data);
ostream& operator<<(ostream& os, NSData* data);
ostream& operator<<(ostream& os, const NSRange& r);

#endif  // __OBJC__

#endif // OS_IOS

struct BacktraceData {
  void* callstack[64];
  int frames;
};

ostream& operator<<(ostream& os, const BacktraceData& bt);

BacktraceData Backtrace();

int utfnlen(const char* s, int n);
inline int utfnlen(const Slice& s) {
  return utfnlen(s.data(), s.size());
}

// Extract and return a single utf rune from a string.
int utfnext(Slice* s);
inline int utfnext(const Slice& s) {
  Slice t(s);
  return utfnext(&t);
}

#endif // VIEWFINDER_UTILS_H
