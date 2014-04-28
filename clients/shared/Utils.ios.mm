// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <cxxabi.h>
#import <execinfo.h>
#import <mach/mach.h>
#import <mach/mach_host.h>
#import <sys/stat.h>
#import <UIKit/UIDevice.h>
#import <UIKit/UIScreen.h>
#import "Callback.h"
#import "Format.h"
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "StringUtils.h"
#import "Utils.h"

namespace {

typedef Callback<void ()> DispatchCallback;

class DispatchNetworkQueue {
 public:
  DispatchNetworkQueue()
      : queue_(dispatch_queue_create("co.viewfinder.network", NULL)) {
  }

  dispatch_queue_t queue() const { return queue_; }

 private:
  dispatch_queue_t queue_;
};

LazyStaticPtr<DispatchNetworkQueue> network_queue;

void DispatchRun(void* context) {
  DispatchCallback* block = reinterpret_cast<DispatchCallback*>(context);
  (*block)();
  delete block;
}

inline void DispatchAsync(
    dispatch_queue_t queue, const DispatchBlock& block) {
  // Note(peter): dispatch_async() is just a simple wrapper around
  // dispatch_async_f() that copies the block and passes a function to run
  // it. We do something similar, but operating on std::function<> objects
  // instead.
  dispatch_async_f(queue, new DispatchCallback(block), &DispatchRun);
}

inline void DispatchAfter(
    double delay, dispatch_queue_t queue, const DispatchBlock& block) {
  dispatch_after_f(dispatch_time(DISPATCH_TIME_NOW,
                                 static_cast<int64_t>(delay * NSEC_PER_SEC)),
                   queue, new DispatchCallback(block), &DispatchRun);
}

struct DeviceInfo {
  DeviceInfo()
      : jailbroken(IsJailbroken()) {
  }

  static bool IsJailbroken() {
#if TARGET_IPHONE_SIMULATOR
    return false;
#else   // !TARGET_IPHONE_SIMULATOR
    // On jailbroken devices, "/bin/bash" is readable. On non-jailbroken
    // devices it isn't accessible.
    struct stat s;
    if (stat("/bin/bash", &s) < 0) {
      return false;
    }
    return s.st_mode & S_IFREG;
#endif  // !TARGET_IPHONE_SIMULATOR
  }

  bool jailbroken;
};

LazyStaticPtr<DeviceInfo> kDeviceInfo;

NSDictionary* DiskSpaceStats() {
  NSError* error = NULL;
  NSArray* paths = NSSearchPathForDirectoriesInDomains(
      NSDocumentDirectory, NSUserDomainMask, YES);
  NSDictionary* dictionary =
      [[NSFileManager defaultManager] attributesOfFileSystemForPath:
       [paths lastObject] error:&error];
  if (!dictionary) {
    LOG("Unable to obtain disk space stats: %s", error);
    return NULL;
  }
  return dictionary;
}

// NOTE(peter): This function destructively edits the input line.
void DemangleCxxSymbols(ostream& os, char* line) {
  for (;;) {
    char* p = strchr(line, ' ');
    if (p) {
      *p = '\0';
    }
    if (!p || p > line) {
      int status;
      char* buf = abi::__cxa_demangle(line, NULL, 0, &status);
      if (buf) {
        os << buf;
      } else {
        os << line;
      }
    }
    if (!p) {
      break;
    }
    os << " ";
    line = p + 1;
  }
}

string GetSDKVersion() {
#ifdef __IPHONE_7_0
  return "7.0";
#else
  // This is the min-sdk version we support.
  return "6.1";
#endif
}

}  // namespace

const string kIOSVersion = ToString([UIDevice currentDevice].systemVersion);
const string kSDKVersion = GetSDKVersion();

string TaskInfo() {
  task_basic_info info;
  mach_msg_type_number_t size = sizeof(info);
  kern_return_t kerr = task_info(
      mach_task_self(), TASK_BASIC_INFO, (task_info_t)&info, &size);
  if (kerr != KERN_SUCCESS) {
    return Format("task_info() failed: %s", mach_error_string(kerr));
  }
  return Format("vmem=%.1f  rmem=%.1f  ucpu=%d.%03d  scpu=%d.%03d",
                info.virtual_size / (1024.0 * 1024.0),
                info.resident_size / (1024.0 * 1024.0),
                info.user_time.seconds, info.user_time.microseconds / 1000,
                info.system_time.seconds, info.system_time.microseconds / 1000);
}

string HostInfo() {
  host_basic_info info;
  mach_msg_type_number_t count = HOST_BASIC_INFO_COUNT;
  kern_return_t kerr = host_info(
      mach_host_self(), HOST_BASIC_INFO, (host_info_t)&info, &count);
  if (kerr != KERN_SUCCESS) {
    return Format("host_info() failed: %s", mach_error_string(kerr));
  }
  return Format("memory=%.1f (%.1f) cpus=%d",
                info.memory_size / (1024.0 * 1024.0),
                info.max_mem / (1024.0 * 1024.0),
                info.avail_cpus);
}

string AppVersion() {
  // Any changes in the version format should be reflected in the backend code:
  // //viewfinder/backend/base/client_version.py
  NSDictionary* d = [[NSBundle mainBundle] infoDictionary];
#ifdef DEVELOPMENT
  const char* type = ".dev";
#elif defined(ADHOC)
  const char* type = ".adhoc";
#else   // !DEVELOPMENT && !ADHOC
  const char* type = "";
#endif  // !DEVELOPMENT && !ADHOC
  const char* jailbroken = kDeviceInfo->jailbroken ? ".jailbroken" : "";
  return Format("%s.%s%s%s",
                d[@"CFBundleShortVersionString"],
                d[@"CFBundleVersion"],
                type, jailbroken);
}

string BuildInfo() {
  NSString* path =
      [[NSBundle mainBundle] pathForResource:@"Viewfinder-Version"
       ofType:@"plist"];
  NSDictionary* d = [NSDictionary dictionaryWithContentsOfFile:path];
  return Format("built at %s: %s/%s",
                d[@"BuildDate"],
                d[@"BuildBranch"],
                d[@"BuildRevision"]);
}

string BuildRevision() {
  NSString* path =
      [[NSBundle mainBundle] pathForResource:@"Viewfinder-Version"
       ofType:@"plist"];
  NSDictionary* d = [NSDictionary dictionaryWithContentsOfFile:path];
  return ToString(d[@"BuildRevision"]);
}

int64_t FreeDiskSpace() {
  NSDictionary* d = DiskSpaceStats();
  if (!d) {
    return -1;
  }
  return [d[NSFileSystemFreeSize] longLongValue];
}

int64_t TotalDiskSpace() {
  NSDictionary* d = DiskSpaceStats();
  if (!d) {
    return -1;
  }
  return [d[NSFileSystemSize] longLongValue];
}

bool IsJailbroken() {
  return kDeviceInfo->jailbroken;
}

bool dispatch_is_main_thread() {
  return [NSThread isMainThread];
}

void dispatch_main(const DispatchBlock& block) {
  if (dispatch_is_main_thread()) {
    block();
  } else {
    DispatchAsync(dispatch_get_main_queue(), block);
  }
}

void dispatch_main_async(const DispatchBlock& block) {
  DispatchAsync(dispatch_get_main_queue(), block);
}

void dispatch_network(const DispatchBlock& block) {
  DispatchAsync(network_queue->queue(), block);
}

void dispatch_high_priority(const DispatchBlock& block) {
  DispatchAsync(
      dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0),
      block);
}

void dispatch_low_priority(const DispatchBlock& block) {
  DispatchAsync(
      dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_LOW, 0),
      block);
}

void dispatch_background(const DispatchBlock& block) {
  DispatchAsync(
      dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_BACKGROUND, 0),
      block);
}

void dispatch_after_main(double delay, const DispatchBlock& block) {
  DispatchAfter(delay, dispatch_get_main_queue(), block);
}

void dispatch_after_network(double delay, const DispatchBlock& block) {
  DispatchAfter(delay, network_queue->queue(), block);
}

void dispatch_after_high_priority(double delay, const DispatchBlock& block) {
  DispatchAfter(delay,
                dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0),
                block);
}

void dispatch_after_low_priority(double delay, const DispatchBlock& block) {
  DispatchAfter(delay,
                dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_LOW, 0),
                block);
}

void dispatch_after_background(double delay, const DispatchBlock& block) {
  DispatchAfter(delay,
                dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_BACKGROUND, 0),
                block);
}

void dispatch_autoreleasepool(const DispatchBlock& block) {
  @autoreleasepool {
    block();
  }
}

ostream& operator<<(ostream& os, const CGPoint& p) {
  os << "<" << p.x << " " << p.y << ">";
  return os;
}

ostream& operator<<(ostream& os, const CGSize& s) {
  os << "<" << s.width << " " << s.height << ">";
  return os;
}

ostream& operator<<(ostream& os, const CGRect& r) {
  os << "<" << r.origin.x << " " << r.origin.y
     << " " << r.size.width << " " << r.size.height << ">";
  return os;
}

// An output operator for NSObject and derived classes.
ostream& operator<<(ostream& os, id obj) {
  if (!obj) {
    os << "(null)";
  } else {
    os << [[obj description] UTF8String];
  }
  return os;
}

ostream& operator<<(ostream& os, NSString* str) {
  if (!str) {
    os << "(null)";
  } else {
    os << [str UTF8String];
  }
  return os;
}

ostream& operator<<(ostream& os, NSData* data) {
  if (!data) {
    os << "(null)";
  } else {
    os.write((const char*)data.bytes, data.length);
  }
  return os;
}

ostream& operator<<(ostream& os, const NSRange& r) {
  os << r.location << "," << r.length;
  return os;
}

ostream& operator<<(ostream& os, const BacktraceData& bt) {
  // Skip the first frame which is internal to Backtrace().
  char** strs = backtrace_symbols(bt.callstack, bt.frames);
  for (int i = 1; i < bt.frames; ++i) {
    DemangleCxxSymbols(os, strs[i]);
    os << "\n";
  }
  free(strs);
  return os;
}

BacktraceData Backtrace() {
  // NOTE(peter): The obvious design would be to have a Backtrace class and put
  // this initialization in the constructor. Unfortunately, the compiler
  // creates 1 or 2 stackframes for that constructor depending on optimization
  // levels. Using a Backtrace() function deterministically adds a single stack
  // frame which can be skipped in the operator<<() method.
  BacktraceData d;
  d.frames = backtrace(d.callstack, 64);
  return d;
}

// local variables:
// mode: c++
// end:
