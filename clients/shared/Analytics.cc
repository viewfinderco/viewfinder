// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <errno.h>
#import "Analytics.h"
#import "ContactMetadata.pb.h"
#import "FileUtils.h"
#import "IdentityManager.h"
#import "Logging.h"
#import "PathUtils.h"

// Shorthand for simple events with no parameters.
#define EVENT(meth_name, event_name) \
  void Analytics::meth_name() { \
    TrackEvent(event_name); \
  }

namespace {

void GetContactProperties(const ContactMetadata& contact, JsonDict* d) {
  d->insert("has_user_id", contact.has_user_id());
  d->insert("registered", contact.label_registered());
  d->insert("identities", contact.identities_size());

  int email = 0;
  int phone = 0;
  int facebook = 0;
  for (int i = 0; i < contact.identities_size(); i++) {
    const string& identity = contact.identities(i).identity();
    if (IdentityManager::IsEmailIdentity(identity)) {
      email++;
    } else if (IdentityManager::IsPhoneIdentity(identity)) {
      phone++;
    } else if (IdentityManager::IsFacebookIdentity(identity)) {
      facebook++;
    }
  }
  if (email) {
    d->insert("email_identities", email);
  }
  if (phone) {
    d->insert("phone_identities", phone);
  }
  if (facebook) {
    d->insert("facebook_identities", facebook);
  }
}

}  // namespace

Analytics::Analytics(bool enabled)
    : enabled_(enabled),
      fd_(-1),
      count_(0) {
}

Analytics::~Analytics() {
}

void Analytics::Launch(const string& reason) {
  TrackEvent("/app-state/launch",
             JsonDict("reason", reason));
}

void Analytics::EnterBackground() {
  TrackEvent("/app-state/background");
}

void Analytics::EnterForeground() {
  TrackEvent("/app-state/foreground");
}

void Analytics::RemoteNotification() {
  TrackEvent("/app-state/remote_notification");
}

void Analytics::SummaryDashboard() {
  TrackEvent("/ui/summary/dashboard");
}

void Analytics::SummaryLibrary() {
  TrackEvent("/ui/summary/events");
}

void Analytics::SummaryInbox() {
  TrackEvent("/ui/summary/inbox");
}

void Analytics::SummaryViewfinder(const string& page, WallTime duration) {
  TrackEvent("/ui/summary/viewfinder",
             JsonDict({
                 { "duration", duration },
                 { "page", page }
               }));
}

void Analytics::DashboardMyInfoButton() {
  TrackEvent("/ui/dashboard/my_info");
}

void Analytics::DashboardContactsButton() {
  TrackEvent("/ui/dashboard/contacts");
}

void Analytics::DashboardSettingsButton() {
  TrackEvent("/ui/dashboard/settings");
}

void Analytics::DashboardPhotoCount() {
  TrackEvent("/ui/dashboard/photo_count");
}

void Analytics::DashboardContactCount() {
  TrackEvent("/ui/dashboard/contact_count");
}

void Analytics::DashboardConversationCount() {
  TrackEvent("/ui/dashboard/conversation_count");
}

void Analytics::DashboardNoticeExpand(int type) {
  TrackEvent("/ui/dashboard/notice_expand", JsonDict("type", type));
}

void Analytics::DashboardNoticeClick(int type) {
  TrackEvent("/ui/dashboard/notice_click", JsonDict("type", type));
}

void Analytics::DashboardNoticeDismiss(int type) {
  TrackEvent("/ui/dashboard/notice_dismiss", JsonDict("type", type));
}

void Analytics::EventPage(WallTime timestamp) {
  TrackEvent("/ui/event", JsonDict("timestamp", int(timestamp)));
}

void Analytics::EventViewfinder(WallTime duration) {
  TrackEvent("/ui/event/viewfinder", JsonDict("duration", duration));
}

void Analytics::EventShareNew(int num_photos, int num_contacts) {
  TrackEvent("/ui/event/share_new",
             JsonDict({
                 { "photos", num_photos },
                 { "contacts", num_contacts }
               }));
}

void Analytics::EventShareExisting(int num_photos) {
  TrackEvent("/ui/event/share_existing",
             JsonDict("photos", num_photos));
}

void Analytics::EventAddFollowers(int num_contacts) {
  TrackEvent("/ui/event/add_followers",
             JsonDict("contacts", num_contacts));
}

void Analytics::EventRemovePhotos(int num_photos) {
  TrackEvent("/ui/event/delete", JsonDict("photos", num_photos));
}

void Analytics::EventExport(int num_photos) {
  TrackEvent("/ui/event/export", JsonDict("photos", num_photos));
}

void Analytics::EventExpand() {
  TrackEvent("/ui/event/expand");
}

void Analytics::EventSearchButton() {
  TrackEvent("/ui/event/search");
}

void Analytics::EventCameraButton() {
  TrackEvent("/ui/event/camera");
}

void Analytics::EventShareButton() {
  TrackEvent("/ui/event/share");
}

void Analytics::EventActionToggle() {
  TrackEvent("/ui/event/action");
}

void Analytics::InboxCardExpand() {
  TrackEvent("/ui/inbox/card_expand");
}

void Analytics::InboxSearchButton() {
  TrackEvent("/ui/inbox/search");
}

void Analytics::InboxCameraButton() {
  TrackEvent("/ui/inbox/camera");
}

void Analytics::InboxShareButton() {
  TrackEvent("/ui/inbox/share");
}

void Analytics::InboxActionToggle() {
  TrackEvent("/ui/inbox/action");
}

void Analytics::ConversationPage(int64_t viewpoint_id) {
  TrackEvent("/ui/conversation", JsonDict("viewpoint_id", viewpoint_id));
}

void Analytics::ConversationAutosaveOff() {
  TrackEvent("/ui/conversation/autosave_off");
}

void Analytics::ConversationAutosaveOn() {
  TrackEvent("/ui/conversation/autosave_on");
}

void Analytics::ConversationLeave() {
  TrackEvent("/ui/conversation/leave");
}

void Analytics::ConversationRemove() {
  TrackEvent("/ui/conversation/remove");
}

void Analytics::ConversationMute() {
  TrackEvent("/ui/conversation/mute");
}

void Analytics::ConversationUnmute() {
  TrackEvent("/ui/conversation/unmute");
}

void Analytics::ConversationViewfinder(WallTime duration) {
  TrackEvent("/ui/conversation/viewfinder", JsonDict("duration", duration));
}

void Analytics::ConversationRemovePhotos(int num_photos) {
  TrackEvent("/ui/conversation/remove_photos",
             JsonDict("photos", num_photos));
}

void Analytics::ConversationSavePhotos(int num_photos) {
  TrackEvent("/ui/conversation/save_photos",
             JsonDict("photos", num_photos));
}

void Analytics::ConversationShareNew(int num_photos, int num_contacts) {
  TrackEvent("/ui/conversation/share_new",
             JsonDict({
                 { "photos", num_photos },
                 { "contacts", num_contacts }
               }));
}

void Analytics::ConversationShareExisting(int num_photos) {
  TrackEvent("/ui/conversation/share_existing",
             JsonDict("photos", num_photos));
}

void Analytics::ConversationAddFollowers(int num_contacts) {
  TrackEvent("/ui/conversation/add_followers",
             JsonDict("contacts", num_contacts));
}

void Analytics::ConversationRemoveFollowers(int num_followers) {
  TrackEvent("/ui/conversation/remove_followers",
             JsonDict("followers", num_followers));
}

void Analytics::ConversationUnshare(int num_photos) {
  TrackEvent("/ui/conversation/unshare", JsonDict("photos", num_photos));
}

void Analytics::ConversationExport(int num_photos) {
  TrackEvent("/ui/conversation/export", JsonDict("photos", num_photos));
}

void Analytics::ConversationCameraButton() {
  TrackEvent("/ui/conversation/camera");
}

void Analytics::ConversationAddPhotosButton() {
  TrackEvent("/ui/conversation/add_photos");
}

void Analytics::ConversationAddPeopleButton() {
  TrackEvent("/ui/conversation/add_people");
}

void Analytics::ConversationEditToggle() {
  TrackEvent("/ui/conversation/edit");
}

void Analytics::ConversationSelectFollowerGroup(int size) {
  TrackEvent("/ui/conversation/select_follower_group", JsonDict("size", size));
}

void Analytics::ConversationSelectFollower(const ContactMetadata& contact) {
  JsonDict props;
  GetContactProperties(contact, &props);
  TrackEvent("/ui/conversation/select_follower", props);
}

void Analytics::ConversationSelectFollowerIdentity(const ContactMetadata& contact, const string& identity) {
  JsonDict props;
  GetContactProperties(contact, &props);
  props.insert("selected_identity", IdentityManager::IdentityType(identity));
  TrackEvent("/ui/conversation/select_follower_identity", props);
}

void Analytics::ConversationUpdateCoverPhoto() {
  TrackEvent("/ui/conversation/update_cover_photo");
}

void Analytics::ConversationUpdateTitle() {
  TrackEvent("/ui/conversation/update_title");
}

EVENT(OnboardingStart, "/ui/onboarding/start");
EVENT(OnboardingSignupCard, "/ui/onboarding/signup_card");
EVENT(OnboardingLoginCard, "/ui/onboarding/login_card");
EVENT(OnboardingResetPasswordCard, "/ui/onboarding/reset_password_card");
EVENT(OnboardingLinkCard, "/ui/onboarding/link_card");
EVENT(OnboardingMergeCard, "/ui/onboarding/merge_card");
EVENT(OnboardingSetPasswordCard, "/ui/onboarding/set_password_card");
EVENT(OnboardingChangePasswordCard, "/ui/onboarding/change_password_card");
EVENT(OnboardingConfirmCard, "/ui/onboarding/confirm_card");
EVENT(OnboardingResetDeviceIdCard, "/ui/onboarding/reset_device_id_card");

EVENT(OnboardingError, "/ui/onboarding/error");
EVENT(OnboardingNetworkError, "/ui/onboarding/network_error");
EVENT(OnboardingCancel, "/ui/onboarding/cancel");
EVENT(OnboardingChangePasswordComplete, "/ui/onboarding/change_password_complete");
EVENT(OnboardingResendCode, "/ui/onboarding/resend_code");
EVENT(OnboardingConfirmEmail, "/ui/onboarding/confirm_email");
EVENT(OnboardingConfirmPhone, "/ui/onboarding/confirm_phone");
EVENT(OnboardingConfirmComplete, "/ui/onboarding/confirm_complete");
EVENT(OnboardingConfirmEmailComplete, "/ui/onboarding/confirm_email_complete");
EVENT(OnboardingConfirmPhoneComplete, "/ui/onboarding/confirm_phone_complete");

EVENT(OnboardingAccountSetupCard, "/ui/onboarding/account_setup_card");
EVENT(OnboardingImportContacts, "/ui/onboarding/import_contacts");
EVENT(OnboardingSkipImportContacts, "/ui/onboarding/skip_import_contacts");
EVENT(OnboardingComplete, "/ui/onboarding/complete");

void Analytics::PhotoExport() {
  TrackEvent("/ui/photo/export", JsonDict("photos", 1));
}

void Analytics::PhotoPage(int photo_id) {
  TrackEvent("/ui/photo", JsonDict("photo_id", photo_id));
}

void Analytics::PhotoShareNew(int num_contacts) {
  TrackEvent("/ui/photo/share_new",
             JsonDict({
                 { "photos", 1 },
                 { "contacts", num_contacts }
               }));
}

void Analytics::PhotoShareExisting() {
  TrackEvent("/ui/photo/share_existing",
             JsonDict("photos", 1));
}

void Analytics::PhotoAddFollowers(int num_contacts) {
  TrackEvent("/ui/photo/add_followers",
             JsonDict("contacts", num_contacts));
}

void Analytics::PhotoRemove() {
  TrackEvent("/ui/photo/delete", JsonDict("photos", 1));
}

void Analytics::PhotoSave() {
  TrackEvent("/ui/photo/save", JsonDict("photos", 1));
}

void Analytics::PhotoUnshare() {
  TrackEvent("/ui/photo/unshare", JsonDict("photos", 1));
}

void Analytics::PhotoToolbarToggle(bool on) {
  TrackEvent("/ui/photo/toolbar_toggle", JsonDict("state", on));
}

void Analytics::PhotoZoom() {
  TrackEvent("/ui/photo/zoom");
}

void Analytics::PhotoSwipeDismiss() {
  TrackEvent("/ui/photo/swipe_dismiss");
}

void Analytics::CameraPage(const string& type) {
  TrackEvent("/ui/camera",
             JsonDict("type", ToLowercase(type)));
}

void Analytics::CameraTakePicture() {
  TrackEvent("/ui/camera/take-picture");
}

void Analytics::CameraFlashOn() {
  TrackEvent("/ui/camera/flash-on");
}

void Analytics::CameraFlashOff() {
  TrackEvent("/ui/camera/flash-off");
}

void Analytics::CameraFlashAuto() {
  TrackEvent("/ui/camera/flash-auto");
}

void Analytics::ContactsPage() {
  TrackEvent("/ui/contacts");
}

void Analytics::ContactsSourceToggle(bool all) {
  TrackEvent("/ui/contacts/source_toggle", JsonDict("all", all));
}

void Analytics::ContactsSearch() {
  TrackEvent("/ui/contacts/search");
}

void Analytics::AddContactsPage() {
  TrackEvent("/ui/add_contacts");
}

void Analytics::AddContactsManualTyping() {
  TrackEvent("/ui/add_contacts/manual/typing");
}

void Analytics::AddContactsManualComplete() {
  TrackEvent("/ui/add_contacts/manual/complete");
}

void Analytics::ContactsFetch(const string& service) {
  TrackEvent(Format("/ui/contacts/fetch/%s", service));
}

void Analytics::ContactsFetchComplete(const string& service) {
  TrackEvent(Format("/ui/contacts/fetch_complete/%s", service));
}

void Analytics::ContactsFetchError(const string& service, const string& reason) {
  TrackEvent(Format("/ui/contacts/fetch_complete/%s", service), JsonDict("reason", reason));
}

void Analytics::ContactsRefresh(const string& service) {
  TrackEvent(Format("/ui/contacts/refresh/%s", service));
}

void Analytics::ContactsRemove(const string& service) {
  TrackEvent(Format("/ui/contacts/remove/%s", service));
}

void Analytics::AddContactsLinkPhoneStart() {
  TrackEvent("/ui/add_contacts/link_phone/start");
}

void Analytics::AddContactsLinkPhoneComplete() {
  TrackEvent("/ui/add_contacts/link_phone/start");
}

void Analytics::ContactInfoPage(bool me) {
  TrackEvent("/ui/contact_info", JsonDict("me", me));
}

void Analytics::ContactInfoShowConversations() {
  TrackEvent("/ui/contact_info/show_conversations");
}

void Analytics::ContactInfoStartConversation() {
  TrackEvent("/ui/contact_info/start_conversation");
}

void Analytics::ContactInfoAddIdentity() {
  TrackEvent("/ui/contact_info/add_identity");
}

void Analytics::ContactInfoChangePassword() {
  TrackEvent("/ui/contact_info/change_password");
}

void Analytics::SettingsCloudStorage() {
  TrackEvent("/ui/settings/cloud_storage");
}

void Analytics::SettingsLogin() {
  TrackEvent("/ui/settings/login");
}

void Analytics::SettingsPage() {
  TrackEvent("/ui/settings");
}

void Analytics::SettingsPrivacyPolicy() {
  TrackEvent("/ui/settings/privacy_policy");
}

void Analytics::SettingsRegister() {
  TrackEvent("/ui/settings/register");
}

void Analytics::SettingsTermsOfService() {
  TrackEvent("/ui/settings/terms_of_service");
}

void Analytics::SettingsUnlink() {
  TrackEvent("/ui/settings/unlink");
}

void Analytics::SendFeedback(int result) {
  TrackEvent("/ui/send_feedback", JsonDict("result", result));
}

void Analytics::Network(bool up, bool wifi) {
  TrackEvent("/network/state",
             JsonDict({
                 { "up", up },
                 { "wifi", wifi }
               }));
}

void Analytics::NetworkAddFollowers(int status, WallTime elapsed) {
  TrackEvent("/network/add_followers",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkAuthViewfinder(int status, WallTime elapsed) {
  TrackEvent("/network/auth_viewfinder",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkBenchmarkDownload(int status, bool up, bool wifi, const string& url,
                                         int64_t bytes, WallTime elapsed) {
  TrackEvent("/network/benchmark_download",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed },
                 { "up", up },
                 { "wifi", wifi },
                 { "url", url },
                 { "bytes", bytes }
               }));
}

void Analytics::NetworkDownloadPhoto(int status, int64_t bytes, const string& type, WallTime elapsed) {
  TrackEvent("/network/download_photo",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed },
                 { "bytes", bytes },
                 { "type", type }
               }));
}

void Analytics::NetworkFetchFacebookContacts(int status, WallTime elapsed) {
  TrackEvent("/network/fetch_facebook_contacts",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkFetchGoogleContacts(int status, WallTime elapsed) {
  TrackEvent("/network/fetch_google_contacts",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkLinkIdentity(int status, WallTime elapsed) {
  TrackEvent("/network/link_identity",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkMergeAccounts(int status, WallTime elapsed) {
  TrackEvent("/network/merge_accounts",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkPing(int status, WallTime elapsed) {
  TrackEvent("/network/ping",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkPostComment(int status, WallTime elapsed) {
  TrackEvent("/network/post_comment",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkQueryContacts(int status, WallTime elapsed) {
  TrackEvent("/network/query_contacts",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkQueryEpisodes(int status, WallTime elapsed) {
  TrackEvent("/network/query_episodes",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkQueryFollowed(int status, WallTime elapsed) {
  TrackEvent("/network/query_followed",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkQueryNotifications(int status, WallTime elapsed) {
  TrackEvent("/network/query_notifications",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkQueryUsers(int status, WallTime elapsed) {
  TrackEvent("/network/query_users",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkQueryViewpoints(int status, WallTime elapsed) {
  TrackEvent("/network/query_viewpoints",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkRecordSubscription(int status, WallTime elapsed) {
  TrackEvent("/network/record_subscription",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkRemoveContacts(int status, WallTime elapsed) {
  TrackEvent("/network/remove_contacts",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkRemoveFollowers(int status, WallTime elapsed) {
  TrackEvent("/network/remove_followers",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkRemovePhotos(int status, WallTime elapsed) {
  TrackEvent("/network/remove_photos",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkResolveContacts(int status, WallTime elapsed) {
  TrackEvent("/network/resolve_contacts",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkSavePhotos(int status, WallTime elapsed) {
  TrackEvent("/network/save_photos",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkShare(int status, WallTime elapsed) {
  TrackEvent("/network/share",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkUnshare(int status, WallTime elapsed) {
  TrackEvent("/network/unshare",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkUpdateDevice(int status, WallTime elapsed) {
  TrackEvent("/network/update_device",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkUpdateFriend(int status, WallTime elapsed) {
  TrackEvent("/network/update_friend",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkUpdateUser(int status, WallTime elapsed) {
  TrackEvent("/network/update_user",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkUpdateUserPhoto(int status, WallTime elapsed) {
  TrackEvent("/network/update_user_photo",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkUpdateViewpoint(int status, WallTime elapsed) {
  TrackEvent("/network/update_viewpoint",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkUploadContacts(int status, WallTime elapsed) {
  TrackEvent("/network/upload_contacts",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkUploadEpisode(int status, WallTime elapsed) {
  TrackEvent("/network/upload_episode",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed }
               }));
}

void Analytics::NetworkUploadPhoto(int status, int64_t bytes, const string& type, WallTime elapsed) {
  TrackEvent("/network/upload_photo",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed },
                 { "bytes", bytes },
                 { "type", type }
               }));
}

void Analytics::NetworkVerifyViewfinder(int status, WallTime elapsed, bool manual_entry) {
  TrackEvent("/network/verify_viewfinder",
             JsonDict({
                 { "status", status },
                 { "elapsed", elapsed },
                 { "manual_entry", manual_entry }
               }));
}

void Analytics::AssetsScan(bool full_scan, int num_assets,
                           int num_scanned, WallTime elapsed) {
  TrackEvent("/assets/scan",
             JsonDict({
                 { "type", full_scan ? "full" : "fast" },
                 { "num_assets", num_assets },
                 { "num_scanned", num_scanned },
                 { "elapsed", elapsed }
               }));
}

void Analytics::LocalUsage(int64_t bytes, int thumbnail_files,
                           int medium_files, int full_files,
                           int original_files) {
  TrackEvent("/storage/usage",
             JsonDict({
                 { "bytes", bytes },
                 { "thumbnail_files", thumbnail_files },
                 { "medium_files", medium_files },
                 { "full_files", full_files },
                 { "original_files", original_files }
               }));
}

void Analytics::TrackEvent(const string& name, JsonDict properties) {
  if (!enabled_) {
    return;
  }

  const string e = FormatEntry(name, properties);

  MutexLock l(&mu_);

  if (fd_ < 0) {
    const string log_filename = NewLogFilename(".analytics");
    const string log_path = JoinPath(LoggingDir(), log_filename);
    fd_ = FileCreate(log_path);
    if (fd_ < 0) {
      LOG("init: unable to open: %s: %d (%s)",
          log_path, errno, strerror(errno));
      return;
    }
    WriteStringToFD(fd_, "[");
  }

  if (count_ > 0) {
    WriteStringToFD(fd_, ",\n");
  }

  WriteStringToFD(fd_, e);
  ++count_;
}

string Analytics::FormatEntry(const string& name, JsonDict properties) {
  properties.insert("name", name);
  properties.insert("timestamp", WallTime_Now());
  string s = properties.FormatCompact();
  if (Slice(s).ends_with("\n")) {
    // Strip the trailing newline added by FormatCompact().
    s.resize(s.size() - 1);
  }
  return s;
}

// local variables:
// mode: c++
// end:
