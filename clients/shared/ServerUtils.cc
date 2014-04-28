// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <unordered_map>
#import <re2/re2.h>
#import "ActivityMetadata.pb.h"
#import "AppState.h"
#import "ContactManager.h"
#import "DBFormat.h"
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "Server.pb.h"
#import "ServerUtils.h"
#import "STLUtils.h"
#import "StringUtils.h"

namespace {

const string kAssetKeyPrefix = DBFormat::asset_key("");

LazyStaticPtr<RE2, const char*> kS3RequestTimeoutErrorRE = {
  "<Code>RequestTimeout</Code>"
};

// Add handlers for new photo & episode handlers below.
template<typename T>
struct LabelHandler {
    string label;
    bool (T::*has)() const;
    bool (T::*getter)() const;
    void (T::*setter)(bool v);
};

template<typename T>
class LabelHandlerMap: public std::unordered_map<string, LabelHandler<T> > {
};

template <typename T>
LabelHandlerMap<T> MakeLabelHandlerMap(LabelHandler<T>* handlers, int num_handlers) {
  LabelHandlerMap<T> handler_map;
  for (int i = 0; i < num_handlers; ++i) {
    const LabelHandler<T>& handler = handlers[i];
    handler_map[handler.label] = handler;
  }
  return handler_map;
}

typedef PhotoMetadata PM;
LabelHandler<PM> kPhotoLabelHandlers[] = {
  { "error", &PM::has_label_error, &PM::label_error, &PM::set_label_error },
  { "removed", &PM::has_label_removed, &PM::label_removed, &PM::set_label_removed },
  { "hidden", &PM::has_label_hidden, &PM::label_hidden, &PM::set_label_hidden },
  { "unshared", &PM::has_label_unshared, &PM::label_unshared, &PM::set_label_unshared },
};
LabelHandlerMap<PM> photo_handler_map = MakeLabelHandlerMap(
    kPhotoLabelHandlers, ARRAYSIZE(kPhotoLabelHandlers));

typedef EpisodeMetadata EM;
LabelHandler<EM> kEpisodeLabelHandlers[] = {
};
LabelHandlerMap<EM> episode_handler_map = MakeLabelHandlerMap(
    kEpisodeLabelHandlers, ARRAYSIZE(kEpisodeLabelHandlers));

typedef QueryViewpointsResponse::FollowerMetadata FM;
LabelHandler<FM> kFollowerLabelHandlers[] = {
  { "removed", &FM::has_label_removed, &FM::label_removed, &FM::set_label_removed },
  { "unrevivable", &FM::has_label_unrevivable, &FM::label_unrevivable, &FM::set_label_unrevivable },
};
LabelHandlerMap<FM> follower_handler_map = MakeLabelHandlerMap(
    kFollowerLabelHandlers, ARRAYSIZE(kFollowerLabelHandlers));

typedef ViewpointMetadata VM;
LabelHandler<VM> kViewpointLabelHandlers[] = {
  { "admin", &VM::has_label_admin, &VM::label_admin, &VM::set_label_admin },
  { "contribute", &VM::has_label_contribute, &VM::label_contribute, &VM::set_label_contribute },
  { "hidden", &VM::has_label_hidden, &VM::label_hidden, &VM::set_label_hidden },
  { "muted", &VM::has_label_muted, &VM::label_muted, &VM::set_label_muted },
  { "autosave", &VM::has_label_autosave, &VM::label_autosave, &VM::set_label_autosave },
  { "removed", &VM::has_label_removed, &VM::label_removed, &VM::set_label_removed },
  { "unrevivable", &VM::has_label_unrevivable, &VM::label_unrevivable, &VM::set_label_unrevivable },
};
LabelHandlerMap<VM> viewpoint_handler_map = MakeLabelHandlerMap(
    kViewpointLabelHandlers, ARRAYSIZE(kViewpointLabelHandlers));

typedef ContactMetadata CM;
LabelHandler<CM> kContactLabelHandlers[] = {
  { "removed", &CM::has_label_contact_removed, &CM::label_contact_removed, &CM::set_label_contact_removed },
};
LabelHandlerMap<CM> contact_handler_map = MakeLabelHandlerMap(
    kContactLabelHandlers, ARRAYSIZE(kContactLabelHandlers));

LabelHandler<CM> kUserLabelHandlers[] = {
  { "registered", &CM::has_label_registered, &CM::label_registered, &CM::set_label_registered },
  { "terminated", &CM::has_label_terminated, &CM::label_terminated, &CM::set_label_terminated },
  { "friend", &CM::has_label_friend, &CM::label_friend, &CM::set_label_friend },
  { "system", &CM::has_label_system, &CM::label_system, &CM::set_label_system },
};
LabelHandlerMap<CM> user_handler_map = MakeLabelHandlerMap(
    kUserLabelHandlers, ARRAYSIZE(kUserLabelHandlers));

LabelHandler<CM> kResolvedContactLabelHandlers[] = {
  { "registered", &CM::has_label_registered, &CM::label_registered, &CM::set_label_registered },
};
LabelHandlerMap<CM> resolved_contact_handler_map = MakeLabelHandlerMap(
    kResolvedContactLabelHandlers, ARRAYSIZE(kResolvedContactLabelHandlers));

typedef std::unordered_map<string, ErrorResponse::ErrorId> ErrorIdMap;

ErrorIdMap MakeErrorIdMap() {
  ErrorIdMap m;
  m["INVALID_JSON_REQUEST"] = ErrorResponse::INVALID_JSON_REQUEST;
  m["NO_USER_ACCOUNT"] = ErrorResponse::NO_USER_ACCOUNT;
  m["UPDATE_PWD_NOT_CONFIRMED"] = ErrorResponse::UPDATE_PWD_NOT_CONFIRMED;
  m["ALREADY_REGISTERED"] = ErrorResponse::ALREADY_REGISTERED;
  return m;
}

const ErrorIdMap error_id_map = MakeErrorIdMap();

typedef std::unordered_map<string, SystemMessage::Severity> SeverityMap;

SeverityMap MakeSeverityMap() {
  SeverityMap m;
  m["SILENT"] = SystemMessage::SILENT;
  m["INFO"] = SystemMessage::INFO;
  m["ATTENTION"] = SystemMessage::ATTENTION;
  m["DISABLE_NETWORK"] = SystemMessage::DISABLE_NETWORK;
  return m;
}

const SeverityMap severity_map = MakeSeverityMap();

template <typename T>
bool MaybeSet(
    T* obj, void (T::*setter)(const string&), const JsonRef& value) {
  if (value.empty()) {
    return false;
  }
  (obj->*setter)(value.string_value());
  return true;
}

template <typename T>
bool MaybeSet(
    T* obj, void (T::*setter)(int64_t), const JsonRef& value) {
  if (value.empty()) {
    return false;
  }
  (obj->*setter)(value.int64_value());
  return true;
}

template <typename T>
bool MaybeSet(
    T* obj, void (T::*setter)(int32_t), const JsonRef& value) {
  if (value.empty()) {
    return false;
  }
  (obj->*setter)(value.int32_value());
  return true;
}

template <typename T>
bool MaybeSet(
    T* obj, void (T::*setter)(double), const JsonRef& value) {
  if (value.empty()) {
    return false;
  }
  (obj->*setter)(value.double_value());
  return true;
}

template <typename T>
void MaybeSet(
    T* obj, void (T::*setter)(bool), const JsonRef& value) {
  if (value.empty()) {
    return;
  }
  (obj->*setter)(value.bool_value());
}

template <typename T>
void MaybeParseResponseHeaders(T* obj, const JsonRef& d) {
  if (d.empty()) {
    return;
  }
  Headers* h = obj->mutable_headers();
  MaybeSet(h, &Headers::set_version, d["version"]);
  MaybeSet(h, &Headers::set_min_required_version, d["min_required_version"]);
  MaybeSet(h, &Headers::set_op_id, d["op_id"]);
}

bool ParseAccountSettingsMetadata(AccountSettingsMetadata* a, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  MaybeSet(a, &AccountSettingsMetadata::set_email_alerts, d["email_alerts"]);
  const JsonRef storage_options(d["storage_options"]);
  for (int i = 0; i < storage_options.size(); ++i) {
    a->add_storage_options(storage_options[i].string_value());
  }
  return true;
}

bool ParseLocation(Location* l, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef Location T;
  MaybeSet(l, &T::set_latitude, d["latitude"]);
  MaybeSet(l, &T::set_longitude, d["longitude"]);
  MaybeSet(l, &T::set_accuracy, d["accuracy"]);
  return true;
}

bool ParsePlacemark(Placemark* p, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef Placemark T;
  MaybeSet(p, &T::set_iso_country_code, d["iso_country_code"]);
  MaybeSet(p, &T::set_country, d["country"]);
  MaybeSet(p, &T::set_state, d["state"]);
  MaybeSet(p, &T::set_locality, d["locality"]);
  MaybeSet(p, &T::set_sublocality, d["sublocality"]);
  MaybeSet(p, &T::set_thoroughfare, d["thoroughfare"]);
  MaybeSet(p, &T::set_subthoroughfare, d["subthoroughfare"]);
  return true;
}

bool ParsePhotoId(PhotoId* i, const JsonRef& v) {
  if (v.empty()) {
    return false;
  }
  MaybeSet(i, &PhotoId::set_server_id, v);
  return true;
}

bool ParseCommentId(CommentId* i, const JsonRef& v) {
  if (v.empty()) {
    return false;
  }
  MaybeSet(i, &CommentId::set_server_id, v);
  return true;
}

bool ParseEpisodeId(EpisodeId* i, const JsonRef& v) {
  if (v.empty()) {
    return false;
  }
  MaybeSet(i, &EpisodeId::set_server_id, v);
  return true;
}

bool ParseViewpointId(ViewpointId* i, const JsonRef& v) {
  if (v.empty()) {
    return false;
  }
  MaybeSet(i, &ViewpointId::set_server_id, v);
  return true;
}

bool ParseCoverPhoto(CoverPhoto* cp, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  if (!ParsePhotoId(cp->mutable_photo_id(), d["photo_id"])) {
    return false;
  }
  if (!ParseEpisodeId(cp->mutable_episode_id(), d["episode_id"])) {
    return false;
  }
  // We specifically ignore the potential URLs returned here--
  // they're not necessary for mobile app use as we already
  // have photo URLs for cover photo as part of querying the
  // episodes to which they belong.
  return true;
}

template <typename T>
bool HandleLabel(const LabelHandlerMap<T>& handler_map, T* p, const string& label) {
  Slice l(label);
  if (l.empty()) {
    // Skip invalid label.
    return false;
  }
  const LabelHandler<T>* handler = FindPtrOrNull(handler_map, l.ToString());
  if (!handler) {
    // Skip unknown labels.
    return false;
  }
  (p->*handler->setter)(true);
  return true;
}

template <typename T>
void ParseLabels(const LabelHandlerMap<T>& handler_map, T* p, const JsonRef& v) {
  if (v.empty()) {
    return;
  }

  // Set all labels to false before parsing any true values.
  for (typename LabelHandlerMap<T>::const_iterator iter = handler_map.begin();
       iter != handler_map.end();
       ++iter) {
    (p->*iter->second.setter)(false);
  }

  // Set true values from array of set labels.
  for (int i = 0; i < v.size(); ++i) {
    HandleLabel(handler_map, p, v[i].string_value());
  }
}

bool ParsePhotoMetadataImage(
    PhotoMetadata::Image* i, const JsonRef& md5, const JsonRef& size) {
  typedef PhotoMetadata::Image T;
  MaybeSet(i, &T::set_md5, md5);
  MaybeSet(i, &T::set_size, size);
  return i->has_md5() || i->has_size();
}

bool ParsePhotoMetadataImages(PhotoMetadata::Images* i, const JsonRef& d) {
  if (!ParsePhotoMetadataImage(
          i->mutable_tn(), d["tn_md5"],
          d["tn_size"])) {
    i->clear_tn();
  }
  if (!ParsePhotoMetadataImage(
          i->mutable_med(), d["med_md5"],
          d["med_size"])) {
    i->clear_med();
  }
  if (!ParsePhotoMetadataImage(
          i->mutable_full(), d["full_md5"],
          d["full_size"])) {
    i->clear_full();
  }
  if (!ParsePhotoMetadataImage(
          i->mutable_orig(), d["orig_md5"],
          d["orig_size"])) {
    i->clear_orig();
  }
  return i->has_tn() || i->has_med() || i->has_full() || i->has_orig();
}

bool ParsePhotoMetadata(PhotoMetadata* p, const JsonRef& d) {
  typedef PhotoMetadata T;
  if (!ParsePhotoId(p->mutable_id(), d["photo_id"])) {
    p->clear_id();
  }
  if (!ParsePhotoId(p->mutable_parent_id(), d["parent_id"])) {
    p->clear_parent_id();
  }
  if (!ParseEpisodeId(p->mutable_episode_id(), d["episode_id"])) {
    p->clear_episode_id();
  }
  MaybeSet(p, &T::set_user_id, d["user_id"]);
  MaybeSet(p, &T::set_sharing_user_id, d["sharing_user_id"]);
  MaybeSet(p, &T::set_aspect_ratio, d["aspect_ratio"]);
  MaybeSet(p, &T::set_timestamp, d["timestamp"]);
  ParseLabels(photo_handler_map, p, d["labels"]);
  if (!ParseLocation(p->mutable_location(), d["location"])) {
    p->clear_location();
  }
  if (!ParsePlacemark(p->mutable_placemark(), d["placemark"])) {
    p->clear_placemark();
  }
  MaybeSet(p, &T::set_caption, d["caption"]);
  MaybeSet(p, &T::set_link, d["link"]);

  if (!ParsePhotoMetadataImages(p->mutable_images(), d)) {
    p->clear_images();
  }

  const JsonRef asset_keys(d["asset_keys"]);
  for (int i = 0; i < asset_keys.size(); i++) {
    Slice fingerprint, url;
    const string asset_key = asset_keys[i].string_value();
    if (!DecodeAssetKey(asset_key, &url, &fingerprint)) {
      continue;
    }
    p->add_asset_fingerprints(ToString(fingerprint));
  }
  return true;
}

bool ParsePhotoUpdate(
    PhotoUpdate* p, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  if (!ParsePhotoMetadata(p->mutable_metadata(), d)) {
    return false;
  }
  typedef PhotoUpdate T;
  MaybeSet(p, &T::set_tn_get_url, d["tn_get_url"]);
  MaybeSet(p, &T::set_tn_put_url, d["tn_put_url"]);
  MaybeSet(p, &T::set_med_get_url, d["med_get_url"]);
  MaybeSet(p, &T::set_med_put_url, d["med_put_url"]);
  MaybeSet(p, &T::set_full_get_url, d["full_get_url"]);
  MaybeSet(p, &T::set_full_put_url, d["full_put_url"]);
  MaybeSet(p, &T::set_orig_get_url, d["orig_get_url"]);
  MaybeSet(p, &T::set_orig_put_url, d["orig_put_url"]);
  return true;
}

bool ParseCommentMetadata(CommentMetadata* v, const JsonRef& d) {
  typedef CommentMetadata T;
  if (!ParseCommentId(v->mutable_comment_id(), d["comment_id"])) {
    v->clear_comment_id();
  }
  if (!ParseViewpointId(v->mutable_viewpoint_id(), d["viewpoint_id"])) {
    v->clear_viewpoint_id();
  }
  MaybeSet(v, &T::set_user_id, d["user_id"]);
  MaybeSet(v, &T::set_asset_id, d["asset_id"]);
  MaybeSet(v, &T::set_timestamp, d["timestamp"]);
  MaybeSet(v, &T::set_message, d["message"]);
  return true;
}

bool ParseEpisodeMetadata(EpisodeMetadata* v, const JsonRef& d) {
  typedef EpisodeMetadata T;
  if (!ParseEpisodeId(v->mutable_id(), d["episode_id"])) {
    v->clear_id();
  }
  if (!ParseEpisodeId(v->mutable_parent_id(), d["parent_ep_id"])) {
    v->clear_parent_id();
  }
  if (!ParseViewpointId(v->mutable_viewpoint_id(), d["viewpoint_id"])) {
    v->clear_viewpoint_id();
  }
  MaybeSet(v, &T::set_user_id, d["user_id"]);
  MaybeSet(v, &T::set_sharing_user_id, d["sharing_user_id"]);
  MaybeSet(v, &T::set_timestamp, d["timestamp"]);
  MaybeSet(v, &T::set_publish_timestamp, d["publish_timestamp"]);
  ParseLabels(episode_handler_map, v, d["labels"]);
  MaybeSet(v, &T::set_title, d["title"]);
  MaybeSet(v, &T::set_description, d["description"]);
  MaybeSet(v, &T::set_name, d["name"]);
  return true;
}

bool ParseFollowerMetadata(QueryViewpointsResponse::FollowerMetadata* fm, const JsonRef& d) {
  typedef QueryViewpointsResponse::FollowerMetadata T;
  MaybeSet(fm, &T::set_follower_id, d["follower_id"]);
  ParseLabels(follower_handler_map, fm, d["labels"]);
  return true;
}

bool ParseViewpointMetadata(ViewpointMetadata* v, const JsonRef& d) {
  typedef ViewpointMetadata T;
  if (!ParseViewpointId(v->mutable_id(), d["viewpoint_id"])) {
    v->clear_id();
  }
  MaybeSet(v, &T::set_user_id, d["user_id"]);
  MaybeSet(v, &T::set_update_seq, d["update_seq"]);
  MaybeSet(v, &T::set_sharing_user_id, d["sharing_user_id"]);
  MaybeSet(v, &T::set_title, d["title"]);
  MaybeSet(v, &T::set_description, d["description"]);
  MaybeSet(v, &T::set_name, d["name"]);
  MaybeSet(v, &T::set_type, d["type"]);
  MaybeSet(v, &T::set_viewed_seq, d["viewed_seq"]);
  if (!ParseCoverPhoto(v->mutable_cover_photo(), d["cover_photo"])) {
    v->clear_cover_photo();
  }
  ParseLabels(viewpoint_handler_map, v, d["labels"]);
  return true;
}

bool ParseContactMetadata(ContactMetadata* c, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef ContactMetadata T;

  MaybeSet(c, &T::set_server_contact_id, d["contact_id"]);
  MaybeSet(c, &T::set_contact_source, d["contact_source"]);
  MaybeSet(c, &T::set_name, d["name"]);
  MaybeSet(c, &T::set_first_name, d["given_name"]);
  MaybeSet(c, &T::set_last_name, d["family_name"]);
  MaybeSet(c, &T::set_rank, d["rank"]);
  const JsonRef identities(d["identities"]);
  for (int i = 0; i < identities.size(); i++) {
    ContactIdentityMetadata* ci = c->add_identities();
    const JsonRef cid(identities[i]);
    MaybeSet(ci, &ContactIdentityMetadata::set_identity, cid["identity"]);
    MaybeSet(ci, &ContactIdentityMetadata::set_description, cid["description"]);
    MaybeSet(ci, &ContactIdentityMetadata::set_user_id, cid["user_id"]);
    DCHECK(ci->has_identity());
    if (ci->has_identity() && !c->has_primary_identity()) {
      c->set_primary_identity(ci->identity());
    }
  }
  ParseLabels(contact_handler_map, c, d["labels"]);
  return true;
}

bool ParseResolvedContactMetadata(ContactMetadata* c, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef ContactMetadata CM;
  typedef ContactIdentityMetadata CIM;
  MaybeSet(c, &CM::set_primary_identity, d["identity"]);
  if (c->has_primary_identity()) {
    c->add_identities()->set_identity(c->primary_identity());
  }
  MaybeSet(c, &CM::set_user_id, d["user_id"]);
  MaybeSet(c, &CM::set_name, d["name"]);
  // Resolved contacts contain some user data, but they're incomplete, so we need to request a full query later.
  c->set_need_query_user(true);
  c->set_contact_source(ContactManager::kContactSourceManual);
  ParseLabels(resolved_contact_handler_map, c, d["labels"]);
  return true;
}

bool ParseUsageCategoryMetadata(UsageCategoryMetadata* u, const JsonRef& d) {
  typedef UsageCategoryMetadata T;
  MaybeSet(u, &T::set_num_photos, d["num_photos"]);
  MaybeSet(u, &T::set_tn_size, d["tn_size"]);
  MaybeSet(u, &T::set_med_size, d["med_size"]);
  MaybeSet(u, &T::set_full_size, d["full_size"]);
  MaybeSet(u, &T::set_orig_size, d["orig_size"]);
  return true;
}

bool ParseUsageMetadata(UsageMetadata* u, const JsonRef& d) {
  const JsonRef& owned_by = d["owned_by"];
  if (!owned_by.empty() &&
      !ParseUsageCategoryMetadata(u->mutable_owned_by(), owned_by)) {
    return false;
  }
  const JsonRef& shared_by = d["shared_by"];
  if (!shared_by.empty() &&
      !ParseUsageCategoryMetadata(u->mutable_shared_by(), shared_by)) {
    return false;
  }
  const JsonRef& visible_to = d["visible_to"];
  if (!visible_to.empty() &&
      !ParseUsageCategoryMetadata(u->mutable_visible_to(), visible_to)) {
    return false;
  }

  return true;
}

bool ParseUserMetadata(ContactMetadata* c, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef ContactMetadata T;
  MaybeSet(c, &T::set_name, d["name"]);
  MaybeSet(c, &T::set_user_id, d["user_id"]);
  MaybeSet(c, &T::set_first_name, d["given_name"]);
  MaybeSet(c, &T::set_last_name, d["family_name"]);
  MaybeSet(c, &T::set_nickname, d["nickname"]);
  MaybeSet(c, &T::set_email, d["email"]);
  MaybeSet(c, &T::set_phone, d["phone"]);
  MaybeSet(c, &T::set_merged_with, d["merged_with"]);
  ParseLabels(user_handler_map, c, d["labels"]);

  if (!(d.Contains("private") ||
        (c->label_friend() && c->label_registered()))) {
    // The server returns incomplete results for users that are not friends.
    // Flag this result as tentative so it won't replace data merged from a contact record
    // or prevent requerying this user in the future.
    // Prospective users may be "friends" before they are registered.  Set the flag in this case
    // to allow names from a matching contact to be used until the prospective user registers.
    c->set_need_query_user(true);
  }
  return true;
}

bool ParseQueryEpisodesEpisode(
    QueryEpisodesResponse::Episode* e, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }

  typedef QueryEpisodesResponse::Episode T;
  MaybeSet(e, &T::set_last_key, d["last_key"]);
  if (!ParseEpisodeMetadata(e->mutable_metadata(), d)) {
    e->clear_metadata();
    return false;
  }

  {
    const JsonRef photos(d["photos"]);
    for (int i = 0; i < photos.size(); ++i) {
      if (!ParsePhotoUpdate(e->add_photos(), photos[i])) {
        return false;
      }
    }
  }

  return true;
}

template <typename A>
bool ParseActivityEpisodes(A* activity, const JsonRef& episodes) {
  typedef ActivityMetadata::Episode E;
  typedef EpisodeId EI;
  typedef PhotoId PI;

  for (int i = 0; i < episodes.size(); ++i) {
    const JsonRef& ed = episodes[i];
    E* e = activity->add_episodes();
    MaybeSet(e->mutable_episode_id(), &EI::set_server_id, ed["episode_id"]);
    const JsonRef photo_ids(ed["photo_ids"]);
    for (int j = 0; j < photo_ids.size(); ++j) {
      MaybeSet(e->add_photo_ids(), &PI::set_server_id, photo_ids[j]);
    }
  }
  return true;
}

bool ParseActivityMetadataAddFollowers(
    ActivityMetadata::AddFollowers* a, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  // Add followers includes only user ids, but the activity metadata
  // accommodates a full contact metadata. We simply set the user_id.
  // The expansive contact metadata is only used for
  // locally-constructed activities which are pending server upload.
  const JsonRef follower_ids(d["follower_ids"]);
  for (int i = 0; i < follower_ids.size(); ++i) {
    a->add_contacts()->set_user_id(follower_ids[i].int64_value());
  }
  return true;
}

bool ParseActivityMetadataMergeAccounts(
    ActivityMetadata::MergeAccounts* m, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef ActivityMetadata::MergeAccounts MA;
  MaybeSet(m, &MA::set_target_user_id, d["target_user_id"]);
  MaybeSet(m, &MA::set_source_user_id, d["source_user_id"]);
  return true;
}

bool ParseActivityMetadataPostComment(
    ActivityMetadata::PostComment* p, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  if (!ParseCommentId(p->mutable_comment_id(), d["comment_id"])) {
    p->clear_comment_id();
  }
  return true;
}

bool ParseActivityMetadataShareExisting(
    ActivityMetadata::ShareExisting* s, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  return ParseActivityEpisodes(s, d["episodes"]);
}

bool ParseActivityMetadataShareNew(
    ActivityMetadata::ShareNew* s, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }

  bool fully_parsed = ParseActivityEpisodes(s, d["episodes"]);
  const JsonRef follower_ids(d["follower_ids"]);
  for (int i = 0; i < follower_ids.size(); ++i) {
    s->add_contacts()->set_user_id(follower_ids[i].int64_value());
  }
  return fully_parsed;
}

bool ParseActivityMetadataUnshare(
    ActivityMetadata::Unshare* u, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  return ParseActivityEpisodes(u, d["episodes"]);
}

bool ParseActivityMetadataUpdateEpisode(
    ActivityMetadata::UpdateEpisode* ue, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef EpisodeId EI;

  bool fully_parsed = true;
  for (auto key : d.member_names()) {
    if (key == "episode_id") {
      MaybeSet(ue->mutable_episode_id(), &EI::set_server_id, d["episode_id"]);
    } else {
      fully_parsed = false;
    }
  }
  return fully_parsed;
}

bool ParseActivityMetadataUpdateViewpoint(
    ActivityMetadata::UpdateViewpoint* ue, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef ViewpointId EI;

  bool fully_parsed = true;
  for (auto key : d.member_names()) {
    if (key == "viewpoint_id") {
      MaybeSet(ue->mutable_viewpoint_id(), &EI::set_server_id, d["viewpoint_id"]);
    } else {
      fully_parsed = false;
    }
  }
  return fully_parsed;
}

bool ParseActivityMetadataUploadEpisode(
    ActivityMetadata::UploadEpisode* up, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef EpisodeId EI;
  typedef PhotoId PI;

  bool fully_parsed = true;
  for (auto key : d.member_names()) {
    if (key == "episode_id") {
      MaybeSet(up->mutable_episode_id(), &EI::set_server_id, d["episode_id"]);
    } else if (key == "photo_ids") {
      const JsonRef photo_ids(d["photo_ids"]);
      for (int i = 0; i < photo_ids.size(); ++i) {
        MaybeSet(up->add_photo_ids(), &PI::set_server_id, photo_ids[i]);
      }
    } else if (key != "viewpoint_id" &&
               key != "activity_id" &&
               key != "user_id" &&
               key != "timestamp") {
      fully_parsed = false;
    }
  }
  return fully_parsed;
}

bool ParseActivityMetadata(ActivityMetadata* a, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef ViewpointId VI;
  typedef ActivityId AI;
  typedef ActivityMetadata T;
  MaybeSet(a->mutable_viewpoint_id(), &VI::set_server_id, d["viewpoint_id"]);
  MaybeSet(a->mutable_activity_id(), &AI::set_server_id, d["activity_id"]);
  MaybeSet(a, &T::set_user_id, d["user_id"]);
  MaybeSet(a, &T::set_timestamp, d["timestamp"]);
  MaybeSet(a, &T::set_update_seq, d["update_seq"]);

  const bool add_followers = ParseActivityMetadataAddFollowers(
      a->mutable_add_followers(), d["add_followers"]);
  if (!add_followers) {
    a->clear_add_followers();
  }

  const bool merge_accounts = ParseActivityMetadataMergeAccounts(
      a->mutable_merge_accounts(), d["merge_accounts"]);
  if (!merge_accounts) {
    a->clear_merge_accounts();
  }

  const bool post_comment = ParseActivityMetadataPostComment(
      a->mutable_post_comment(), d["post_comment"]);
  if (!post_comment) {
    a->clear_post_comment();
  }

  const bool share_new = ParseActivityMetadataShareNew(
      a->mutable_share_new(), d["share_new"]);
  if (!share_new) {
    a->clear_share_new();
  }

  const bool share_existing = ParseActivityMetadataShareExisting(
      a->mutable_share_existing(), d["share_existing"]);
  if (!share_existing) {
    a->clear_share_existing();
  }

  const bool unshare = ParseActivityMetadataUnshare(
      a->mutable_unshare(), d["unshare"]);
  if (!unshare) {
    a->clear_unshare();
  }

  const bool update_episode = ParseActivityMetadataUpdateEpisode(
      a->mutable_update_episode(), d["update_episode"]);
  if (!update_episode) {
    a->clear_update_episode();
  }

  const bool update_viewpoint = ParseActivityMetadataUpdateViewpoint(
      a->mutable_update_viewpoint(), d["update_viewpoint"]);
  if (!update_viewpoint) {
    a->clear_update_viewpoint();
  }

  const bool upload_episode = ParseActivityMetadataUploadEpisode(
      a->mutable_upload_episode(), d["upload_episode"]);
  if (!upload_episode) {
    a->clear_upload_episode();
  }

  return (add_followers || post_comment || share_existing || share_new ||
          unshare || update_episode || update_viewpoint ||upload_episode);
}

bool ParseEpisodeSelection(EpisodeSelection* e, const JsonRef& ed) {
  typedef EpisodeSelection E;
  MaybeSet(e, &E::set_episode_id, ed["episode_id"]);
  MaybeSet(e, &E::set_get_attributes, ed["get_attributes"]);
  MaybeSet(e, &E::set_get_photos, ed["get_photos"]);
  MaybeSet(e, &E::set_photo_start_key, ed["photo_start_key"]);
  return true;
}

bool ParseViewpointSelection(ViewpointSelection* v, const JsonRef& vd) {
  typedef ViewpointSelection V;
  MaybeSet(v, &V::set_viewpoint_id, vd["viewpoint_id"]);
  MaybeSet(v, &V::set_get_attributes, vd["get_attributes"]);
  MaybeSet(v, &V::set_get_followers, vd["get_followers"]);
  MaybeSet(v, &V::set_follower_start_key, vd["follower_start_key"]);
  MaybeSet(v, &V::set_get_activities, vd["get_activities"]);
  MaybeSet(v, &V::set_activity_start_key, vd["activity_start_key"]);
  MaybeSet(v, &V::set_get_episodes, vd["get_episodes"]);
  MaybeSet(v, &V::set_episode_start_key, vd["episode_start_key"]);
  MaybeSet(v, &V::set_get_comments, vd["get_comments"]);
  MaybeSet(v, &V::set_comment_start_key, vd["comment_start_key"]);
  return true;
}

bool ParseUserIdentityMetadata(ContactIdentityMetadata* id, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  MaybeSet(id, &ContactIdentityMetadata::set_identity, d["identity"]);
  // Authority is not used on the client side.
  return true;
}

bool ParseInvalidateMetadata(InvalidateMetadata* inv, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }

  typedef InvalidateMetadata I;
  MaybeSet(inv, &I::set_all, d["all"]);
  if (inv->all()) {
    return true;
  }

  const JsonRef& viewpoints = d["viewpoints"];
  for (int i = 0; i < viewpoints.size(); ++i) {
    ViewpointSelection vs;
    if (ParseViewpointSelection(&vs, viewpoints[i])) {
      inv->add_viewpoints()->CopyFrom(vs);
    }
  }
  const JsonRef& episodes = d["episodes"];
  for (int i = 0; i < episodes.size(); ++i) {
    EpisodeSelection es;
    if (ParseEpisodeSelection(&es, episodes[i])) {
      inv->add_episodes()->CopyFrom(es);
    }
  }
  typedef ContactSelection C;
  const JsonRef& contacts = d["contacts"];
  if (!contacts.empty()) {
    MaybeSet(inv->mutable_contacts(), &C::set_start_key,
             contacts["start_key"]);
    MaybeSet(inv->mutable_contacts(), &C::set_all,
             contacts["all"]);
  }

  const JsonRef& users = d["users"];
  if (!users.empty()) {
    for (int i = 0; i < users.size(); ++i) {
      inv->add_users()->set_user_id(users[i].int64_value());
    }
  }

  return true;
}

bool ParseInlineInvalidation(
    QueryNotificationsResponse::InlineInvalidation* ii, const JsonRef& d) {
  typedef QueryNotificationsResponse::InlineViewpoint IV;
  if (d.empty()) {
    return false;
  }
  bool activity = ParseActivityMetadata(
      ii->mutable_activity(), d["activity"]);
  if (!activity) {
    ii->clear_activity();
  }
  const JsonRef& inline_viewpoint = d["viewpoint"];
  if (!inline_viewpoint.empty()) {
    IV* iv = ii->mutable_viewpoint();
    MaybeSet(iv, &IV::set_viewpoint_id, inline_viewpoint["viewpoint_id"]);
    MaybeSet(iv, &IV::set_update_seq, inline_viewpoint["update_seq"]);
    MaybeSet(iv, &IV::set_viewed_seq, inline_viewpoint["viewed_seq"]);
  }

  const JsonRef& inline_comment = d["comment"];
  if (!inline_comment.empty()) {
    if (!ParseCommentMetadata(ii->mutable_comment(), inline_comment)) {
      return false;
    }
  }

  const JsonRef& inline_user = d["user"];
  if (!inline_user.empty()) {
    // For now, usage is the only info in "user".
    const JsonRef& usage = inline_user["usage"];
    if (!usage.empty()) {
      if (!ParseUsageMetadata(ii->mutable_usage(), usage)) {
        return false;
      }
    }
  }

  return true;
}

bool ParseQueryNotificationsNotification(
    QueryNotificationsResponse::Notification* n, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  typedef QueryNotificationsResponse::InlineInvalidation II;
  typedef QueryNotificationsResponse::Notification T;
  MaybeSet(n, &T::set_notification_id, d["notification_id"]);
  MaybeSet(n, &T::set_name, d["name"]);
  MaybeSet(n, &T::set_sender_id, d["sender_id"]);
  MaybeSet(n, &T::set_op_id, d["op_id"]);
  MaybeSet(n, &T::set_timestamp, d["timestamp"]);

  bool invalidate = ParseInvalidateMetadata(n->mutable_invalidate(), d["invalidate"]);
  if (!invalidate) {
    n->clear_invalidate();
  }
  bool inline_invalidate =
      ParseInlineInvalidation(n->mutable_inline_invalidate(), d["inline"]);
  if (!inline_invalidate) {
    n->clear_inline_invalidate();
  }
  return true;
}

bool ParseQueryViewpointsViewpoint(
    QueryViewpointsResponse::Viewpoint* v, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }

  typedef QueryViewpointsResponse::Viewpoint T;
  MaybeSet(v, &T::set_follower_last_key, d["follower_last_key"]);
  MaybeSet(v, &T::set_activity_last_key, d["activity_last_key"]);
  MaybeSet(v, &T::set_episode_last_key, d["episode_last_key"]);
  MaybeSet(v, &T::set_comment_last_key, d["comment_last_key"]);

  if (!ParseViewpointMetadata(v->mutable_metadata(), d)) {
    v->clear_metadata();
    return false;
  }

  {
    const JsonRef followers(d["followers"]);
    for (int i = 0; i < followers.size(); ++i) {
      ParseFollowerMetadata(v->add_followers(), followers[i]);
    }
  }

  {
    const JsonRef activities(d["activities"]);
    for (int i = 0; i < activities.size(); ++i) {
      ParseActivityMetadata(v->add_activities(), activities[i]);
    }
  }

  {
    const JsonRef episodes(d["episodes"]);
    for (int i = 0; i < episodes.size(); ++i) {
      ParseEpisodeMetadata(v->add_episodes(), episodes[i]);
    }
  }

  {
    const JsonRef comments(d["comments"]);
    for (int i = 0; i < comments.size(); ++i) {
      ParseCommentMetadata(v->add_comments(), comments[i]);
    }
  }

  return true;
}

ErrorResponse::ErrorId ParseErrorId(const string& s) {
  return FindOrDefault(error_id_map, s, ErrorResponse::UNKNOWN);
}

SystemMessage::Severity ParseSeverity(const string& s) {
  return FindOrDefault(severity_map, s, SystemMessage::UNKNOWN);
}


}  // namespace

bool IsS3RequestTimeout(int status, const Slice& data) {
  return status == 400 &&
      RE2::PartialMatch(data, *kS3RequestTimeoutErrorRE);
}

string EncodeAssetKey(const Slice& url, const Slice& fingerprint) {
  string s = kAssetKeyPrefix;
  url.AppendToString(&s);
  if (!fingerprint.empty()) {
    s += "#";
    fingerprint.AppendToString(&s);
  }
  return s;
}

bool DecodeAssetKey(Slice key, Slice* url, Slice* fingerprint) {
  if (!key.starts_with(kAssetKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kAssetKeyPrefix.size());
  const int pos = key.rfind('#');
  if (pos == key.npos) {
    // No asset-fingerprint, just the asset-url.
    if (url)  {
      *url = key;
    }
  } else {
    if (url) {
      *url = key.substr(0, pos);
    }
    if (fingerprint) {
      *fingerprint = key.substr(pos + 1);
    }
  }
  return true;
}

bool ParseAuthResponse(
    AuthResponse* r, const string& data) {
  typedef AuthResponse T;

  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  MaybeParseResponseHeaders(r, d["headers"]);
  MaybeSet(r, &T::set_user_id, d["user_id"]);
  MaybeSet(r, &T::set_device_id, d["device_id"]);
  MaybeSet(r, &T::set_cookie, d["cookie"]);
  MaybeSet(r, &T::set_token_digits, d["token_digits"]);

  // LOG("parse auth:\n%s\n%s", d.FormatStyled(), *r);
  return true;
}

bool ParseErrorResponse(
    ErrorResponse* r, const string& data) {
  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  typedef ErrorResponse::Error T;
  const JsonRef error = d["error"];
  if (error.empty()) {
    return false;
  }
  MaybeSet(r->mutable_error(), &T::set_method, error["method"]);
  MaybeSet(r->mutable_error(), &T::set_text, error["message"]);
  const JsonRef id = error["id"];
  if (!id.empty()) {
    r->mutable_error()->set_error_id(ParseErrorId(id.string_value()));
  }

  // LOG("parse error:\n%s\n%s", d.FormatStyled(), *r);
  return true;
}

bool ParsePingResponse(
    PingResponse* p, const string& data) {
  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  typedef SystemMessage T;
  const JsonRef msg(d["message"]);
  if (msg.empty()) {
    // Message is optional.
    return true;
  }

  MaybeSet(p->mutable_message(), &T::set_title, msg["title"]);
  MaybeSet(p->mutable_message(), &T::set_body, msg["body"]);
  MaybeSet(p->mutable_message(), &T::set_link, msg["link"]);
  MaybeSet(p->mutable_message(), &T::set_identifier, msg["identifier"]);
  const JsonRef severity = msg["severity"];
  if (!severity.empty()) {
    p->mutable_message()->set_severity(ParseSeverity(severity.string_value()));
  }

  if (!p->message().has_identifier() || !p->message().has_severity() ||
      !p->message().has_title() || p->message().severity() == SystemMessage::UNKNOWN) {
    return false;
  }

  return true;
}

bool ParseUploadContactsResponse(
    UploadContactsResponse* r, const string& data) {
  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  MaybeParseResponseHeaders(r, d["headers"]);

  const JsonRef contact_ids(d["contact_ids"]);
  for (int i = 0; i < contact_ids.size(); i++) {
    r->add_contact_ids(contact_ids[i].string_value());
  }
  return true;
}

bool ParseUploadEpisodeResponse(
    UploadEpisodeResponse* r, const string& data) {
  typedef UploadEpisodeResponse T;

  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  MaybeParseResponseHeaders(r, d["headers"]);

  const JsonRef photos = d["photos"];
  for (int i = 0; i < photos.size(); ++i) {
    ParsePhotoUpdate(r->add_photos(), photos[i]);
  }

  // LOG("parse upload episode:\n%s\n%s", d.FormatStyled(), *r);
  return true;
}

bool ParseQueryContactsResponse(
    QueryContactsResponse* r, ContactSelection* cs,
    int limit, const string& data) {
  typedef QueryContactsResponse T;

  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  MaybeParseResponseHeaders(r, d["headers"]);
  MaybeSet(r, &T::set_last_key, d["last_key"]);

  const JsonRef contacts(d["contacts"]);
  for (int i = 0; i < contacts.size(); ++i) {
    ParseContactMetadata(r->add_contacts(), contacts[i]);
  }

  if (contacts.size() >= limit) {
    cs->set_start_key(r->last_key());
  }

  // LOG("parse query contacts:\n%s\n%s", d.FormatStyled(), *r);
  return true;
}

bool ParseQueryEpisodesResponse(
    QueryEpisodesResponse* r, vector<EpisodeSelection>* v,
    int limit, const string& data) {
  typedef QueryEpisodesResponse T;
  typedef std::unordered_map<
    string, QueryEpisodesResponse::Episode*> EpisodeMap;

  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  EpisodeMap map;

  MaybeParseResponseHeaders(r, d["headers"]);

  const JsonRef episodes(d["episodes"]);
  for (int i = 0; i < episodes.size(); ++i) {
    QueryEpisodesResponse::Episode* e = r->add_episodes();
    ParseQueryEpisodesEpisode(e, episodes[i]);
    map[e->metadata().id().server_id()] = e;
  }

  // Loop over the episode selections and update them to reflect the
  // retrieved data.
  if (v != NULL) {
    for (int i = 0; i < v->size(); ++i) {
      EpisodeSelection* s = &(*v)[i];
      QueryEpisodesResponse::Episode* e = FindOrNull(map, s->episode_id());
      if (!e) {
        // The episode wasn't returned in the response, perhaps because it was
        // deleted or no longer accessible. Validate the entire selection.
        continue;
      }
      if (e->photos_size() >= limit) {
        s->set_get_photos(false);
        s->set_photo_start_key(e->last_key());
      }
    }
  }

  // LOG("parse query episodes:\n%s\n%s", d.FormatStyled(), *r);
  return true;
}

bool ParseQueryFollowedResponse(
    QueryFollowedResponse* r, const string& data) {
  typedef QueryFollowedResponse T;

  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  MaybeParseResponseHeaders(r, d["headers"]);
  MaybeSet(r, &T::set_last_key, d["last_key"]);

  const JsonRef viewpoints(d["viewpoints"]);
  for (int i = 0; i < viewpoints.size(); ++i) {
    ParseViewpointMetadata(r->add_viewpoints(), viewpoints[i]);
  }

  // LOG("parse query followed:\n%s\n%s", d.FormatStyled(), *r);
  return true;
}

bool ParseQueryNotificationsResponse(
    QueryNotificationsResponse* r, NotificationSelection* ns,
    int limit, const string& data) {
  typedef QueryNotificationsResponse T;

  // Get the integer notification id for the first queried key,
  // if one was queried.
  int64_t exp_first_id = 0;
  if (ns->has_last_key() && !ns->last_key().empty()) {
    FromString<int64_t>(ns->last_key(), &exp_first_id);
    exp_first_id += 1;
  }

  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  MaybeParseResponseHeaders(r, d["headers"]);
  MaybeSet(r, &T::set_last_key, d["last_key"]);
  MaybeSet(r, &T::set_retry_after, d["retry_after"]);

  bool nuclear_invalidation = false;
  const JsonRef notifications(d["notifications"]);
  for (int i = 0; i < notifications.size(); ++i) {
    ParseQueryNotificationsNotification(
        r->add_notifications(), notifications[i]);
    if (r->notifications(i).invalidate().all()) {
      nuclear_invalidation = true;
      break;
    } else if (i == 0) {
      // If the query contained a last key, compare the first returned
      // notification id to the expected first id. On a gap, we
      // trigger nuclear invalidation.
      if (exp_first_id != 0 &&
          r->notifications(i).notification_id() != exp_first_id) {
        LOG("notification: notification ids skipped from %d to %d",
            exp_first_id, r->notifications(0).notification_id());
        nuclear_invalidation = true;
        break;
      } else if (r->headers().min_required_version() >
                 AppState::protocol_version()) {
        // Handle the case of a min-required-version too new for client.
        ns->set_max_min_required_version(r->headers().min_required_version());
        ns->set_low_water_notification_id(r->notifications(i).notification_id() - 1);
      }
    }
  }

  // If there was a gap in the notification id sequence or if an "all"
  // invalidation was encountered, we indicate total invalidation by
  // clearing the last_key and setting query_done to false in the
  // notification selection.
  if (nuclear_invalidation) {
    ns->set_last_key("");
    ns->clear_query_done();
  } else {
    // Otherwise, set the last key and mark queries for notifications
    // "done" if the number of queried notifications is less than the limit.
    if (r->has_last_key()) {
      ns->set_last_key(r->last_key());
    }
    ns->set_query_done(r->notifications_size() < limit);
  }

  // LOG("parse query notifications:\n%s\n%s", d.FormatStyled(), *r);
  return true;
}

bool ParseQueryUsersResponse(
    QueryUsersResponse* r, const string& data) {
  typedef QueryUsersResponse T;

  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  MaybeParseResponseHeaders(r, d["headers"]);

  const JsonRef users(d["users"]);
  for (int i = 0; i < users.size(); ++i) {
    const JsonRef& user_dict = users[i];
    QueryUsersResponse::User* user_proto = r->add_user();
    ContactMetadata* contact = user_proto->mutable_contact();
    ParseUserMetadata(contact, user_dict);

    const JsonRef private_dict = user_dict["private"];
    if (!private_dict.empty()) {
      const JsonRef ids = private_dict["user_identities"];
      if (!ids.empty()) {
        for (int j = 0; j < ids.size(); j++) {
          const JsonRef id_dict = ids[j];
          ContactIdentityMetadata* id_proto = contact->add_identities();
          ParseUserIdentityMetadata(id_proto, id_dict);
        }
      }
      const JsonRef subs = private_dict["subscriptions"];
      if (!subs.empty()) {
        for (int j = 0; j < subs.size(); j++) {
          const JsonRef sub_dict = subs[j];
          ServerSubscriptionMetadata* sub_proto = user_proto->add_subscriptions();
          ParseServerSubscriptionMetadata(sub_proto, sub_dict);
        }
      }
      const JsonRef account_settings_dict = private_dict["account_settings"];
      if (!account_settings_dict.empty()) {
        ParseAccountSettingsMetadata(user_proto->mutable_account_settings(), account_settings_dict);
      }
      MaybeSet(user_proto, &QueryUsersResponse::User::set_no_password, private_dict["no_password"]);
    }
  }

  // LOG("parse query users:\n%s\n%s", d.FormatStyled(), *r);
  return true;
}

bool ParseQueryViewpointsResponse(
    QueryViewpointsResponse* r, vector<ViewpointSelection>* v,
    int limit, const string& data) {
  typedef QueryViewpointsResponse T;
  typedef std::unordered_map<
    string, QueryViewpointsResponse::Viewpoint*> ViewpointMap;

  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  ViewpointMap map;

  MaybeParseResponseHeaders(r, d["headers"]);

  const JsonRef viewpoints(d["viewpoints"]);
  for (int i = 0; i < viewpoints.size(); ++i) {
    QueryViewpointsResponse::Viewpoint* p = r->add_viewpoints();
    ParseQueryViewpointsViewpoint(p, viewpoints[i]);
    map[p->metadata().id().server_id()] = p;
  }

  // Loop over the viewpoint selections and update them to reflect the
  // retrieved data.
  if (v != NULL) {
    for (int i = 0; i < v->size(); ++i) {
      ViewpointSelection* s = &(*v)[i];
      QueryViewpointsResponse::Viewpoint* p = FindOrNull(map, s->viewpoint_id());
      if (!p) {
        // The viewpoint wasn't returned in the response, perhaps because it was
        // deleted or no longer accessible. Validate the entire selection.
        continue;
      }
      if (p->followers_size() >= limit) {
        s->set_get_followers(false);
        s->set_follower_start_key(p->follower_last_key());
      }
      if (p->activities_size() >= limit) {
        s->set_get_activities(false);
        s->set_activity_start_key(p->activity_last_key());
      }
      if (p->episodes_size() >= limit) {
        s->set_get_episodes(false);
        s->set_episode_start_key(p->episode_last_key());
      }
      if (p->comments_size() >= limit) {
        s->set_get_comments(false);
        s->set_comment_start_key(p->comment_last_key());
      }
    }
  }

  // LOG("parse query viewpoints:\n%s\n%s", d.FormatStyled(), *r);
  return true;
}

bool ParseResolveContactsResponse(
    ResolveContactsResponse* r, const string& data) {
  JsonValue d;
  if (!d.Parse(data)) {
    return false;
  }

  MaybeParseResponseHeaders(r, d["headers"]);

  const JsonRef contacts(d["contacts"]);
  for (int i = 0; i < contacts.size(); i++) {
    if (!ParseResolvedContactMetadata(r->add_contacts(), contacts[i])) {
      return false;
    }
  }

  return true;
}

bool ParseServerSubscriptionMetadata(ServerSubscriptionMetadata* sub, const JsonRef& d) {
  if (d.empty()) {
    return false;
  }
  MaybeSet(sub, &ServerSubscriptionMetadata::set_transaction_id, d["transaction_id"]);
  MaybeSet(sub, &ServerSubscriptionMetadata::set_subscription_id, d["subscription_id"]);
  MaybeSet(sub, &ServerSubscriptionMetadata::set_timestamp, d["timestamp"]);
  MaybeSet(sub, &ServerSubscriptionMetadata::set_expiration_ts, d["expiration_ts"]);
  MaybeSet(sub, &ServerSubscriptionMetadata::set_product_type, d["product_type"]);
  MaybeSet(sub, &ServerSubscriptionMetadata::set_quantity, d["quantity"]);
  MaybeSet(sub, &ServerSubscriptionMetadata::set_payment_type, d["payment_type"]);
  return true;
}

// local variables:
// mode: c++
// end:
