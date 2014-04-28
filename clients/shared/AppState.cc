// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AppState.h"
#import "Analytics.h"
#import "AsyncState.h"
#import "Breadcrumb.pb.h"
#import "CommentTable.h"
#import "ContactManager.h"
#import "DayTable.h"
#import "DBStats.h"
#import "Defines.h"
#import "FileUtils.h"
#import "GeocodeManager.h"
#import "ImageIndex.h"
#import "NetworkManager.h"
#import "NetworkQueue.h"
#import "NotificationManager.h"
#import "PathUtils.h"
#import "PeopleRank.h"
#import "PhotoStorage.h"
#import "PlacemarkHistogram.h"
#import "PlacemarkTable.h"
#import "Timer.h"

namespace {

#ifndef DB_FORMAT_VALUE
#define DB_FORMAT_VALUE "56"
#endif  // DB_FORMAT_VALUE

#ifndef RESET_STATE
#define RESET_STATE false
#endif  // RESET_STATE

const bool kResetState = RESET_STATE;

// The major format of the database. If the major format does not match, the
// database and all associated data (including photos!) is destroyed.
const string kFormatKey = DBFormat::metadata_key("format");
const string kFormatValue = DB_FORMAT_VALUE;

const int kCacheSize = 1 * 1024 * 1024;

const string kInitMaintenanceKey = DBFormat::metadata_key("init_maintenance");
const string kServerHostKey = DBFormat::metadata_key("server_host");
const string kDeviceIdKey = DBFormat::metadata_key("device_id");
const string kUserIdKey = DBFormat::metadata_key("user_id");
const string kUserCookieKey = DBFormat::metadata_key("user_cookie");
const string kXsrfCookieKey = DBFormat::metadata_key("xsrf_cookie");
const string kCloudStorageKey = DBFormat::metadata_key("cloud_storage");
const string kStoreOriginalsKey = DBFormat::metadata_key("store_originals");
const string kNoPasswordKey = DBFormat::metadata_key("no_password");
const string kRefreshCompletedKey = DBFormat::metadata_key("refresh_completed");
const string kUploadLogsKey = DBFormat::metadata_key("upload_logs");
const string kLastLoginTimestampKey = DBFormat::metadata_key("last_login_timestamp");
const string kRegistrationVersionKey = DBFormat::metadata_key("registration_version");
const string kSystemMessageKey = DBFormat::metadata_key("system_message");
const string kLastBreadcrumbKey = DBFormat::metadata_key("last_breadcrumb");

// Maintains a sequence of local operation ids. The ids from this
// sequence are combined with the device id to encode a server-side
// operation id, passed with mutating requests (share, unshare,
// upload, delete, remove, etc.). The operation id (and an associated
// timestamp) are included in the JSON request "headers" dict. The
// activity which is subsequently generated for that operation will be
// composed exactly of the op timestamp, device id, and local
// operation id.
const string kNextOperationIdKey = DBFormat::metadata_key("next_operation_id");

const DBRegisterKeyIntrospect kMetadataKeyIntrospect(
    DBFormat::metadata_key(""), NULL, [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kLastBreadcrumbKeyIntrospect(
    kLastBreadcrumbKey, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<Breadcrumb>(value);
    });

// TODO(peter): This function is duplicated in UIAppState.mm.
void DeleteOld(const string& old_dir) {
  int files = 0;
  int dirs = 0;
  if (DirRemove(old_dir, true, &files, &dirs)) {
    LOG("%s: removed %d files, %d dirs", old_dir, files, dirs);
  }
}

}  // namespace

const string AppState::kLinkEndpoint = "link";
const string AppState::kLoginEndpoint = "login";
const string AppState::kLoginResetEndpoint = "login_reset";
const string AppState::kMergeTokenEndpoint = "merge_token";
const string AppState::kRegisterEndpoint = "register";
const string AppState::kVerifyEndpoint = "verify";

AppState::AppState(const string& base_dir, const string& server_host,
                   int server_port, bool production)
    : server_protocol_((server_host == "localhost") ? "http" : "https"),
      server_host_(server_host),
      server_port_(server_port),
      base_dir_(base_dir),
      library_dir_(JoinPath(base_dir_, LibraryPath())),
      database_dir_(JoinPath(library_dir_, "Database")),
      photo_dir_(JoinPath(library_dir_, "Photos")),
      server_photo_dir_(JoinPath(library_dir_, "ServerPhotos")),
      auth_path_(JoinPath(library_dir_, "co.viewfinder.auth")),
      production_(production),
      cloud_storage_(false),
      store_originals_(false),
      no_password_(false),
      refresh_completed_(false),
      upload_logs_(false),
      account_setup_(false),
      last_login_timestamp_(0),
      fake_logout_(false) {
#ifdef FAKE_LOGIN
  fake_logout_ = true;
#endif  // FAKE_LOGIN
}

AppState::~AppState() {
  // Delete the async state first. This will block until all of the running
  // async operations have completed.
  Kill();
}

bool AppState::Init(InitAction init_action) {
  WallTimer timer;
  if (!OpenDB(init_action == INIT_RESET)) {
    return false;
  }
  InitDirs();

  VLOG("init: db: %.03f ms", timer.Milliseconds());
  VLOG("init: db size: %.2f MB", db()->DiskUsage() / (1024.0 * 1024.0));
  timer.Restart();

  analytics_.reset(new Analytics(production_));
  VLOG("init: analytics: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  activity_table_.reset(new ActivityTable(this));
  VLOG("init: activity table: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  async_.reset(new AsyncState);
  VLOG("init: async state: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  comment_table_.reset(new CommentTable(this));
  VLOG("init: comment table: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  day_table_.reset(new DayTable(this, NewDayTableEnv()));
  VLOG("init: day table (pre-init): %0.3f ms", timer.Milliseconds());
  timer.Restart();

  episode_table_.reset(new EpisodeTable(this));
  VLOG("init: episode table: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  image_index_.reset(new ImageIndex);
  VLOG("init: image index: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  people_rank_.reset(new PeopleRank(this));
  VLOG("init: people rank: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  photo_table_.reset(new PhotoTable(this));
  VLOG("init: photo table: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  placemark_histogram_.reset(new PlacemarkHistogram(this));
  VLOG("init: placemark histogram: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  placemark_table_.reset(new PlacemarkTable(this));
  VLOG("init: placemark table: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  photo_storage_.reset(new PhotoStorage(this));
  VLOG("init: photo storage: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  viewpoint_table_.reset(new ViewpointTable(this));
  VLOG("init: viewpoint table: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  // IMPORTANT: Initialization order dependencies:
  // * ContactManager and NetworkQueue depend on NotificationManager
  notification_manager_.reset(new NotificationManager(this));
  VLOG("init: notification manager: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  contact_manager_.reset(new ContactManager(this));
  VLOG("init: contact manager: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  net_queue_.reset(new NetworkQueue(this));
  VLOG("init: network queue: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  return true;
}

void AppState::RunMaintenance(InitAction init_action) {
  WallTimer timer;

  ProgressUpdateBlock progress_update = [this](const string msg) {
    maintenance_progress_.Run(msg);
  };

  // The init_maintenance flag indicates that maintenance should be run in a
  // "silent" mode because the database was just reset.
  const bool init_maintenance = db()->Exists(kInitMaintenanceKey);
  if (init_maintenance) {
    progress_update = NULL;
  }

  // Run database migrations as necessary.
  // NOTE: This MUST be done first to move any DB tables into a state
  // that the rest of the code has been upgraded to expect.
  const bool migrated = MaybeMigrate(progress_update);
  VLOG("init: db migration: %0.3f ms", timer.Milliseconds());
  timer.Restart();

#if defined(ENABLE_DB_STATS)
  // Compute database statistics.
  //
  // NOTE(peter): This takes 1.5 secs on my client and proportionally longer
  // for larger users like Chris.
  DBStats stats(this);
  stats.ComputeStats();
  VLOG("init: db statistics: %0.3f ms", timer.Milliseconds());
  timer.Restart();
#endif  // DEVELOPMENT

  // Consistency check of database tables.
  const bool fscked = MaybeFSCK(init_action == INIT_FSCK, progress_update);
  VLOG("init: fscked? %s: %0.3f ms", fscked ? "yes" : "no",
      timer.Milliseconds());
  timer.Restart();

  // Possibly unquarantine photos.
  const bool unquarantined =
      photo_table_->MaybeUnquarantinePhotos(progress_update);
  VLOG("init: unquarantine: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  // Start day table initialization after all other tables are
  // initialized, as it may quickly start refreshing. We always
  // force a full refresh if any of the maintenance tasks resulted
  // in DB modifications.
  const bool reset = day_table_->Initialize(
      !init_maintenance && (migrated || fscked || unquarantined));
  VLOG("init: day table: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  ProcessPhotoDuplicateQueue();
  VLOG("init: process duplicate queue: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  if (init_maintenance) {
    db()->Delete(kInitMaintenanceKey);
  }

  maintenance_done_.Run(!init_maintenance && reset);
}

bool AppState::NeedDeviceIdReset() const {
  DCHECK(!device_uuid_.empty());
#if (TARGET_IPHONE_SIMULATOR)
  return false;
#endif  // (TARGET_IPHONE_SIMULATOR)
  return auth_.device_uuid() != device_uuid_;
}

void AppState::SetUserAndDeviceId(int64_t user_id, int64_t device_id) {
  if (auth_.user_id() == user_id && auth_.device_id() == device_id) {
    return;
  }
  // If we're updating the device id, also update the device_uuid.
  if (auth_.device_id() != device_id && device_id != 0) {
    DCHECK(!device_uuid_.empty());
    auth_.set_device_uuid(device_uuid_);
  }
  auth_.set_user_id(user_id);
  auth_.set_device_id(device_id);
  set_last_login_timestamp(WallTime_Now());
  WriteAuthMetadata();
  VLOG("setting user_id=%d device_id=%d", user_id, device_id);
  async_->dispatch_main([this, user_id, device_id] {
      settings_changed_.Run(false);
      if (user_id == 0 && device_id == 0) {
        // User is being logged out: force a maintenance run.
        dispatch_after_low_priority(0.5, [this] {
            maintenance_done_.Run(false);
          });
      }
    });
}

void AppState::SetAuthCookies(
    const string& user_cookie, const string& xsrf_cookie) {
  bool changed = false;
  if (auth_.user_cookie() != user_cookie) {
    auth_.set_user_cookie(user_cookie);
    changed = true;
  }
  if (auth_.xsrf_cookie() != xsrf_cookie) {
    auth_.set_xsrf_cookie(xsrf_cookie);
    changed = true;
  }
  if (changed) {
    WriteAuthMetadata();
  }
}

void AppState::ClearAuthMetadata() {
  auth_.Clear();
  WriteAuthMetadata();
}

int64_t AppState::NewLocalOperationId() {
  MutexLock l(&next_op_id_mu_);
  const int64_t id = next_op_id_++;
  db_->Put(kNextOperationIdKey, next_op_id_);
  return id;
}

DBHandle AppState::NewDBTransaction() {
  return db_->NewTransaction();
}

DBHandle AppState::NewDBSnapshot() {
  return db_->NewSnapshot();
}

void AppState::set_server_host(const Slice& host) {
  server_host_ = host.as_string();
  db_->Put(kServerHostKey, host);
}

void AppState::set_last_breadcrumb(const Breadcrumb& b) {
  if (!last_breadcrumb_.get()) {
    last_breadcrumb_.reset(new Breadcrumb);
  }
  last_breadcrumb_->CopyFrom(b);
  db_->PutProto(kLastBreadcrumbKey, *last_breadcrumb_);
}

void AppState::set_cloud_storage(bool v) {
  cloud_storage_ = v;
  db_->Put(kCloudStorageKey, cloud_storage_);
}

void AppState::set_store_originals(bool v) {
  store_originals_ = v;
  db_->Put(kStoreOriginalsKey, store_originals_);
}

void AppState::set_no_password(bool v) {
  no_password_ = v;
  db_->Put(kNoPasswordKey, no_password_);
  async_->dispatch_main([this] {
      settings_changed_.Run(true);
    });
}

void AppState::set_refresh_completed(bool v) {
  refresh_completed_ = true;
  db_->Put(kRefreshCompletedKey, refresh_completed_);
}

void AppState::set_upload_logs(bool v) {
  upload_logs_ = v;
  db_->Put(kUploadLogsKey, upload_logs_);
}

void AppState::set_last_login_timestamp(WallTime v) {
  last_login_timestamp_ = v;
  db_->Put(kLastLoginTimestampKey, last_login_timestamp_);
}

void AppState::set_registration_version(RegistrationVersion v) {
  registration_version_ = v;
  db_->Put(kRegistrationVersionKey, static_cast<int>(registration_version_));
}

void AppState::set_system_message(const SystemMessage& msg) {
  if (msg.identifier() == system_message_.identifier()) {
    return;
  }
  system_message_ = msg;
  db_->PutProto(kSystemMessageKey, system_message_);
  LOG("setting system_message=%s", system_message_);
  async_->dispatch_main([this] {
    system_message_changed_.Run();
  });
}

void AppState::clear_system_message() {
  // Call set_system_message, we want to notify watchers when the message is cleared.
  set_system_message(SystemMessage());
}

bool AppState::network_wifi() const {
  return net_manager_->network_wifi();
}

void AppState::Kill() {
  async_.reset(NULL);
}

bool AppState::OpenDB(bool reset) {
  DirCreate(library_dir_);
  db_.reset(NewDB(database_dir_));

  if (reset || kResetState) {
    VLOG("%s: recreating database", db_->dir());
    Clean(library_dir_);
  }

  for (int i = 0; i < 2; ++i) {
    if (!db_->Open(kCacheSize)) {
#ifndef DEVELOPMENT
      // In non-development builds, try to stumble ahead if the database is
      // corrupt or cannot otherwise be opened.
      if (i == 0) {
        Clean(library_dir_);
        continue;
      }
#endif  // DEVELOPMENT
      return false;
    }

    bool empty = true;
    for (DB::PrefixIterator iter(db_, "");
         iter.Valid();
         iter.Next()) {
      empty = false;
      break;
    }

    if (empty) {
      // A new database, initialize the format major key.
      if (!InitDB()) {
        return false;
      }
    } else {
      // An existing database, make sure the format major key matches.
      string value;
      if (!db_->Get(kFormatKey, &value) ||
          kFormatValue != value) {
        VLOG("%s: major format mismatch, recreating database", db_->dir());
        db_->Close();
        Clean(library_dir_);
        continue;
      }
    }

    const string old_dir(JoinPath(library_dir_, "old"));
    dispatch_after_background(5, [old_dir] { DeleteOld(old_dir); });
    InitVars();
    return true;
  }
  return false;
}

bool AppState::InitDB() {
  DBHandle updates = NewDBTransaction();
  updates->Put(kFormatKey, kFormatValue);
  updates->Put(kInitMaintenanceKey, "");
  if (!updates->Commit()) {
    VLOG("%s: unable to initialize database format", db_->dir());
    db_->Close();
    return false;
  }
  return true;
}

void AppState::InitDirs() {
  // Ensure that the photos directory exists.
  DirCreate(photo_dir_);
  DirCreate(server_photo_dir_);
}

void AppState::InitVars() {
  // Load the auth metadata, falling back to initializing the auth metadata
  // from the old database keys.
  if (!ReadFileToProto(auth_path_, &auth_)) {
    auth_.set_device_id(db_->Get<int>(kDeviceIdKey, 0));
    auth_.set_user_id(db_->Get<int>(kUserIdKey, 0));
    auth_.set_user_cookie(db_->Get<string>(kUserCookieKey));
    auth_.set_xsrf_cookie(db_->Get<string>(kXsrfCookieKey));
    WriteAuthMetadata();
    db_->Delete(kDeviceIdKey);
    db_->Delete(kUserIdKey);
    db_->Delete(kUserCookieKey);
    db_->Delete(kXsrfCookieKey);
  }

  // If the auth doesn't have the device's unique identifier, set it.
  if (!auth_.has_device_uuid()) {
    DCHECK(!device_uuid_.empty());
    auth_.set_device_uuid(device_uuid_);
    WriteAuthMetadata();
  }

#ifdef RESET_AUTH
  auth_.Clear();
#endif  // RESET_AUTH

  last_breadcrumb_.reset(new Breadcrumb);
  if (!db_->GetProto(kLastBreadcrumbKey, last_breadcrumb_.get())) {
    last_breadcrumb_.reset(NULL);
  }

  next_op_id_ = db_->Get<int64_t>(kNextOperationIdKey, 1);
  server_host_ = db_->Get<string>(kServerHostKey, server_host_);
  // Cloud storage is not currently available.
  //cloud_storage_ = db_->Get<bool>(kCloudStorageKey, false);
  store_originals_ = db_->Get<bool>(kStoreOriginalsKey, false);
  no_password_ = db_->Get<bool>(kNoPasswordKey, false);
  refresh_completed_ = db_->Get<bool>(kRefreshCompletedKey, false);
  upload_logs_ = db_->Get<bool>(kUploadLogsKey, true);
  last_login_timestamp_ = db_->Get<WallTime>(kLastLoginTimestampKey, 0);
  registration_version_ = static_cast<RegistrationVersion>(
      db_->Get<int>(kRegistrationVersionKey, REGISTRATION_GOOGLE_FACEBOOK));
  db_->GetProto(kSystemMessageKey, &system_message_);

  if (user_id() && !last_login_timestamp_) {
    // The login must have predated our support of last_login_timestamp,
    // so initialize it now.
    set_last_login_timestamp(WallTime_Now());
  }

  VLOG("device_id=%d, user_id=%d", device_id(), user_id());
  VLOG("cloud_storage=%s", cloud_storage_ ? "on" : "off");
  VLOG("store_originals=%s", store_originals_ ? "on" : "off");
  VLOG("no_password=%s", no_password_ ? "true" : "false");
  VLOG("refresh_completed=%s", refresh_completed_ ? "on" : "off");
  VLOG("upload_logs=%s", upload_logs_ ? "on" : "off");
  VLOG("registration_version=%s", registration_version_);
  VLOG("server_host=%s", server_host_);
  VLOG("system_message=%s", system_message_);
}

void AppState::Clean(const string& lib_dir) {
  // Move the existing database and photo directories to a new directory
  // which will be deleted asynchronously in the background.
  const string old_dir(JoinPath(lib_dir, "old"));
  DirCreate(old_dir);
  const string unique_dir(JoinPath(old_dir, NewUUID()));
  DirCreate(unique_dir);

  const string kSubdirs[] = {
    "Database",
    "Photos",
  };
  for (int i = 0; i < ARRAYSIZE(kSubdirs); ++i) {
    FileRename(JoinPath(lib_dir, kSubdirs[i]),
               JoinPath(unique_dir, kSubdirs[i]));
  }
}

bool AppState::MaybeFSCK(bool force, ProgressUpdateBlock progress_update) {
  DBHandle updates = NewDBTransaction();
  const bool repair = true;
  bool fscked = false;

  // NOTE: these should be ordered from most self-contained (e.g. have
  // the least references to other assets) to the least self-contained.
  if (photo_table_->FSCK(force, progress_update, updates)) {
    fscked = true;
  }
  if (episode_table_->FSCK(force, progress_update, updates)) {
    fscked = true;
  }
  if (viewpoint_table_->FSCK(force, progress_update, updates)) {
    fscked = true;
  }
  if (activity_table_->FSCK(force, progress_update, updates)) {
    fscked = true;
  }

  if (repair) {
    updates->Commit();
    return fscked;
  }
  updates->Abandon();
  return false;
}

void AppState::WriteAuthMetadata() {
  // Note, include the auth metadata in backup so that it transfers to new
  // devices.
  CHECK(WriteProtoToFile(auth_path_, auth_, false /* exclude_from_backup */));
}

// local variables:
// mode: c++
// end:
