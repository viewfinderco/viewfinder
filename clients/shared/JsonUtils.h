// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_JSON_UTILS_H
#define VIEWFINDER_JSON_UTILS_H

#import <functional>
#import <initializer_list>
#import <json/json.h>
#import "Utils.h"

// A wrapper around Json::Value that allows us to define better semantics for
// various operations. Note that JsonRef holds a const-reference and only
// contains const methods. Mutable methods are part of JsonValue.
class JsonRef {
 public:
  JsonRef(const JsonRef& v)
      : const_value_(v.const_value_) {
  }
  JsonRef(const Json::Value& v)
      : const_value_(v) {
  }

  // Returns the formatted json value.
  string Format() const;
  string FormatStyled() const;
  string FormatCompact() const;

  // Returns true if the value is an object and contains the specified key.
  bool Contains(const char* key) const;

  // Retrieves the value at index, returning Json::Value::null if the value is
  // not an array or the index is invalid.
  JsonRef operator[](int index) const;

  // Retrieves the value at key, return Json::Value::null if the value is non
  // at object or the key is not present.
  JsonRef operator[](const char* key) const;

  Json::Value::Members member_names() const {
    if (const_value_.type() != Json::objectValue) {
      return Json::Value::Members();
    }
    return const_value_.getMemberNames();
  }

  bool empty() const {
    return const_value_.empty();
  }
  int size() const {
    return const_value_.size();
  }

  bool bool_value() const {
    return const_value_.asBool();
  }
  int32_t int32_value() const {
    return const_value_.asInt();
  }
  int64_t int64_value() const {
    return const_value_.asInt64();
  }
  double double_value() const {
    return const_value_.asDouble();
  }
  string string_value() const;

 private:
  const Json::Value& const_value_;
};

class JsonValue : public JsonRef {
  friend class JsonArray;
  friend class JsonDict;

 public:
  JsonValue(const JsonValue& v)
      : JsonRef(value_),
        value_(v.value_) {
  }
  JsonValue(Json::ValueType type = Json::nullValue)
      : JsonRef(value_),
        value_(type) {
  }
  JsonValue(bool v)
      : JsonRef(value_),
        value_(v) {
  }
  JsonValue(int32_t v)
      : JsonRef(value_),
        value_(v) {
  }
  JsonValue(uint32_t v)
      : JsonRef(value_),
        value_(v) {
  }
  JsonValue(int64_t v)
      : JsonRef(value_),
        value_(v) {
  }
  JsonValue(uint64_t v)
      : JsonRef(value_),
        value_(v) {
  }
  JsonValue(double v)
      : JsonRef(value_),
        value_(v) {
  }
  JsonValue(const char* v)
      : JsonRef(value_),
        value_(v) {
  }
  JsonValue(const string& v)
      : JsonRef(value_),
        value_(v) {
  }
  JsonValue(const Json::Value& v)
      : JsonRef(value_),
        value_(v) {
  }
  // Array initializer.
  JsonValue(std::initializer_list<JsonValue> init)
      : JsonRef(value_),
        value_(Json::arrayValue) {
    for (auto v : init) {
      value_[size()] = v.value_;
    }
  }
  // Object initializer.
  JsonValue(std::initializer_list<std::pair<const char*, JsonValue>> init)
      : JsonRef(value_),
        value_(Json::objectValue) {
    for (auto v : init) {
      value_[v.first] = v.second.value_;
    }
  }

  // Parses the json data, returning true if the data could be parsed and false
  // otherwise.
  bool Parse(const string& data);

 private:
#ifdef __OBJC__
  // Do not allow a JsonValue to be constructed from an objective-c object.
  JsonValue(id v);
#endif  // __OBJC__

 protected:
  Json::Value value_;
};

class JsonArray : public JsonValue {
 public:
  JsonArray()
      : JsonValue(Json::arrayValue) {
  }
  JsonArray(const JsonArray& a)
      : JsonValue(a) {
  }
  JsonArray(std::initializer_list<JsonValue> init)
      : JsonValue(init) {
  }
  JsonArray(int count, const std::function<JsonValue (int i)>& generator)
      : JsonArray() {
    for (int i = 0; i < count; ++i) {
      push_back(generator(i));
    }
  }

  void push_back(const JsonValue& v) {
    value_[size()] = v.value_;
  }
};

class JsonDict : public JsonValue {
 public:
  JsonDict()
      : JsonValue(Json::objectValue) {
  }
  JsonDict(const JsonDict& d)
      : JsonValue(d) {
  }
  JsonDict(const char* key, const JsonValue& value)
      : JsonDict() {
    insert(key, value);
  }
  JsonDict(std::initializer_list<std::pair<const char*, JsonValue>> init)
      : JsonValue(init) {
  }

  void insert(const char* key, const JsonValue& v) {
    value_[key] = v.value_;
  }
};

JsonValue ParseJSON(const string& data);

#endif // VIEWFINDER_JSON_UTILS_H
