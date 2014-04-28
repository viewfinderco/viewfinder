// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <unordered_map>
#import "Callback.h"
#import "DBFormat.h"
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "STLUtils.h"
#import "WallTime.h"

namespace {

class IntrospectMap {
  struct IntrospectData {
    DBIntrospectCallback key;
    DBIntrospectCallback value;
  };

 public:
  IntrospectMap() {
    // Keys that are already human readable.
    const string kNullKeys[] = {
      DBFormat::asset_deletion_key(""),
      DBFormat::deprecated_contact_name_key(),
      DBFormat::contact_remove_queue_key(""),
      DBFormat::contact_upload_queue_key(""),
      DBFormat::deprecated_full_text_index_comment_key(),
      DBFormat::deprecated_full_text_index_episode_key(),
      DBFormat::deprecated_full_text_index_viewpoint_key(),
      DBFormat::new_user_key(),
      DBFormat::placemark_histogram_key(),
      DBFormat::placemark_histogram_sort_key(),
      DBFormat::server_contact_id_key(""),
      DBFormat::deprecated_user_name_key(),
      DBFormat::user_queue_key(),
      DBFormat::user_update_queue_key(),
    };
    for (int i = 0; i < ARRAYSIZE(kNullKeys); ++i) {
      Register(kNullKeys[i], NULL, NULL);
    }
  }

  void Register(const string& prefix,
                DBIntrospectCallback key,
                DBIntrospectCallback value) {
    DCHECK(!ContainsKey(m_, prefix));
    IntrospectData* d = &m_[prefix];
    d->key = key;
    d->value = value;
  }

  void Unregister(const string& prefix) {
    DCHECK(ContainsKey(m_, prefix));
    m_.erase(prefix);
  }

  string Format(const Slice& key, const Slice& value) const {
    // First check for an exact match.
    const string prefix = GetPrefix(key);
    const IntrospectData* d = FindPtrOrNull(m_, key.ToString());
    if (d) {
      return FormatData(d, prefix, key, value);
    }
    // Next check for a prefix match.
    d = FindPtrOrNull(m_, prefix);
    DCHECK(d != NULL);
    if (d) {
      return FormatData(d, prefix, key, value);
    }
    // If we couldn't find a match, just return the raw key (not the value
    // which is often binary garbage). Note the DCHECK above means we shouldn't
    // get here unless somebody was lazy.
    return key.ToString();
  }

 private:
  static string GetPrefix(const Slice& key) {
    Slice::size_type n = key.find('/');
    if (n == string::npos) {
      return key.ToString();
    }
    return key.substr(0, n + 1).ToString();
  }

  static string FormatData(const IntrospectData* d, const string& prefix,
                           const Slice& key, const Slice& value) {
    const string formatted_key = FormatKey(d, prefix, key);
    const string formatted_value = FormatValue(d, value);
    if (formatted_value.empty()) {
      return formatted_key;
    }
    return ::Format("%s -> %s", formatted_key, formatted_value);
  }

  static string FormatKey(const IntrospectData* d, const string& prefix,
                          const Slice& key) {
    if (d->key) {
      const string s = d->key(key);
      if (!s.empty()) {
        return prefix + s;
      }
    }
    return key.ToString();
  }

  static string FormatValue(const IntrospectData* d, const Slice& value) {
    if (!value.empty() && d->value) {
      return d->value(value);
    }
    return string();
  }

 private:
  std::unordered_map<string, IntrospectData> m_;
};

LazyStaticPtr<IntrospectMap> introspect;

}  // namespace

const string DBIntrospect::kUnhandledValue = "<unhandled value>";

string DBIntrospect::Format(const Slice& key, const Slice& value) {
  return introspect->Format(key, value);
}

DBRegisterKeyIntrospect::DBRegisterKeyIntrospect(
    const Slice& prefix,
    const DBIntrospectCallback& key,
    const DBIntrospectCallback& value)
    : prefix_(prefix.ToString()) {
  introspect->Register(prefix_, key, value);
}

DBRegisterKeyIntrospect::~DBRegisterKeyIntrospect() {
  introspect->Unregister(prefix_);
}
