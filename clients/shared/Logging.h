// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_LOGGING_H
#define VIEWFINDER_LOGGING_H

#import "Format.h"
#import "Utils.h"
#import "WallTime.h"

const char* LogFormatFileLine(const char* file_line);

class LogStream : private std::streambuf {
  typedef Formatter::Arg Arg;

 public:
  explicit LogStream(string* output);
  ~LogStream();

  LogStream& operator<<(ostream& (*val)(ostream&)) {
    strm_ << val;
    return *this;
  }

  template <typename T>
  LogStream& operator<<(const T &val) {
    strm_ << val;
    return *this;
  }

  LogStream& operator()(const char* fmt) {
    Format(fmt).Apply(strm_);
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0) {
    const Arg* const args[] = { &a0 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1) {
    const Arg* const args[] = { &a0, &a1 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2) {
    const Arg* const args[] = { &a0, &a1, &a2 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3) {
    const Arg* const args[] = { &a0, &a1, &a2, &a3 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4) {
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5) {
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6) {
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6, const Arg& a7) {
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6, &a7 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6, const Arg& a7, const Arg& a8) {
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6, &a7, &a8 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6, const Arg& a7, const Arg& a8, const Arg& a9) {
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6, &a7, &a8,
        &a9 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6, const Arg& a7, const Arg& a8, const Arg& a9,
      const Arg& a10) {
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6, &a7, &a8,
        &a9, &a10 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

  LogStream& operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6, const Arg& a7, const Arg& a8, const Arg& a9,
      const Arg& a10, const Arg& a11) {
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6, &a7, &a8,
        &a9, &a10, &a11 };
    Format(fmt).Apply(strm_, args, ARRAYSIZE(args));
    return *this;
  }

 private:
  int sync();
  int overflow(int c);

 private:
  ostream strm_;
  string* const output_;
  char buf_[256];
};

class LogStreamVoidify {
 public:
  LogStreamVoidify() { }
  void operator&(LogStream&) { }
};

struct LogArgs {
  LogArgs(const char* file_line, bool v);

  string message;
  const char* const file_line;
  const double timestamp;
  const int pid;
  const int tid;
  const bool vlog;
};

typedef std::function<void (const LogArgs&)> LogSink;

class LogMessage {
  struct Helper {
    Helper(bool d, bool r, const char* file_line)
        : die(d),
          args(file_line, r) {
    }
    ~Helper();

    const bool die;
    LogArgs args;
  };

 public:
  LogMessage(const char* file_line, bool die, bool vlog);
  ~LogMessage();

  LogStream& stream() { return stream_; }

 private:
  Helper helper_;
  LogStream stream_;
};

class Logging {
  typedef std::function<void ()> LogCallback;
  typedef std::function<void (LogStream&)> LogFatalCallback;

 public:
  class Initializer {
   public:
    Initializer() {
      Logging::Init();
    }
  };

 public:
  static void AddLogSink(const LogSink& sink);
  static int AddLogFatal(const LogCallback& callback);
  static int AddLogRotate(const LogCallback& callback);
  static void RemoveLogFatal(int id);
  static void RemoveLogRotate(int id);
  static void SetFatalHook(const LogFatalCallback& callback);
  static void InitFileLogging();

 private:
  static void Init();
};

static Logging::Initializer kLoggingInitializer;

class ScopedLogSink {
  struct Impl;

 public:
  ScopedLogSink();
  ~ScopedLogSink();

  string output() const { return output_; }

 private:
  Impl* impl_;
  string output_;
};

#define LOG_FILE_LINE3(x)  #x
#define LOG_FILE_LINE2(x)  LOG_FILE_LINE3(x)
#define LOG_FILE_LINE      __FILE__ ":" LOG_FILE_LINE2(__LINE__) ":"

#define LOG \
  LogMessage(LOG_FILE_LINE, false, false).stream()
// VLOG is like LOG, except it is only output to a file, not to stderr.
#define VLOG \
  LogMessage(LOG_FILE_LINE, false, true).stream()
#define DIE \
  LogMessage(LOG_FILE_LINE, true, false).stream()
#define CHECK(cond)                               \
  (cond) ? (void) 0 :                             \
  LogStreamVoidify() &                            \
  LogMessage(LOG_FILE_LINE, true, false).stream() \
  << "check failed: " << #cond

#ifdef DEBUG
#define DCHECK(cond) CHECK(cond)
#else
#define DCHECK(cond)                               \
  (cond) ? (void) 0 :                              \
  LogStreamVoidify() &                             \
  LogMessage(LOG_FILE_LINE, false, false).stream() \
  << "dcheck failed: " << #cond
#endif

// Function is overloaded for integral types to allow static const
// integrals declared in classes and not defined to be used as arguments to
// CHECK* macros. It's not encouraged though.
template <class T>
inline const T&       GetReferenceableValue(const T&           t) { return t; }
inline char           GetReferenceableValue(char               t) { return t; }
inline unsigned char  GetReferenceableValue(unsigned char      t) { return t; }
inline signed char    GetReferenceableValue(signed char        t) { return t; }
inline short          GetReferenceableValue(short              t) { return t; }
inline unsigned short GetReferenceableValue(unsigned short     t) { return t; }
inline int            GetReferenceableValue(int                t) { return t; }
inline unsigned int   GetReferenceableValue(unsigned int       t) { return t; }
inline long           GetReferenceableValue(long               t) { return t; }
inline unsigned long  GetReferenceableValue(unsigned long      t) { return t; }
inline long long      GetReferenceableValue(long long          t) { return t; }
inline unsigned long long GetReferenceableValue(unsigned long long t) {
  return t;
}

// Helper functions for CHECK_OP macro.
// The (int, int) specialization works around the issue that the compiler
// will not instantiate the template version of the function on values of
// unnamed enum type - see comment below.
#define DEFINE_CHECK_OP_IMPL(name, op)                                  \
  template <class T1, class T2>                                         \
  inline string* Check##name##Impl(const T1& v1, const T2& v2,          \
                                   const char* names) {                 \
    if (v1 op v2) return NULL;                                          \
    else return new string(Format("%s (%s vs %s)", names, v1, v2));     \
  }                                                                     \
  inline string* Check##name##Impl(int v1, int v2, const char* names) { \
    return Check##name##Impl<int, int>(v1, v2, names);                  \
  }

// Use _EQ, _NE, _LE, etc. in case the simpler names EQ, NE, LE, etc are
// already defined. This happens if, for example, those are used as token names
// in a yacc grammar.
DEFINE_CHECK_OP_IMPL(_EQ, ==)
DEFINE_CHECK_OP_IMPL(_NE, !=)
DEFINE_CHECK_OP_IMPL(_LE, <=)
DEFINE_CHECK_OP_IMPL(_LT, < )
DEFINE_CHECK_OP_IMPL(_GE, >=)
DEFINE_CHECK_OP_IMPL(_GT, > )
#undef DEFINE_CHECK_OP_IMPL

// In debug mode, avoid constructing CheckOpStrings if possible,
// to reduce the overhead of CHECK statments by 2x.
// Real DCHECK-heavy tests have seen 1.5x speedups.
#define CHECK_OP(name, op, val1, val2)                   \
  while (string* _result =                               \
         Check##name##Impl(                              \
             GetReferenceableValue(val1),                \
             GetReferenceableValue(val2),                \
             #val1 " " #op " " #val2))                   \
    LogMessage(LOG_FILE_LINE, true, false).stream()      \
        << "check failed: " << *_result

// Equality/Inequality checks - compare two values, and log a FATAL message
// including the two values when the result is not as expected.  The values
// must have operator<<(ostream, ...) defined.
//
// You may append to the error message like so:
//   CHECK_NE(1, 2) << ": The world must be ending!";
//
// We are very careful to ensure that each argument is evaluated exactly
// once, and that anything which is legal to pass as a function argument is
// legal here.  In particular, the arguments may be temporary expressions
// which will end up being destroyed at the end of the apparent statement,
// for example:
//   CHECK_EQ(string("abc")[1], 'b');
//
// WARNING: These don't compile correctly if one of the arguments is a pointer
// and the other is NULL. To work around this, simply static_cast NULL to the
// type of the desired pointer.

#define CHECK_EQ(val1, val2) CHECK_OP(_EQ, ==, val1, val2)
#define CHECK_NE(val1, val2) CHECK_OP(_NE, !=, val1, val2)
#define CHECK_LE(val1, val2) CHECK_OP(_LE, <=, val1, val2)
#define CHECK_LT(val1, val2) CHECK_OP(_LT, < , val1, val2)
#define CHECK_GE(val1, val2) CHECK_OP(_GE, >=, val1, val2)
#define CHECK_GT(val1, val2) CHECK_OP(_GT, > , val1, val2)
#define CHECK_NEAR(val1, val2) CHECK_OP(_LT, < , fabs((val1) - (val2)), \
                                        std::numeric_limits<float>::epsilon())

#ifdef DEBUG
#define DCHECK_EQ(val1, val2) CHECK_EQ(val1, val2)
#define DCHECK_NE(val1, val2) CHECK_NE(val1, val2)
#define DCHECK_LE(val1, val2) CHECK_LE(val1, val2)
#define DCHECK_LT(val1, val2) CHECK_LT(val1, val2)
#define DCHECK_GE(val1, val2) CHECK_GE(val1, val2)
#define DCHECK_GT(val1, val2) CHECK_GT(val1, val2)
#define DCHECK_NEAR(val1, val2) CHECK_NEAR(val1, val2)
#else // DEBUG
#define DCHECK_EQ(val1, val2) while(false) CHECK_EQ(val1, val2)
#define DCHECK_NE(val1, val2) while(false) CHECK_NE(val1, val2)
#define DCHECK_LE(val1, val2) while(false) CHECK_LE(val1, val2)
#define DCHECK_LT(val1, val2) while(false) CHECK_LT(val1, val2)
#define DCHECK_GE(val1, val2) while(false) CHECK_GE(val1, val2)
#define DCHECK_GT(val1, val2) while(false) CHECK_GT(val1, val2)
#define DCHECK_NEAR(val1, val2) while(false) CHECK_NEAR(val1, val2)
#endif // DEBUG

string NewLogFilename(const string& suffix);
bool ParseLogFilename(const string& filename, WallTime* timestamp, string* suffix);

#endif // VIEWFINDER_LOGGING_H
