// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_VALUE_UTILS_H
#define VIEWFINDER_VALUE_UTILS_H

#import <Foundation/NSArray.h>
#import <Foundation/NSDictionary.h>
#import <Foundation/NSValue.h>
#import <QuartzCore/CATransform3D.h>
#import <UIKit/UIGeometry.h>
#import "StringUtils.h"

class Value {
 public:
  Value(const Value& v)
      : value_(v.value_) {
  }
  Value(id v)
      : value_(v) {
  }
  Value(bool v)
      : value_([[NSNumber alloc] initWithBool:v]) {
  }
  Value(char v)
      : value_([[NSNumber alloc] initWithChar:v]) {
  }
  Value(unsigned char v)
      : value_([[NSNumber alloc] initWithUnsignedChar:v]) {
  }
  Value(short v)
      : value_([[NSNumber alloc] initWithShort:v]) {
  }
  Value(unsigned short v)
      : value_([[NSNumber alloc] initWithUnsignedShort:v]) {
  }
  Value(int v)
      : value_([[NSNumber alloc] initWithInt:v]) {
  }
  Value(unsigned int v)
      : value_([[NSNumber alloc] initWithUnsignedInt:v]) {
  }
  Value(long v)
      : value_([[NSNumber alloc] initWithLong:v]) {
  }
  Value(unsigned long v)
      : value_([[NSNumber alloc] initWithUnsignedLong:v]) {
  }
  Value(long long v)
      : value_([[NSNumber alloc] initWithLongLong:v]) {
  }
  Value(unsigned long long v)
      : value_([[NSNumber alloc] initWithUnsignedLongLong:v]) {
  }
  Value(float v)
      : value_([[NSNumber alloc] initWithFloat:v]) {
  }
  Value(double v)
      : value_([[NSNumber alloc] initWithDouble:v]) {
  }
  Value(const char* v)
      : value_(NewNSString(Slice(v))) {
  }
  Value(const string& v)
      : value_(NewNSString(v)) {
  }
  Value(CGColorRef v)
      : value_((__bridge id)v) {
  }
  Value(CFStringRef v)
      : value_((__bridge id)v) {
  }
  Value(CFBooleanRef v)
      : value_((__bridge id)v) {
  }
  Value(CFNumberRef v)
      : value_((__bridge id)v) {
  }
  Value(CFTypeRef v)
      : value_((__bridge id)v) {
  }
  Value(const CGPoint& p)
      : value_([NSValue valueWithCGPoint:p]) {
  }
  Value(const CGRect& r)
      : value_([NSValue valueWithCGRect:r]) {
  }
  Value(const CGSize& s)
      : value_([NSValue valueWithCGSize:s]) {
  }
  Value(const CATransform3D& t)
      : value_([NSValue valueWithCATransform3D:t]) {
  }
  Value(const UIOffset& o)
      : value_([NSValue valueWithUIOffset:o]) {
  }
  ~Value() {
    reset(NULL);
  }

  // Initializes the reference without incrementing the reference count.
  void acquire(id new_value) {
    value_ = new_value;
  }

  // Initializes the reference and increments the reference count.
  void reset(id new_value) {
    value_ = new_value;
  }

  id get() const { return value_; }
  operator id() const { return value_; }

  Value& operator=(const Value& other) {
    reset(other.value_);
    return *this;
  }

  bool bool_value() const {
    return [(NSNumber*)get() boolValue];
  }
  char char_value() const {
    return [(NSNumber*)get() charValue];
  }
  unsigned char uchar_value() const {
    return [(NSNumber*)get() unsignedCharValue];
  }
  short short_value() const {
    return [(NSNumber*)get() shortValue];
  }
  unsigned short ushort_value() const {
    return [(NSNumber*)get() unsignedShortValue];
  }
  int int_value() const {
    return [(NSNumber*)get() intValue];
  }
  unsigned int uint_value() const {
    return [(NSNumber*)get() unsignedIntValue];
  }
  long long_value() const {
    return [(NSNumber*)get() longValue];
  }
  unsigned long ulong_value() const {
    return [(NSNumber*)get() unsignedLongValue];
  }
  int64_t int64_value() const {
    return [(NSNumber*)get() longLongValue];
  }
  uint64_t uint64_value() const {
    return [(NSNumber*)get() unsignedLongLongValue];
  }
  float float_value() const {
    return [(NSNumber*)get() floatValue];
  }
  double double_value() const {
    return [(NSNumber*)get() doubleValue];
  }
  CGRect rect_value() const {
    CGRect r;
    [(NSValue*)get() getValue:&r];
    return r;
  }

 private:
  Value& operator=(id value);

 private:
  id value_;
};

class Array : public Value {
 public:
  Array()
      : Value([[NSMutableArray alloc] initWithCapacity:5]) {
  }
  Array(NSArray* a)
      : Value([a isKindOfClass:[NSArray class]] ? a : NULL) {
  }
  Array(const Array& a)
      : Value(a) {
  }
  Array(CFArrayRef a)
      : Value((__bridge NSArray*)a) {
  }
  Array(const Value& v1)
      : Value([[NSMutableArray alloc] initWithCapacity:1]) {
    push_back(v1);
  }
  Array(const Value& v1, const Value& v2)
      : Value([[NSMutableArray alloc] initWithCapacity:2]) {
    push_back(v1);
    push_back(v2);
  }
  Array(const Value& v1, const Value& v2, const Value& v3)
      : Value([[NSMutableArray alloc] initWithCapacity:3]) {
    push_back(v1);
    push_back(v2);
    push_back(v3);
  }
  Array(const Value& v1, const Value& v2, const Value& v3,
        const Value& v4)
      : Value([[NSMutableArray alloc] initWithCapacity:4]) {
    push_back(v1);
    push_back(v2);
    push_back(v3);
    push_back(v4);
  }
  Array(const Value& v1, const Value& v2, const Value& v3,
        const Value& v4, const Value& v5)
      : Value([[NSMutableArray alloc] initWithCapacity:5]) {
    push_back(v1);
    push_back(v2);
    push_back(v3);
    push_back(v4);
    push_back(v5);
  }
  Array(const Value& v1, const Value& v2, const Value& v3,
        const Value& v4, const Value& v5, const Value& v6)
      : Value([[NSMutableArray alloc] initWithCapacity:6]) {
    push_back(v1);
    push_back(v2);
    push_back(v3);
    push_back(v4);
    push_back(v5);
    push_back(v6);
  }
  Array(const Value& v1, const Value& v2, const Value& v3,
        const Value& v4, const Value& v5, const Value& v6,
        const Value& v7)
      : Value([[NSMutableArray alloc] initWithCapacity:7]) {
    push_back(v1);
    push_back(v2);
    push_back(v3);
    push_back(v4);
    push_back(v5);
    push_back(v6);
    push_back(v7);
  }
  Array(const Value& v1, const Value& v2, const Value& v3,
        const Value& v4, const Value& v5, const Value& v6,
        const Value& v7, const Value& v8)
      : Value([[NSMutableArray alloc] initWithCapacity:8]) {
    push_back(v1);
    push_back(v2);
    push_back(v3);
    push_back(v4);
    push_back(v5);
    push_back(v6);
    push_back(v7);
    push_back(v8);
  }
  Array(const Value& v1, const Value& v2, const Value& v3,
        const Value& v4, const Value& v5, const Value& v6,
        const Value& v7, const Value& v8, const Value& v9)
      : Value([[NSMutableArray alloc] initWithCapacity:9]) {
    push_back(v1);
    push_back(v2);
    push_back(v3);
    push_back(v4);
    push_back(v5);
    push_back(v6);
    push_back(v7);
    push_back(v8);
    push_back(v9);
  }
  Array(const Value& v1, const Value& v2, const Value& v3,
        const Value& v4, const Value& v5, const Value& v6,
        const Value& v7, const Value& v8, const Value& v9,
        const Value& v10)
      : Value([[NSMutableArray alloc] initWithCapacity:10]) {
    push_back(v1);
    push_back(v2);
    push_back(v3);
    push_back(v4);
    push_back(v5);
    push_back(v6);
    push_back(v7);
    push_back(v8);
    push_back(v9);
    push_back(v10);
  }
  Array(const Value& v1, const Value& v2, const Value& v3,
        const Value& v4, const Value& v5, const Value& v6,
        const Value& v7, const Value& v8, const Value& v9,
        const Value& v10, const Value& v11)
      : Value([[NSMutableArray alloc] initWithCapacity:11]) {
    push_back(v1);
    push_back(v2);
    push_back(v3);
    push_back(v4);
    push_back(v5);
    push_back(v6);
    push_back(v7);
    push_back(v8);
    push_back(v9);
    push_back(v10);
    push_back(v11);
  }
  template <typename T>
  Array(int count, T (^generator)(int i))
      : Value([[NSMutableArray alloc] initWithCapacity:count]) {
    for (int i = 0; i < count; ++i) {
      push_back(generator(i));
    }
  }

  Array& push_back(const Value& value) {
    [array() addObject:value];
    return *this;
  }
  Array& pop_back() {
    [array() removeLastObject];
    return *this;
  }

  template <typename T>
  T at(int index) const {
    return [array() objectAtIndex:index];
  }

  Value operator[](int index) const {
    return at<Value>(index);
  }

  int size() const {
    return [array() count];
  }
  bool empty() const {
    return size() == 0;
  }

  NSMutableArray* array() const {
    return (NSMutableArray*)get();
  }
  operator CFArrayRef() const __attribute__((cf_returns_not_retained)) {
    return (__bridge CFArrayRef)array();
  }
  operator NSArray*() const {
    return array();
  }
  operator NSMutableArray*() const {
    return array();
  }
};

class Dict : public Value {
 public:
  Dict()
      : Value([[NSMutableDictionary alloc] initWithCapacity:5]) {
  }
  Dict(NSDictionary* d)
      : Value([d isKindOfClass:[NSDictionary class]] ? d : NULL) {
  }
  Dict(const Dict& d)
      : Value(d) {
  }
  Dict(const Value& k1, const Value& v1)
      : Value([[NSMutableDictionary alloc] initWithCapacity:1]) {
    insert(k1, v1);
  }
  Dict(const Value& k1, const Value& v1,
       const Value& k2, const Value& v2)
      : Value([[NSMutableDictionary alloc] initWithCapacity:2]) {
    insert(k1, v1);
    insert(k2, v2);
  }
  Dict(const Value& k1, const Value& v1,
       const Value& k2, const Value& v2,
       const Value& k3, const Value& v3)
      : Value([[NSMutableDictionary alloc] initWithCapacity:3]) {
    insert(k1, v1);
    insert(k2, v2);
    insert(k3, v3);
  }
  Dict(const Value& k1, const Value& v1,
       const Value& k2, const Value& v2,
       const Value& k3, const Value& v3,
       const Value& k4, const Value& v4)
      : Value([[NSMutableDictionary alloc] initWithCapacity:4]) {
    insert(k1, v1);
    insert(k2, v2);
    insert(k3, v3);
    insert(k4, v4);
  }
  Dict(const Value& k1, const Value& v1,
       const Value& k2, const Value& v2,
       const Value& k3, const Value& v3,
       const Value& k4, const Value& v4,
       const Value& k5, const Value& v5)
      : Value([[NSMutableDictionary alloc] initWithCapacity:5]) {
    insert(k1, v1);
    insert(k2, v2);
    insert(k3, v3);
    insert(k4, v4);
    insert(k5, v5);
  }
  Dict(const Value& k1, const Value& v1,
       const Value& k2, const Value& v2,
       const Value& k3, const Value& v3,
       const Value& k4, const Value& v4,
       const Value& k5, const Value& v5,
       const Value& k6, const Value& v6)
      : Value([[NSMutableDictionary alloc] initWithCapacity:6]) {
    insert(k1, v1);
    insert(k2, v2);
    insert(k3, v3);
    insert(k4, v4);
    insert(k5, v5);
    insert(k6, v6);
  }


  Dict clone() const {
    return Dict([[NSMutableDictionary alloc] initWithDictionary:dict()]);
  }

  Dict& insert(const Value& key, const Value& value) {
    [dict() setObject:value forKey:key];
    return *this;
  }
  Dict& erase(const Value& key) {
    [dict() removeObjectForKey:key];
    return *this;
  }

  id find(const Value& key) const {
    return [dict() objectForKey:key];
  }
  Array find_array(const Value& key) const {
    return [dict() objectForKey:key];
  }
  Dict find_dict(const Value& key) const {
    return [dict() objectForKey:key];
  }
  Value find_value(const Value& key) const {
    return [dict() objectForKey:key];
  }

  int size() const {
    return [dict() count];
  }
  bool empty() const {
    return size() == 0;
  }

  NSMutableDictionary* dict() const {
    return (NSMutableDictionary*)get();
  }
  operator CFDictionaryRef() const __attribute__((cf_returns_not_retained)) {
    return (__bridge CFDictionaryRef)dict();
  }
  operator NSDictionary*() const {
    return dict();
  }
  operator NSMutableDictionary*() const {
    return dict();
  }
};

class Set : public Value {
 public:
  Set()
      : Value([[NSMutableSet alloc] initWithCapacity:5]) {
  }
  Set(NSSet* s)
      : Value([s isKindOfClass:[NSSet class]] ? s : NULL) {
  }
  Set(const Set& s)
      : Value(s) {
  }
  Set(const Value& v1)
      : Value([[NSMutableSet alloc] initWithCapacity:1]) {
    insert(v1);
  }
  Set(const Value& v1,
      const Value& v2)
      : Value([[NSMutableSet alloc] initWithCapacity:2]) {
    insert(v1);
    insert(v2);
  }
  Set(const Value& v1,
      const Value& v2,
      const Value& v3)
      : Value([[NSMutableSet alloc] initWithCapacity:3]) {
    insert(v1);
    insert(v2);
    insert(v3);
  }
  Set(const Value& v1,
      const Value& v2,
      const Value& v3,
      const Value& v4)
      : Value([[NSMutableSet alloc] initWithCapacity:4]) {
    insert(v1);
    insert(v2);
    insert(v3);
    insert(v4);
  }
  Set(const Value& v1,
      const Value& v2,
      const Value& v3,
      const Value& v4,
      const Value& v5)
      : Value([[NSMutableSet alloc] initWithCapacity:5]) {
    insert(v1);
    insert(v2);
    insert(v3);
    insert(v4);
    insert(v5);
  }

  Set& insert(const Value& value) {
    [set() addObject:value];
    return *this;
  }

  bool contains(const Value& value) const {
    return [set() containsObject:value];
  }

  int size() const {
    return [set() count];
  }
  bool empty() const {
    return size() == 0;
  }

  NSMutableSet* set() const {
    return (NSMutableSet*)get();
  }
  operator NSSet*() const {
    return set();
  }
  operator NSMutableSet*() const {
    return set();
  }
};

#endif  // VIEWFINDER_VALUE_UTILS_H
