// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_CONTACT_MANAGER_H
#define VIEWFINDER_CONTACT_MANAGER_H

#import <re2/re2.h>
#import "Callback.h"
#import "DB.h"
#import "FullTextIndex.h"
#import "ScopedPtr.h"
#import "Server.pb.h"
#import "Utils.h"

class Analytics;
class AppState;
class ContactMetadata;
class ContactSelection;
class FullTextQuery;
class NotificationManager;
class QueryContactsResponse;
class QueryNotificationsResponse;
class QueryUsersResponse;
class UserSelection;

class ContactManager {
  typedef Callback<void ()> FetchCallback;
  typedef vector<FetchCallback> FetchContactsList;
  // Multimaps apparently do strange things with blocks, so use a map of vectors instead.
  typedef std::unordered_map<string, FetchContactsList> FetchContactsMap;

 public:
  typedef vector<ContactMetadata> ContactVec;

  enum {
    SORT_BY_RANK = 1 << 0,
    SORT_BY_NAME = 1 << 1,
    ALLOW_EMPTY_SEARCH = 1 << 2,
    VIEWFINDER_USERS_ONLY = 1 << 3,
    SKIP_FACEBOOK_CONTACTS = 1 << 4,
    PREFIX_MATCH = 1 << 5,
  };

  // Reachability enum.
  enum {
    REACHABLE_BY_EMAIL = 1 << 0,
    REACHABLE_BY_SMS = 1 << 1,
  };

  struct AutocompleteUserInfo {
    string name;
    int64_t user_id;
    int score;
  };

  static const string kContactSourceGmail;
  static const string kContactSourceFacebook;
  static const string kContactSourceIOSAddressBook;
  static const string kContactSourceManual;

  static const string kContactIndexName;
  static const string kUserIndexName;

  // Represents the state of a pending upload contacts operation
  struct UploadContacts {
    OpHeaders headers;
    vector<ContactMetadata> contacts;
  };

  struct RemoveContacts {
    OpHeaders headers;
    vector<string> server_contact_ids;
  };

  // Internal search types.
  struct ContactMatch {
    ContactMatch()
        : sort_key_initialized(false) {
    }
    ContactMetadata metadata;
    string sort_key;
    bool sort_key_initialized;
  };

  // A map from user id to ContactMatch.
  typedef std::unordered_map<int64_t, ContactMatch> UserMatchMap;

  // A map from contact id to ContactMatch.
  typedef std::unordered_map<string, ContactMatch> ContactMatchMap;

 public:
  ContactManager(AppState* state);
  ~ContactManager();

  void ProcessAddressBookImport(
      const vector<ContactMetadata>& contacts,
      const DBHandle& updates, FetchCallback done);
  void ProcessMergeAccounts(
      const string& op_id, const string& completion_db_key,
      const DBHandle& updates);
  void ProcessQueryContacts(
      const QueryContactsResponse& r,
      const ContactSelection& cs, const DBHandle& updates);
  void ProcessQueryNotifications(
      const QueryNotificationsResponse& r, const DBHandle& updates);
  void ProcessQueryUsers(
      const QueryUsersResponse& r,
      const vector<int64_t>& user_ids, const DBHandle& updates);
  void ProcessResolveContact(const string& identity, const ContactMetadata* metadata);
  void Search(const string& query, ContactVec* contacts,
              ScopedPtr<RE2>* filter_re,
              int search_options = SORT_BY_RANK) const;
  string FirstName(int64_t user_id, bool allow_nickname = true);
  string FirstName(const ContactMetadata& c, bool allow_nickname = true);
  string FullName(int64_t user_id, bool allow_nickname = true);
  string FullName(const ContactMetadata& c, bool allow_nickname = true);
  vector<int64_t> ViewfinderContacts();
  void Reset();

  // Check to see if we already have info for the specified user and queue for
  // retrieval if we don't.
  void MaybeQueueUser(int64_t user_id, const DBHandle& updates);

  // Unconditionally queue the specified user for retrieval.
  void QueueUser(int64_t user_id, const DBHandle& updates);

  // Gets the list of user-ids that need to be queried.
  void ListQueryUsers(vector<int64_t>* user_ids, int limit);

  // Updates the list of queued contacts
  void MaybeQueueUploadContacts();

  // Gets the list of contacts that need to be uploaded.
  const UploadContacts* queued_upload_contacts() { return queued_upload_contacts_.get(); }

  // Marks the queued contacts as uploaded.
  void CommitQueuedUploadContacts(const UploadContactsResponse& resp, bool success);

  void MaybeQueueRemoveContacts();
  const RemoveContacts* queued_remove_contacts() { return queued_remove_contacts_.get(); }
  void CommitQueuedRemoveContacts(bool success);

  // Validates queried contacts.
  void Validate(const ContactSelection& s, const DBHandle& updates);

  // Invalidates contacts to query.
  void Invalidate(const ContactSelection& s, const DBHandle& updates);

  // Clears existing invalidation so that all contacts are re-queried.
  void InvalidateAll(const DBHandle& updates);

  // Invalidates user to query.
  void InvalidateUser(const UserSelection& us, const DBHandle& updates);

  // Gets the current contact invalidation. Returns true if an
  // invalidation is available; false if none.
  bool GetInvalidation(ContactSelection* cs);

  // Lookup user by user id; uses in-memory user cache.
  bool LookupUser(int64_t user_id, ContactMetadata* c) const;
  bool LookupUser(int64_t user_id, ContactMetadata* c, const DBHandle& db) const;
  // Lookup user by identity; NOT CACHED.
  bool LookupUserByIdentity(const string& identity, ContactMetadata* c) const;
  bool LookupUserByIdentity(const string& identity, ContactMetadata* c, const DBHandle& db) const;

  // Attempt to resolve the given identity to a user.  This method is asynchronous; callers
  // should be listening on contact_resolved().
  void ResolveContact(const string& identity);

  // Returns true if the contact is for a registered (as opposed to
  // prospective) user.
  static bool IsRegistered(const ContactMetadata& c);

  // Returns true if the contact is for a prospective (as opposed to
  // registered) user.
  static bool IsProspective(const ContactMetadata& c);

  // Returns true if the given string looks like a valid and potentially complete email.
  static bool IsResolvableEmail(const Slice& email);

  // Returns true if any identity in the specified contact metadata is a valid
  // email/phone identity. If not NULL, sets "*identity" to the first
  // email/phone identity if one is found.
  static bool GetEmailIdentity(const ContactMetadata& c, string* identity);
  static bool GetPhoneIdentity(const ContactMetadata& c, string* identity);

  // Returns a name for the specified contact metadata, formatted
  // according to the "shorten" parameter. The preference is to use
  // name or first_name if available and revert to email or phone
  // number as necessary.  Specify "always_include_full" to format
  // full name as a parenthetical suffix in the event that there is a
  // nickname (e.g. "<nickname> (<full name>)").
  static string FormatName(const ContactMetadata& c, bool shorten,
                           bool always_include_full = true);

  // Fetch the contacts for the specified auth service. Returns true if we
  // queued an operation to refresh contacts for the specified service. Returns
  // false if the network is down or the service isn't valid.
  bool FetchFacebookContacts(const string& access_token, FetchCallback done);
  bool FetchGoogleContacts(const string& refresh_token, FetchCallback done);

  // Clear any outstanding fetch contacts operations.
  void ClearFetchContacts();

  // Sets the current user's name and queues an update to the network.
  // Returns false if the given name is invalid.
  bool SetMyName(const string& first, const string& last, const string& name);

  // Construct full name based on first and last. Some locales reverse the
  // combination of first/last names.
  static string ConstructFullName(const string& first, const string& last);

  // Sets the nickname for the specified user and queues an update to the
  // network.
  void SetFriendNickname(int64_t user_id, const string& nickname);

  void QueueUpdateSelf();
  void CommitQueuedUpdateSelf();
  bool queued_update_self() const { return queued_update_self_; }

  void QueueUpdateFriend(int64_t user_id);
  void CommitQueuedUpdateFriend();
  int64_t queued_update_friend() const { return queued_update_friend_; }

  AppState* state() const { return state_; }

  // contact_changed callbacks are run on an unspecified thread
  // whenever a contact is updated.
  CallbackSet* contact_changed() { return &contact_changed_; }

  // contact_resolved callbacks are run on the main thread when a ResolveContact finishes.
  // The metadata will be NULL if the contact could not be found.
  CallbackSet2<const string&, const ContactMetadata*>* contact_resolved() { return &contact_resolved_; }

  // Returns the count of the total number of contacts.
  int count() const { return count_; }

  // Returns the count of viewfinder contacts.
  int viewfinder_count() const { return viewfinder_count_; }

  // Returns the number of contacts from the given source.
  int CountContactsForSource(const string& source);

  // Returns the number of Viewfinder contacts (with user_id set) from given source.
  int CountViewfinderContactsForSource(const string& source);

  // Returns the last successful import of this source, or 0 if none is found.
  WallTime GetLastImportTimeForSource(const string& source);
  void SetLastImportTimeForSource(const string& source, WallTime timestamp);

  // Extracts and sets the value of *email/*phone using contact metadata
  // "c". If the email/phone is present, it's returned immediately; otherwise,
  // if the email/phone can be extracted from the identity, that's
  // returned. Returns true on success; false otherwise.
  static bool EmailForContact(const ContactMetadata& c, string* email);
  static bool PhoneForContact(const ContactMetadata& c, string* phone);

  // Returns the various means by which the user is reachable outside of
  // the Viewfinder platform. The return value is a bitwise-or of the
  // reachability enums (e.g. REACHABLE_BY_SMS, REACHABLE_BY_EMAIL).
  static int Reachability(const ContactMetadata& c);

  // Parses the first and last name from "full_name". The values, if
  // they can be parsed, are stored in *first and *last respectively.
  // Returns true if names can be parsed; false otherwise.
  static bool ParseFullName(const string& full_name, string* first, string* last);


  // Comparison function for determining if name "a" is less than name
  // "b". Performs a case-insensitive comparison and sorts letters before
  // non-letters so that numbers sort after letters.
  static bool NameLessThan(const Slice& a, const Slice& b);

  // Comparison function for determining if contact "a" is less than name "b"
  // using a name comparison.
  static bool ContactNameLessThan(
      const ContactMetadata& a, const ContactMetadata& b);

  // Rewrites the full-text index for this contact.  Rewrites the indexed_names
  // field of this contact, so the metadata must be persisted to the database
  // afterwards.
  void UpdateTextIndex(ContactMetadata* c, FullTextIndex* index, const DBHandle& updates);

  // Writes the given metadata to the database, merging it with any existing data for
  // the same identity.  Should be used after a contact_resolved callback if the
  // new data needs to be saved.
  void MergeResolvedContact(const ContactMetadata& c, const DBHandle& updates);

  // If "identity" has been resolved recently, copy it into *metadata and return true.
  bool GetCachedResolvedContact(const string& identity, ContactMetadata* metadata);

  // Returns a value for the contact_source field based on the given identity.  This is a heuristic
  // used for backwards compatibility until we have added an explicit source to all contacts.
  static string GetContactSourceForIdentity(const string& identity);

  // Sets the primary_identity field of *m (if necessary) to the best of the known identities.
  static void ChoosePrimaryIdentity(ContactMetadata* m);

  // Returns a single display name for this contact to be used for sorting and related operations
  // (such as iOS table headers).  Uses the first available field out of nickname, name, and primary_identity.
  static string ContactNameForSort(const ContactMetadata& m);

  // TODO(ben): Do these need to be public?
  void RemoveUser(int64_t user_id, const DBHandle& updates);
  void RemoveServerContact(const string& server_contact_id, const DBHandle& updates);
  void RemoveContact(const string& contact_id, bool upload, const DBHandle& updates);
  void SaveUser(const ContactMetadata& m, WallTime now, const DBHandle& updates);

  // Returns the assigned contact_id. If the "upload" bool is set for a
  // non-uploadable contact source, it is ignored.
  // This method is efficient to call if the given contact already exists.
  string SaveContact(const ContactMetadata& m, bool upload, WallTime now, const DBHandle& updates);

  // Updates the index for the given contact, which is assumed not to have actually changed.
  // (probably only useful from migrations).
  void ReindexContact(ContactMetadata* m, const DBHandle& updates);

  // Deletes all contacts and causes them to be re-queried from the server.
  void ResetAll();

  // Returns a list of contacts who have been converted to registered users since
  // the last call to ResetNewUsers.
  void GetNewUsers(ContactVec* new_users);
  void ResetNewUsers(const DBHandle& updates);
  CallbackSet* new_user_callback() { return &new_user_callback_; }

  typedef CallbackSet3<const QueryUsersResponse&,
                       const vector<int64_t>&, const DBHandle&> ProcessUsersCallback;
  ProcessUsersCallback* process_users() { return &process_users_; }

  // Returns a string that can be used in search (in other indexes) to find records related to the given user.
  static string FormatUserToken(int64_t user_id);

  // Prefix common to all FormatUserToken() strings.
  static const string kUserTokenPrefix;

  // Returns the user id encoded in the token or 0.
  static int64_t ParseUserToken(const Slice& token);

  // Adds any users matching the query who also appear in *index to *results.
  void GetAutocompleteUsers(const Slice& query, FullTextIndex* index, vector<AutocompleteUserInfo>* results);

 private:
  static string IdentityToIndexPhrase(const string& identity);
  void MaybeParseFirstAndLastNames(ContactMetadata* c);

  void LinkUserIdentity(int64_t user_id, const string& identity, const ContactMetadata& contact_template,
                        const DBHandle& updates);
  // If this identity is linked to a user, unlink it.
  void UnlinkIdentity(const string& identity, const DBHandle& updates);

  void WatchForFetchContacts(const string& op_id, FetchCallback done);

  // Run all completed FetchContacts callbacks if we have no more query_contacts calls to make.
  void MaybeRunFetchCallbacksLocked();

  void SearchUsers(const FullTextQuery& query, int search_options,
                   UserMatchMap* user_matches, StringSet* all_terms) const;
  void SearchContacts(const FullTextQuery& query, int search_options,
                      ContactMatchMap* user_matches, StringSet* all_terms) const;
  void MergeSearchResults(UserMatchMap* user_matches, ContactMatchMap* contact_matches,
                          vector<ContactMatch*>* match_vec) const;
  void BuildSearchResults(const vector<ContactMatch*>& match_vec, int search_options, ContactVec* results) const;

 private:
  AppState* const state_;
  int count_;
  int viewfinder_count_;
  CallbackSet contact_changed_;
  CallbackSet new_user_callback_;
  CallbackSet2<const string&, const ContactMetadata*> contact_resolved_;
  ProcessUsersCallback process_users_;

  // "Fetch ops" are an increasingly misnamed mechanism for callbacks to be
  // scheduled after our state has been synchronized with the server.
  // A single callback will be moved from one of the following data structures
  // to another before finally being run.
  mutable Mutex fetch_ops_mu_;
  // A list of callbacks that are waiting for uploads to be processed.
  // When the last upload has been assigned an op id, they are moved to
  // pending_fetch_ops_.
  FetchContactsList pending_upload_ops_;
  // Maps op id to FetchContacts callback.  Callbacks are moved from pending to completed when
  // a query_notifications for the op id has been processed.
  FetchContactsMap pending_fetch_ops_;
  // A list of FetchContacts callbacks whose notifications and invalidations we have seen.
  // They will be called the next time we have no more query_contacts calls to perform.
  FetchContactsList completed_fetch_ops_;

  ScopedPtr<UploadContacts> queued_upload_contacts_;
  ScopedPtr<RemoveContacts> queued_remove_contacts_;

  mutable Mutex cache_mu_;
  typedef std::unordered_map<int64_t, ContactMetadata*> UserMetadataCache;
  mutable UserMetadataCache user_cache_;

  typedef std::unordered_map<string, const ContactMetadata*> ResolvedContactCache;
  ResolvedContactCache resolved_contact_cache_;

  typedef std::unordered_set<string> ResolvingContactSet;
  ResolvingContactSet resolving_contacts_;

  Mutex queue_mu_;
  bool queued_update_self_;
  int64_t queued_update_friend_;

  ScopedPtr<FullTextIndex> user_index_;
  ScopedPtr<FullTextIndex> contact_index_;
};

bool DecodeUserIdKey(Slice key, int64_t* user_id);

bool IsValidEmailAddress(const Slice& address, string* error);

#endif  // VIEWFINDER_CONTACT_MANAGER_H
