// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_FORMAT_H
#define VIEWFINDER_FORMAT_H

#import <iostream>
#import <sstream>
#import <string>
#import "Utils.h"
#import "StringUtils.h"

class Formatter {
  enum {
    kSize = 0
  };

 public:
  // A single argument to the formatter. Stores a pointer to the argument and
  // provides methods to output the typed argument to an ostream and to
  // retrieve its value as an int.
  class Arg {
    typedef void (*PutType)(ostream& os, const void* val);
    typedef int (*AsIntType)(const void* val);

    template <typename T>
    struct Helper {
      static void Put(ostream& os, const T* val) {
        os << *val;
      }

#ifdef __OBJC__
      static void PutValue(ostream& os, T val) {
        os << val;
      }
#endif  // __OBJC__

      static int AsInt(const T* val) {
        return ExtractInt(*val);
      }
      static int Zero(const T* val) {
        return 0;
      }

      static int ExtractInt(char val) { return val; };
      static int ExtractInt(unsigned char val) { return val; };
      static int ExtractInt(short val) { return val; };
      static int ExtractInt(unsigned short val) { return val; };
      static int ExtractInt(int val) { return val; };
      static int ExtractInt(unsigned int val) { return val; };
      static int ExtractInt(long val) { return val; };
      static int ExtractInt(unsigned long val) { return val; };
      static int ExtractInt(long long val) { return val; };
      static int ExtractInt(unsigned long long val) { return val; };
      static int ExtractInt(float val) { return static_cast<int>(val); };
      static int ExtractInt(double val) { return static_cast<int>(val); };
      static int ExtractInt(long double val) { return static_cast<int>(val); };
      template <typename Q> static int ExtractInt(const Q& val) { return 0; };
    };

   public:
    template <typename T>
    Arg(const T& v)
        : val_(&v),
          put_(reinterpret_cast<PutType>(&Helper<T>::Put)),
          as_int_(reinterpret_cast<AsIntType>(&Helper<T>::AsInt)) {
    }
    template <typename T>
    Arg(const volatile T& v)
        // Somewhat confusingly, const_cast is used to cast about volatile.
        : val_(const_cast<const T*>(&v)),
          put_(reinterpret_cast<PutType>(&Helper<volatile T>::Put)),
          as_int_(reinterpret_cast<AsIntType>(&Helper<volatile T>::AsInt)) {
    }

#ifdef __OBJC__
    Arg(id v)
        : val_((__bridge const void*) v),
          put_(reinterpret_cast<PutType>(&Helper<id>::PutValue)),
          as_int_(reinterpret_cast<AsIntType>(&Helper<id>::Zero)) {
    }
    Arg(NSString* v)
        : val_((__bridge const void*) v),
          put_(reinterpret_cast<PutType>(&Helper<NSString*>::PutValue)),
          as_int_(reinterpret_cast<AsIntType>(&Helper<NSString*>::Zero)) {
    }
    Arg(NSData* v)
        : val_((__bridge const void*) v),
          put_(reinterpret_cast<PutType>(&Helper<NSData*>::PutValue)),
          as_int_(reinterpret_cast<AsIntType>(&Helper<NSData*>::Zero)) {
    }
#endif  // __OBJC__

    void Put(ostream& os) const {
      put_(os, val_);
    }

    int AsInt() const {
      return as_int_(val_);
    }

   private:
    const void* const val_;
    const PutType put_;
    const AsIntType as_int_;
  };

  // A node in the list of arguments to the formatter. Contains a single
  // argument and a reference to the tail of the list. The tail of the list is
  // the Format object itself.
  template <typename Tail>
  class ArgList {
   public:
    enum {
      kIndex = Tail::kSize,
      kSize = 1 + kIndex,
    };

   public:
    ArgList(const Arg& a, const Tail& t)
        : arg_(a),
          tail_(t) {
    }

    // Returns a new list with the specified argument prepended (i.e. argument
    // index 0 is at the end of the list).
    ArgList<ArgList<Tail> > operator%(const Arg& arg) const {
      return ArgList<ArgList<Tail> >(arg, *this);
    }

    // Applies the arguments in the list to the associated format object,
    // outputting the result to the ostream.
    void Apply(ostream& os) const {
      Formatter::Arg const* array[kSize];
      Fill(array)->Apply(os, array, kSize);
    }

    // Applies the arguments in the list to the associated format object,
    // outputting the result to a string.
    string ToString() const {
      std::ostringstream ss;
      ss << *this;
      return ss.str();
    }

    // Returns a string containing the format string and all of the arguments.
    string DebugString() const {
      Arg const* array[kSize];
      return Fill(array)->DebugString(array, kSize);
    }

    // Fills the specified array with pointers to the arguments.
    const Formatter* Fill(Arg const** array) const {
      array[kIndex] = &arg_;
      return tail_.Fill(array);
    }

    // String conversion operator.
    operator string() const {
      return ToString();
    }

#ifdef __OBJC__
    NSString* ToNSString() const {
      return NewNSString(ToString());
    }
    operator NSString*() const {
      return ToNSString();
    }
#endif  // __OBJC__

   private:
    const Arg& arg_;
    const Tail& tail_;
  };

 public:
  explicit Formatter(const string& str)
      : format_(str) {
  }

  ArgList<Formatter> operator%(const Arg& arg) const {
    return ArgList<Formatter>(arg, *this);
  }

  // Outputs the format object to the ostream. An error will occur if the
  // format string requires any arguments.
  void Apply(ostream& os) const {
    Apply(os, NULL, 0);
  }

  // Applies the array of arguments to the format object, outputting the result
  // to the ostream.
  void Apply(ostream& os, const Arg* const* args, int args_count) const;

  // Outputs the format object to a string. An error will occur if the format
  // string requires any arguments.
  string ToString() const {
    std::ostringstream ss;
    Apply(ss, NULL, 0);
    return ss.str();
  }

  // Returns the format string.
  const string& DebugString() const {
    return format_;
  }

  // String conversion operator.
  operator string() const {
    return ToString();
  }

#ifdef __OBJC__
  operator NSString*() const {
    return ToNSString();
  }
  NSString* ToNSString() const {
    return NewNSString(ToString());
  }
#endif  // __OBJC__

 private:
  // Internal method for generating the debug string using the specified array
  // of arguments.
  string DebugString(const Arg* const* args, int args_count) const;

  // The Formatter object is the tail of the argument list. This is a required
  // method to be compatible with ArgList.
  const Formatter* Fill(Arg const** array) const { return this; }

 private:
  const string format_;
};

struct FormatMaker {
  typedef Formatter::Arg Arg;

  FormatMaker() {
  }
  explicit FormatMaker(const string& s)
      : str(s) {
  }

  Formatter operator()(const char* fmt) const {
    return Formatter(fmt);
  }

  FormatMaker operator()(const char* fmt, const Arg& a0) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  FormatMaker operator()(const char* fmt, const Arg& a0, const Arg& a1) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0, &a1 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  FormatMaker operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0, &a1, &a2 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  FormatMaker operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0, &a1, &a2, &a3 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  FormatMaker operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  FormatMaker operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  FormatMaker operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  FormatMaker operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6, const Arg& a7) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6, &a7 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  string operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6, const Arg& a7, const Arg& a8) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6, &a7, &a8 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  FormatMaker operator()(const char* fmt, const Arg& a0, const Arg& a1,
      const Arg& a2, const Arg& a3, const Arg& a4, const Arg& a5,
      const Arg& a6, const Arg& a7, const Arg& a8, const Arg& a9) const {
    std::ostringstream ss;
    const Arg* const args[] = { &a0, &a1, &a2, &a3, &a4, &a5, &a6, &a7, &a8,
        &a9 };
    Formatter(fmt).Apply(ss, args, ARRAYSIZE(args));
    return FormatMaker(ss.str());
  }

  operator string() const {
    return str;
  }

#ifdef __OBJC__
  operator NSString*() const {
    return NewNSString(str);
  }
#endif  // __OBJC__

  string str;
};

extern const FormatMaker& Format;

inline ostream& operator<<(ostream& os, const FormatMaker& format) {
  os << format.str;
  return os;
}

inline ostream& operator<<(ostream& os, const Formatter& format) {
  format.Apply(os);
  return os;
}

template <typename Tail>
inline ostream& operator<<(ostream& os, const Formatter::ArgList<Tail>& args) {
  args.Apply(os);
  return os;
}

#endif // VIEWFINDER_FORMAT_H
