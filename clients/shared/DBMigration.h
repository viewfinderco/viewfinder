// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_DB_MIGRATION_H
#define VIEWFINDER_DB_MIGRATION_H

#import "AppState.h"
#import "DB.h"

class DBMigration {
 public:
  DBMigration(AppState* state, ProgressUpdateBlock progress_update);
  virtual ~DBMigration();

  // Runs all migrations for the client which haven't yet been run.
  // Returns true if any migration was performed.
  bool MaybeMigrate();

  // Switch from using a single migration version enum to keeping a
  // row per migration step. This migration preserves accounting for
  // migration steps up to and including MAYBE_UNQUARANTINE_PHOTOS.
  void UseMigrationKeys(const DBHandle& updates);

  // Re-save every episode to generate the parent-child index.
  void EpisodeParentChildIndex(const DBHandle& updates);

  // Set the "upload_metadata" bit for each episode if applicable.
  void InitializeUploadEpisodeBit(const DBHandle& updates);

  // Check if photo has label_error() and either error_download_full
  // or error_download_thumbnail, clear label_error() and requery the
  // episode.
  void MaybeUnquarantinePhotos(const DBHandle& updates);

  // Move the PhotoId.asset_key field to PhotoMetadata.asset_keys.
  void MoveAssetKeys(const DBHandle& updates);

  // Rebuilds episode activity index to handle multiple activities
  // sharing photos from within same episode.
  void MultipleEpisodeActivityIndex(const DBHandle& updates);

  // Removes obsolete day summary row metadata.
  void RemoveDaySummaryRows(const DBHandle& updates);

  // Removes placemarks with bad locations or invalid placemark data.
  void RemoveInvalidPlacemarks(const DBHandle& updates);

  // Resets all pending save_photos activities to upload to the server.
  void UploadSavePhotos(const DBHandle& updates);

  // Introduce secondary index mapping from comment server id to activity.
  void CommentActivityIndex(const DBHandle& updates);

  // Requery all user metadata so that we can properly overlay user
  // metadata on top of contact metadata.
  void RequeryUsers(const DBHandle& updates);

  // Erase all contacts and requery.  (see also InvalidateContacts below to
  // requery without wiping the current state)
  void RequeryContacts(const DBHandle& updates);

  // Splits asset_keys and asset_fingerprints fields; creates asset
  // fingerprint reverse index and removes asset key reverse index.
  void SplitAssetKeys(const DBHandle& updates);

  // Removes the reverse_asset_key index ("/ar/url#fingerprint") and
  // creates the asset fingerprint index ("af/fingerprint").
  void AssetFingerprintIndex(const DBHandle& updates);

  // Rewrites the ContactMetadata::indexed_names field to include the
  // exact data that was indexed.
  void ContactIndexStoreRaw(const DBHandle& updates);

  // Same as ContactIndexStoreRaw, for contact_id_key instead of
  // contact_key.
  void ContactIdIndexStoreRaw(const DBHandle& updates);

  // Set cover photos for all viewpoints.
  void SetCoverPhotos(const DBHandle& updates);

  // Restore photo=>episode link for instances where
  // immediately-quarantined photos were skipped.
  void QuarantinedPhotoEpisode(const DBHandle& updates);

  // Invoke "save_photos" api call on all episodes shared to
  // conversations and include all photos which are not removed,
  // unshared, or already present in the library. Unset the
  // "personal" label if set on the conversation.
  void SaveComingledLibrary(const DBHandle& updates);

  // Converts the contacts table to the new schema with contacts
  // and users stored sepparately.
  void SplitContactsUsers(const DBHandle& updates);

  // Deletes stale records left by a bug in SplitContactsUsers.
  void ContactAliasCleanup(const DBHandle& updates);

  // Delete the erroneous empty contact record "c/" if it exists.
  void DeleteEmptyContact(const DBHandle& updates);

  // Adds an index on the ContactMetadata::server_contact_id field.
  void IndexServerContactId(const DBHandle& updates);

  // Requery the "self" user record in order to retrieve the user's identities
  // and "no_password" setting.
  void RequerySelf(const DBHandle& updates);

  // Sets the "need_query_user" flag on incomplete user records and queues them for querying.
  void ResetNeedQueryUser(const DBHandle& updates);

  // Requeries all contacts and merges with the local state.
  void InvalidateContacts(const DBHandle& updates);

  // Ensures that all contacts have an identity, the primary identity
  // is also present in the identities array, and that the primary
  // identity is set for all contacts
  void CleanupContactIdentities(const DBHandle& updates);

  // Change the state of any "removed" photo to "hidden" if the
  // episode is shared (e.g. not part of the default viewpoint).
  void MoveRemovedPhotosToHidden(const DBHandle& updates);

  // Repair and verify the follower table as well as create the reverse
  // follower table which looks up viewpoint ids by follower ids.
  void BuildFollowerTables(const DBHandle& updates);

  // Add a local id to all comments' viewpoint_id field.
  void CanonicalizeCommentViewpoint(const DBHandle& updates);

  // Re-saves all comments to update the full-text index.
  void ReindexComments(const DBHandle& updates);

  // Build follower groups by iterating over all viewpoints and adding
  // each to the follower group defined by the sorted array of
  // follower ids.
  void BuildFollowerGroups(const DBHandle& updates);

  // Re-saves all episodes to update the full-text index.
  void ReindexEpisodes(const DBHandle& updates);

  // Re-saves all viewpoints to update the full-text index.
  void ReindexViewpoints(const DBHandle& updates);

  // Deletes any contact records without a contact_id set.
  void DeleteIdlessContacts(const DBHandle& updates);

  // Re-saves all contacts to update the full-text index.
  void ReindexContacts(const DBHandle& updates);

  // Re-saves all users to update the full-text index.
  void ReindexUsers(const DBHandle& updates);

  // Removes any terminated user ids from viewpoint followers.
  void RemoveTerminatedFollowers(const DBHandle& updates);

  // Removes old feed event day table data from DB.
  void RemoveFeedEventData(const DBHandle& updates);

  // Remove local-only photos in order to minimize the duplicate detection work
  // required when upgrading to iOS 7.
  virtual void RemoveLocalOnlyPhotos(const DBHandle& updates) { };

  // Convert from old to new asset fingerprints.
  virtual void ConvertAssetFingerprints(const DBHandle& updates) { };

  // Index photos via their perceptual fingerprint.
  virtual void IndexPhotos(const DBHandle& updates) { };

  // Prepare the viewpoint garbage collection queue.
  void PrepareViewpointGCQueue(const DBHandle& updates);

  // Remove photos with duplicate asset keys which have not been uploaded to
  // the server.
  virtual void RemoveAssetDuplicatePhotos(const DBHandle& updates) { }

 protected:
  // Runs "migrator" and "progress_update" blocks if the migration
  // hasn't yet been done.
  typedef void (DBMigration::*migration_func)(const DBHandle&);
  void RunMigration(const string& migration_key, migration_func migrator,
                    const DBHandle& updates);

  // Runs "migrator" and "progress_update" blocks if the migration hasn't been
  // done yet, but only if running on iOS and "min_ios_version <= kIOSVersion <
  // max_ios_version". Either or both of min_ios_version and max_ios_version
  // can be NULL which unrestricts that range of the version check.
  virtual void RunIOSMigration(const char* min_ios_version, const char* max_ios_version,
                               const string& migration_key, migration_func migrator,
                               const DBHandle& updates) = 0;

  // Flushes the transaction if it has a lot of pending data.
  // Should only be used in idempotent migrations.
  void MaybeFlush(const DBHandle& updates);

 private:
  AppState* state_;
  ProgressUpdateBlock progress_update_;
  bool migrated_;
};

#endif  // VIEWFINDER_DB_MIGRATION_H

// local variables:
// mode: c++
// end:
