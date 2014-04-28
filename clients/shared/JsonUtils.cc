// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "JsonUtils.h"
#import "Logging.h"
#import "StringUtils.h"

string JsonRef::Format() const {
#ifdef DEBUG
  return FormatStyled();
#else  // DEBUG
  return FormatCompact();
#endif // DEBUG
}

string JsonRef::FormatStyled() const {
  Json::StyledWriter writer;
  return writer.write(const_value_);
}

string JsonRef::FormatCompact() const {
  Json::FastWriter writer;
  return writer.write(const_value_);
}

bool JsonRef::Contains(const char* key) const {
  if (const_value_.type() != Json::objectValue) {
    return false;
  }
  return const_value_.isMember(key);
}

JsonRef JsonRef::operator[](int index) const {
  if (const_value_.type() != Json::arrayValue) {
    return Json::Value::null;
  }
  return const_value_[index];
}

JsonRef JsonRef::operator[](const char* key) const {
  if (const_value_.type() != Json::objectValue) {
    return Json::Value::null;
  }
  return const_value_[key];
}

string JsonRef::string_value() const {
  if (const_value_.type() == Json::arrayValue ||
      const_value_.type() == Json::objectValue) {
    return string();
  }
  return const_value_.asString();
}

bool JsonValue::Parse(const string& data) {
  if (data.empty()) {
    return true;
  }
  Json::Reader reader;
  if (!reader.parse(data, value_)) {
    LOG("network: error parsing json: %s\n%s",
        reader.getFormatedErrorMessages(), data);
    value_ = Json::Value();
    return false;
  }
  return true;
}

JsonValue ParseJSON(const string& data) {
  JsonValue root;
  root.Parse(data);
  return JsonValue(root);
}
