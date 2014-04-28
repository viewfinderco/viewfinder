// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "ActivityTable.h"
#import "ContactManager.h"
#import "CommentTable.h"
#import "DBFormat.h"
#import "DBMigration.h"
#import "EpisodeMetadata.pb.h"
#import "EpisodeTable.h"
#import "IdentityManager.h"
#import "InvalidateMetadata.pb.h"
#import "PeopleRank.h"
#import "PhotoTable.h"
#import "PlacemarkTable.h"
#import "ServerUtils.h"
#import "Timer.h"
#import "ViewpointTable.h"

namespace {

// DEPRECATED.
// The enum for migration steps and the migration version key are
// deprecated in favor of using separate keys for each step. Separate
// keys allow the migrations to be added in any order and from
// independent development branches without merge issues.
enum MigrationEnum {
  EPISODE_PARENT_CHILD_INDEX = 1,
  INITIALIZE_UPLOAD_EPISODE_BIT,
  MAYBE_UNQUARANTINE_PHOTOS,
};
const string kDBMigrationVersionKey = DBFormat::metadata_key("migration_version");
// End DEPRECATED.

const string kMigrationKeyPrefix = DBFormat::db_migration_key("");
// Ordered by putative migration order, not lexicographically.
const string kUseMigrationKeysKey = DBFormat::db_migration_key("use_migration_keys");
const string kEpisodeParentChildIndexKey = DBFormat::db_migration_key("episode_parent_child_index");
const string kInitializeUploadEpisodeBitKey = DBFormat::db_migration_key("initialize_update_episode_bit");
const string kMaybeUnquarantinePhotosKey = DBFormat::db_migration_key("maybe_unquarantine_photos");
const string kMoveAssetKeysKey = DBFormat::db_migration_key("move_asset_keys");
const string kMultipleEpisodeActivityIndexKey = DBFormat::db_migration_key("multiple_episode_activity_index");
const string kRemoveDaySummaryRowsKey = DBFormat::db_migration_key("remove_day_summary_rows");
const string kRemoveInvalidPlacemarksKey = DBFormat::db_migration_key("remove_invalid_placemarks");
const string kUploadSavePhotosKey = DBFormat::db_migration_key("upload_save_photos");
const string kCommentActivityIndexKey = DBFormat::db_migration_key("comment_activity_index");
// See also kInvalidateContactsKey below.
const string kRequeryContactsKey = DBFormat::db_migration_key("requery_contacts4");
const string kSplitAssetKeysKey = DBFormat::db_migration_key("split_asset_keys");
const string kAssetFingerprintIndexKey = DBFormat::db_migration_key("asset_fingerprint_index");
const string kContactIndexStoreRawKey = DBFormat::db_migration_key("contact_index_store_raw");
const string kContactIdIndexStoreRawKey = DBFormat::db_migration_key("contact_id_index_store_raw");
const string kSetCoverPhotosKey = DBFormat::db_migration_key("set_cover_photos5");
const string kQuarantinedPhotoEpisodeKey = DBFormat::db_migration_key("quarantined_photo_episode");
const string kSaveComingledLibraryKey = DBFormat::db_migration_key("save_comingled_library");
const string kSplitContactsUsersKey = DBFormat::db_migration_key("split_contacts_users");
const string kContactAliasCleanupKey = DBFormat::db_migration_key("contact_alias_cleanup");
const string kDeleteEmptyContactKey = DBFormat::db_migration_key("delete_empty_contact");
const string kIndexServerContactIdKey = DBFormat::db_migration_key("index_server_contact_id");
const string kRequerySelfKey = DBFormat::db_migration_key("requery_self");
const string kResetNeedQueryUsersKey = DBFormat::db_migration_key("reset_need_query_users2");
const string kInvalidateContactsKey = DBFormat::db_migration_key("invalidate_contacts");
const string kCleanupContactIdentitiesKey = DBFormat::db_migration_key("cleanup_contact_identities2");
const string kMoveRemovedPhotosToHiddenKey = DBFormat::db_migration_key("move_removed_photos_to_hidden");
const string kBuildFollowerTablesKey = DBFormat::db_migration_key("build_follower_tables");
const string kCanonicalizeCommentViewpointKey = DBFormat::db_migration_key("canonicalize_comment_viewpoint");
const string kReindexCommentsKey = DBFormat::db_migration_key("reindex_comments3");
const string kBuildFollowerGroupsKey = DBFormat::db_migration_key("build_follower_groups3");
const string kReindexEpisodesKey = DBFormat::db_migration_key("reindex_episodes8");
const string kReindexViewpointsKey = DBFormat::db_migration_key("reindex_viewpoints4");
const string kDeleteIdlessContactsKey = DBFormat::db_migration_key("delete_idless_contacts");
const string kReindexContactsKey = DBFormat::db_migration_key("reindex_contacts5");
const string kReindexUsersKey = DBFormat::db_migration_key("reindex_users2");
const string kRemoveTerminatedFollowersKey = DBFormat::db_migration_key("remove_terminated_followers");
const string kRemoveFeedEventDataKey = DBFormat::db_migration_key("remove_feed_event_data");
const string kRemoveLocalOnlyPhotosKey = DBFormat::db_migration_key("remove_local_only_photos");
const string kConvertAssetFingerprintsKey = DBFormat::db_migration_key("convert_asset_fingerprints");
const string kIndexPhotosKey = DBFormat::db_migration_key("index_photos");
const string kRequeryUsersKey = DBFormat::db_migration_key("requery_users2");
const string kPrepareViewpointGCQueueKey = DBFormat::db_migration_key("prepare_viewpoint_gc_queue");
const string kRemoveAssetDuplicatePhotosKey = DBFormat::db_migration_key("remove_asset_duplicate_photos_key");

const DBRegisterKeyIntrospect kMigrationKeyIntrospect(
    kMigrationKeyPrefix,
    [](Slice key) {
      return key.ToString();
    }, NULL);

void AddUniqueUser(AppState* state,
                   int64_t user_id,
                   std::unordered_set<int64_t>* unique_users,
                   vector<ContactMetadata>* users) {
  if (!user_id || ContainsKey(*unique_users, user_id)) {
    return;
  }
  unique_users->insert(user_id);
  ContactMetadata cm;
  if (!state->contact_manager()->LookupUser(user_id, &cm)) {
    LOG("failed to lookup user %d", user_id);
    return;
  }

  if (cm.label_terminated()) {
    return;
  }
  if (cm.user_id() != user_id) {
    // The user id changed; we must have followed a merged_with link.
    // Put both source and target user ids in the deduping set.
    unique_users->insert(cm.user_id());
  }
  users->push_back(cm);
}

void ListParticipants(AppState* state, const ViewpointHandle& vh,
                      vector<ContactMetadata>* participants,
                      const DBHandle& db) {
  std::unordered_set<int64_t> unique_participants;
  if (!vh->provisional()) {
    // Add viewpoint owner as first participant, but only if this viewpoint is
    // not provisional.
    AddUniqueUser(state, state->user_id(), &unique_participants, participants);
  }

  // Next, add all users who were added during share_new or add_followers activities.
  for (ScopedPtr<ActivityTable::ActivityIterator> iter(
           state->activity_table()->NewViewpointActivityIterator(
               vh->id().local_id(), 0, false, db));
       !iter->done();
       iter->Next()) {
    ActivityHandle ah = iter->GetActivity();

    // merge_accounts activities contain a single user id.
    if (ah->has_merge_accounts()) {
      AddUniqueUser(state, ah->merge_accounts().target_user_id(), &unique_participants, participants);
    }

    // add_followers and share_new activities have a list of users.
    const ::google::protobuf::RepeatedPtrField<ContactMetadata>* contacts = NULL;
    if (ah->has_add_followers()) {
      contacts = &ah->add_followers().contacts();
    } else if (ah->has_share_new()) {
      contacts = &ah->share_new().contacts();
    }
    if (contacts) {
      for (int i = 0; i < contacts->size(); ++i) {
        ContactMetadata cm = contacts->Get(i);
        if (cm.has_user_id()) {
          AddUniqueUser(state, cm.user_id(), &unique_participants, participants);
        } else {
          // It's a local prospective user that hasn't made it to the server, so just use
          // the metadata we have directly.
          participants->push_back(cm);
        }
      }
    }
  }
}

}  // namespace

DBMigration::DBMigration(AppState* state, ProgressUpdateBlock progress_update)
    : state_(state),
      progress_update_(progress_update),
      migrated_(false) {
}

DBMigration::~DBMigration() {
}

bool DBMigration::MaybeMigrate() {
  DBHandle updates = state_->NewDBTransaction();

  RunMigration(kUseMigrationKeysKey,
               &DBMigration::UseMigrationKeys,
               updates);
  RunMigration(kEpisodeParentChildIndexKey,
               &DBMigration::EpisodeParentChildIndex,
               updates);
  RunMigration(kInitializeUploadEpisodeBitKey,
               &DBMigration::InitializeUploadEpisodeBit,
               updates);
  RunMigration(kMaybeUnquarantinePhotosKey,
               &DBMigration::MaybeUnquarantinePhotos,
               updates);
  RunMigration(kMoveAssetKeysKey,
               &DBMigration::MoveAssetKeys,
               updates);
  RunMigration(kMultipleEpisodeActivityIndexKey,
               &DBMigration::MultipleEpisodeActivityIndex,
               updates);
  RunMigration(kRemoveDaySummaryRowsKey,
               &DBMigration::RemoveDaySummaryRows,
               updates);
  RunMigration(kRemoveInvalidPlacemarksKey,
               &DBMigration::RemoveInvalidPlacemarks,
               updates);
  RunMigration(kUploadSavePhotosKey,
               &DBMigration::UploadSavePhotos,
               updates);
  RunMigration(kCommentActivityIndexKey,
               &DBMigration::CommentActivityIndex,
               updates);
  RunMigration(kRequeryContactsKey,
               &DBMigration::RequeryContacts,
               updates);
  RunMigration(kSplitAssetKeysKey,
               &DBMigration::SplitAssetKeys,
               updates);
  RunMigration(kAssetFingerprintIndexKey,
               &DBMigration::AssetFingerprintIndex,
               updates);
  RunMigration(kContactIndexStoreRawKey,
               &DBMigration::ContactIndexStoreRaw,
               updates);
  RunMigration(kContactIdIndexStoreRawKey,
               &DBMigration::ContactIdIndexStoreRaw,
               updates);
  RunMigration(kSetCoverPhotosKey,
               &DBMigration::SetCoverPhotos,
               updates);
  RunMigration(kQuarantinedPhotoEpisodeKey,
               &DBMigration::QuarantinedPhotoEpisode,
               updates);
  RunMigration(kSaveComingledLibraryKey,
               &DBMigration::SaveComingledLibrary,
               updates);
  RunMigration(kSplitContactsUsersKey,
               &DBMigration::SplitContactsUsers,
               updates);
  RunMigration(kContactAliasCleanupKey,
               &DBMigration::ContactAliasCleanup,
               updates);
  RunMigration(kDeleteEmptyContactKey,
               &DBMigration::DeleteEmptyContact,
               updates);
  RunMigration(kIndexServerContactIdKey,
               &DBMigration::IndexServerContactId,
               updates);
  RunMigration(kRequerySelfKey,
               &DBMigration::RequerySelf,
               updates);
  RunMigration(kResetNeedQueryUsersKey,
               &DBMigration::ResetNeedQueryUser,
               updates);
  RunMigration(kInvalidateContactsKey,
               &DBMigration::InvalidateContacts,
               updates);
  RunMigration(kCleanupContactIdentitiesKey,
               &DBMigration::CleanupContactIdentities,
               updates);
  RunMigration(kMoveRemovedPhotosToHiddenKey,
               &DBMigration::MoveRemovedPhotosToHidden,
               updates);
  RunMigration(kBuildFollowerTablesKey,
               &DBMigration::BuildFollowerTables,
               updates);
  RunMigration(kCanonicalizeCommentViewpointKey,
               &DBMigration::CanonicalizeCommentViewpoint,
               updates);
  RunMigration(kReindexCommentsKey,
               &DBMigration::ReindexComments,
               updates);
  RunMigration(kBuildFollowerGroupsKey,
               &DBMigration::BuildFollowerGroups,
               updates);
  RunMigration(kReindexEpisodesKey,
               &DBMigration::ReindexEpisodes,
               updates);
  RunMigration(kReindexViewpointsKey,
               &DBMigration::ReindexViewpoints,
               updates);
  RunMigration(kDeleteIdlessContactsKey,
               &DBMigration::DeleteIdlessContacts,
               updates);
  RunMigration(kReindexContactsKey,
               &DBMigration::ReindexContacts,
               updates);
  RunMigration(kReindexUsersKey,
               &DBMigration::ReindexUsers,
               updates);
  RunMigration(kRemoveTerminatedFollowersKey,
               &DBMigration::RemoveTerminatedFollowers,
               updates);
  RunMigration(kRemoveFeedEventDataKey,
               &DBMigration::RemoveFeedEventData,
               updates);
  RunIOSMigration("7.0", NULL, kRemoveLocalOnlyPhotosKey,
                  &DBMigration::RemoveLocalOnlyPhotos,
                  updates);
  RunIOSMigration(NULL, "7.0", kConvertAssetFingerprintsKey,
                  &DBMigration::ConvertAssetFingerprints,
                  updates);
  RunIOSMigration(NULL, NULL, kIndexPhotosKey,
                  &DBMigration::IndexPhotos,
                  updates);
  RunMigration(kRequeryUsersKey,
               &DBMigration::RequeryUsers,
               updates);
  RunMigration(kPrepareViewpointGCQueueKey,
               &DBMigration::PrepareViewpointGCQueue,
               updates);
  RunIOSMigration(NULL, NULL, kRemoveAssetDuplicatePhotosKey,
                  &DBMigration::RemoveAssetDuplicatePhotos,
                  updates);

  if (updates->tx_count() > 0) {
    migrated_ = true;
  }
  updates->Commit(false);
  return migrated_;
}

void DBMigration::RunMigration(
    const string& migration_key, migration_func migrator,
    const DBHandle& updates) {
  if (!updates->Exists(migration_key)) {
    if (progress_update_) {
      progress_update_("Upgrading Data to Latest Version");
    }
    LOG("migrate: running %s", migration_key);
    (this->*migrator)(updates);
    updates->Put(migration_key, "");
  }
  // Flush the transaction to disk, but do not run commit callbacks until
  // all migrations have finished.  It's definitely safe to flush here
  // between migrations; idempotent migrations may define their own
  // flush points.
  MaybeFlush(updates);
}

void DBMigration::MaybeFlush(const DBHandle& updates) {
  if (updates->tx_count() > 1000) {
    migrated_ = true;
    updates->Flush(false);
  }
}

void DBMigration::UseMigrationKeys(const DBHandle& updates) {
  const int cur_version = updates->Get<int>(kDBMigrationVersionKey, 0);
  if (cur_version > EPISODE_PARENT_CHILD_INDEX) {
    updates->Put(kEpisodeParentChildIndexKey, "");
  }
  if (cur_version > INITIALIZE_UPLOAD_EPISODE_BIT) {
    updates->Put(kInitializeUploadEpisodeBitKey, "");
  }
  if (cur_version > MAYBE_UNQUARANTINE_PHOTOS) {
    updates->Put(kMaybeUnquarantinePhotosKey, "");
  }
}

void DBMigration::EpisodeParentChildIndex(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::episode_key());
       iter.Valid();
       iter.Next()) {
    const int64_t ep_id = state_->episode_table()->DecodeContentKey(iter.key());
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(ep_id, updates);
    if (eh->has_parent_id()) {
      eh->Lock();
      eh->SaveAndUnlock(updates);
    }
  }
}

void DBMigration::InitializeUploadEpisodeBit(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::episode_key());
       iter.Valid();
       iter.Next()) {
    const int64_t ep_id = state_->episode_table()->DecodeContentKey(iter.key());
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(ep_id, updates);
    bool need_upload = true;
    // If shared from another user, obviously must be uploaded.
    if (eh->has_parent_id() && eh->user_id() != state_->user_id()) {
      need_upload = false;
    } else if (eh->has_viewpoint_id()) {
      // If has viewpoint id and is the default viewpoint, must be uploaded.
      ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
          eh->viewpoint_id(), updates);
      if (vh.get() && vh->is_default()) {
        need_upload = false;
      }
    }
    if (need_upload) {
      eh->Lock();
      eh->set_upload_episode(true);
      eh->SaveAndUnlock(updates);
    }
  }
}

void DBMigration::MaybeUnquarantinePhotos(const DBHandle& updates) {
  std::unordered_map<int64_t, PhotoHandle> unquarantined;

  for (DB::PrefixIterator iter(updates, DBFormat::episode_key());
       iter.Valid();
       iter.Next()) {
    const int64_t ep_id = state_->episode_table()->DecodeContentKey(iter.key());
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(ep_id, updates);
    if (eh->id().has_server_id()) {
      bool episode_invalidated = false;
      vector<int64_t> photo_ids;
      eh->ListAllPhotos(&photo_ids);
      for (int i = 0; i < photo_ids.size(); ++i) {
        // Skip removed && hidden photos.
        if (eh->IsHidden(photo_ids[i]) || eh->IsRemoved(photo_ids[i])) {
          continue;
        }

        PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_ids[i], updates);
        if (ph->label_error() &&
            (ph->error_download_full() || ph->error_download_thumbnail())) {
          // Add photo to the unquarantined map. We add the photo
          // to a map for later processing as there may be more
          // episodes which referenced the same photo before it
          // was quarantined.
          unquarantined[photo_ids[i]] = ph;

          // Re-post photo to episode so it can be queried. If the photo was
          // actually removed before being quarantined, it will have the
          // REMOVED label and will be re-removed when the episode is queried.
          eh->Lock();
          eh->AddPhoto(photo_ids[i]);
          eh->SaveAndUnlock(updates);

          // Set episode invalidation so we re-query photos, and where not
          // manually removed (no REMOVED label will arrive with photo),
          // will re-post the photo to the episode in question. Assuming the
          // download of missing image assets is successful, the photo will
          // be correctly restored.
          if (!episode_invalidated && !eh->upload_episode()) {
            LOG("db migration: invalidating episode %s", eh->id());
            EpisodeSelection s;
            s.set_episode_id(eh->id().server_id());
            s.set_get_photos(true);
            state_->episode_table()->Invalidate(s, updates);
            episode_invalidated = true;
          }
        }
      }
    }
  }

  // Clear error label on all unquarantined photos so we proceed with
  // another download attempt.
  for (std::unordered_map<int64_t, PhotoHandle>::iterator iter =
           unquarantined.begin();
       iter != unquarantined.end();
       ++iter) {
    PhotoHandle ph = iter->second;
    LOG("db migration: resetting error bit on photo %s", *ph);
    ph->Lock();
    ph->clear_label_error();
    if (ph->error_download_thumbnail()) {
      ph->set_download_thumbnail(true);
    }
    if (ph->error_download_full()) {
      ph->set_download_full(true);
    }
    ph->SaveAndUnlock(updates);
  }
}

void DBMigration::MoveAssetKeys(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::photo_key());
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    PhotoMetadata photo;
    if (!photo.ParseFromString(ToString(value))) {
      continue;
    }

    if (photo.id().has_deprecated_asset_key()) {
      const string& asset_key = photo.id().deprecated_asset_key();
      bool found = false;
      for (int i = 0; i < photo.asset_keys_size(); i++) {
        if (photo.asset_keys(i) == asset_key) {
          found = true;
          break;
        }
      }
      if (!found) {
        photo.add_asset_keys(asset_key);
      }
      photo.mutable_id()->clear_deprecated_asset_key();
      CHECK(updates->PutProto(key, photo));
    }
  }
}

void DBMigration::MultipleEpisodeActivityIndex(const DBHandle& updates) {
  // Delete existing episode-activity index.
  for (DB::PrefixIterator iter(updates, DBFormat::episode_activity_key(""));
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  // Recreate by re-saving every share activity.
  for (DB::PrefixIterator iter(updates, DBFormat::activity_key());
       iter.Valid();
       iter.Next()) {
    const int64_t activity_id = state_->activity_table()->DecodeContentKey(iter.key());
    ActivityHandle ah = state_->activity_table()->LoadActivity(activity_id, updates);
    if (ah->has_share_new() || ah->has_share_existing()) {
      ah->Lock();
      ah->SaveAndUnlock(updates);
    }
  }
}

void DBMigration::RemoveDaySummaryRows(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::day_summary_row_key(""));
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
}

void DBMigration::RemoveInvalidPlacemarks(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::placemark_key(""));
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    Location l;
    bool should_delete =
        (!DecodePlacemarkKey(key, &l) || !PlacemarkTable::IsLocationValid(l));
    if (!should_delete) {
      // Check the stored placemark.
      Placemark pm;
      should_delete =
          (!updates->GetProto(key, &pm) || !PlacemarkTable::IsPlacemarkValid(pm));
    }
    if (should_delete) {
      updates->Delete(key);
    }
  }
}

void DBMigration::UploadSavePhotos(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::activity_key());
       iter.Valid();
       iter.Next()) {
    const int64_t activity_id = state_->activity_table()->DecodeContentKey(iter.key());
    ActivityHandle ah = state_->activity_table()->LoadActivity(activity_id, updates);
    if (ah->has_save_photos()) {
      ah->Lock();
      ah->set_upload_activity(true);
      ah->SaveAndUnlock(updates);
    }
  }
}

void DBMigration::CommentActivityIndex(const DBHandle& updates) {
  // Recreate by re-saving every share activity.
  for (DB::PrefixIterator iter(updates, DBFormat::activity_key());
       iter.Valid();
       iter.Next()) {
    const int64_t activity_id = state_->activity_table()->DecodeContentKey(iter.key());
    ActivityHandle ah = state_->activity_table()->LoadActivity(activity_id, updates);
    if (ah->has_post_comment()) {
      ah->Lock();
      ah->SaveAndUnlock(updates);
    }
  }
}

void DBMigration::RequeryUsers(const DBHandle& updates) {
  // Requery all user metadata.
  for (DB::PrefixIterator iter(updates, DBFormat::user_id_key());
       iter.Valid();
       iter.Next()) {
    int64_t user_id = 0;
    if (DecodeUserIdKey(iter.key(), &user_id)) {
      state_->contact_manager()->MaybeQueueUser(user_id, updates);
    }
  }
}

void DBMigration::RequeryContacts(const DBHandle& updates) {
  if (state_->contact_manager()->count() > 0) {
    // Only requery contacts if we have contacts.
    state_->contact_manager()->InvalidateAll(updates);

    // Clear out the existing contact data. We're going to query all of the
    // contacts and users again and want to start from scratch.
    for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
         iter.Valid();
         iter.Next()) {
      updates->Delete(iter.key());
    }
    for (DB::PrefixIterator iter(updates, DBFormat::deprecated_contact_id_key());
         iter.Valid();
         iter.Next()) {
      updates->Delete(iter.key());
    }
    for (DB::PrefixIterator iter(updates, DBFormat::deprecated_contact_name_key());
         iter.Valid();
         iter.Next()) {
      updates->Delete(iter.key());
    }
    for (DB::PrefixIterator iter(updates, DBFormat::full_text_index_key(ContactManager::kContactIndexName));
         iter.Valid();
         iter.Next()) {
      updates->Delete(iter.key());
    }
    // Re-query every user-id referenced in any activity.
    for (DB::PrefixIterator iter(updates, DBFormat::activity_key());
         iter.Valid();
         iter.Next()) {
      ActivityMetadata m;
      if (!m.ParseFromString(ToString(iter.value()))) {
        continue;
      }
      state_->contact_manager()->MaybeQueueUser(m.user_id(), updates);

      typedef ::google::protobuf::RepeatedPtrField<ContactMetadata> ContactArray;
      const ContactArray* contacts = ActivityTable::GetActivityContacts(m);
      if (contacts) {
        for (int i = 0; i < contacts->size(); ++i) {
          state_->contact_manager()->MaybeQueueUser(
              contacts->Get(i).user_id(), updates);
        }
      }
    }
  }
}

void DBMigration::SplitAssetKeys(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::photo_key());
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    PhotoMetadata photo;
    if (!photo.ParseFromArray(value.data(), value.size())) {
      continue;
    }

    bool changed = false;
    StringSet fingerprints;
    // Should initially be empty, but check anyway to be idempotent.
    for (int i = 0; i < photo.asset_fingerprints_size(); i++) {
      fingerprints.insert(photo.asset_fingerprints(i));
    }

    StringSet keys;
    for (int i = 0; i < photo.asset_keys_size(); i++) {
      Slice url, fingerprint;
      if (!DecodeAssetKey(photo.asset_keys(i), &url, &fingerprint)) {
        continue;
      }
      if (url.empty()) {
        changed = true;
      } else {
        keys.insert(photo.asset_keys(i));
      }
      if (!fingerprint.empty()) {
        bool inserted = fingerprints.insert(ToString(fingerprint)).second;
        changed = changed || inserted;
      }
    }

    if (changed) {
      photo.clear_asset_keys();
      for (StringSet::iterator it = keys.begin(); it != keys.end(); ++it) {
        photo.add_asset_keys(*it);
      }

      photo.clear_asset_fingerprints();
      for (StringSet::iterator it = fingerprints.begin(); it != fingerprints.end(); ++it) {
        photo.add_asset_fingerprints(*it);
      }

      CHECK(updates->PutProto(key, photo));
    }
  }
}

void DBMigration::AssetFingerprintIndex(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::deprecated_asset_reverse_key(""));
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    Slice fingerprint;
    if (!DecodeDeprecatedAssetReverseKey(key, &fingerprint, NULL)) {
      continue;
    }

    updates->Put(EncodeAssetFingerprintKey(fingerprint), value);
    updates->Delete(key);
  }
}

static void RewriteContactIndexedNames(const Slice& key, const Slice& value, const DBHandle& updates) {
  ContactMetadata m;
  if (!m.ParseFromArray(value.data(), value.size())) {
    return;
  }
  if (m.indexed_names_size() > 0) {
    for (int i = 0; i < m.indexed_names_size(); i++) {
      m.set_indexed_names(i, DBFormat::deprecated_contact_name_key() +
                          (string)Format("%s %s", m.indexed_names(i), m.primary_identity()));
    }
    CHECK(updates->PutProto(key, m));
  }
}

void DBMigration::ContactIndexStoreRaw(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
       iter.Valid();
       iter.Next()) {
    RewriteContactIndexedNames(iter.key(), iter.value(), updates);
  }
}

void DBMigration::ContactIdIndexStoreRaw(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::deprecated_contact_id_key());
       iter.Valid();
       iter.Next()) {
    RewriteContactIndexedNames(iter.key(), iter.value(), updates);
  }
}

void DBMigration::SetCoverPhotos(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const int64_t vp_id = state_->viewpoint_table()->DecodeContentKey(iter.key());
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(vp_id, updates);
    if (!vh.get()) {
      continue;
    }

    PhotoHandle ph;
    EpisodeHandle eh = vh->GetAnchorEpisode(&ph);
    if (ph.get()) {
      DCHECK(eh.get());
      if (!eh.get()) {
        continue;
      }
      vh->Lock();
      vh->mutable_cover_photo()->mutable_photo_id()->CopyFrom(ph->id());
      vh->mutable_cover_photo()->mutable_episode_id()->CopyFrom(eh->id());
      vh->SaveAndUnlock(updates);
    }
  }
}

void DBMigration::QuarantinedPhotoEpisode(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::episode_photo_key(""));
       iter.Valid();
       iter.Next()) {
    if (iter.value() != EpisodeTable::kQuarantinedValue) {
      continue;
    }

    int64_t photo_id;
    int64_t episode_id;
    if (DecodeEpisodePhotoKey(iter.key(), &episode_id, &photo_id)) {
      const string pe_key = EncodePhotoEpisodeKey(photo_id, episode_id);
      if (!updates->Exists(pe_key)) {
        LOG("restoring photo episode key for %d => %d", photo_id, episode_id);
        updates->Put(pe_key, string());
      }
    }
  }
}

void DBMigration::SaveComingledLibrary(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const int64_t vp_id = state_->viewpoint_table()->DecodeContentKey(iter.key());
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(vp_id, updates);
    if (!vh.get() || vh->is_default()) {
      continue;
    }
    // Super-special case for Spencer, Brett, Andy & Mike to avoid comingling.
    if (state_->user_id() == 1 ||
        state_->user_id() == 6 ||
        state_->user_id() == 11 ||
        state_->user_id() == 89) {
      if (!vh->deprecated_label_personal()) {
        continue;
      }
    }

    // Get list of episodes in the viewpoint.
    vector<EpisodeHandle> episodes;
    vh->ListEpisodes(&episodes);

    // Compile the vec of photo_id/episode_id pairs for saving.
    std::unordered_set<int64_t> unique_photo_ids;
    PhotoSelectionVec photo_ids;
    for (int i = 0; i < episodes.size(); ++i) {
      // Don't save from episodes which were shared by this user.
      if (episodes[i]->user_id() == state_->user_id()) {
        continue;
      }
      vector<int64_t> ep_photo_ids;
      episodes[i]->ListPhotos(&ep_photo_ids);
      for (int j = 0; j < ep_photo_ids.size(); ++j) {
        const int64_t photo_id = ep_photo_ids[j];
        if (!ContainsKey(unique_photo_ids, photo_id) &&
            !state_->photo_table()->PhotoInLibrary(photo_id, updates)) {
          photo_ids.push_back(PhotoSelection(photo_id, episodes[i]->id().local_id()));
        }
        unique_photo_ids.insert(photo_id);
      }
    }

    // Save photos to library.
    if (!photo_ids.empty()) {
      state_->viewpoint_table()->SavePhotos(photo_ids, 0 /* autosave_viewpoint_id */, updates);
    }

    if (vh->deprecated_label_personal()) {
      // Unset personal label on conversation.
      vh->Lock();
      vh->clear_deprecated_label_personal();
      vh->set_update_follower_metadata(true);
      vh->SaveAndUnlock(updates);
    }
  }
}

void DBMigration::SplitContactsUsers(const DBHandle& updates) {
  const WallTime now = WallTime_Now();
  // First, delete the old indexes.
  for (DB::PrefixIterator iter(updates, DBFormat::deprecated_contact_id_key());
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, DBFormat::deprecated_contact_name_key());
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }

  // Next, read all the contacts into memory.
  vector<ContactMetadata> contacts;
  for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
       iter.Valid();
       iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      continue;
    }
    // The old schema denormalized contacts, so discard any redundant copies.
    if (iter.key() != DBFormat::contact_key(m.primary_identity())) {
      continue;
    }
    contacts.push_back(m);
  }

  // Finally, reconstruct the database.
  for (int i = 0; i < contacts.size(); i++) {
    const ContactMetadata& m = contacts[i];
    if (m.user_id()) {
      // Transfer the appropriate fields to a new user object
      ContactMetadata user;
      // Strip out "viewfinder" identities (which are just user ids)
      if (!m.primary_identity().empty() && !IdentityManager::IsViewfinderIdentity(m.primary_identity())) {
        user.set_primary_identity(m.primary_identity());
      }
      for (int j = 0; j < m.deprecated_identities_size(); j++) {
        if (!IdentityManager::IsViewfinderIdentity(m.deprecated_identities(j)) &&
            !m.deprecated_identities(j).empty()) {
          user.add_identities()->set_identity(m.deprecated_identities(j));
        }
      }
      if (!m.name().empty()) {
        user.set_name(m.name());
      }
      if (!m.first_name().empty()) {
        user.set_first_name(m.first_name());
      }
      if (!m.last_name().empty()) {
        user.set_last_name(m.last_name());
      }
      if (!m.nickname().empty()) {
        user.set_nickname(m.nickname());
      }
      user.set_user_id(m.user_id());
      if (m.has_merged_with()) {
        user.set_merged_with(m.merged_with());
      }
      if (!m.email().empty()) {
        user.set_email(m.email());
      }
      if (m.has_label_registered()) {
        user.set_label_registered(m.label_registered());
      }
      if (m.has_label_terminated()) {
        user.set_label_terminated(m.label_terminated());
      }
      state_->contact_manager()->SaveUser(user, now, updates);
    } else {
      // No user id, so it's just a contact.
      // Contacts don't have VF: identities or rules about user_*name, so we can almost use the old proto directly
      // (but it does need to be mutable);
      ContactMetadata copy(m);
      for (int j = 0; j < m.deprecated_identities_size(); j++) {
        if (!IdentityManager::IsViewfinderIdentity(m.deprecated_identities(j)) &&
            !m.deprecated_identities(j).empty()) {
          copy.add_identities()->set_identity(m.deprecated_identities(j));
        }
      }
      if (copy.identities_size() == 0) {
        continue;
      }
      copy.clear_deprecated_identities();
      if (!copy.has_contact_source()) {
        copy.set_contact_source(ContactManager::GetContactSourceForIdentity(copy.primary_identity()));
      }
      state_->contact_manager()->SaveContact(copy, false, now, updates);
    }
  }
}

void DBMigration::ContactAliasCleanup(const DBHandle& updates) {
  // Delete the records that should have been deleted by the previous migration.
  for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
       iter.Valid();
       iter.Next()) {
    if (iter.key().starts_with("c/Email:") ||
        iter.key().starts_with("c/FacebookGraph:") ||
        iter.key().starts_with("c/Phone:") ||
        iter.key().starts_with("c/VF:")) {
      updates->Delete(iter.key());
    }
  }
}

void DBMigration::DeleteEmptyContact(const DBHandle& updates) {
  const string key("c/");
  if (updates->Exists(key)) {
    updates->Delete(key);
  }
}

void DBMigration::RequerySelf(const DBHandle& updates) {
  if (state_->user_id()) {
    state_->contact_manager()->QueueUser(state_->user_id(), updates);
  }
}

void DBMigration::IndexServerContactId(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
       iter.Valid();
       iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      continue;
    }
    if (m.has_server_contact_id()) {
      CHECK(m.has_contact_id());
      updates->Put(DBFormat::server_contact_id_key(m.server_contact_id()), m.contact_id());
    }
  }
}

void DBMigration::ResetNeedQueryUser(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::user_id_key());
       iter.Valid();
       iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      continue;
    }
    // If the record doesn't look complete, queue it up to re-query.
    // In particular, resolve_contacts could give us 'name' with no first/last name,
    // and the 'registered' label used to be missing from contacts that are not friends.
    if (m.name().empty() ||
        m.first_name().empty() ||
        m.last_name().empty() ||
        !m.label_registered() ||
        !m.label_friend()) {
      m.set_need_query_user(true);
      updates->PutProto(iter.key(), m);
      state_->contact_manager()->QueueUser(m.user_id(), updates);
    }
  }
}

void DBMigration::InvalidateContacts(const DBHandle& updates) {
  if (state_->contact_manager()->count() > 0) {
    // Only requery contacts if we have contacts.
    state_->contact_manager()->InvalidateAll(updates);
  }
}

void DBMigration::CleanupContactIdentities(const DBHandle& updates) {
  const WallTime now = WallTime_Now();
  for (DB::PrefixIterator iter(updates, DBFormat::contact_key("")); iter.Valid(); iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      continue;
    }

    // If any identities are the empty string, clear them.
    if (m.has_primary_identity() && m.primary_identity().empty()) {
      m.clear_primary_identity();
    }
    for (int i = m.identities_size() - 1; i >= 0; i--) {
      if (m.identities(i).identity().empty()) {
        m.mutable_identities()->SwapElements(i, m.identities_size() - 1);
        m.mutable_identities()->RemoveLast();
      }
    }

    // If there are no identities, delete it (identity-less contacts have only been created by bugs).
    if (m.primary_identity().empty() &&
        m.identities_size() == 0) {
      if (m.contact_id().empty()) {
        DCHECK(false) << "empty contact id in contact: " << m;
        continue;
      }
      state_->contact_manager()->RemoveContact(m.contact_id(), true, updates);
      continue;
    }

    bool changed = false;
    if (m.primary_identity().empty()) {
      // If there is no primary identity, set it.
      ContactManager::ChoosePrimaryIdentity(&m);
      changed = true;
    } else {
      // Ensure the primary identity exists in the identities list.
      StringSet identities;
      for (int i = 0; i < m.identities_size(); i++) {
        identities.insert(m.identities(i).identity());
      }
      if (!ContainsKey(identities, m.primary_identity())) {
        m.add_identities()->set_identity(m.primary_identity());
        changed = true;
        if (m.identities_size() > 1) {
          // Put the newly-added identity first in the list.
          m.mutable_identities()->SwapElements(0, m.identities_size() - 1);
        }
      }
    }

    if (changed) {
      // If any changes were made, delete the old contact and re-save.
      if (!m.contact_id().empty()) {
        state_->contact_manager()->RemoveContact(m.contact_id(), true, updates);
        m.clear_contact_id();
      }
      state_->contact_manager()->SaveContact(m, true, now, updates);
    }
  }
}

void DBMigration::MoveRemovedPhotosToHidden(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::episode_key());
       iter.Valid();
       iter.Next()) {
    const int64_t ep_id = state_->episode_table()->DecodeContentKey(iter.key());
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(ep_id, updates);
    if (eh->id().has_server_id() && !eh->InLibrary()) {
      vector<int64_t> photo_ids;
      vector<int64_t> hide_ids;
      eh->ListAllPhotos(&photo_ids);
      for (int i = 0; i < photo_ids.size(); ++i) {
        // Consider only removed photos.
        if (!eh->IsRemoved(photo_ids[i])) {
          continue;
        }
        hide_ids.push_back(photo_ids[i]);
      }

      // Hide photos in episode.
      if (!hide_ids.empty()) {
        eh->Lock();
        for (int i = 0; i < hide_ids.size(); ++i) {
          eh->HidePhoto(hide_ids[i]);
        }
        eh->SaveAndUnlock(updates);
      }
    }
  }
}

void DBMigration::BuildFollowerTables(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const int64_t vp_id = state_->viewpoint_table()->DecodeContentKey(iter.key());
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(vp_id, updates);
    if (!vh.get()) {
      continue;
    }
    vh->Lock();

    vector<int64_t> follower_ids;
    vh->ListFollowers(&follower_ids);
    std::unordered_set<int64_t> follower_set(follower_ids.begin(), follower_ids.end());

    vector<ContactMetadata> participants;
    ListParticipants(state_, vh, &participants, updates);
    for (int i = 0; i < participants.size(); ++i) {
      if (participants[i].has_user_id()) {
        const int64_t user_id = participants[i].user_id();
        vh->AddFollower(user_id);
        follower_set.erase(user_id);
      }
    }
    if (!follower_set.empty()) {
      for (std::unordered_set<int64_t>::iterator iter = follower_set.begin();
           iter != follower_set.end();
           ++iter) {
        vh->RemoveFollower(*iter);
      }
    }

    vh->SaveAndUnlock(updates);
  }
}

void DBMigration::CanonicalizeCommentViewpoint(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::comment_key());
       iter.Valid();
       iter.Next()) {
    const int64_t c_id = state_->comment_table()->DecodeContentKey(iter.key());
    CommentHandle ch = state_->comment_table()->LoadComment(c_id, updates);
    if (!ch.get()) {
      continue;
    }
    ch->Lock();
    state_->viewpoint_table()->CanonicalizeViewpointId(ch->mutable_viewpoint_id(), updates);
    ch->SaveAndUnlock(updates);
  }
}

void DBMigration::ReindexComments(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::comment_key());
       iter.Valid();
       iter.Next()) {
    const int64_t c_id = state_->comment_table()->DecodeContentKey(iter.key());
    CommentHandle ch = state_->comment_table()->LoadComment(c_id, updates);
    if (!ch.get()) {
      continue;
    }
    ch->Lock();
    ch->SaveAndUnlock(updates);

    MaybeFlush(updates);
  }
}

void DBMigration::BuildFollowerGroups(const DBHandle& updates) {
  state_->people_rank()->Reset();
  for (DB::PrefixIterator iter(updates, DBFormat::follower_group_key_deprecated(""));
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, DBFormat::follower_group_key(""));
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const int64_t vp_id = state_->viewpoint_table()->DecodeContentKey(iter.key());
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(vp_id, updates);
    if (!vh.get()) {
      continue;
    }

    vector<int64_t> follower_ids;
    vh->ListFollowers(&follower_ids);
    if (!vh->label_removed()) {
      state_->people_rank()->AddViewpoint(vh->id().local_id(), follower_ids, updates);
    }
  }
}

void DBMigration::ReindexEpisodes(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::episode_key());
       iter.Valid();
       iter.Next()) {
    const int64_t e_id = state_->episode_table()->DecodeContentKey(iter.key());
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(e_id, updates);
    if (!eh.get()) {
      continue;
    }
    eh->Lock();
    eh->SaveAndUnlock(updates);

    MaybeFlush(updates);
  }
}

void DBMigration::ReindexViewpoints(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const int64_t vp_id = state_->viewpoint_table()->DecodeContentKey(iter.key());
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(vp_id, updates);
    if (!vh.get()) {
      continue;
    }
    vh->Lock();
    vh->SaveAndUnlock(updates);

    MaybeFlush(updates);
  }
}

void DBMigration::DeleteIdlessContacts(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
       iter.Valid();
       iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      continue;
    }

    if (m.contact_id().empty()) {
      // All contacts without ids should have been deleted by the combination of SplitContactsUsers,
      // ContactAliasCleanup, and DeleteEmptyContact.  However, we have seen these contacts on several
      // beta users' devices, and they cause a crash in ReindexContacts.
      LOG("deleting idless contact: %s", m);
      updates->Delete(iter.key());
    }
  }
}

void DBMigration::ReindexContacts(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
       iter.Valid();
       iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      continue;
    }

    state_->contact_manager()->ReindexContact(&m, updates);

    MaybeFlush(updates);
  }
}

void DBMigration::ReindexUsers(const DBHandle& updates) {
  const WallTime now = WallTime_Now();
  for (DB::PrefixIterator iter(updates, DBFormat::user_id_key());
       iter.Valid();
       iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      continue;
    }

    state_->contact_manager()->SaveUser(m, now, updates);

    MaybeFlush(updates);
  }
}

// Remove terminated users as followers from their viewpoints.
void DBMigration::RemoveTerminatedFollowers(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
       iter.Valid();
       iter.Next()) {
    ContactMetadata m;
    // Skip if we can't decode or (more likely) if the user isn't terminated.
    if (!m.ParseFromArray(iter.value().data(), iter.value().size()) ||
        !m.has_user_id() || !m.label_terminated()) {
      continue;
    }

    vector<int64_t> viewpoint_ids;
    state_->viewpoint_table()->ListViewpointsForUserId(
        m.user_id(), &viewpoint_ids, updates);

    for (int i = 0; i < viewpoint_ids.size(); ++i) {
      ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
          viewpoint_ids[i], updates);
      if (!vh.get()) {
        continue;
      }
      vh->Lock();
      vh->RemoveFollower(m.user_id());
      vh->SaveAndUnlock(updates);
    }

    MaybeFlush(updates);
  }
}

// Remove all feed-event-related data from DB.
void DBMigration::RemoveFeedEventData(const DBHandle& updates) {
  const string kFeedDayKeyPrefix = "fday/";
  const DBRegisterKeyIntrospect kFeedDayKeyIntrospect(
      kFeedDayKeyPrefix,
      [](Slice key) { return string(); },
      [](Slice value) { return string(); });
  for (DB::PrefixIterator iter(updates, kFeedDayKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  const string kDayFeedEventKeyPrefix = "dfev/";
  const DBRegisterKeyIntrospect kDayFeedEventKeyIntrospect(
      kDayFeedEventKeyPrefix,
      [](Slice key) { return string(); },
      [](Slice value) { return string(); });
  for (DB::PrefixIterator iter(updates, kDayFeedEventKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  const string kDayActivityInvalidationKeyPrefix = "dais/";
  const DBRegisterKeyIntrospect kDayActivityInvalidationKeyIntrospect(
      kDayActivityInvalidationKeyPrefix,
      [](Slice key) { return string(); },
      [](Slice value) { return string(); });
  for (DB::PrefixIterator iter(updates, kDayActivityInvalidationKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  const string kTrapdoorFeedEventKeyPrefix = "tfe/";
  const DBRegisterKeyIntrospect kTrapdoorFeedEventKeyIntrospect(
      kTrapdoorFeedEventKeyPrefix,
      [](Slice key) { return string(); },
      [](Slice value) { return string(); });
  for (DB::PrefixIterator iter(updates, kTrapdoorFeedEventKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  const string kEpisodeFeedEventKeyPrefix = "efes/";
  const DBRegisterKeyIntrospect kEpisodeFeedEventKeyIntrospect(
      kEpisodeFeedEventKeyPrefix,
      [](Slice key) { return string(); },
      [](Slice value) { return string(); });
  for (DB::PrefixIterator iter(updates, kEpisodeFeedEventKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  const string kFullFeedEventSummaryKey = DBFormat::metadata_key("full_feed_event_summary");
  updates->Delete(kFullFeedEventSummaryKey);

  // Flush to ensure that all deletes go through using the
  // still-registered introspection methods.
  updates->Flush(false);
}

void DBMigration::PrepareViewpointGCQueue(const DBHandle& updates) {
  // First, delete any existing, spurious viewpoints queued for GC.
  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_gc_key(""));
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }

  // Create a GC key for every removed viewpoint. If viewpoint is
  // unrevivable (e.g. user removed themselves), schedule for immediate
  // GC; otherwise, schedule with standard expiration.
  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const int64_t vp_id = state_->viewpoint_table()->DecodeContentKey(iter.key());
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(vp_id, updates);
    if (!vh.get() || !vh->label_removed()) {
      continue;
    }
    const WallTime expiration = vh->GetGCExpiration();
    updates->Put(EncodeViewpointGCKey(vp_id, expiration), string());
  }
}

// local variables:
// mode: c++
// end:
