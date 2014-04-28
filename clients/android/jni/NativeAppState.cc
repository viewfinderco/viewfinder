// Copyright 2013 Viewfinder. All Rights Reserved.
// Author: Marc Berhault.
// Author: Mike Purtell.

#include <functional>
#include <string>
#include <android/log.h>
#include <leveldb/db.h>
#include <unicode/putil.h>
#include <sys/types.h>
#include "AsyncState.h"
#include "ContactManager.h"
#include "DayTable.h"
#include "DayTableEnv.h"
#include "DB.h"
#include "DBMigrationAndroid.h"
#include "FileUtils.h"
#include "JNIUtils.h"
#include "LocaleUtils.android.h"
#include "LocaleUtils.h"
#include "Logging.h"
#include "NativeAppState.h"
#include "NetworkManagerAndroid.h"
#include "PathUtils.h"
#include "PhotoStorage.h"
#include "ScopedHandle.h"
#include "StringUtils.android.h"
#include "StringUtils.h"
#include "Utils.android.h"
#include "WallTime.android.h"

#define TAG "viewfinder.NativeAppState"

namespace {

// Helper macro to avoid stuttering when registering java natives.
#define JAVA_NATIVE(f)  { #f, f }

class JavaAppState {
 public:
  static void Register(JNIEnv* env) {
    JavaClass(env, "co/viewfinder/AppState")
        .BindStaticMethod("localizedCaseInsensitiveCompare",
                          &localized_case_insensitive_compare)
        .BindStaticMethod("localizedNumberFormat",
                          &localized_number_format)
        .BindStaticMethod("newUUID",
                          &new_uuid)
        .BindStaticMethod("getTimeZoneOffset",
                          &time_zone_offset)
        .BindStaticMethod("getTimeZoneName",
                          &time_zone_name)
        .BindStaticMethod("getFreeDiskSpace",
                          &free_disk_space)
        .BindStaticMethod("getTotalDiskSpace",
                          &total_disk_space)
        .RegisterNatives({
            JAVA_NATIVE(LoadNative),
            JAVA_NATIVE(UnloadNative),
            JAVA_NATIVE(RunMaintenance),
            JAVA_NATIVE(AppDidBecomeActive),
            JAVA_NATIVE(GetDBHandle),
            JAVA_NATIVE(GetActivityTable),
            JAVA_NATIVE(GetContactManager),
            JAVA_NATIVE(GetDayTable),
            JAVA_NATIVE(GetEpisodeTable),
            JAVA_NATIVE(GetNetworkManager),
            JAVA_NATIVE(GetPhotoStorage),
            JAVA_NATIVE(GetPhotoTable),
            JAVA_NATIVE(GetViewpointTable),
            JAVA_NATIVE(SetAuthCookies),
            JAVA_NATIVE(GetUserCookie),
            JAVA_NATIVE(GetUserID),
            JAVA_NATIVE(GetXsrfCookie),
          });
  }

 private:
  static jlong LoadNative(
      JNIEnv* env, jobject obj, jstring j_path, jboolean reset, jint server_port) {
    // Need to initialize app-version before Logging.
    app_version = JavaMethod<string ()>::Invoke(env, obj, "appVersion");

    const string path = JavaToCppString(env, j_path);
    InitApplicationPath(path);
    Logging::InitFileLogging();

    // Init ICU data from local file.
    u_setDataDirectory(JoinPath(path, "icudt51l.dat").c_str());

    // TODO(marc): setup extra log sink in debug mode only.
    Logging::AddLogSink([](const LogArgs& args) {
        // No need to output timestamp or thread id as the android log already
        // captures that.
        __android_log_print(
            args.vlog ? ANDROID_LOG_VERBOSE : ANDROID_LOG_INFO,
            TAG, "%s %s", args.file_line, &args.message[0]);
      });

    ScopedPtr<NativeAppState> state(new NativeAppState(HomeDir(), server_port, env, obj));
    const AppState::InitAction init_action =
        reset ? AppState::INIT_RESET : AppState::INIT_NORMAL;
    if (!state->Init(init_action)) {
      LOG("unable to initialize native app state");
      return 0;
    }
    return CppToJavaPointer(env, state.release());
  }

  static void UnloadNative(JNIEnv* env, jclass, jlong j_app_state) {
    delete JavaToCppPointer<NativeAppState>(env, j_app_state);
  }

  static void RunMaintenance(JNIEnv* env, jclass, jlong j_app_state, jboolean reset) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    const AppState::InitAction init_action =
        reset ? AppState::INIT_RESET : AppState::INIT_NORMAL;
    dispatch_low_priority([state, init_action] {
        state->RunMaintenance(init_action);
      });
  }

  static jlong GetDBHandle(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppToJavaPointer(env, new DBHandle(state->db()));
  }

  static jlong GetActivityTable(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppToJavaPointer(env, state->activity_table());
  }

  static jlong GetContactManager(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppToJavaPointer(env, state->contact_manager());
  }

  static jlong GetDayTable(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppToJavaPointer(env, state->day_table());
  }

  static jlong GetEpisodeTable(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppToJavaPointer(env, state->episode_table());
  }

  static jlong GetNetworkManager(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppToJavaPointer(env, state->net_manager());
  }

  static jlong GetPhotoStorage(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppToJavaPointer(env, state->photo_storage());
  }

  static jlong GetPhotoTable(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppToJavaPointer(env, state->photo_table());
  }

  static jlong GetViewpointTable(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppToJavaPointer(env, state->viewpoint_table());
  }

  static void AppDidBecomeActive(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    LOG("AppDidBecomeActive");
    state->app_did_become_active()->Run();
  }

  static void AppWillResignActive(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    LOG("AppWillResignActive");
    state->app_will_resign_active()->Run();
  }

  static void SetAuthCookies(JNIEnv* env, jclass, jlong j_app_state,
                             jbyteArray j_user_cookie, jbyteArray j_xsrf_cookie) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    const string uc = j_user_cookie == NULL ? "" : JavaByteArrayToCppString(env, j_user_cookie);
    const string xc = j_xsrf_cookie == NULL ? "" : JavaByteArrayToCppString(env, j_xsrf_cookie);
    state->SetAuthCookies(uc, xc);
  }

  static jbyteArray GetUserCookie(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppStringToJavaByteArray(env, state->auth().user_cookie());
  }

  static jlong GetUserID(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return state->user_id();
  }

  static jbyteArray GetXsrfCookie(JNIEnv* env, jclass, jlong j_app_state) {
    NativeAppState* const state = JavaToCppPointer<NativeAppState>(env, j_app_state);
    return CppStringToJavaByteArray(env, state->auth().xsrf_cookie());
  }
};

template <typename ContentTable>
class JavaContentTable {
  typedef typename ContentTable::ContentHandle ContentHandle;

 protected:
  static ContentHandle* GetHandlePointer(JNIEnv* env, jlong j_handle) {
    return JavaToCppPointer<ContentHandle>(env, j_handle);
  }

  static jlong LoadHandle(
      JNIEnv* env, jclass, jlong table, jlong content_id, jlong j_db) {
    ContentTable* const t = JavaToCppPointer<ContentTable>(env, table);
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    ContentHandle h = t->LoadContent(content_id, *db);
    if (!h.get()) {
      return 0;
    }
    return CppToJavaPointer(env, new ContentHandle(h));
  }

  static void ReleaseHandle(JNIEnv* env, jclass, jlong j_handle) {
    delete GetHandlePointer(env, j_handle);
  }

  static jbyteArray LoadProto(
      JNIEnv* env, jclass, jlong j_handle) {
    ContentHandle* const h = GetHandlePointer(env, j_handle);
    return CppToJavaProto(env, **h);
  }
};

class JavaActivityTable : private JavaContentTable<ActivityTable> {
 public:
  static void Register(JNIEnv* env) {
    JavaClass(env, "co/viewfinder/ActivityTable")
        .RegisterNatives({
            JAVA_NATIVE(LoadHandle),
            JAVA_NATIVE(ReleaseHandle),
            JAVA_NATIVE(LoadProto),
            JAVA_NATIVE(FormatName),
            JAVA_NATIVE(FormatTimestamp),
            JAVA_NATIVE(FormatContent),
          });
  }

 private:
  static jstring FormatName(
      JNIEnv* env, jclass, jlong j_ah, jboolean shorten) {
    ActivityHandle* const ah = GetHandlePointer(env, j_ah);
    return CppToJavaString(env, (*ah)->FormatName(shorten));
  }

  static jstring FormatTimestamp(
      JNIEnv* env, jclass, jlong j_ah, jboolean shorten) {
    ActivityHandle* const ah = GetHandlePointer(env, j_ah);
    return CppToJavaString(env, (*ah)->FormatTimestamp(shorten));
  }

  static jstring FormatContent(
      JNIEnv* env, jclass, jlong j_ah,
      jbyteArray j_activity_row, jboolean shorten) {
    ActivityHandle* const ah = GetHandlePointer(env, j_ah);
    ViewpointSummaryMetadata::ActivityRow activity_row;
    if (j_activity_row &&
        !JavaToCppProto(env, j_activity_row, &activity_row)) {
      return CppToJavaString(env, "");
    }
    const string result = (*ah)->FormatContent(
        j_activity_row ? &activity_row : NULL, shorten);
    return CppToJavaString(env, result);
  }
};

class JavaContactManager {
 public:
  static void Register(JNIEnv* env) {
    // TODO(marc): missing ContactManager functionality (used in ios/Source):
    // - callbacks: contact_changed, contact_resolved, process_users, new_user_callback
    // - Fetch: Fetch(Google|Facebook)Contacts, ProcessAddressBookImport
    // - ResetNewUsers
    JavaClass(env, "co/viewfinder/ContactManager")
        .RegisterNatives({
            JAVA_NATIVE(ConstructFullName),
            JAVA_NATIVE(Count),
            JAVA_NATIVE(CountContactsForSource),
            JAVA_NATIVE(CountViewfinderContactsForSource),
            JAVA_NATIVE(FirstNameFromId),
            JAVA_NATIVE(FirstNameFromProto),
            JAVA_NATIVE(FullNameFromId),
            JAVA_NATIVE(FullNameFromProto),
            JAVA_NATIVE(GetCachedResolvedContact),
            JAVA_NATIVE(GetLastImportTimeForSource),
            JAVA_NATIVE(GetNewUsers),
            JAVA_NATIVE(LookupUser),
            JAVA_NATIVE(LookupUserByIdentity),
            JAVA_NATIVE(MergeResolvedContact),
            JAVA_NATIVE(QueueUser),
            JAVA_NATIVE(Reset),
            JAVA_NATIVE(ResetAll),
            JAVA_NATIVE(ResolveContact),
            JAVA_NATIVE(SaveContact),
            JAVA_NATIVE(Search),
            JAVA_NATIVE(SetLastImportTimeForSource),
            JAVA_NATIVE(SetFriendNickname),
            JAVA_NATIVE(SetMyName),
            JAVA_NATIVE(ViewfinderCount),
         });
    j_class_byte_array_ = new ScopedGlobalRef<jclass>(env);
    j_class_byte_array_->reset(JavaFindClass(env, "[B"));
  }

 private:
  static jstring ConstructFullName(JNIEnv* env, jclass, jstring j_first, jstring j_last) {
    const string first = JavaToCppString(env, j_first);
    const string last = JavaToCppString(env, j_last);
    return CppToJavaString(env, ContactManager::ConstructFullName(first, last));
  }

  static int Count(JNIEnv* env, jclass, jlong j_contact_manager) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    return contact_manager->count();
  }

  static int CountContactsForSource(JNIEnv* env, jclass, jlong j_contact_manager, jstring j_source) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string source = JavaToCppString(env, j_source);
    return contact_manager->CountContactsForSource(source);
  }

  static int CountViewfinderContactsForSource(JNIEnv* env, jclass, jlong j_contact_manager, jstring j_source) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string source = JavaToCppString(env, j_source);
    return contact_manager->CountViewfinderContactsForSource(source);
  }

  static jstring FirstNameFromId(JNIEnv* env, jclass, jlong j_contact_manager,
                                 jlong j_user_id, jboolean j_allow_nickname) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    return CppToJavaString(env, contact_manager->FirstName(j_user_id, j_allow_nickname));
  }

  static jstring FirstNameFromProto(JNIEnv* env, jclass, jlong j_contact_manager,
                                    jbyteArray j_contact, jboolean j_allow_nickname) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    ContactMetadata cm;
    if (!JavaToCppProto(env, j_contact, &cm)) {
      return CppToJavaString(env, "");
    }

    return CppToJavaString(env, contact_manager->FirstName(cm, j_allow_nickname));
  }

  static jstring FullNameFromId(JNIEnv* env, jclass, jlong j_contact_manager,
                                jlong j_user_id, jboolean j_allow_nickname) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    return CppToJavaString(env, contact_manager->FullName(j_user_id, j_allow_nickname));
  }

  static jstring FullNameFromProto(JNIEnv* env, jclass, jlong j_contact_manager,
                                   jbyteArray j_contact, jboolean j_allow_nickname) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    ContactMetadata cm;
    if (!JavaToCppProto(env, j_contact, &cm)) {
      return CppToJavaString(env, "");
    }

    return CppToJavaString(env, contact_manager->FullName(cm, j_allow_nickname));
  }

  static jbyteArray GetCachedResolvedContact(JNIEnv* env, jclass, jlong j_contact_manager, jstring j_identity) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string identity = JavaToCppString(env, j_identity);

    ContactMetadata cm;
    if (!contact_manager->GetCachedResolvedContact(identity, &cm)) {
      return NULL;
    }
    return CppToJavaProto(env, cm);
  }

  static jdouble GetLastImportTimeForSource(JNIEnv* env, jclass, jlong j_contact_manager, jstring j_source) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string source = JavaToCppString(env, j_source);
    return contact_manager->GetLastImportTimeForSource(source);
  }

  static jobjectArray GetNewUsers(JNIEnv* env, jclass, jlong j_contact_manager) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    vector<ContactMetadata> contacts;
    contact_manager->GetNewUsers(&contacts);
    return CppContactVecToJavaObjectArray(env, contacts);
  }

  static jbyteArray LookupUser(JNIEnv* env, jclass, jlong j_contact_manager, jlong j_user_id, jlong j_db_handle) {
    ContactMetadata cm;
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);

    string value;
    bool ret;
    if (j_db_handle == NULL) {
      ret = contact_manager->LookupUser(j_user_id, &cm);
    } else {
      DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db_handle);
      ret = contact_manager->LookupUser(j_user_id, &cm, *db);
    }
    if (!ret) {
      return NULL;
    }
    return CppToJavaProto(env, cm);
  }

  static jbyteArray LookupUserByIdentity(JNIEnv* env, jclass, jlong j_contact_manager,
                                         jstring j_identity, jlong j_db_handle) {
    ContactMetadata cm;
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string identity = JavaToCppString(env, j_identity);

    string value;
    bool ret;
    if (j_db_handle == NULL) {
      ret = contact_manager->LookupUserByIdentity(identity, &cm);
    } else {
      DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db_handle);
      ret = contact_manager->LookupUserByIdentity(identity, &cm, *db);
    }
    if (!ret) {
      return NULL;
    }
    return CppToJavaProto(env, cm);
  }

  static void MergeResolvedContact(JNIEnv* env, jclass, jlong j_contact_manager, jbyteArray j_contact) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    ContactMetadata contact;
    CHECK(JavaToCppProto(env, j_contact, &contact));

    DBHandle updates = contact_manager->state()->NewDBTransaction();
    contact_manager->MergeResolvedContact(contact, updates);
    updates->Commit();
  }

  static void QueueUser(JNIEnv* env, jclass, jlong j_contact_manager, jlong j_user_id) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    DBHandle updates = contact_manager->state()->NewDBTransaction();
    contact_manager->QueueUser(j_user_id, updates);
    updates->Commit();
  }

  static void Reset(JNIEnv* env, jclass, jlong j_contact_manager) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    contact_manager->Reset();
  }

  static void ResetAll(JNIEnv* env, jclass, jlong j_contact_manager) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    contact_manager->ResetAll();
  }

  static void ResolveContact(JNIEnv* env, jclass, jlong j_contact_manager, jstring j_identity) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string identity = JavaToCppString(env, j_identity);
    contact_manager->ResolveContact(identity);
  }

  static jstring SaveContact(JNIEnv* env, jclass, jlong j_contact_manager, jbyteArray j_contact, jboolean j_upload,
                            jdouble j_now) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    ContactMetadata contact;
    CHECK(JavaToCppProto(env, j_contact, &contact));

    DBHandle updates = contact_manager->state()->NewDBTransaction();
    const string ret = contact_manager->SaveContact(contact, j_upload, j_now, updates);
    updates->Commit();

    return CppToJavaString(env, ret);
  }

  static jobjectArray Search(JNIEnv* env, jclass, jlong j_contact_manager,
                             jstring j_search_text, jboolean j_all_users) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string search_text = JavaToCppString(env, j_search_text);

    const int viewfinder_users_only = j_all_users ? 0 : ContactManager::VIEWFINDER_USERS_ONLY;
    const int search_options = viewfinder_users_only |
                               ContactManager::SORT_BY_NAME |
                               ContactManager::ALLOW_EMPTY_SEARCH |
                               ContactManager::PREFIX_MATCH;
    vector<ContactMetadata> contacts;
    // TODO(marc): support search_filter.
    contact_manager->Search(search_text, &contacts, NULL, search_options);
    return CppContactVecToJavaObjectArray(env, contacts);
  }

  static void SetLastImportTimeForSource(JNIEnv* env, jclass, jlong j_contact_manager,
                                         jstring j_source, jdouble j_timestamp) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string source = JavaToCppString(env, j_source);
    return contact_manager->SetLastImportTimeForSource(source, j_timestamp);
  }

  static bool SetMyName(JNIEnv* env, jclass, jlong j_contact_manager,
                        jstring j_first, jstring j_last, jstring j_name) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string first = JavaToCppString(env, j_first);
    const string last = JavaToCppString(env, j_last);
    const string name = JavaToCppString(env, j_name);
    return contact_manager->SetMyName(first, last, name);
  }

  static void SetFriendNickname(JNIEnv* env, jclass, jlong j_contact_manager, jlong j_user_id, jstring j_nickname) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    const string nickname = JavaToCppString(env, j_nickname);
    contact_manager->SetFriendNickname(j_user_id, nickname);
  }

  static int ViewfinderCount(JNIEnv* env, jclass, jlong j_contact_manager) {
    ContactManager* const contact_manager = JavaToCppPointer<ContactManager>(env, j_contact_manager);
    return contact_manager->viewfinder_count();
  }

  static jobjectArray CppContactVecToJavaObjectArray(JNIEnv* env, const vector<ContactMetadata>& v) {
    jobjectArray ret = env->NewObjectArray(v.size(), j_class_byte_array_->get(), NULL);
    // TODO(marc): trim out fields that java doesn't care about.
    for (int i = 0; i < v.size(); i++) {
      ScopedLocalRef<jbyteArray> el(env, CppToJavaProto(env, v[i]));
      env->SetObjectArrayElement(ret, i, el);
    }
  return ret;
}

 private:
  static ScopedGlobalRef<jclass>* j_class_byte_array_;
};

ScopedGlobalRef<jclass>* JavaContactManager::j_class_byte_array_;

class JavaDayTable {
 public:
  static void Register(JNIEnv* env) {
    JavaClass(env, "co/viewfinder/DayTable")
        .RegisterNatives({
            JAVA_NATIVE(LoadViewpointSummary),
            JAVA_NATIVE(LoadViewpointTimestampAndIdentifier),
          });
  }

 private:
  static jbyteArray LoadViewpointSummary(
      JNIEnv* env, jclass, jlong j_day_table, jlong j_db, jlong viewpoint_id) {
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    const string key = EncodeViewpointSummaryKey(viewpoint_id);
    string value;
    if ((*db)->Get(key, &value)) {
      // The fast path: the ViewpointSummary exists in the snapshot, just
      // return the bytes and let java decode the proto.
      return CppStringToJavaByteArray(env, value);
    }

    // The slow path: the ViewpointSummary does not exist and needs to be
    // rebuilt from the ViewpointMetadata.
    DayTable* const day_table = JavaToCppPointer<DayTable>(env, j_day_table);
    AppState* const state = day_table->state();
    DayTable::ViewpointSummaryHandle vsh(
        new DayTable::ViewpointSummary(day_table, *db));
    vsh->Rebuild(state->viewpoint_table()->LoadViewpoint(viewpoint_id, *db));
    // Serialize the ViewpointSummary to a string for return to java-land.
    return CppToJavaProto(env, *vsh);
  }

  static jbyteArray LoadViewpointTimestampAndIdentifier(
      JNIEnv* env, jclass, jlong j_db, jlong viewpoint_id) {
    // This code is based on DayTable::ConversationSummary::GetViewpointRowIndex();
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    string key;
    if (!(*db)->Get(EncodeViewpointConversationKey(viewpoint_id), &key)) {
      LOG("day table: failed to find row index for viewpoint %d", viewpoint_id);
      return NULL;
    }
    WallTime timestamp;
    int64_t identifier;
    if (!DecodeTimestampAndIdentifier(key, &timestamp, &identifier)) {
      LOG("day table: failed to decode key %s", key);
      return NULL;
    }
    SummaryRow row;
    row.set_day_timestamp(timestamp);
    row.set_identifier(identifier);
    return CppToJavaProto(env, row);
  }
};

class JavaDB {
 public:
  static void Register(JNIEnv* env) {
    JavaClass(env, "co/viewfinder/DB")
        .RegisterNatives({
            JAVA_NATIVE(Put),
            JAVA_NATIVE(Get),
            JAVA_NATIVE(Exists),
            JAVA_NATIVE(NewSnapshot),
            JAVA_NATIVE(NewHandle),
            JAVA_NATIVE(ReleaseHandle),
         });
  }

 private:
  static void Put(
      JNIEnv* env, jclass, jlong j_db, jstring j_key, jbyteArray j_value) {
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    const string key = JavaToCppString(env, j_key);
    const string value = JavaByteArrayToCppString(env, j_value);
    (*db)->Put(key, value);
  }

  static jbyteArray Get(
      JNIEnv* env, const DBHandle& db, const string& key) {
    string value;
    if (!db->Get(key, &value)) {
      return NULL;
    }
    return CppStringToJavaByteArray(env, value);
  }

  static jbyteArray Get(
      JNIEnv* env, jclass, jlong j_db, jstring j_key) {
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    return Get(env, *db, JavaToCppString(env, j_key));
  }

  static jboolean Exists(
      JNIEnv* env, jclass, jlong j_db, jstring j_key) {
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    return (*db)->Exists(JavaToCppString(env, j_key));
  }

  static jlong NewSnapshot(
      JNIEnv* env, jclass, jlong j_db) {
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    return CppToJavaPointer(env, new DBHandle((*db)->NewSnapshot()));
  }

  static jlong NewHandle(
      JNIEnv* env, jclass, jlong j_db) {
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    return CppToJavaPointer(env, new DBHandle(*db));
  }

  static void ReleaseHandle(
      JNIEnv* env, jclass, jlong db_handle) {
    delete JavaToCppPointer<DBHandle>(env, db_handle);
  }
};

class JavaEpisodeTable : private JavaContentTable<EpisodeTable> {
 public:
  static void Register(JNIEnv* env) {
    JavaClass(env, "co/viewfinder/EpisodeTable")
        .RegisterNatives({
            JAVA_NATIVE(LoadHandle),
            JAVA_NATIVE(ReleaseHandle),
            JAVA_NATIVE(GetEpisodeForPhoto),
            JAVA_NATIVE(ListEpisodes),
            JAVA_NATIVE(LoadProto),
            JAVA_NATIVE(FormatLocation),
            JAVA_NATIVE(FormatContributor),
          });
  }

 private:
  static jlong GetEpisodeForPhoto(
      JNIEnv* env, jclass, jlong table, jlong photo_id, jlong j_db) {
    EpisodeTable* const t = JavaToCppPointer<EpisodeTable>(env, table);
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    PhotoHandle ph = t->state()->photo_table()->LoadPhoto(photo_id, *db);
    if (!ph.get()) {
      return 0;
    }
    EpisodeHandle eh = t->GetEpisodeForPhoto(ph, *db);
    if (!eh.get()) {
      return 0;
    }
    return CppToJavaPointer(env, new EpisodeHandle(eh));
  }

  static jlongArray ListEpisodes(
      JNIEnv* env, jclass, jlong table, jlong photo_id, jlong j_db) {
    EpisodeTable* const t = JavaToCppPointer<EpisodeTable>(env, table);
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    vector<int64_t> episode_ids;
    if (!t->ListEpisodes(photo_id, &episode_ids, *db)) {
      return NULL;
    }
    return CppVectorToJavaLongArray(env, episode_ids);
  }

  static jstring FormatLocation(
      JNIEnv* env, jclass, jlong j_eh, jboolean shorten) {
    EpisodeHandle* const eh = GetHandlePointer(env, j_eh);
    return CppToJavaString(env, (*eh)->FormatLocation(shorten));
  }

  static jstring FormatContributor(
      JNIEnv* env, jclass, jlong j_eh, jboolean shorten) {
    EpisodeHandle* const eh = GetHandlePointer(env, j_eh);
    return CppToJavaString(env, (*eh)->FormatContributor(shorten));
  }
};

class JavaNetworkManager {
 public:
  static void Register(JNIEnv* env) {
    JavaClass(env, "co/viewfinder/NetworkManager")
        .RegisterNatives({
            JAVA_NATIVE(AuthViewfinder),
            JAVA_NATIVE(ChangePassword),
            JAVA_NATIVE(HandleError),
            JAVA_NATIVE(HandleDone),
            JAVA_NATIVE(HandleRedirect),
            JAVA_NATIVE(VerifyViewfinder),
         });
  }

 private:
  static void AuthViewfinder(JNIEnv* env, jclass, jlong j_net_mgr,
                             jstring j_endpoint, jstring j_identity, jstring j_password, jstring j_first,
                             jstring j_last, jstring j_name, jboolean j_error_if_linked, jobject j_callback) {
    NetworkManager* const net_manager = JavaToCppPointer<NetworkManager>(env, j_net_mgr);
    const string endpoint = JavaToCppString(env, j_endpoint);
    const string identity = JavaToCppString(env, j_identity);
    const string password = JavaToCppString(env, j_password);
    const string first = JavaToCppString(env, j_first);
    const string last = JavaToCppString(env, j_last);
    const string name = JavaToCppString(env, j_name);

    ScopedGlobalRef<jobject> java_callback(env, env->NewGlobalRef(j_callback));
    JavaStaticMethod<void (jobject, int, int, string)> callback(env, "co/viewfinder/NetworkManager", "authDone");

    dispatch_main([=] {
      net_manager->AuthViewfinder(endpoint, identity, password, first, last, name, j_error_if_linked,
                                  [java_callback, callback](int status, int error_id, string error_message) {
                                    callback.Invoke(java_callback, status, error_id, error_message);
                                  });
    });
  }

  static void ChangePassword(JNIEnv* env, jclass, jlong j_net_mgr,
                             jstring j_old_password, jstring j_new_password, jobject j_callback) {
    NetworkManager* const net_manager = JavaToCppPointer<NetworkManager>(env, j_net_mgr);
    const string old_password = JavaToCppString(env, j_old_password);
    const string new_password = JavaToCppString(env, j_new_password);

    ScopedGlobalRef<jobject> java_callback(env, env->NewGlobalRef(j_callback));
    JavaStaticMethod<void (jobject, int, int, string)> callback(env, "co/viewfinder/NetworkManager", "authDone");

    dispatch_main([=] {
      net_manager->ChangePassword(old_password, new_password,
                                  [java_callback, callback](int status, int error_id, string error_message) {
                                    callback.Invoke(java_callback.get(), status, error_id, error_message);
                                  });
    });
  }

  static void HandleError(JNIEnv* env, jclass, jlong j_request, jstring j_error) {
    NetworkRequestImpl* req = JavaToCppPointer<NetworkRequestImpl>(env, j_request);
    req->Error(JavaToCppString(env, j_error));
  }

  static void HandleDone(JNIEnv* env, jclass, jlong j_request, jstring j_data, jint j_code) {
    NetworkRequestImpl* req = JavaToCppPointer<NetworkRequestImpl>(env, j_request);
    req->Done(JavaToCppString(env, j_data), j_code);
  }

  static void HandleRedirect(JNIEnv* env, jclass, jlong j_request, jstring j_redirect_host) {
    NetworkRequestImpl* req = JavaToCppPointer<NetworkRequestImpl>(env, j_request);
    req->Redirect(JavaToCppString(env, j_redirect_host));
  }

  static void VerifyViewfinder(JNIEnv* env, jclass, jlong j_net_mgr,
                               jstring j_identity, jstring j_access_token, jboolean j_manual_entry,
                               jobject j_callback) {
    NetworkManager* const net_manager = JavaToCppPointer<NetworkManager>(env, j_net_mgr);
    const string identity = JavaToCppString(env, j_identity);
    const string access_token = JavaToCppString(env, j_access_token);

    ScopedGlobalRef<jobject> java_callback(env, env->NewGlobalRef(j_callback));
    JavaStaticMethod<void (jobject, int, int, string)> callback(env, "co/viewfinder/NetworkManager", "authDone");

    dispatch_main([=] {
      net_manager->VerifyViewfinder(identity, access_token, j_manual_entry,
                                  [java_callback, callback](int status, int error_id, string error_message) {
                                    callback.Invoke(java_callback.get(), status, error_id, error_message);
                                  });
    });
  }
};

class JavaPhotoSelection {
 public:
  static void Register(JNIEnv* env) {
    const JavaClass c(env, "co/viewfinder/PhotoSelection");
    photo_id_ = c.GetField<int64_t>("mPhotoId");
    episode_id_ = c.GetField<int64_t>("mEpisodeId");
  }

  static PhotoSelection ToCpp(JNIEnv* env, jobject obj) {
    return PhotoSelection(
        env->GetLongField(obj, photo_id_),
        env->GetLongField(obj, episode_id_));
  }

  static PhotoSelectionVec ToCpp(JNIEnv* env, jobjectArray array) {
    PhotoSelectionVec v(env->GetArrayLength(array));
    for (int i = 0; i < v.size(); ++i) {
      ScopedLocalRef<jobject> obj(env, env->GetObjectArrayElement(array, i));
      v[i] = ToCpp(env, obj);
    }
    return v;
  }

 private:
  static jfieldID photo_id_;
  static jfieldID episode_id_;
};

jfieldID JavaPhotoSelection::photo_id_;
jfieldID JavaPhotoSelection::episode_id_;

class JavaPhotoStorage {
 public:
  static void Register(JNIEnv* env) {
    JavaClass(env, "co/viewfinder/PhotoStorage")
        .RegisterNatives({
            JAVA_NATIVE(LowerBoundFullPath),
          });
  }

 private:
  static jstring LowerBoundFullPath(JNIEnv* env, jclass, jlong j_photo_storage, jlong j_photo_id, jint j_max_size) {
    PhotoStorage* const photo_storage = JavaToCppPointer<PhotoStorage>(env, j_photo_storage);
    // We don't expect to need the filename metadata for now, so don't return it.
    string filename_metadata;
    const string filename = photo_storage->LowerBound(j_photo_id, j_max_size, &filename_metadata);
    // We return the full path to the photo. We may need to adjust this if we care about just the filename.
    if (filename.empty()) {
      return NULL;
    }
    return CppToJavaString(env, photo_storage->PhotoPath(filename));
  }
};


class JavaPhotoTable : private JavaContentTable<PhotoTable> {
 public:
  static void Register(JNIEnv* env) {
    JavaClass(env, "co/viewfinder/PhotoTable")
        .RegisterNatives({
            JAVA_NATIVE(LoadHandle),
            JAVA_NATIVE(ReleaseHandle),
            JAVA_NATIVE(LoadProto),
            JAVA_NATIVE(FormatLocation),
          });
  }

 private:
  static jstring FormatLocation(
      JNIEnv* env, jclass, jlong j_ph, jboolean shorten) {
    PhotoHandle* const ph = GetHandlePointer(env, j_ph);
    return CppToJavaString(env, (*ph)->FormatLocation(shorten));
  }
};

class JavaViewpointTable : private JavaContentTable<ViewpointTable> {
 public:
  static void Register(JNIEnv* env) {
    JavaClass(env, "co/viewfinder/ViewpointTable")
        .RegisterNatives({
            JAVA_NATIVE(LoadHandle),
            JAVA_NATIVE(ReleaseHandle),
            JAVA_NATIVE(LoadProto),
            JAVA_NATIVE(DefaultTitle),
            JAVA_NATIVE(FormatTitle),
            JAVA_NATIVE(AddFollowers),
            JAVA_NATIVE(CommitShareNew),
            JAVA_NATIVE(ListViewpointsForPhotoId),
            JAVA_NATIVE(ListViewpointsForUserId),
            JAVA_NATIVE(PostComment),
            JAVA_NATIVE(RemoveFollowers),
            JAVA_NATIVE(RemoveViewpoint),
            JAVA_NATIVE(ShareNew),
            JAVA_NATIVE(ShareExisting),
            JAVA_NATIVE(Unshare),
            JAVA_NATIVE(UpdateCoverPhoto),
            JAVA_NATIVE(UpdateShareNew),
            JAVA_NATIVE(UpdateTitle),
            JAVA_NATIVE(UpdateViewedSeq),
            JAVA_NATIVE(UpdateAutosaveLabel),
            JAVA_NATIVE(UpdateHiddenLabel),
            JAVA_NATIVE(UpdateMutedLabel),
          });
  }

 private:
  static jstring DefaultTitle(
      JNIEnv* env, jclass, jlong j_vh) {
    ViewpointHandle* const vh = GetHandlePointer(env, j_vh);
    return CppToJavaString(env, (*vh)->DefaultTitle());
  }

  static jstring FormatTitle(
      JNIEnv* env, jclass, jlong j_vh,
      jboolean shorten, jboolean normalize_whitespace) {
    ViewpointHandle* const vh = GetHandlePointer(env, j_vh);
    return CppToJavaString(env, (*vh)->FormatTitle(shorten, normalize_whitespace));
  }

  static jboolean AddFollowers(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id,
      jobjectArray j_contacts) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    const vector<ContactMetadata> contacts = JavaToCppContactVec(env, j_contacts);
    return t->AddFollowers(viewpoint_id, contacts).get() != NULL;
  }

  static jboolean CommitShareNew(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id, jlong j_db) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    return t->CommitShareNew(viewpoint_id, *db);
  }

  static jlongArray ListViewpointsForPhotoId(
      JNIEnv* env, jclass, jlong table, jlong photo_id, jlong j_db) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    vector<int64_t> viewpoint_ids;
    t->ListViewpointsForPhotoId(photo_id, &viewpoint_ids, *db);
    if (viewpoint_ids.empty()) {
      return NULL;
    }
    return CppVectorToJavaLongArray(env, viewpoint_ids);
  }

  static jlongArray ListViewpointsForUserId(
      JNIEnv* env, jclass, jlong table, jlong user_id, jlong j_db) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    DBHandle* const db = JavaToCppPointer<DBHandle>(env, j_db);
    vector<int64_t> viewpoint_ids;
    t->ListViewpointsForUserId(user_id, &viewpoint_ids, *db);
    if (viewpoint_ids.empty()) {
      return NULL;
    }
    return CppVectorToJavaLongArray(env, viewpoint_ids);
  }

  static jboolean PostComment(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id,
      jstring j_message, jlong reply_to_photo_id) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    const string message = JavaToCppString(env, j_message);
    return t->PostComment(viewpoint_id, message, reply_to_photo_id).get() != NULL;
  }

  static jboolean RemoveFollowers(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id,
      jlongArray j_user_ids) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    const vector<int64_t> user_ids = JavaLongArrayToCppVector(env, j_user_ids);
    return t->RemoveFollowers(viewpoint_id, user_ids).get() != NULL;
  }

  static jboolean RemoveViewpoint(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    return t->Remove(viewpoint_id).get() != NULL;
  }

  static jlong ShareNew(
      JNIEnv* env, jclass, jlong table, jobjectArray j_photo_ids,
      jobjectArray j_contacts, jstring j_title, jboolean provisional) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    const PhotoSelectionVec photo_ids = JavaPhotoSelection::ToCpp(env, j_photo_ids);
    const vector<ContactMetadata> contacts = JavaToCppContactVec(env, j_contacts);
    const string title = JavaToCppString(env, j_title);
    ViewpointHandle vh = t->ShareNew(photo_ids, contacts, title, provisional);
    if (!vh.get()) {
      return 0;
    }
    return CppToJavaPointer(env, new ViewpointHandle(vh));
  }

  static jlong ShareExisting(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id,
      jobjectArray j_photo_ids, jboolean update_cover_photo) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    const PhotoSelectionVec photo_ids = JavaPhotoSelection::ToCpp(env, j_photo_ids);
    ViewpointHandle vh = t->ShareExisting(viewpoint_id, photo_ids, update_cover_photo);
    if (!vh.get()) {
      return 0;
    }
    return CppToJavaPointer(env, new ViewpointHandle(vh));
  }

  static jboolean Unshare(
      JNIEnv* env, jclass, jlong table,
      jlong viewpoint_id, jobjectArray j_photo_ids) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    const PhotoSelectionVec photo_ids = JavaPhotoSelection::ToCpp(env, j_photo_ids);
    return t->Unshare(viewpoint_id, photo_ids).get() != NULL;
  }

  static jboolean UpdateCoverPhoto(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id,
      jlong photo_id, jlong episode_id) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    return t->UpdateCoverPhoto(viewpoint_id, photo_id, episode_id).get() != NULL;
  }

  static jboolean UpdateShareNew(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id,
      jlong activity_id, jobjectArray j_photo_ids) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    const PhotoSelectionVec photo_ids = JavaPhotoSelection::ToCpp(env, j_photo_ids);
    return t->UpdateShareNew(viewpoint_id, activity_id, photo_ids);
  }

  static jboolean UpdateTitle(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id, jstring j_title) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    const string title = JavaToCppString(env, j_title);
    return t->UpdateTitle(viewpoint_id, title).get() != NULL;
  }

  static jboolean UpdateViewedSeq(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    return t->UpdateViewedSeq(viewpoint_id).get() != NULL;
  }

  static jboolean UpdateAutosaveLabel(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id, jboolean autosave) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    return t->UpdateAutosaveLabel(viewpoint_id, autosave).get() != NULL;
  }

  static jboolean UpdateHiddenLabel(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id, jboolean hidden) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    return t->UpdateHiddenLabel(viewpoint_id, hidden).get() != NULL;
  }

  static jboolean UpdateMutedLabel(
      JNIEnv* env, jclass, jlong table, jlong viewpoint_id, jboolean muted) {
    ViewpointTable* const t = JavaToCppPointer<ViewpointTable>(env, table);
    return t->UpdateMutedLabel(viewpoint_id, muted).get() != NULL;
  }

  static vector<ContactMetadata> JavaToCppContactVec(
      JNIEnv* env, jobjectArray contacts) {
    vector<ContactMetadata> v(env->GetArrayLength(contacts));
    for (int i = 0; i < v.size(); ++i) {
      ScopedLocalRef<jobject> obj(env, env->GetObjectArrayElement(contacts, i));
      CHECK(JavaToCppProto(env, (jbyteArray)obj.get(), &v[i]));
    }
    return v;
  }
};

}  // namespace

// Called at library load time. We can do static work such as registering
// native functions, and caching class and methods IDs. However, we don't have
// access to things like the application path.
jint JNI_OnLoad(JavaVM* jvm, void* reserved) {
  InitDispatch(jvm);

  JNIEnv* const env = GetJNIEnv(jvm);
  JavaAppState::Register(env);
  JavaActivityTable::Register(env);
  JavaContactManager::Register(env);
  JavaDayTable::Register(env);
  JavaDB::Register(env);
  JavaEpisodeTable::Register(env);
  JavaNetworkManager::Register(env);
  JavaPhotoSelection::Register(env);
  JavaPhotoStorage::Register(env);
  JavaPhotoTable::Register(env);
  JavaViewpointTable::Register(env);

  return JNI_VERSION_1_6;
}


NativeAppState::NativeAppState(
    const string& base_dir, int server_port, JNIEnv* env, jobject app_state)
    : AppState(base_dir, "", server_port, true),
      jvm_(GetJavaVM(env)),
      weak_app_state_(env->NewWeakGlobalRef(app_state)) {
  AddJavaCallback(env, app_state, "maintenanceProgress", maintenance_progress());
  AddJavaCallback(env, app_state, "maintenanceDone", maintenance_done());
  maintenance_done()->Add([this](bool reset) {
      day_table_->ResumeAllRefreshes();
      async()->dispatch_main([this]{
          // Signal an initial day table update in case there were no day table
          // refreshes to perform.
          day_table_->update()->Run();
        });
    });

  phone_number_country_code = JavaMethod<string ()>::Invoke(
      env, app_state, "getPhoneNumberCountryCode");
  device_uuid_ = JavaMethod<string ()>::Invoke(
      env, app_state, "getDeviceUUID");
  device_os_ = JavaStaticMethod<string ()>::Invoke(
      env, "co/viewfinder/Utils", "osAndroidRelease");
  device_model_ = JavaStaticMethod<string ()>::Invoke(
      env, "co/viewfinder/Utils", "deviceMakeModel");
  locale_country_ = JavaStaticMethod<string ()>::Invoke(
      env, "co/viewfinder/AppState", "getLocaleCountry");
  locale_language_ = JavaStaticMethod<string ()>::Invoke(
      env, "co/viewfinder/AppState", "getLocaleLanguage");
}

NativeAppState::~NativeAppState() {
}

AppState::InitAction NativeAppState::GetInitAction() {
  return INIT_NORMAL;
}

bool NativeAppState::Init(InitAction init_action) {
  if (init_action == AppState::INIT_RESET) {
    ClearAuthMetadata();
  }

  if (!AppState::Init(init_action)) {
    return false;
  }

  JNIEnv* const env = jni_env();

  set_server_host(JavaMethod<string ()>::Invoke(env, app_state(env), "getServerHost"));

  WallTimer timer;
  net_manager_.reset(new NetworkManagerAndroid(this));
  VLOG("init: network manager: %0.3f ms", timer.Milliseconds());
  timer.Restart();

  AddJavaCallback(env, app_state(env), "onDayTableUpdate", day_table()->update());
  return true;
}

void NativeAppState::RunMaintenance(InitAction init_action) {
  AppState::RunMaintenance(init_action);
}

void NativeAppState::SetupViewpointTransition(int64_t viewpoint_id, const DBHandle& updates) {
  // TODO(peter): Unimplemented.
}

bool NativeAppState::CloudStorageEnabled() {
  return cloud_storage();
}

void NativeAppState::DeleteAsset(const string& key) {
  // No assets on android. Nothing to do.
}

void NativeAppState::ProcessPhotoDuplicateQueue() {
  // No duplicate photo queue on android. Nothing to process.
}

void NativeAppState::LoadViewfinderImages(
    int64_t photo_id, const DBHandle& db,
    Callback<void (bool)> completion) {
  // TODO(peter): Unimplemented.
}

int NativeAppState::TimeZoneOffset(WallTime t) const {
  return time_zone_offset(t);
}

string NativeAppState::timezone() const {
  return time_zone_name();
}

DayTableEnv* NativeAppState::NewDayTableEnv() {
  return NewDayTableAndroidEnv(this);
}

bool NativeAppState::MaybeMigrate(ProgressUpdateBlock progress_update) {
  DBMigrationAndroid migration(this, progress_update);
  return migration.MaybeMigrate();
}
