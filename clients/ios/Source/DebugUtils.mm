// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <dlfcn.h>
#import <fcntl.h>
#if TARGET_IPHONE_SIMULATOR
#import <libproc.h>
#endif // TARGET_IPHONE_SIMULATOR
#import <mach/mach.h>
#import <mach/vm_map.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <sys/param.h>
#import <unordered_map>
#import <CoreData/CoreData.h>
#import "DebugUtils.h"
#import "Defines.h"
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "Mutex.h"
#import "STLUtils.h"
#import "Timer.h"
#import "Utils.h"
#import "ValueUtils.h"

namespace {

const int64_t kKilobyte = 1024LL;
const int64_t kMegabyte = 1024 * kKilobyte;
const int64_t kGigabyte = 1024 * kMegabyte;

NSString* const kNetworkInjectVersionKey =
    @"co.viewfinder.Viewfinder.network_inject_version";
NSString* const kNetworkInjectClassesKey =
    @"co.viewfinder.Viewfinder.network_inject_classes";

class TaskVMRegionTracker {
  struct RegionInfo {
    RegionInfo()
        : size(0),
          resident(0),
          dirty(0) {
    }
    void Increment(double s, double r, double d) {
      size += s;
      resident += r;
      dirty += d;
    }
    double size;
    double resident;
    double dirty;
  };

  typedef std::unordered_map<string, RegionInfo> NameToSizeMap;

 public:
  TaskVMRegionTracker()
      : pid_(getpid()),
        task_(mach_task_self()),
        page_size_(getpagesize()) {
  }

  string Track(bool verbose) {
    MutexLock l(&mu_);

    // Make a copy of the previous region snapshot, but clear out each
    // entry. This ensures that we'll show a negative delta for any entry that
    // no longer appears.
    NameToSizeMap name_to_size(last_name_to_size_);
    for (NameToSizeMap::iterator iter(name_to_size.begin());
         iter != name_to_size.end();
         ++iter) {
      iter->second = RegionInfo();
    }

    vm_address_t address = 0;
    natural_t depth = 0;
    string s;

    // Walk through the address space gathering info about each region.
    for (vm_size_t size = 0; ; address += size) {
      struct vm_region_submap_info_64 info;
      mach_msg_type_number_t count = VM_REGION_SUBMAP_INFO_COUNT_64;
      kern_return_t krc = vm_region_recurse_64(
          task_, &address, &size, &depth, (vm_region_info_64_t)&info, &count);
      if (krc != KERN_SUCCESS) {
        break;
      }
      if (info.is_submap) {
        depth += 1;
        continue;
      }

      // Is this even necessary? Copied from psutil
      // (https://code.google.com/p/psutil).
      if (info.share_mode == SM_COW && info.ref_count == 1) {
        // Treat single reference SM_COW as SM_PRIVATE
        info.share_mode = SM_PRIVATE;
      }

      // Translate the region into a textual name. These heuristics try to
      // match the output of vmmap(1).
      string name;
      if (info.user_tag == 0 ||
          info.user_tag == VM_MEMORY_SHARED_PMAP ||
          info.user_tag == VM_MEMORY_UNSHARED_PMAP ||
          info.is_submap) {
        if (info.protection & VM_PROT_EXECUTE) {
          name = "__TEXT";
        } else if (info.protection & VM_PROT_WRITE) {
          name = "__DATA";
        } else {
          name = "__LINKEDIT";
        }
      } else {
        name = RegionName(info.user_tag, info.share_mode);
      }

      double resident = info.pages_resident * page_size_;
      double dirty = info.pages_dirtied * page_size_;
      const char* path = NULL;

      // Look up the mapping associated with the address. dladdr() allows us to
      // lookup any shared library associated with the address.
      Dl_info dli;
      if (dladdr((const void*)address, &dli)) {
        path = dli.dli_fname;
      }
#if TARGET_IPHONE_SIMULATOR
      // On the simulator we can use the more general
      // proc_regionfilename(). That function does not exist on devices.
      char buf[PATH_MAX];
      if (!path) {
        memset(buf, 0, sizeof(buf));
        if (proc_regionfilename(pid_, address, buf, sizeof(buf)) > 0) {
          path = buf;
          name = "Mapped File";
        }
      }
#endif  // TARGET_IPHONE_SIMULATOR

      if (verbose) {
        s += Format(
            "%-20s %08x-%08x [%7s %7s %7s] %c%c%c SM=%s",
            name, address, address + size,
            FormatSize(size), FormatSize(resident), FormatSize(dirty),
            (info.protection & VM_PROT_READ) ? 'r' : '-',
            (info.protection & VM_PROT_WRITE) ? 'w' : '-',
            (info.protection & VM_PROT_EXECUTE) ? 'x' : '-',
            ShareModeToString(info.share_mode));
        if (path) {
          s += Format("  %s", path);
        }
        s += "\n";
      }

      name_to_size[name].Increment(size, resident, dirty);
      name_to_size["Total"].Increment(size, resident, dirty);
    }
    if (verbose) {
      s += "\n";
    }

    // Sort the region names by virtual address space size.
    vector<pair<double, string> > size_and_name;
    for (NameToSizeMap::const_iterator iter(name_to_size.begin());
         iter != name_to_size.end();
         ++iter) {
      size_and_name.push_back(std::make_pair(iter->second.size, iter->first));
    }
    std::sort(size_and_name.begin(), size_and_name.end(),
              std::greater<pair<double, string> >());

    // NOTE(pmattis): Output the info (current and delta) for each region
    // name. Note that the "Total" does not match up with the vmem and rmem
    // lines from TaskInfo(). The virtual address space for "Total" is smaller
    // because it does not contain all of the address space for submap
    // regions. But this matches up with the "VM Tracker" Instrument. The
    // resident size for "Total" is larger than rmem and I'm not sure
    // why. Regardless, it matches up with the "VM Tracker" Instrument.
    for (int i = 0; i < size_and_name.size(); ++i) {
      const string& name = size_and_name[i].second;
      const RegionInfo* info = FindPtrOrNull(name_to_size, name);
      if (!info) {
        continue;
      }
      const RegionInfo last = FindOrDefault(last_name_to_size_, name, RegionInfo());
      s += Format("%-20s %10s %s %10s %s %10s %s\n",
                  size_and_name[i].second,
                  FormatSize(info->size),
                  FormatDelta(info->size, last.size),
                  FormatSize(info->resident),
                  FormatDelta(info->resident, last.resident),
                  FormatSize(info->dirty),
                  FormatDelta(info->dirty, last.dirty));
    }

    last_name_to_size_ = name_to_size;
    return s;
  }

 private:
  static string RegionName(int tag, int share_mode) {
    switch (tag) {
      case VM_MEMORY_STACK:
        if (share_mode == SM_EMPTY) {
          return "Stack Guard";
        }
        return "Stack";
      case VM_MEMORY_MALLOC:
        return "Malloc";
      case VM_MEMORY_MALLOC_SMALL:
        return "Malloc Small";
      case VM_MEMORY_MALLOC_LARGE:
        return "Malloc Large";
      case VM_MEMORY_MALLOC_HUGE:
        return "Malloc Huge";
      case VM_MEMORY_MALLOC_TINY:
        return "Malloc Tiny";
      case VM_MEMORY_TCMALLOC:
        return "TCMalloc";
      case VM_MEMORY_IOKIT:
        return "IOKit";
      case VM_MEMORY_JAVASCRIPT_CORE:
      case VM_MEMORY_JAVASCRIPT_JIT_EXECUTABLE_ALLOCATOR:
      case VM_MEMORY_JAVASCRIPT_JIT_REGISTER_FILE:
        return "Javascript";
      case VM_MEMORY_SQLITE:
        return "SQLite";
      case VM_MEMORY_COREGRAPHICS:
      case VM_MEMORY_COREGRAPHICS_DATA:
      case VM_MEMORY_COREGRAPHICS_SHARED:
      case VM_MEMORY_COREGRAPHICS_FRAMEBUFFERS:
      case VM_MEMORY_COREGRAPHICS_BACKINGSTORES:
        return "CoreGraphics";
      case VM_MEMORY_IMAGEIO:
        return "ImageIO";
      case VM_MEMORY_ASSETSD:
        return "Assetsd";
      case VM_MEMORY_LAYERKIT:
        return "CALayer";
      case VM_MEMORY_CGIMAGE:
        return "CGImage";
      case VM_MEMORY_GLSL:
        return "GLSL";
      case VM_MEMORY_OS_ALLOC_ONCE:
        return "OS Alloc Once";
      case VM_MEMORY_LIBDISPATCH:
        return "Dispatch";
      default:
        return Format("Tag=%d", tag);
    }
  }

  static const char* ShareModeToString(int share_mode) {
    switch (share_mode) {
      case SM_COW:              return "COW";
      case SM_PRIVATE:          return "PRV";
      case SM_EMPTY:            return "NUL";
      case SM_SHARED:           return "SHM";
      case SM_TRUESHARED:       return "SHM";
      case SM_PRIVATE_ALIASED:  return "ALI";
      case SM_SHARED_ALIASED:   return "S/A";
      default:                  return "???";
    }
  }

  static string FormatSize(double v) {
    if (v < kMegabyte) {
      return Format("%.1fK", v / kKilobyte);
    } else if (v < kGigabyte) {
      return Format("%.1fM", v / kMegabyte);
    }
    return  Format("%.1fG", v / kGigabyte);
  }

  static string FormatDelta(double new_val, double old_val) {
    if (new_val == old_val) {
      return Format("%8s", "");
    }
    const double v = new_val - old_val;
    const double m = fabs(v);
    if (m < kMegabyte) {
      return Format("%+7.1fK", v / kKilobyte);
    } else if (m < kGigabyte) {
      return Format("%+7.1fM", v / kMegabyte);
    }
    return  Format("%+7.1fG", v / kGigabyte);
  }

 private:
  Mutex mu_;
  const pid_t pid_;
  const vm_map_t task_;
  const vm_size_t page_size_;
  NameToSizeMap last_name_to_size_;
};

LazyStaticPtr<TaskVMRegionTracker> tracker;

#ifndef APPSTORE

SEL MakeSwizzledSelector(SEL selector) {
  return NSSelectorFromString(
      Format("_vf_swizzle_%x_%@", arc4random(), NSStringFromSelector(selector)));
}

// TODO(peter): I'm not sure if this is necessary. The idea was taken from
// PonyDebugger. It protects against recursive calling of the swizzled
// selector.
void SwizzleGuard(NSObject* object, SEL selector, void (^implementation)()) {
  if (!objc_getAssociatedObject(object, selector)) {
    objc_setAssociatedObject(
        object, selector, object, OBJC_ASSOCIATION_ASSIGN);
    implementation();
    objc_setAssociatedObject(
        object, selector, NULL, OBJC_ASSOCIATION_ASSIGN);
  }
}

void ReplaceImplementation(
    SEL selector, SEL swizzled_selector, Class c,
    struct objc_method_description method_description,
    id implementation_block, id undefined_block) {
  if ([c instancesRespondToSelector:selector]) {
    unsigned int num_methods = 0;
    Method* methods = class_copyMethodList(c, &num_methods);
    bool implements_selector = false;

    for (int i = 0; i < num_methods; i++) {
      SEL method_selector = method_getName(methods[i]);
      if (selector == method_selector) {
        implements_selector = true;
        break;
      }
    }

    free(methods);
    if (!implements_selector) {
      // The class responds to "selector", but does not actually have an
      // implementation of "selector". Huh? It just means "c" is a sub-class of
      // a class which implements "selector". We'll already be swizzling the
      // super-class selector, so there is no need to swizzle "c" as well.
      return;
    }
  }

  const IMP implementation = imp_implementationWithBlock(
      [c instancesRespondToSelector:selector] ? implementation_block : undefined_block);
  const Method old_method = class_getInstanceMethod(c, selector);
  if (old_method) {
    class_addMethod(c, swizzled_selector, implementation, method_description.types);
    const Method new_method = class_getInstanceMethod(c, swizzled_selector);
    method_exchangeImplementations(old_method, new_method);
  } else {
    class_addMethod(c, selector, implementation, method_description.types);
  }
}

static char kAssociatedURLKey;

void SetAssociatedURL(NSURLConnection* conn, NSURL* url) {
  objc_setAssociatedObject(conn, &kAssociatedURLKey, url, OBJC_ASSOCIATION_RETAIN);
}

NSURL* GetAssociatedURL(NSURLConnection* conn) {
  return (NSURL*)objc_getAssociatedObject(conn, &kAssociatedURLKey);
}

void InjectWillSendRequest(Class c) {
  SEL selector = @selector(connection:willSendRequest:redirectResponse:);
  SEL swizzled_selector = MakeSwizzledSelector(selector);

  Protocol* protocol = @protocol(NSURLConnectionDataDelegate);
  if (!protocol) {
    protocol = @protocol(NSURLConnectionDelegate);
  }

  struct objc_method_description method_description =
      protocol_getMethodDescription(protocol, selector, NO, YES);

  typedef NSURLRequest* (^WillSendRequestBlock)(
      id<NSURLConnectionDelegate>, NSURLConnection*, NSURLRequest*, NSURLResponse*);

  WillSendRequestBlock undefined = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSURLRequest* request,
      NSURLResponse* response) {
    SwizzleGuard(slf, selector, ^{
        SetAssociatedURL(connection, request.URL);
        VLOG("%p: %s: will send request",
             (__bridge void*)connection, request.URL);
      });
    return request;
  };

  WillSendRequestBlock implementation = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSURLRequest* request,
      NSURLResponse* response) {
    NSURLRequest* r = objc_msgSend(slf, swizzled_selector, connection, request, response);
    undefined(slf, connection, request, response);
    return r;
  };

  ReplaceImplementation(
      selector, swizzled_selector, c,
      method_description, implementation, undefined);
}

void InjectDidReceiveResponse(Class c) {
  SEL selector = @selector(connection:didReceiveResponse:);
  SEL swizzled_selector = MakeSwizzledSelector(selector);

  Protocol* protocol = @protocol(NSURLConnectionDataDelegate);
  if (!protocol) {
    protocol = @protocol(NSURLConnectionDelegate);
  }

  struct objc_method_description method_description =
      protocol_getMethodDescription(protocol, selector, NO, YES);

  typedef void (^DidReceiveResponseBlock)(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSURLResponse* response);

  DidReceiveResponseBlock undefined = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSURLResponse* response) {
    SwizzleGuard(slf, selector, ^{
        int status = -1;
        if ([response isKindOfClass:[NSHTTPURLResponse class]]) {
          status = [(NSHTTPURLResponse*)response statusCode];
        }
        VLOG("%p: %s: did receive response: %d",
             (__bridge void*)connection, response.URL, status);
      });
  };

  DidReceiveResponseBlock implementation = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSURLResponse* response) {
    undefined(slf, connection, response);
    objc_msgSend(slf, swizzled_selector, connection, response);
  };

  ReplaceImplementation(
      selector, swizzled_selector, c,
      method_description, implementation, undefined);
}

void InjectDidReceiveData(Class c) {
  SEL selector = @selector(connection:didReceiveData:);
  SEL swizzled_selector = MakeSwizzledSelector(selector);

  Protocol* protocol = @protocol(NSURLConnectionDataDelegate);
  if (!protocol) {
    protocol = @protocol(NSURLConnectionDelegate);
  }

  struct objc_method_description method_description =
      protocol_getMethodDescription(protocol, selector, NO, YES);

  typedef void (^DidReceiveDataBlock)(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSData* data);

  DidReceiveDataBlock undefined = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSData* data) {
    VLOG("%p: %s: did receive data: %d",
         (__bridge void*)connection, GetAssociatedURL(connection), data.length);
  };

  DidReceiveDataBlock implementation = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSData* data) {
    undefined(slf, connection, data);
    objc_msgSend(slf, swizzled_selector, connection, data);
  };

  ReplaceImplementation(
      selector, swizzled_selector, c,
      method_description, implementation, undefined);
}

void InjectDidFinishLoading(Class c) {
  SEL selector = @selector(connectionDidFinishLoading:);
  SEL swizzled_selector = MakeSwizzledSelector(selector);

  Protocol* protocol = @protocol(NSURLConnectionDataDelegate);
  if (!protocol) {
    protocol = @protocol(NSURLConnectionDelegate);
  }

  struct objc_method_description method_description =
      protocol_getMethodDescription(protocol, selector, NO, YES);

  typedef void (^DidFinishLoadingBlock)(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection);

  DidFinishLoadingBlock undefined = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection) {
    VLOG("%p: %s: did finish loading",
         (__bridge void*)connection, GetAssociatedURL(connection));
  };

  DidFinishLoadingBlock implementation = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection) {
    undefined(slf, connection);
    objc_msgSend(slf, swizzled_selector, connection);
  };

  ReplaceImplementation(
      selector, swizzled_selector, c,
      method_description, implementation, undefined);
}

void InjectDidFailWithError(Class c) {
  SEL selector = @selector(connection:didFailWithError:);
  SEL swizzled_selector = MakeSwizzledSelector(selector);

  Protocol* protocol = @protocol(NSURLConnectionDelegate);

  struct objc_method_description method_description =
      protocol_getMethodDescription(protocol, selector, NO, YES);

  typedef void (^DidFailWithErrorBlock)(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSError* error);

  DidFailWithErrorBlock undefined = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSError* error) {
    VLOG("%p: %s: did fail with error: %s",
         (__bridge void*)connection, GetAssociatedURL(connection),
         error.localizedDescription);
  };

  DidFailWithErrorBlock implementation = ^(
      id<NSURLConnectionDelegate> slf,
      NSURLConnection* connection,
      NSError* error) {
    undefined(slf, connection, error);
    objc_msgSend(slf, swizzled_selector, connection, error);
  };

  ReplaceImplementation(
      selector, swizzled_selector, c,
      method_description, implementation, undefined);
}

void InjectIntoDelegateClass(Class c) {
  InjectWillSendRequest(c);
  InjectDidReceiveData(c);
  InjectDidReceiveResponse(c);
  InjectDidFinishLoading(c);
  InjectDidFailWithError(c);
}

string InjectVersion() {
  return Format("%s/%s", kIOSVersion, BuildRevision());
}

bool HaveInjectClasses() {
  NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
  NSString* inject_version = [defaults stringForKey:kNetworkInjectVersionKey];
  if (!inject_version) {
    return false;
  }
  if (ToString(inject_version) != InjectVersion()) {
    return false;
  }
  if (![defaults stringArrayForKey:kNetworkInjectClassesKey]) {
    return false;
  }
  return true;
}

vector<string> GetInjectClasses() {
  NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
  NSArray* classes = [defaults stringArrayForKey:kNetworkInjectClassesKey];
  vector<string> v;
  for (NSString* s in classes) {
    v.push_back(ToString(s));
  }
  return v;
}

void SetInjectClasses(const vector<string>& v) {
  Array classes;
  for (int i = 0; i < v.size(); ++i) {
    classes.push_back(v[i]);
  }
  NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
  [defaults setObject:NewNSString(InjectVersion()) forKey:kNetworkInjectVersionKey];
  [defaults setObject:classes forKey:kNetworkInjectClassesKey];
  [defaults synchronize];
}

void BuildInjectClasses() {
  // Loop over all of the classes linked into the binary looking for any that
  // respond to certain NSURLConnectionDelegate selectors. This is both slow
  // and problematic. Slow because there are thousands of classes and the
  // checking takes ~100ms. Problematic because calling "isSubclassOfClass" or
  // "instancesRespondToSelector" causes the "initialize" routine for the class
  // to be invoked. The MFMessageWebProtocol class does something funky in its
  // "initialize" routine which cause subsequent calls to [NSURLConnection
  // sendSynchronousRequest] to not fail immediately if the requested URL could
  // not be found, but to instead timeout after 60 seconds.
  vector<string> injections;
  NSInteger num_classes = objc_getClassList(NULL, 0);
  if (num_classes > 0) {
    Class* classes = (__unsafe_unretained Class *)malloc(sizeof(Class) * num_classes);
    num_classes = objc_getClassList(classes, num_classes);

    // Swizzle any classes that implement one of these selectors.
    const SEL kSelectors[] = {
      @selector(connectionDidFinishLoading:),
      @selector(connection:didReceiveResponse:)
    };

    for (int i = 0; i < num_classes; ++i) {
      Class c = classes[i];
      const string n(ToString(NSStringFromClass(c)));
      if (n == "NetworkCallbacks" ||
          n == "MFMessageWebProtocol") {
        // Skip introspection of the Viewfinder NetworkCallbacks class for
        // which we already have logging. Skip introspection of
        // MFMessageWebProtocol due to the NSURLConnection bug it causes when
        // its "initialize" method is called.
        continue;
      }
      if (!class_getClassMethod(c, @selector(isSubclassOfClass:))) {
        continue;
      }
      if (![c isSubclassOfClass:[NSObject class]]) {
        continue;
      }
      for (int j = 0; j < ARRAYSIZE(kSelectors); ++j) {
        if ([c instancesRespondToSelector:kSelectors[j]]) {
          injections.push_back(class_getName(c));
          break;
        }
      }
    }

    free(classes);
  }

  // LOG("built network inject classes: %s", injections);
  SetInjectClasses(injections);
  DCHECK_EQ(injections, GetInjectClasses());
}

void InjectAllNSURLConnectionDelegateClasses() {
  WallTimer timer;
  if (!HaveInjectClasses()) {
    BuildInjectClasses();
  }
  const vector<string> injections = GetInjectClasses();
  int count = 0;
  for (int i = 0; i < injections.size(); ++i) {
    Class c = objc_getClass(injections[i].c_str());
    if (!c) {
      LOG("unable to find network injection class: %s", injections[i]);
      continue;
    }
    InjectIntoDelegateClass(c);
    ++count;
  }
  LOG("network injected %d classes: %.03f ms", count, timer.Milliseconds());
}

#if 0
void InjectExecuteFetchRequest(Class c) {
  SEL selector = @selector(executeFetchRequest:error:);
  SEL swizzled_selector = MakeSwizzledSelector(selector);

  Method method = class_getInstanceMethod(c, selector);
  if (!method) {
    return;
  }
  struct objc_method_description method_description = {
    selector,
    (char*)method_getTypeEncoding(method),
  };

  typedef NSArray* (^ExecuteFetchRequestBlock)(
      NSManagedObjectContext*, NSFetchRequest*, NSError**);

  ExecuteFetchRequestBlock implementation = ^(
      NSManagedObjectContext* slf,
      NSFetchRequest* request,
      NSError** error) {
    WallTimer t;
    NSArray* r = objc_msgSend(slf, swizzled_selector, request, error);
    t.Stop();
    VLOG("execute fetch request (%.2f ms):\n%s", t.Milliseconds(), request);
    return r;
  };

  ReplaceImplementation(
      selector, swizzled_selector, c,
      method_description, implementation, NULL);
}

void InjectCoreDataClasses() {
  Class c = objc_getClass("NSManagedObjectContext");
  if (c) {
    InjectExecuteFetchRequest(c);
  }
}
#endif

void InjectInit(void*) {
  InjectAllNSURLConnectionDelegateClasses();
  // InjectCoreDataClasses();
}

dispatch_once_t kInjectOnce;

#endif  // !APPSTORE

}  // namespace

string MemStats(bool verbose) {
  return Format("stats: %s  freedisk=%.01f\n%s",
                TaskInfo(), double(FreeDiskSpace()) / (1 << 30),
                tracker->Track(verbose));
}

string FileStats() {
  char buf[MAXPATHLEN + 1];
  string s("Files:\n");
  for (int fd = 0; fd < (int) FD_SETSIZE; ++fd) {
    if (fcntl(fd, F_GETPATH, buf) != -1) {
      s += Format("%3d  %s\n", fd, buf);
    }
  }
  return s;
}

string DebugStats(bool verbose) {
  string s = MemStats(verbose);
  if (verbose) {
    s += Format("\n%s", FileStats());
  }
  return s;
}

static void PrintDebugStats(int count) {
  // Output verbose region statistics every 300 seconds.
  // NOTE(peter): Verbose region statistics are currently disabled as we're
  // not experiencing out of memory problems anymore.
  const bool verbose = false; // (count % 15) == 0;
  VLOG("%s", DebugStats(verbose));
  dispatch_after_main(60, ^{ PrintDebugStats(count + 1); });
}

void DebugStatsLoop() {
  PrintDebugStats(0);
}

void DebugInject() {
#ifndef APPSTORE
  dispatch_once_f(&kInjectOnce, NULL, &InjectInit);
#endif  // !APPSTORE
}

// local variables:
// mode: c++
// end:
