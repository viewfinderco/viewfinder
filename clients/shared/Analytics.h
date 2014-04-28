// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "JsonUtils.h"
#import "Mutex.h"
#import "WallTime.h"

class ContactMetadata;

class Analytics {
 public:
  explicit Analytics(bool enabled);
  ~Analytics();

  ////
  ////  TODO(peter): get rid of these boilerplate methods and call
  ////  TrackEvent directly instead.
  ////

  // App state.
  void Launch(const string& reason);
  void EnterBackground();
  void EnterForeground();
  void RemoteNotification();

  // Summary page.
  void SummaryDashboard();
  void SummaryLibrary();
  void SummaryInbox();
  void SummaryViewfinder(const string& page, WallTime duration);

  // Dashboard page.
  void DashboardMyInfoButton();
  void DashboardContactsButton();
  void DashboardSettingsButton();
  void DashboardPhotoCount();
  void DashboardContactCount();
  void DashboardConversationCount();
  void DashboardNoticeExpand(int type);
  void DashboardNoticeClick(int type);
  void DashboardNoticeDismiss(int type);

  // Event page.
  void EventPage(WallTime timestamp);
  void EventViewfinder(WallTime duration);
  void EventShareNew(int num_photos, int num_contacts);
  void EventShareExisting(int num_photos);
  void EventAddFollowers(int num_contacts);
  void EventRemovePhotos(int num_photos);
  void EventExport(int num_photos);
  void EventExpand();
  void EventSearchButton();
  void EventCameraButton();
  void EventShareButton();
  void EventActionToggle();

  // Inbox page.
  void InboxCardExpand();
  void InboxSearchButton();
  void InboxCameraButton();
  void InboxShareButton();
  void InboxActionToggle();

  // Conversation page.
  void ConversationPage(int64_t viewpoint_id);
  void ConversationAutosaveOff();
  void ConversationAutosaveOn();
  void ConversationLeave();
  void ConversationRemove();
  void ConversationMute();
  void ConversationUnmute();
  void ConversationViewfinder(WallTime duration);
  void ConversationRemovePhotos(int num_photos);
  void ConversationSavePhotos(int num_photos);
  void ConversationShareNew(int num_photos, int num_contacts);
  void ConversationShareExisting(int num_photos);
  void ConversationAddFollowers(int num_contacts);
  void ConversationRemoveFollowers(int num_followers);
  void ConversationUnshare(int num_photos);
  void ConversationExport(int num_photos);
  void ConversationCameraButton();
  void ConversationAddPhotosButton();
  void ConversationAddPeopleButton();
  void ConversationEditToggle();
  void ConversationSelectFollowerGroup(int size);
  void ConversationSelectFollower(const ContactMetadata& contact);
  void ConversationSelectFollowerIdentity(const ContactMetadata& contact, const string& identity);
  void ConversationUpdateCoverPhoto();
  void ConversationUpdateTitle();

  // Onboarding pages.
  void OnboardingStart();
  void OnboardingSignupCard();
  void OnboardingLoginCard();
  void OnboardingResetPasswordCard();
  void OnboardingLinkCard();
  void OnboardingMergeCard();
  void OnboardingSetPasswordCard();
  void OnboardingChangePasswordCard();
  void OnboardingConfirmCard();
  void OnboardingResetDeviceIdCard();

  void OnboardingError();
  void OnboardingNetworkError();
  void OnboardingCancel();
  void OnboardingChangePasswordComplete();
  void OnboardingResendCode();
  void OnboardingConfirmEmail();
  void OnboardingConfirmPhone();
  void OnboardingConfirmComplete();
  void OnboardingConfirmEmailComplete();
  void OnboardingConfirmPhoneComplete();

  void OnboardingAccountSetupCard();
  void OnboardingImportContacts();
  void OnboardingSkipImportContacts();
  void OnboardingComplete();

  // Photo page.
  void PhotoExport();
  void PhotoPage(int photo_id);
  void PhotoShareNew(int num_contacts);
  void PhotoShareExisting();
  void PhotoAddFollowers(int num_contacts);
  void PhotoRemove();
  void PhotoSave();
  void PhotoUnshare();
  void PhotoToolbarToggle(bool on);
  void PhotoZoom();
  void PhotoSwipeDismiss();

  // Camera page.
  void CameraPage(const string& type);
  void CameraTakePicture();
  void CameraFlashOn();
  void CameraFlashOff();
  void CameraFlashAuto();

  // Contacts page.
  void ContactsPage();
  void ContactsSourceToggle(bool all);
  void ContactsSearch();

  // Add contacts page.
  void AddContactsPage();
  void AddContactsManualTyping();
  void AddContactsManualComplete();
  void ContactsFetch(const string& service);
  void ContactsFetchComplete(const string& service);
  void ContactsFetchError(const string& service, const string& reason);
  void ContactsRefresh(const string& service);
  void ContactsRemove(const string& service);
  void AddContactsLinkPhoneStart();
  void AddContactsLinkPhoneComplete();

  // Contact info page.
  void ContactInfoPage(bool me);
  void ContactInfoShowConversations();
  void ContactInfoStartConversation();
  void ContactInfoAddIdentity();
  void ContactInfoChangePassword();

  // Settings page.
  void SettingsCloudStorage();
  void SettingsLogin();
  void SettingsPage();
  void SettingsPrivacyPolicy();
  void SettingsRegister();
  void SettingsTermsOfService();
  void SettingsUnlink();

  // Send feedback.
  void SendFeedback(int result);

  // Network.
  void Network(bool up, bool wifi);
  void NetworkAddFollowers(int status, WallTime elapsed);
  void NetworkAuthViewfinder(int status, WallTime elapsed);
  void NetworkBenchmarkDownload(int status, bool up, bool wifi, const string& url, int64_t bytes, WallTime elapsed);
  void NetworkDownloadPhoto(int status, int64_t bytes, const string& type, WallTime elapsed);
  void NetworkFetchFacebookContacts(int status, WallTime elapsed);
  void NetworkFetchGoogleContacts(int status, WallTime elapsed);
  void NetworkLinkIdentity(int status, WallTime elapsed);
  void NetworkMergeAccounts(int status, WallTime elapsed);
  void NetworkPing(int status, WallTime elapsed);
  void NetworkPostComment(int status, WallTime elapsed);
  void NetworkQueryContacts(int status, WallTime elapsed);
  void NetworkQueryEpisodes(int status, WallTime elapsed);
  void NetworkQueryFollowed(int status, WallTime elapsed);
  void NetworkQueryNotifications(int status, WallTime elapsed);
  void NetworkQueryUsers(int status, WallTime elapsed);
  void NetworkQueryViewpoints(int status, WallTime elapsed);
  void NetworkRecordSubscription(int status, WallTime elapsed);
  void NetworkRemoveContacts(int status, WallTime elapsed);
  void NetworkRemoveFollowers(int status, WallTime elapsed);
  void NetworkRemovePhotos(int status, WallTime elapsed);
  void NetworkResolveContacts(int status, WallTime elapsed);
  void NetworkSavePhotos(int status, WallTime elapsed);
  void NetworkShare(int status, WallTime elapsed);
  void NetworkUnshare(int status, WallTime elapsed);
  void NetworkUpdateDevice(int status, WallTime elapsed);
  void NetworkUpdateFriend(int status, WallTime elapsed);
  void NetworkUpdateUser(int status, WallTime elapsed);
  void NetworkUpdateUserPhoto(int status, WallTime elapsed);
  void NetworkUpdateViewpoint(int status, WallTime elapsed);
  void NetworkUploadContacts(int status, WallTime elapsed);
  void NetworkUploadEpisode(int status, WallTime elapsed);
  void NetworkUploadPhoto(int status, int64_t bytes, const string& type, WallTime elapsed);
  void NetworkVerifyViewfinder(int status, WallTime elapsed, bool manual_entry);

  // Assets.
  void AssetsScan(bool full_scan, int num_assets,
                  int num_scanned, WallTime elapsed);

  // Local storage.
  void LocalUsage(int64_t bytes, int thumbnail_files,
                  int medium_files, int full_files,
                  int original_files);

 private:
  void TrackEvent(const string& name, JsonDict properties = JsonDict());
  string FormatEntry(const string& name, JsonDict properties);

 private:
  const bool enabled_;
  Mutex mu_;
  int fd_;
  int count_;
};
