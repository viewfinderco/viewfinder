// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_DB_MIGRATION_ANDROID_H
#define VIEWFINDER_DB_MIGRATION_ANDROID_H

#import "DBMigration.h"

class AppState;

class DBMigrationAndroid : public DBMigration {
 public:
  DBMigrationAndroid(AppState* state, ProgressUpdateBlock progress_update);
  virtual ~DBMigrationAndroid();

  virtual void RemoveLocalOnlyPhotos(const DBHandle& updates);
  virtual void ConvertAssetFingerprints(const DBHandle& updates);
  virtual void IndexPhotos(const DBHandle& updates);

 protected:
  virtual void RunIOSMigration(const char* min_ios_version, const char* max_ios_version,
                               const string& migration_key, migration_func migrator,
                               const DBHandle& updates);
};

#endif  // VIEWFINDER_DB_MIGRATION_IOS_H

// local variables:
// mode: c++
// end:
