// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <fstream>
#import <errno.h>
#import <fcntl.h>
#import <pthread.h>
#import <string.h>
#import <sys/types.h>
#ifdef OS_ANDROID
#import <linux/sysctl.h>
#else   // !OS_ANDROID
#import <sys/sysctl.h>
#endif  // !OS_ANDROID
#import <unistd.h>
#import <re2/re2.h>
#import "Callback.h"
#import "Compat.android.h"
#import "FileUtils.h"
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "PathUtils.h"
#import "StringUtils.h"
#import "WallTime.h"

namespace {

#if TARGET_IPHONE_SIMULATOR
const int64_t kMaxLogBytes = 1000 << 20;      // 1000 MB
const int64_t kMaxLogFileBytes = 100 << 20;   // 100 MB
const string kLogSuffix = "";
#else  // TARGET_IPHONE_SIMULATOR
const int64_t kMaxLogBytes = 20 << 20;        // 20 MB
const int64_t kMaxLogFileBytes = 100 << 10;   // 100 KB
const string kLogSuffix = ".gz";
#endif  // TARGET_IPHONE_SIMULATOR

LazyStaticPtr<RE2, const char*> kLogFilenameRE = { "([^.]+)(\\..*)" };

pthread_once_t logging_init = PTHREAD_ONCE_INIT;

CallbackSet1<const LogArgs&>* sinks;
CallbackSet* fatals;
CallbackSet* rotates;
std::function<void (LogStream&)> fatal_hook;

class FileDescriptorStreamBuf : public std::streambuf {
 public:
  FileDescriptorStreamBuf(int fd)
      : fd_(fd),
        synced_offset_(0) {
    // setp() takes a pointer to the beginning of the buffer and just past its end.
    setp(&buf_[0], &buf_[sizeof(buf_)]);
  }
  ~FileDescriptorStreamBuf() {
    sync();
  }

 protected:
  int sync() {
    const int num = pptr() - pbase();
    if (num > 0) {
      WriteStringToFD(fd_, Slice(buf_, num), true);
      pbump(-num);
      synced_offset_ += num;
    }
    return 0;
  }

  int overflow(int c) {
    if (c != EOF) {
      sync();
      *pptr() = c;
      pbump(1);
    }
    return c;
  }

  // seekoff is a combined seek/tell method that is used in ostream::tellp().
  // We don't support seeking, but we do need to implement this for offset 0 so we can
  // tell how much has been written.
  // http://www.cplusplus.com/reference/ostream/ostream/tellp/ specifies
  // that tellp() always calls exactly seekoff(0, ios_base::cur, ios_base::out).
  std::streampos seekoff(std::streamoff off, std::ios_base::seekdir way, std::ios_base::openmode which) {
    if (off != 0 || way != std::ios_base::cur || which != std::ios_base::out) {
      return -1;
    }
    return synced_offset_ + (pptr() - pbase());
  }

 private:
  int fd_;
  char buf_[4096 - sizeof(int) - sizeof(std::streambuf)];
  int64_t synced_offset_;
};

void StderrOutput(const LogArgs& args) {
  if (args.vlog) {
    // Don't output VLOGs to stderr.
    return;
  }

  std::cerr << WallTimeFormat("%F %T:%Q", args.timestamp)
            << " [" << args.pid << ":" << args.tid << "]"
            << " " << args.file_line << " ";

  const char* ptr = &args.message[0];
  const char* end = ptr + args.message.size();
  bool prefix = false;

  while (ptr < end) {
    if (prefix) {
      prefix = false;
      std::cerr.write("    ", 4);
    }

    const char* lf = std::find(ptr, end, '\n');
    if (lf != end) {
      prefix = true;
      lf += 1;
    }

    std::cerr.write(ptr, lf - ptr);
    ptr = lf;
  }
}

void LoggingInit() {
  sinks = new CallbackSet1<const LogArgs&>;
  fatals = new CallbackSet;
  rotates = new CallbackSet;
  Logging::AddLogSink([](const LogArgs& args) {
      StderrOutput(args);
    });
}

#ifdef DEVELOPMENT

// Returns true if the current process is being debugged (either running under
// the debugger or has a debugger attached post facto). Apparently Apple frowns
// on the use of sysctl() in AppStore binaries, so only compile this code for
// debug builds.
bool AmIBeingDebugged() {
  // Initialize mib, which tells sysctl the info we want, in this case we're
  // looking for information about a specific process ID.
  int mib[4];
  mib[0] = CTL_KERN;
  mib[1] = KERN_PROC;
  mib[2] = KERN_PROC_PID;
  mib[3] = getpid();

  kinfo_proc info;
  // Initialize the flags so that, if sysctl fails for some bizarre reason, we
  // get a predictable result.
  info.kp_proc.p_flag = 0;

  // Call sysctl.
  size_t size = sizeof(info);
  CHECK_EQ(0, sysctl(mib, sizeof(mib) / sizeof(*mib), &info, &size, NULL, 0));

  // We're being debugged if the P_TRACED flag is set.
  return (info.kp_proc.p_flag & P_TRACED) != 0;
}

#else  // !DEVELOPMENT

bool AmIBeingDebugged() {
  return false;
}

#endif  // !DEVELOPMENT

// The file descriptor we're logging to. When we're not running under the
// debugger, this is initialized to STDERR_FILENO. When running under the
// debugger this variable is initialized to the first open log file
// descriptor. After the initialization (which takes place on the main thread
// before locking is an issue), we use dup2() to clone the file descriptor for
// new log files on top of the the existing log_fd.
int log_fd = -1;
ostream* log_stream = NULL;
int64_t log_file_size;
string log_file_base;
string log_file_name;
int log_file_id;

int NewLogFile() {
  const string base = NewLogFilename("");
  if (base != log_file_base) {
    log_file_id = 0;
  } else {
    ++log_file_id;
  }
  for (; ; ++log_file_id) {
    const string name = (log_file_id == 0) ?
        Format("%s.log", base) :
        Format("%s.%d.log", base, log_file_id);
    const string path = JoinPath(LoggingDir(), name);
    const int new_fd = FileCreate(path);
    if (new_fd < 0) {
      continue;
    }
    log_file_base = base;
    log_file_name = name;
    const string s = Format("init: log file: %s\n", name);
    WriteStringToFD(new_fd, s, true);
    return new_fd;
  }
  return -1;
}

Mutex garbage_collect_mu;

// Iterate over the log files from newest to oldest, deleting files when their
// cumulative size exceeds kMaxLogBytes.
void GarbageCollectLogs() {
  MutexLock l(&garbage_collect_mu);

  const string queue_dir = LoggingQueueDir();
  vector<string> old_logs;
  DirList(queue_dir, &old_logs);

  // TODO(pmattis): Is the sort necessary?
  std::sort(old_logs.begin(), old_logs.end());
  std::reverse(old_logs.begin(), old_logs.end());
  int64_t cumulative_size = 0;

  for (int i = 0; i < old_logs.size(); ++i) {
    const int file_size = FileSize(JoinPath(queue_dir, old_logs[i]));
    if (file_size < 0) {
      continue;
    }
    cumulative_size += file_size;
    if (i >= 1 && cumulative_size >= kMaxLogBytes) {
      LOG("init: deleting: %s", old_logs[i]);
      FileRemove(JoinPath(queue_dir, old_logs[i]));
    }
  }
}

void CompressAndRename(
    const string& src, const string& dest_dir, const string& dest_name) {
#if TARGET_IPHONE_SIMULATOR
  FileRename(src, JoinPath(dest_dir, dest_name));
#else  // TARGET_IPHONE_SIMULATOR
  if (FileSize(src) > kMaxLogFileBytes * 2) {
    // Something's gone wrong with log rotation; just delete the log
    // instead of trying to read it into memory.
    FileRemove(src);
    return;
  }
  string raw = ReadFileToString(src);
  if (raw.empty()) {
    return;
  }
  // Gzip the data.
  string gzip = GzipEncode(raw);
  raw.clear();
  // Write to tmp/<dest-name>.
  const string tmp_path = JoinPath(TmpDir(), dest_name);
  WriteStringToFile(tmp_path, gzip);
  gzip.clear();
  // Move from tmp/<dest-name> to <dest-dir>/<dest-name>.
  FileRename(tmp_path, JoinPath(dest_dir, dest_name));
  // Remove <src> file.
  FileRemove(src);
#endif  // TARGET_IPHONE_SIMULATOR
}

void MaybeRotateLog() {
  if (log_file_size < kMaxLogFileBytes) {
    return;
  }
  const string old_file_name = log_file_name;
  const int new_fd = NewLogFile();
  log_stream->flush();
  const int err = dup2(new_fd, log_fd);
  close(new_fd);
  if (err < 0) {
    return;
  }
  if (!old_file_name.empty()) {
    dispatch_background([old_file_name] {
        CompressAndRename(JoinPath(LoggingDir(), old_file_name),
                          LoggingQueueDir(), old_file_name + kLogSuffix);
        GarbageCollectLogs();
        rotates->Run();
      });
  }
  log_file_size = FileSize(log_fd);
}

}  // namespace

const char* LogFormatFileLine(const char* file) {
  if (!file) {
    return NULL;
  }
  const char* p = strrchr(file, '/');
  if (p) file = p + 1;
  return file;
}

LogStream::LogStream(string* output)
    : strm_(this),
      output_(output) {
  setp(&buf_[0], &buf_[sizeof(buf_) - 1]);
}

LogStream::~LogStream() {
  sync();
  if (*output_->rbegin() != '\n') {
    output_->append("\n", 1);
  }
}

int LogStream::sync() {
  const int num = pptr() - pbase();
  if (num > 0) {
    output_->append(buf_, num);
    pbump(-num);
  }
  return 0;
}

int LogStream::overflow(int c) {
  if (c != EOF) {
    *pptr() = c;
    pbump(1);
    sync();
  }
  return c;
}

LogArgs::LogArgs(const char* fl, bool v)
    : file_line(LogFormatFileLine(fl)),
      timestamp(WallTime_Now()),
      pid(getpid()),
#ifdef OS_ANDROID
      tid(gettid()),
#else
      tid(pthread_mach_thread_np(pthread_self())),
#endif
      vlog(v) {
}

LogMessage::Helper::~Helper() {
  sinks->Run(args);
  if (die) {
    fatals->Run();
    abort();
  }
}

LogMessage::LogMessage(
    const char* file_line, bool die, bool vlog)
    : helper_(die, vlog, file_line),
      stream_(&helper_.args.message) {
}

LogMessage::~LogMessage() {
  if (helper_.die) {
    if (fatal_hook) {
      fatal_hook(stream_);
    }
    stream_ << "\n";
  }
}

void Logging::AddLogSink(const LogSink& sink) {
  sinks->Add(sink);
}

int Logging::AddLogFatal(const LogCallback& callback) {
  return fatals->Add(callback);
}

int Logging::AddLogRotate(const LogCallback& callback) {
  return rotates->Add(callback);
}

void Logging::RemoveLogFatal(int id) {
  fatals->Remove(id);
}

void Logging::RemoveLogRotate(int id) {
  rotates->Remove(id);
}

void Logging::SetFatalHook(const LogFatalCallback& callback) {
  fatal_hook = callback;
}

void Logging::InitFileLogging() {
  // TODO(ben): stderr on a device that is not being debugged is weird; writing to it with write() works
  // but through a c++ stream doesn't (manual flushing doesn't seem to work).  Now that we're writing through
  // a stream, we need to turn off our stderr integration until we figure out what's going on.
  /*if (!AmIBeingDebugged()) {
    // We're not being run under a debugger. Redirect stderr to our log
    // file. When we're running under a debugger we want to leave stderr alone
    // because it outputs to the debugger console.
    log_fd = STDERR_FILENO;
    log_stream = &std::cerr;
    log_file_size = kMaxLogFileBytes;
    }*/

  DirCreate(LibraryDir());
  const string logging_dir = LoggingDir();
  const string queue_dir = LoggingQueueDir();

  DirCreate(logging_dir);
  DirCreate(queue_dir);

  {
    // Move any existing log files into the queue directory.
    vector<string> old_logs;
    DirList(logging_dir, &old_logs);
    dispatch_background([old_logs, logging_dir, queue_dir] {
        for (int i = 0; i < old_logs.size(); ++i) {
          const string src = JoinPath(logging_dir, old_logs[i]);
          if (src == queue_dir) {
            // Skip moving the queue dir into itself (which would fail anyways).
            continue;
          }
          CompressAndRename(src, queue_dir, old_logs[i] + kLogSuffix);
        }
        GarbageCollectLogs();
      });
  }

  if (!AmIBeingDebugged()) {
    // We're not being run under a debugger. Clear the stderr log sink to
    // prevent double-writing of log messages to the same file.
    sinks->Clear();
  }

  if (log_fd < 0) {
    log_fd = NewLogFile();
    log_file_size = FileSize(log_fd);
    log_stream = new ostream(new FileDescriptorStreamBuf(log_fd));
  }

  Logging::AddLogSink([](const LogArgs& args) {
      // Note, we're protected by sinks->mu_ here. The 3rd parameter to
      // WallTimeFormat specifies UTC time.
      const std::ostream::pos_type old_size = log_stream->tellp();
      *log_stream << WallTimeFormat("%F %T:%Q", args.timestamp, false)
                  << " [" << args.pid << ":" << args.tid << "]"
                  << (args.file_line ? " " : "")
                  << (args.file_line ? args.file_line : "")
                  << " " << args.message;
      log_file_size += log_stream->tellp() - old_size;

      MaybeRotateLog();
    });

  // Perform an initial log rotation. This will create the initial log file if
  // !AmIBeingDebugged().
  MaybeRotateLog();
}

void Logging::Init() {
  pthread_once(&logging_init, &LoggingInit);
}

struct ScopedLogSink::Impl {
  CallbackSet1<const LogArgs&> old_sinks;
};

ScopedLogSink::ScopedLogSink()
    : impl_(new Impl) {
  sinks->Swap(&impl_->old_sinks);
  sinks->Add([this](const LogArgs& args) {
      output_ += Format("%s [%d:%d] %s %s",
                        WallTimeFormat("%F %T:%Q", args.timestamp),
                        args.pid, args.tid, args.file_line ? args.file_line : "",
                        args.message);
    });
}

ScopedLogSink::~ScopedLogSink() {
  sinks->Swap(&impl_->old_sinks);
  delete impl_;
}

string NewLogFilename(const string& suffix) {
  // The 3rd parameter to WallTimeFormat specifies UTC time.
  return Format("%s-%s%s",
                WallTimeFormat("%F-%H-%M-%S.%Q", WallTime_Now(), false),
                AppVersion(), suffix);
}

bool ParseLogFilename(
    const string& filename, WallTime* timestamp, string* suffix) {
  string datetime;
  if (!RE2::FullMatch(filename, *kLogFilenameRE, &datetime, suffix)) {
    return false;
  }
  struct tm t;
  memset(&t, 0, sizeof(t));
  if (!strptime(datetime.c_str(), "%F-%H-%M-%S", &t)) {
    return false;
  }
  t.tm_isdst = -1;
  *timestamp = timegm(&t);
  return true;
}
