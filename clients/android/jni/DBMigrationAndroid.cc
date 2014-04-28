// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "DBMigrationAndroid.h"

DBMigrationAndroid::DBMigrationAndroid(AppState* state, ProgressUpdateBlock progress_update)
    : DBMigration(state, progress_update) {
}

DBMigrationAndroid::~DBMigrationAndroid() {
}

void DBMigrationAndroid::RunIOSMigration(
    const char* min_ios_version, const char* max_ios_version,
    const string& migration_key, migration_func migrator,
    const DBHandle& updates) {
  // IOS migrations are not run on Android.
}

void DBMigrationAndroid::RemoveLocalOnlyPhotos(const DBHandle& updates) {
}

void DBMigrationAndroid::ConvertAssetFingerprints(const DBHandle& updates) {
}

void DBMigrationAndroid::IndexPhotos(const DBHandle& updates) {
}

// local variables:
// mode: c++
// end:
