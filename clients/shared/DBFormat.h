// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_DB_FORMAT_H
#define VIEWFINDER_DB_FORMAT_H

#import "Callback.h"
#import "Format.h"
#import "Utils.h"
#import "WallTime.h"

class DBFormat {
 public:
  // This list is sorted by value rather than by function name, to make it easier to find non-conflicting prefixes.
  static string asset_key(const string& s) {
    return "a/" + s;
  }
  static string activity_key() {
    return "ac/";
  }
  static string activity_server_key() {
    return "acs/";
  }
  static string activity_timestamp_key(const string& s) {
    return "act/" + s;
  }
  static string asset_deletion_key(const string& s) {
    return "ad/" + s;
  }
  static string asset_fingerprint_key(const string& s) {
    return "af/" + s;
  }
  static string animated_stat_key(const string& s) {
    return "ast/" + s;
  }
  static string deprecated_asset_reverse_key(const string& s) {
    return "ar/" + s;
  }
  static string contact_key(const string& s) {
    return "c/" + s;
  }
  static string comment_activity_key(const string& s) {
    return "ca/" + s;
  }
  static string compose_autosuggest_key(const string& s) {
    return "cas/" + s;
  }
  static string contact_remove_queue_key(const string& server_contact_id) {
    return "ccrq/" + server_contact_id;
  }
  static string contact_upload_queue_key(const string& s) {
    return "ccuq/" + s;
  }
  static string deprecated_contact_id_key() {
    return "ci/";
  }
  static string deprecated_contact_id_key(const int64_t i) {
    return deprecated_contact_id_key() + ToString(i);
  }
  static string deprecated_contact_name_key() {
    return "cn/";
  }
  static string comment_key() {
    return "co/";
  }
  static string comment_server_key() {
    return "cos/";
  }
  static string user_queue_key() {
    return "cq/";
  }
  static string user_queue_key(const int64_t i) {
    return user_queue_key() + ToString(i);
  }
  static string server_contact_id_key(const string& s) {
    return "csi/" + s;
  }
  static string contact_source_key(const string& s) {
    return "csm/" + s;
  }
  static string user_update_queue_key() {
    return "cuq/";
  }
  static string user_update_queue_key(const int64_t i) {
    return user_update_queue_key() + ToString(i);
  }
  static string day_key(const string& s) {
    return "day/" + s;
  }
  static string db_migration_key(const string& s) {
    return "dbm/" + s;
  }
  static string day_event_key(const string& s) {
    return "dev/" + s;
  }
  static string day_episode_invalidation_key(const string& s) {
    return "dis/" + s;
  }
  static string day_summary_row_key(const string& s) {
    return "dsr/" + s;
  }
  static string episode_key() {
    return "e/";
  }
  static string episode_event_key(const string& s) {
    return "ees/" + s;
  }
  static string episode_photo_key(const string& s) {
    return "ep/" + s;
  }
  static string episode_activity_key(const string& s) {
    return "epa/" + s;
  }
  static string episode_parent_child_key(const string& s) {
    return "epc/" + s;
  }
  static string episode_selection_key(const string& eps) {
    return "eps/" + eps;
  }
  static string episode_server_key() {
    return "es/";
  }
  static string episode_timestamp_key(const string& s) {
    return "et/" + s;
  }
  static string deprecated_full_text_index_comment_key() {
    return "ftic/";
  }
  static string deprecated_full_text_index_episode_key() {
    return "ftie/";
  }
  static string deprecated_full_text_index_viewpoint_key() {
    return "ftiv/";
  }
  static string full_text_index_key() {
    return "ft/";
  }
  static string full_text_index_key(const string& s) {
    return "ft/" + s + "/";
  }
  static string follower_group_key_deprecated(const string& s) {
    return "fg/" + s;
  }
  static string follower_group_key(const string& s) {
    return "fog/" + s;
  }
  static string follower_viewpoint_key(const string& s) {
    return "fvp/" + s;
  }
  static string image_index_key(const string& s) {
    return "ii/" + s;
  }
  static string local_subscription_key(const string& s) {
    return "ls/" + s;
  }
  static string metadata_key(const string& s) {
    return "m/" + s;
  }
  static string new_user_key() {
    return "nu/";
  }
  static string new_user_key(int64_t user_id) {
    return new_user_key() + ToString(user_id);
  }
  static string network_queue_key(const string& s) {
    return "nq/" + s;
  }
  static string photo_key() {
    return "p/";
  }
  static string photo_duplicate_queue_key() {
    return "pdq/";
  }
  static string photo_episode_key(const string& s) {
    return "pe/" + s;
  }
  static string placemark_histogram_key() {
    return "ph/";
  }
  static string placemark_histogram_key(const string& s) {
    return "ph/" + s;
  }
  static string placemark_histogram_sort_key() {
    return "phs/";
  }
  static string placemark_histogram_sort_key(const string& s, int weight) {
    return Format("phs/%010d/%s", weight, s);
  }
  static string placemark_key(const string& s) {
    return "pl/" + s;
  }
  static string photo_path_key(const string& s) {
    return "pp/" + s;
  }
  static string photo_path_access_key(const string& s) {
    return "ppa/" + s;
  }
  static string photo_server_key() {
    return "ps/";
  }
  static string photo_url_key(const string& s) {
    return "pu/" + s;
  }
  static string quarantined_activity_key(const string& s) {
    return "qa/" + s;
  }
  static string server_subscription_key(const string& s) {
    return "ss/" + s;
  }
  static string trapdoor_event_key() {
    return "te/";
  }
  static string trapdoor_event_key(int64_t vp_id, const string& event_key) {
    return Format("%s%s/%s", trapdoor_event_key(), vp_id, event_key);
  }
  static string trapdoor_key(const string& s) {
    return "trp/" + s;
  }
  static string user_id_key() {
    return "u/";
  }
  static string user_id_key(int64_t user_id) {
    return user_id_key() + ToString(user_id);
  }
  static string user_invalidation_key(const string& s) {
    return "ui/" + s;
  }
  static string user_identity_key(const string& s) {
    return "uid/" + s;
  }
  static string deprecated_user_name_key() {
    return "un/";
  }
  static string viewpoint_key() {
    return "v/";
  }
  static string viewpoint_conversation_key(const string& s) {
    return "vcs/" + s;
  }
  static string viewpoint_activity_key(const string& vpa) {
    return "vpa/" + vpa;
  }
  static string viewpoint_follower_key(const string& s) {
    return "vpf/" + s;
  }
  static string viewpoint_gc_key(const string& s) {
    return "vpgc/" + s;
  }
  static string viewpoint_invalidation_key(const string& s) {
    return "vpi/" + s;
  }
  static string viewpoint_selection_key(const string& vps) {
    return "vps/" + vps;
  }
  static string viewpoint_scroll_offset_key(const string& s) {
    return "vpso/" + s;
  }
  static string viewpoint_server_key() {
    return "vs/";
  }
  static string viewpoint_summary_key() {
    return "vsum/";
  }
};

class DBIntrospect {
 public:
  // Translates a raw key into a human readable debug key.
  static string Format(const Slice& key, const Slice& value = Slice());

  template <typename Message>
  static string FormatProto(const Slice& value) {
    Message m;
    if (!m.ParseFromArray(value.data(), value.size())) {
      return string();
    }
    return ToString(m);
  }

  // Common format for timestamps in human readable debug keys.
  static WallTimeFormat timestamp(WallTime t) {
    return WallTimeFormat("%Y-%m-%d-%H-%M-%S", t);
  }

  static const string kUnhandledValue;
};

using DBIntrospectCallback = Callback<string (Slice)>;

// Registers a block to be invoked when DBIntrospect::Format() is
// called. prefix must match the prefix of the key up to and including the "/"
// (e.g. "m/").
class DBRegisterKeyIntrospect {
 public:
  DBRegisterKeyIntrospect(const Slice& prefix,
                          const DBIntrospectCallback& key,
                          const DBIntrospectCallback& value);
  ~DBRegisterKeyIntrospect();

 private:
  const string prefix_;
};

#endif  // VIEWFINDER_DB_FORMAT_H
