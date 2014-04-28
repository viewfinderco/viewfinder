// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <unordered_map>
#import <unordered_set>
#import <re2/re2.h>
#import "Analytics.h"
#import "AppState.h"
#import "AsyncState.h"
#import "ContactManager.h"
#import "ContactMetadata.pb.h"
#import "DB.h"
#import "DigestUtils.h"
#import "FullTextIndex.h"
#import "IdentityManager.h"
#import "InvalidateMetadata.pb.h"
#import "LazyStaticPtr.h"
#import "LocaleUtils.h"
#import "Logging.h"
#import "NetworkManager.h"
#import "NotificationManager.h"
#import "PeopleRank.h"
#import "PhoneUtils.h"
#import "STLUtils.h"
#import "StringUtils.h"
#import "Timer.h"

const string ContactManager::kContactSourceGmail = "gm";
const string ContactManager::kContactSourceFacebook = "fb";
const string ContactManager::kContactSourceIOSAddressBook = "ip";
const string ContactManager::kContactSourceManual = "m";

const string ContactManager::kContactIndexName = "con";
const string ContactManager::kUserIndexName = "usr";

const string ContactManager::kUserTokenPrefix = "_user";

namespace {

const string kContactSelectionKey = DBFormat::metadata_key("contact_selection");
// The contacts_format key is no longer used but may exist in old databases.
// Leaving it commented out here as a reminder to not re-use the name.
// const string kFormatKey = DBFormat::metadata_key("contacts_format");
const string kMergeAccountsCompletionKey =
    DBFormat::metadata_key("merge_accounts_completion_key");
const string kMergeAccountsOpIdKey =
    DBFormat::metadata_key("merge_accounts_op_id_key");
const string kQueuedUpdateSelfKey = DBFormat::metadata_key("queued_update_self");

const string kNewUserCallbackTriggerKey = "ContactManagerNewUsers";

const int kUploadContactsLimit = 50;

// Parse everything between unicode separator characters. This
// will include all punctuation, both internal to the string and
// leading and trailing.
LazyStaticPtr<RE2, const char*> kWordUnicodeRE = { "([^\\pZ]+)" };
LazyStaticPtr<RE2, const char*> kWhitespaceUnicodeRE = { "([\\pZ]+)" };

LazyStaticPtr<RE2, const char*> kIdRE = { "u/([[:digit:]]+)" };
LazyStaticPtr<RE2, const char*> kQueueRE = { "cq/([[:digit:]]+)" };
LazyStaticPtr<RE2, const char*> kUpdateQueueRE = { "cuq/([[:digit:]]+)" };
LazyStaticPtr<RE2, const char*> kContactUploadQueueRE = { "ccuq/(.*)" };
LazyStaticPtr<RE2, const char*> kContactRemoveQueueRE = { "ccrq/(.*)" };
LazyStaticPtr<RE2, const char*> kNewUserRE = { "nu/([[:digit:]]+)" };

// Format used to build filter regexp (case-insensitve match) on the filter
// string or on the filter string alone or with a leading separator character.
const char* kFilterREFormat = "(?i)(?:^|[\\s]|[[:punct:]])(%s)";

// kEmailFullRE is used to decide when to start a ResolveContact
// operation. We require at least one dot in the domain portion, and
// at least two characters after the last dot.
LazyStaticPtr<RE2, const char*> kEmailFullRE = { "^[^ @]+@[^ @]+\\.[^. @]{2,}" };

LazyStaticPtr<RE2, const char*> kUserTokenRE = { "_user([0-9]+)_" };

const DBRegisterKeyIntrospect kContactKeyIntrospect(
    DBFormat::contact_key(""), NULL, [](Slice value) {
      return DBIntrospect::FormatProto<ContactMetadata>(value);
    });

const DBRegisterKeyIntrospect kDeprecatedContactIdKeyIntrospect(
    DBFormat::deprecated_contact_id_key(), NULL, [](Slice value) {
      return DBIntrospect::FormatProto<ContactMetadata>(value);
    });

const DBRegisterKeyIntrospect kContactSelectionKeyIntrospect(
    kContactSelectionKey, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<ContactSelection>(value);
    });

const DBRegisterKeyIntrospect kContactSourceKeyIntrospect(
    DBFormat::contact_source_key(""), NULL, [](Slice value) {
      return DBIntrospect::FormatProto<ContactSourceMetadata>(value);
    });

const DBRegisterKeyIntrospect kUserIdKeyIntrospect(
    DBFormat::user_id_key(), NULL, [](Slice value) {
      return DBIntrospect::FormatProto<ContactMetadata>(value);
    });

const DBRegisterKeyIntrospect kUserIdentityKeyIntrospect(
    DBFormat::user_identity_key(""), NULL, [](Slice value) {
      return ToString(value);
    });


// Identities with higher priority should be given preference when choosing
// the primary identity.
int PrimaryIdentityPriority(const Slice& identity) {
  if (IdentityManager::IsEmailIdentity(identity)) {
    return 3;
  } else if (IdentityManager::IsPhoneIdentity(identity)) {
    return 2;
  } else {
    // Facebook, etc.
    return 1;
  }
}

struct ContactMatchRankLess {
  AppState* state;
  WallTime now;

  ContactMatchRankLess(AppState* s)
      : state(s),
        now(state->WallTime_Now()) {
  }

  bool operator()(const ContactManager::ContactMatch* a, const ContactManager::ContactMatch* b) const {
    // TODO(pmattis): This sorts identities with viewfinder user ids to the
    // top. Not clear if this is the right thing to do long term.
    if (a->metadata.has_user_id() != b->metadata.has_user_id()) {
      return !a->metadata.has_user_id() < !b->metadata.has_user_id();
    } else {
      // This sorts identities which are registered before ones that
      // are still prospective.
      if (a->metadata.label_registered() != b->metadata.label_registered()) {
        return !a->metadata.label_registered() < !b->metadata.label_registered();
      }
    }
    // Contacts with non-viewfinder identities came from the user's own contact import,
    // so rank them above contacts that are only known because of transitive viewfinder
    // connections.
    if (IdentityManager::IsViewfinderIdentity(a->metadata.primary_identity()) !=
        IdentityManager::IsViewfinderIdentity(b->metadata.primary_identity())) {
      return IdentityManager::IsViewfinderIdentity(a->metadata.primary_identity()) <
          IdentityManager::IsViewfinderIdentity(b->metadata.primary_identity());
    }
    // Ranks are considered in order of email, phone & facebook.
    const int a_priority = PrimaryIdentityPriority(a->metadata.primary_identity());
    const int b_priority = PrimaryIdentityPriority(b->metadata.primary_identity());
    if (a_priority != b_priority) {
      return a_priority > b_priority;
    }
    // Use people rank weight (sort descending) if user ids are available.
    if (a->metadata.has_user_id() && b->metadata.has_user_id()) {
      const double a_weight = state->people_rank()->UserRank(a->metadata.user_id(), now);
      const double b_weight = state->people_rank()->UserRank(b->metadata.user_id(), now);
      if (a_weight != b_weight) {
        return a_weight > b_weight;
      }
    }
    if (a->metadata.has_rank() != b->metadata.has_rank()) {
      return !a->metadata.has_rank() < !b->metadata.has_rank();
    }
    // If identity type is the same, use rank for direct comparison.
    if (a->metadata.rank() != b->metadata.rank()) {
      return a->metadata.rank() < b->metadata.rank();
    }
    if (a->metadata.name() != b->metadata.name()) {
      return a->metadata.name() < b->metadata.name();
    }
    return a->metadata.primary_identity() < b->metadata.primary_identity();
  }
};

struct ContactMatchNameLess {
  bool operator()(ContactManager::ContactMatch* a, ContactManager::ContactMatch* b) const {
    // This method inlines parts of ContactNameLessThan so it can cache the sort keys.
    if (!a->sort_key_initialized) {
      a->sort_key_initialized = true;
      a->sort_key = ContactManager::ContactNameForSort(a->metadata);
    }
    if (!b->sort_key_initialized) {
      b->sort_key_initialized = true;
      b->sort_key = ContactManager::ContactNameForSort(b->metadata);
    }
    if (a->sort_key != b->sort_key) {
      return ContactManager::NameLessThan(a->sort_key, b->sort_key);
    }
    return a->metadata.primary_identity() < b->metadata.primary_identity();
  }
};

// Returns true if the given user can be shown as a user (rather than a contact) in search results.
bool IsViewfinderUser(const ContactMetadata& m) {
  if (!m.has_user_id() ||
      m.has_merged_with() ||
      m.label_terminated() ||
      m.label_system()) {
    // Non-users, merged accounts, terminated accounts, and system users are never shown.
    return false;
  }
  if (m.label_friend()) {
    // For friends, we receive terminate and merge notifications so the above data should always be
    // accurate.  Unregistered friends (i.e. prospective users in one of your conversations) will be
    // shown as invited users.
    return true;
  } else {
    // For non-friends, our information comes because we have their linked identity as a contact.
    // If the user is unlinked from that identity, we will never find out whether the user is
    // terminated, so we must not show it.
    if (m.identities_size() == 0) {
      return false;
    }

    // Non-friends should not be shown as users unless they are fully registered.
    return m.label_registered();
  }
}

void HashString(SHA256_CTX* ctx, const Slice& s) {
  SHA256_Update(ctx, s.data(), s.size());
  const char delimiter = 0;
  SHA256_Update(ctx, &delimiter, 1);
}

string ComputeContactId(const ContactMetadata& metadata) {
  SHA256_CTX ctx;
  SHA256_Init(&ctx);
  HashString(&ctx, metadata.primary_identity());
  for (int i = 0; i < metadata.identities_size(); i++) {
    if (metadata.identities(i).identity().empty()) {
      continue;
    }
    HashString(&ctx, metadata.identities(i).identity());
    HashString(&ctx, metadata.identities(i).description());
  }
  HashString(&ctx, "\0");  // Mark the end of the list
  HashString(&ctx, metadata.name());
  HashString(&ctx, metadata.first_name());
  HashString(&ctx, metadata.last_name());
  HashString(&ctx, metadata.nickname());
  int64_t rank = metadata.rank();
  SHA256_Update(&ctx, &rank, sizeof(rank));
  uint8_t digest[SHA256_DIGEST_LENGTH];
  SHA256_Final(&ctx, digest);
  // 256 bits is far more than we need for this case (and its size
  // affects the fulltext index size, so truncate to 128 bits (22
  // bytes after b64 without padding).
  const string contact_id = Format("%s:%s", metadata.contact_source(),
                                   Base64HexEncode(Slice((const char*)digest, 16), false));
  if (metadata.has_contact_id()) {
    CHECK_EQ(contact_id, metadata.contact_id());
  }
  return contact_id;
}

// Adds the given identity to the contact, updating primary_identity if necessary.
void AddIdentity(ContactMetadata* metadata, const string& identity) {
  metadata->add_identities()->set_identity(identity);
  if (metadata->primary_identity().empty() ||
      (PrimaryIdentityPriority(identity) > PrimaryIdentityPriority(metadata->primary_identity()))) {
    metadata->set_primary_identity(identity);
  }
}

// Adds the given identity to the contact (which must be a user) and updates the identity-to-user index.
void AddIdentityAndSave(ContactMetadata* metadata, const string& identity, const DBHandle& updates) {
  AddIdentity(metadata, identity);
  updates->Put(DBFormat::user_identity_key(identity), ToString(metadata->user_id()));
}

// Copies any identities from source to target if they are not already present.
// Does not update indexes so should only be used for transient objects.
void MergeIdentities(const ContactMetadata& source, ContactMetadata* target) {
  StringSet identities;
  for (int i = 0; i < target->identities_size(); i++) {
    identities.insert(target->identities(i).identity());
  }
  if (!source.primary_identity().empty() &&
      !ContainsKey(identities, source.primary_identity())) {
    AddIdentity(target, source.primary_identity());
    identities.insert(source.primary_identity());
  }
  for (int i = 0; i < source.identities_size(); i++) {
    if (!ContainsKey(identities, source.identities(i).identity())) {
      AddIdentity(target, source.identities(i).identity());
    }
  }
}

// Returns true if the two objects have at least one identity in common.
bool IdentitiesOverlap(const ContactMetadata& a, const ContactMetadata& b) {
  StringSet identities;
  if (!a.primary_identity().empty()) {
    identities.insert(a.primary_identity());
  }
  for (int i = 0; i < a.identities_size(); i++) {
    identities.insert(a.identities(i).identity());
  }
  if (!b.primary_identity().empty()) {
    if (ContainsKey(identities, b.primary_identity())) {
      return true;
    }
  }
  for (int i = 0; i < b.identities_size(); i++) {
    if (ContainsKey(identities, b.identities(i).identity())) {
      return true;
    }
  }
  return false;
}

bool IsUploadableContactSource(const Slice& contact_source) {
  return (contact_source == ContactManager::kContactSourceIOSAddressBook ||
          contact_source == ContactManager::kContactSourceManual);
}

bool DecodeNewUserKey(Slice key, int64_t* user_id) {
  return RE2::FullMatch(key, *kNewUserRE, user_id);
}

}  // namespace

bool DecodeUserIdKey(Slice key, int64_t* user_id) {
  return RE2::FullMatch(key, *kIdRE, user_id);
}

bool IsValidEmailAddress(const Slice& address, string* error) {
  vector<string> parts = SplitAllowEmpty(address.ToString(), "@");
  if (parts.size() <= 1) {
    *error = "You seem to be missing an \"@\" symbol.";
    return false;
  }
  if (parts.size() > 2) {
    *error = Format("I found %d \"@\" symbols. That's %d too many.",
                    parts.size() - 1, parts.size() - 2);
    return false;
  }
  if (RE2::FullMatch(address, ".*[\\pZ\\pC].*")) {
    *error = "There's a space in your email address - please remove it.";
    return false;
  }
  const Slice user(parts[0]);
  if (user.empty()) {
    *error = "This email is missing a username (you know, the bit before the \"@\").";
    return false;
  }
  const Slice domain(parts[1]);
  if (domain.empty()) {
    *error = "This email is missing a domain (you know, the bit after the \"@\").";
    return false;
  }
  parts = SplitAllowEmpty(parts[1], ".");
  if (parts.size() <= 1) {
    *error = "This email is missing a domain (maybe it's .com? .edu?).";
    return false;
  }
  for (int i = 0; i < parts.size(); ++i) {
    if (parts[i].empty()) {
      if (i == parts.size() - 1) {
        *error = "This email is missing a domain (maybe it's .com? .edu?).";
      } else {
        *error = "I'm not sure what to do with \"..\".";
      }
      return false;
    }
  }
  if (address.size() > 1000) {
    // Officially the limit is 254 characters; allow some extra room for non-compliant servers, unicode, etc.
    // http://stackoverflow.com/questions/386294/what-is-the-maximum-length-of-a-valid-email-address
    *error = "That's too long to be an email address.";
    return false;
  }
  return true;
}

ContactManager::ContactManager(AppState* state)
    : state_(state),
      count_(0),
      viewfinder_count_(0),
      queued_update_self_(false),
      queued_update_friend_(0),
      user_index_(new FullTextIndex(state_, kUserIndexName)),
      contact_index_(new FullTextIndex(state_, kContactIndexName)) {

  DBHandle updates = state_->NewDBTransaction();

  for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
       iter.Valid();
       iter.Next()) {
    ++count_;
  }

  // Count contacts with viewfinder user ids.
  for (DB::PrefixIterator iter(updates, DBFormat::user_id_key());
       iter.Valid();
       iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      LOG("contacts: unable to parse contact metadata: %s", iter.key());
      continue;
    }
    if (m.user_id() != state_->user_id() && IsViewfinderUser(m)) {
      ++viewfinder_count_;
    }
  }

  LOG("contacts: %d contact%s, %d VF",
      count_, Pluralize(count_), viewfinder_count_);

  queued_update_self_ = state_->db()->Get<bool>(kQueuedUpdateSelfKey, false);
  QueueUpdateFriend(0);

  // Re-initialize any merge accounts operation watch.
  ProcessMergeAccounts(updates->Get<string>(kMergeAccountsOpIdKey),
                       updates->Get<string>(kMergeAccountsCompletionKey),
                       NULL);

  state_->network_ready()->Add([this](int priority) {
      MaybeQueueUploadContacts();
      MaybeQueueRemoveContacts();
    });

  // Set up callbacks for handling notification mgr callbacks.
  state_->notification_manager()->process_notifications()->Add(
      [this](const QueryNotificationsResponse& p, const DBHandle& updates) {
        ProcessQueryNotifications(p, updates);
    });
  state_->notification_manager()->nuclear_invalidations()->Add(
      [this](const DBHandle& updates) {
        InvalidateAll(updates);
    });

  // We do not want to send the settings to the server if the
  // "settings changed" callback was triggered by a download.
  state_->settings_changed()->Add(
      [this](bool downloaded) {
        if (!downloaded) {
          QueueUpdateSelf();
        }
      });
}

ContactManager::~ContactManager() {
  // Free cache entries.
  Clear(&user_cache_);
  Clear(&resolved_contact_cache_);
}

void ContactManager::ProcessMergeAccounts(
    const string& op_id, const string& completion_db_key,
    const DBHandle& updates) {
  if (op_id.empty() || completion_db_key.empty()) {
    return;
  }
  if (updates.get()) {
    updates->Put(kMergeAccountsOpIdKey, op_id);
    updates->Put(kMergeAccountsCompletionKey, completion_db_key);
    // Force a query notification.
    state_->notification_manager()->Invalidate(updates);
  }

  // We're abusing the fetch contacts infrastructure here, which handles
  // watching for an op id in the query notifications stream.
  pending_fetch_ops_[op_id].push_back([this, completion_db_key] {
      LOG("merge accounts complete");
      DBHandle updates = state_->NewDBTransaction();
      updates->Delete(kMergeAccountsOpIdKey);
      updates->Delete(kMergeAccountsCompletionKey);
      updates->Delete(completion_db_key);
      updates->Commit();
      state_->async()->dispatch_main([this] {
          state_->settings_changed()->Run(true);
        });
    });
}

void ContactManager::ProcessAddressBookImport(
    const vector<ContactMetadata>& contacts,
    const DBHandle& updates, FetchCallback done) {
  CHECK(!dispatch_is_main_thread());

  StringSet existing;

  for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
       iter.Valid(); iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      continue;
    }
    if (m.contact_source() != kContactSourceIOSAddressBook) {
      continue;
    }
    DCHECK(!m.contact_id().empty());
    existing.insert(m.contact_id());
  }

  const WallTime now = WallTime_Now();
  for (int i = 0; i < contacts.size(); ++i) {
    const string contact_id = SaveContact(contacts[i], true, now, updates);
    existing.erase(contact_id);
  }

  for (StringSet::iterator it = existing.begin(); it != existing.end(); ++it) {
    RemoveContact(*it, true, updates);
  }

  LOG("contacts: %d contact%s, %d VF, updated %d entr%s, deleted/replaced %d entr%s",
      count_, Pluralize(count_), viewfinder_count_,
      contacts.size(), Pluralize(contacts.size(), "y", "ies"),
      existing.size(), Pluralize(existing.size(), "y", "ies"));

  updates->AddCommitTrigger("ProcessAddressBookImport", [this, done] {
      // The next time we reach the end of the upload-contacts queue, schedule our callback.
      MutexLock lock(&fetch_ops_mu_);
      pending_upload_ops_.push_back(done);
      state_->async()->dispatch_main([this] {
          state_->net_manager()->Dispatch();
        });
    });
}

void ContactManager::ProcessQueryContacts(
    const QueryContactsResponse& r,
    const ContactSelection& cs, const DBHandle& updates) {
  // Validate the contact selection based on queried contacts.
  Validate(cs, updates);

  const WallTime now = WallTime_Now();
  for (int i = 0; i < r.contacts_size(); ++i) {
    const ContactMetadata& u = r.contacts(i);

    if (u.label_contact_removed()) {
      CHECK(u.has_server_contact_id());
      RemoveServerContact(u.server_contact_id(), updates);
      continue;
    }

    if (!u.has_primary_identity()) {
      continue;
    }

    SaveContact(u, false, now, updates);

    // If the server gave us any identities with no associated user id, this is our indication that
    // that identity is no longer bound to any user, so unlink it if necessary.
    // We do this in ProcessQueryContacts instead of SaveContact because the absence of a user id
    // in other contexts does not imply that the identity is unbound.
    for (int j = 0; j < u.identities_size(); ++j) {
      if (!u.identities(j).has_user_id()) {
        UnlinkIdentity(u.identities(j).identity(), updates);
      }
    }
  }

  LOG("contacts: %d contact%s, %d VF, updated %d entr%s",
      count_, Pluralize(count_), viewfinder_count_,
      r.contacts_size(), Pluralize(r.contacts_size(), "y", "ies"));

  updates->AddCommitTrigger("SaveContacts", [this] {
      MutexLock lock(&fetch_ops_mu_);
      MaybeRunFetchCallbacksLocked();
    });
}

void ContactManager::ProcessQueryNotifications(
    const QueryNotificationsResponse& r, const DBHandle& updates) {
  MutexLock lock(&fetch_ops_mu_);

  for (int i = 0; i < r.notifications_size(); ++i) {
    const QueryNotificationsResponse::Notification& n = r.notifications(i);
    if (n.has_invalidate()) {
      const InvalidateMetadata& invalidate = n.invalidate();
      if (invalidate.has_contacts()) {
        Invalidate(invalidate.contacts(), updates);
      }
      for (int j = 0; j < invalidate.users_size(); ++j) {
        InvalidateUser(invalidate.users(j), updates);
      }
    }
    if (n.has_op_id()) {
      // The query notifications processing is performed on the network thread,
      // the same thread that manipulates the fetch_op_ map in FetchContacts().
      auto ops = pending_fetch_ops_[n.op_id()];
      for (auto it = ops.begin(); it != ops.end(); ++it) {
        VLOG("contacts: got notification that op %s is complete; awaiting contact fetch", n.op_id());
        const FetchCallback& done = *it;
        updates->AddCommitTrigger(
            Format("FetchContacts:%s", n.op_id()), [this, done] {
              MutexLock lock(&fetch_ops_mu_);
              VLOG("contacts: moving callback from notification to contact queue");
              completed_fetch_ops_.push_back(done);
              MaybeRunFetchCallbacksLocked();
            });
      }
      pending_fetch_ops_.erase(n.op_id());
    }
  }
}

void ContactManager::ProcessQueryUsers(
    const QueryUsersResponse& r,
    const vector<int64_t>& q, const DBHandle& updates) {
  typedef std::unordered_set<int64_t> UserIdSet;
  UserIdSet user_ids(q.begin(), q.end());

  const WallTime now = WallTime_Now();
  for (int i = 0; i < r.user_size(); ++i) {
    ContactMetadata u = r.user(i).contact();
    if (!u.has_user_id()) {
      continue;
    }
    user_ids.erase(u.user_id());

    // Update the metadata.
    SaveUser(u, now, updates);
  }

  // Delete any user that was queried but not returned in the
  // result. Presumably we don't have permission to retrieve their info and we
  // want to avoid looping attempting retrieval that will never succeed.
  for (UserIdSet::iterator iter(user_ids.begin());
       iter != user_ids.end();
       ++iter) {
    updates->Delete(DBFormat::user_queue_key(*iter));
  }

  LOG("contacts: %d contact%s, %d VF, updated %d entr%s (%d user%s not returned)",
      count_, Pluralize(count_), viewfinder_count_,
      r.user_size(), Pluralize(r.user_size(), "y", "ies"),
      user_ids.size(), Pluralize(user_ids.size()));

  updates->AddCommitTrigger("SaveUsers", [this] {
      MutexLock lock(&fetch_ops_mu_);
      MaybeRunFetchCallbacksLocked();
    });

  process_users_.Run(r, q, updates);
}

void ContactManager::ProcessResolveContact(
    const string& identity, const ContactMetadata* metadata) {
  {
    MutexLock lock(&cache_mu_);
    resolving_contacts_.erase(identity);
  }
  // The network manager runs these callbacks on its thread, but everything else wants to run
  // on the main thread. Copy the arguments and dispatch to the main thread.
  const ContactMetadata* metadata_copy = NULL;
  if (metadata) {
    LOG("contacts: resolved identity %s to user_id %d", identity, metadata->user_id());
    MutexLock lock(&cache_mu_);
    delete FindOrNull(resolved_contact_cache_, identity);
    resolved_contact_cache_[identity] = new ContactMetadata(*metadata);
    if (resolved_contact_cache_.size() % 100 == 0) {
      LOG("contact: resolved contact cache at %d entries", resolved_contact_cache_.size());
    }
    // Copy the metadata for use in the callback
    metadata_copy = new ContactMetadata(*metadata);
  } else {
    LOG("contacts: error resolving identity %s", identity);
  }
  dispatch_main([this, identity, metadata_copy] {
      contact_resolved_.Run(identity, metadata_copy);
      delete metadata_copy;
    });
}

void ContactManager::SearchUsers(const FullTextQuery& query, int search_options,
                                 UserMatchMap* user_matches, StringSet* all_terms) const {
  if (query.empty() && (search_options & ALLOW_EMPTY_SEARCH)) {
    // Special case handling of empty searches. We could just search for the
    // term "", but that would match every name key and be unacceptably slow.
    for (DB::PrefixIterator iter(state_->db(), DBFormat::user_id_key());
         iter.Valid();
         iter.Next()) {
      const Slice value = iter.value();
      ContactMetadata c;
      if (c.ParseFromArray(value.data(), value.size()) &&
          IsViewfinderUser(c)) {
        ContactMatch& m = (*user_matches)[c.user_id()];
        m.metadata.Swap(&c);
      }
    }
    return;
  }

  for (ScopedPtr<FullTextResultIterator> iter(user_index_->Search(state_->db(), query));
       iter->Valid();
       iter->Next()) {
    // The search process gave us ids; map those to ContactMetadata.
    const int64_t user_id = FromString<int64_t>(iter->doc_id());
    ContactMetadata m;
    if (!LookupUser(user_id, &m)) {
      LOG("contacts: unable to lookup contact metadata for id %s", user_id);
      continue;
    }
    if (!IsViewfinderUser(m)) {
      continue;
    }
    ContactMatch& c = (*user_matches)[m.user_id()];
    c.metadata.MergeFrom(m);
    iter->GetRawTerms(all_terms);
  }
}

void ContactManager::SearchContacts(const FullTextQuery& query, int search_options,
                                    ContactMatchMap* contact_matches, StringSet* all_terms) const {
  if (search_options & VIEWFINDER_USERS_ONLY) {
    return;
  }
  if (query.empty() && (search_options & ALLOW_EMPTY_SEARCH)) {
    for (DB::PrefixIterator iter(state_->db(), DBFormat::contact_key(""));
         iter.Valid();
         iter.Next()) {
      const Slice value = iter.value();
      ContactMetadata c;
      if (c.ParseFromArray(value.data(), value.size())) {
        ContactMatch& m = (*contact_matches)[c.contact_id()];
        m.metadata.Swap(&c);
      }
    }
   return;
  }

  for (ScopedPtr<FullTextResultIterator> iter(contact_index_->Search(state_->db(), query));
       iter->Valid();
       iter->Next()) {
    const string contact_id = iter->doc_id().as_string();
    ContactMetadata m;
    if (!state_->db()->GetProto(DBFormat::contact_key(contact_id), &m)) {
      LOG("contacts: unable to lookup contact metadata for contact id %s", contact_id);
      continue;
    }
    if ((search_options & SKIP_FACEBOOK_CONTACTS) &&
        m.contact_source() == kContactSourceFacebook) {
      continue;
    }
    ContactMatch& c = (*contact_matches)[m.contact_id()];
    c.metadata.MergeFrom(m);
    iter->GetRawTerms(all_terms);
  }
}

// The MatchMaps are non-const because we need access to the non-const ContactMatches they contain;
// this method does not modify the maps themselves.
void ContactManager::MergeSearchResults(UserMatchMap* user_matches, ContactMatchMap* contact_matches,
                                        vector<ContactMatch*>* match_vec) const {
  // Build up a vector of the matches.  Combine users and contacts with heuristic deduping.
  StringSet registered_user_identities;
  StringSet prospective_user_identities;
  for (UserMatchMap::iterator iter(user_matches->begin());
       iter != user_matches->end();
       ++iter) {
    ContactMatch* m = &iter->second;
    match_vec->push_back(m);
    StringSet* identity_set = m->metadata.label_registered() ?
                              &registered_user_identities :
                              &prospective_user_identities;
    if (!m->metadata.primary_identity().empty()) {
      identity_set->insert(m->metadata.primary_identity());
    }
    for (int i = 0; i < m->metadata.identities_size(); i++) {
      identity_set->insert(m->metadata.identities(i).identity());
    }
  }

  typedef std::unordered_multimap<string, ContactMatch*> ContactByNameMap;
  ContactByNameMap contact_by_name;
  for (ContactMatchMap::iterator iter(contact_matches->begin());
       iter != contact_matches->end();
       ++iter) {
    ContactMatch* m = &iter->second;
    // Hide any contacts for which we have a matching registered user.
    // Remove any contact identities that match a prospective user.
    if (!m->metadata.primary_identity().empty()) {
      if (ContainsKey(registered_user_identities, m->metadata.primary_identity())) {
        continue;
      }
      if (ContainsKey(prospective_user_identities, m->metadata.primary_identity())) {
        m->metadata.clear_primary_identity();
      }
    }
    bool seen_registered_identity = false;
    for (int i = 0; i < m->metadata.identities_size(); i++) {
      const string& identity = m->metadata.identities(i).identity();
      if (ContainsKey(registered_user_identities, identity)) {
        seen_registered_identity = true;
        break;
      }
      if (ContainsKey(prospective_user_identities, identity)) {
        ProtoRepeatedFieldRemoveElement(m->metadata.mutable_identities(), i--);
      }
    }
    if (seen_registered_identity || m->metadata.identities_size() == 0) {
      continue;
    }
    if (m->metadata.primary_identity().empty()) {
      ChoosePrimaryIdentity(&m->metadata);
    }

    // Heuristically dedupe non-user contacts by name.
    string name;
    if (!m->metadata.name().empty()) {
      name = m->metadata.name();
    } else if (!m->metadata.primary_identity().empty()) {
      name = IdentityManager::IdentityToName(m->metadata.primary_identity());
    }
    if (!name.empty()) {
      pair<ContactByNameMap::iterator, ContactByNameMap::iterator> match_by_name(
          contact_by_name.equal_range(name));
      ContactMatch* overlap = NULL;
      for (ContactByNameMap::iterator i = match_by_name.first; i != match_by_name.second; ++i) {
        // Facebook contacts don't convey any useful information (they're only used for the name
        // and the user is prompted to enter an email address if they select one), so hide
        // them if there are any real contacts with the same name.
        if (m->metadata.contact_source() == kContactSourceFacebook &&
            i->second->metadata.contact_source() != kContactSourceFacebook) {
          // We have a non-facebook contact, so skip this one.
          continue;
        } else if (m->metadata.contact_source() != kContactSourceFacebook &&
                   i->second->metadata.contact_source() == kContactSourceFacebook) {
          // This contact can replace an earlier facebook one.
          i->second->metadata.Swap(&m->metadata);
          continue;
        }

        // Non-facebook contacts can be combined if they have at least one identity in common.
        if (IdentitiesOverlap(m->metadata, i->second->metadata)) {
          overlap = i->second;
          break;
        }
      }
      if (overlap != NULL) {
        MergeIdentities(m->metadata, &overlap->metadata);
        continue;
      }

      contact_by_name.insert(ContactByNameMap::value_type(name, m));
    }

    match_vec->push_back(m);
  }
}

void ContactManager::BuildSearchResults(const vector<ContactMatch*>& match_vec, int search_options,
                                        ContactVec* results) const {
  // Output the matching contact metadata.
  std::unordered_set<int64_t> user_ids;
  for (int i = 0; i < match_vec.size(); ++i) {
    ContactMetadata* m = &match_vec[i]->metadata;
    if ((search_options & VIEWFINDER_USERS_ONLY) &&
        !m->has_user_id()) {
      continue;
    }
    if ((m->has_user_id() && !user_ids.insert(m->user_id()).second) ||
        m->has_merged_with() ||
        m->label_terminated()) {
      continue;
    }
    if (m->has_user_id() && m->user_id() == state_->user_id()) {
      // Skip any contact/user records for the current user.  This happens at the end of the process
      // rather than when this user record is first read so that any matching contact records can be
      // merged into it rather than displayed separately.
      continue;
    }
    results->push_back(ContactMetadata());
    results->back().Swap(m);
  }
}

void ContactManager::Search(
    const string& query, ContactVec* contacts,
    ScopedPtr<RE2>* filter_re, int search_options) const {
  WallTimer timer;
  int parse_options = 0;
  if (search_options & ContactManager::PREFIX_MATCH) {
    parse_options |= FullTextQuery::PREFIX_MATCH;
  }
  ScopedPtr<FullTextQuery> parsed_query(FullTextQuery::Parse(query, parse_options));
  StringSet all_terms;

  UserMatchMap user_matches;
  SearchUsers(*parsed_query, search_options, &user_matches, &all_terms);

  ContactMatchMap contact_matches;
  SearchContacts(*parsed_query, search_options, &contact_matches, &all_terms);

  vector<ContactMatch*> match_vec;
  MergeSearchResults(&user_matches, &contact_matches, &match_vec);

  // Sort the match vector.
  DCHECK_NE((search_options & SORT_BY_RANK) != 0,
            (search_options & SORT_BY_NAME) != 0);
  if (search_options & SORT_BY_RANK) {
    std::sort(match_vec.begin(), match_vec.end(), ContactMatchRankLess(state_));
  } else {
    std::sort(match_vec.begin(), match_vec.end(), ContactMatchNameLess());
  }

  BuildSearchResults(match_vec, search_options, contacts);


  // Build up a regular expression that will match the start of any filter
  // terms.
  if (filter_re) {
    FullTextQueryTermExtractor extractor(&all_terms);
    extractor.VisitNode(*parsed_query);
    filter_re->reset(FullTextIndex::BuildFilterRE(all_terms));
  }
  //LOG("contact: searched for [%s] (with options 0x%x).  Found %d results in %f milliseconds",
  //    query, search_options, contacts->size(), timer.Milliseconds());
}

string ContactManager::FirstName(int64_t user_id, bool allow_nickname) {
  ContactMetadata c;
  if (user_id == 0 || !LookupUser(user_id, &c)) {
    return "";
  }
  return FirstName(c, allow_nickname);
}

string ContactManager::FirstName(const ContactMetadata& c, bool allow_nickname) {
  if (c.user_id() == state_->user_id()) {
    return "You";
  }
  if (allow_nickname && !c.nickname().empty()) {
    return c.nickname();
  } else if (c.has_first_name()) {
    return c.first_name();
  } else if (c.has_name()) {
    return c.name();
  } else if (c.has_email()) {
    return c.email();
  } else {
    string email;
    if (ContactManager::EmailForContact(c, &email)) {
      return email;
    }
    string phone;
    if (ContactManager::PhoneForContact(c, &phone)) {
      return phone;
    }
  }
  return string();
}

string ContactManager::FullName(int64_t user_id, bool allow_nickname) {
  ContactMetadata c;
  if (user_id == 0 || !LookupUser(user_id, &c)) {
    return "";
  }
  return FullName(c, allow_nickname);
}

string ContactManager::FullName(const ContactMetadata& c, bool allow_nickname) {
  if (c.user_id() == state_->user_id()) {
    return "You";
  }
  if (allow_nickname && !c.nickname().empty()) {
    return c.nickname();
  } else if (c.has_name()) {
    return c.name();
  } else if (c.has_first_name()) {
    return c.first_name();
  } else if (c.has_email()) {
    return c.email();
  } else {
    string email;
    if (ContactManager::EmailForContact(c, &email)) {
      return email;
    }
    string phone;
    if (ContactManager::PhoneForContact(c, &phone)) {
      return phone;
    }
  }
  return string();
}

vector<int64_t> ContactManager::ViewfinderContacts() {
  vector<int64_t> ids;
  for (DB::PrefixIterator iter(state_->db(), DBFormat::user_id_key());
       iter.Valid();
       iter.Next()) {
    int64_t v;
    if (DecodeUserIdKey(iter.key(), &v)) {
      ids.push_back(v);
    }
  }
  sort(ids.begin(), ids.end());
  return ids;
}

void ContactManager::Reset() {
  count_ = 0;
  viewfinder_count_ = 0;

  {
    MutexLock l(&cache_mu_);
    user_cache_.clear();
  }

  {
    MutexLock l(&queue_mu_);
    queued_update_self_ = false;
    queued_update_friend_ = 0;
  }
}

void ContactManager::MaybeQueueUser(int64_t user_id, const DBHandle& updates) {
  const string user_queue_key = DBFormat::user_queue_key(user_id);
  if (updates->Exists(user_queue_key)) {
    // User is already queued for retrieval.
    return;
  }
  ContactMetadata c;
  if (updates->GetProto(DBFormat::user_id_key(user_id), &c) &&
      !c.need_query_user()) {
    // We've already retrieved the user metadata.
    return;
  }
  QueueUser(user_id, updates);
}

void ContactManager::QueueUser(int64_t user_id, const DBHandle& updates) {
  const string user_queue_key = DBFormat::user_queue_key(user_id);
  updates->Put(user_queue_key, string());
}

void ContactManager::ListQueryUsers(vector<int64_t>* ids, int limit) {
  for (DB::PrefixIterator iter(state_->db(), DBFormat::user_queue_key());
       iter.Valid();
       iter.Next()) {
    int64_t v;
    if (RE2::FullMatch(iter.key(), *kQueueRE, &v)) {
      ids->push_back(v);
    }
    if (ids->size() >= limit) {
      break;
    }
  }
}

void ContactManager::MaybeQueueUploadContacts() {
  if (queued_upload_contacts_.get()) {
    return;
  }
  ScopedPtr<UploadContacts> u(new UploadContacts);

  bool more = false;
  for (DB::PrefixIterator iter(state_->db(), DBFormat::contact_upload_queue_key(""));
       iter.Valid();
       iter.Next()) {
    string contact_id;
    if (!RE2::FullMatch(iter.key(), *kContactUploadQueueRE, &contact_id)) {
      continue;
    }
    ContactMetadata m;
    if (!state_->db()->GetProto(DBFormat::contact_key(contact_id), &m)) {
      continue;
    }
    if (!IsUploadableContactSource(m.contact_source())) {
      LOG("contact: non-upload contact queued: %s; removing from upload queue", iter.key());
      state_->db()->Delete(iter.key());
      continue;
    }
    if (u->contacts.size() >= kUploadContactsLimit) {
      more = true;
      break;
    }
    u->contacts.push_back(m);
  }
  if (u->contacts.size() > 0) {
    u->headers.set_op_id(state_->NewLocalOperationId());
    u->headers.set_op_timestamp(WallTime_Now());
    if (!more) {
      // If we are uploading contacts and this is the last batch, attach any pending upload contacts
      // to this op id.
      MutexLock lock(&fetch_ops_mu_);
      const string op_id = EncodeOperationId(state_->device_id(), u->headers.op_id());
      for (auto it = pending_upload_ops_.begin(); it != pending_upload_ops_.end(); ++it) {
        pending_fetch_ops_[op_id].push_back(*it);
      }
      pending_upload_ops_.clear();
    }
    queued_upload_contacts_.reset(u.release());
  } else {
    // Nothing to do.  If there are any pending_upload_ops, we just did an import that added no
    // contacts.  Go ahead and run any upload callbacks.
    MutexLock lock(&fetch_ops_mu_);
    for (auto it = pending_upload_ops_.begin(); it != pending_upload_ops_.end(); ++it) {
      (*it)();
    }
    pending_upload_ops_.clear();
  }
}

void ContactManager::CommitQueuedUploadContacts(const UploadContactsResponse& resp, bool success) {
  CHECK(queued_upload_contacts_.get());
  if (!queued_upload_contacts_.get()) {
    // Silence the code analyzer.
    return;
  }
  DBHandle updates(state_->NewDBTransaction());
  const WallTime now = WallTime_Now();
  const vector<ContactMetadata>& contacts = queued_upload_contacts_->contacts;
  for (int i = 0; i < contacts.size(); i++) {
    updates->Delete(DBFormat::contact_upload_queue_key(contacts[i].contact_id()));
  }
  if (success) {
    if (resp.contact_ids_size() == contacts.size()) {
      // Merge the contact ids returned from the server into our local contacts.
      for (int i = 0; i < contacts.size(); i++) {
        ContactMetadata m(contacts[i]);
        m.set_server_contact_id(resp.contact_ids(i));
        SaveContact(m, false, now, updates);
      }
    } else {
      DCHECK(false) << Format("uploaded %s contacts, got %s ids back", contacts.size(), resp.contact_ids_size());
    }
  } else {
    LOG("contact: failed to upload contacts; will not retry");
  }
  updates->Commit();
  queued_upload_contacts_.reset(NULL);
}

void ContactManager::MaybeQueueRemoveContacts() {
  if (queued_remove_contacts_.get()) {
    return;
  }
  ScopedPtr<RemoveContacts> r(new RemoveContacts);

  for (DB::PrefixIterator iter(state_->db(), DBFormat::contact_remove_queue_key(""));
       iter.Valid();
       iter.Next()) {
    string server_contact_id;
    if (!RE2::FullMatch(iter.key(), *kContactRemoveQueueRE, &server_contact_id)) {
      continue;
    }
    r->server_contact_ids.push_back(server_contact_id);
  }
  if (r->server_contact_ids.size() > 0) {
    r->headers.set_op_id(state_->NewLocalOperationId());
    r->headers.set_op_timestamp(WallTime_Now());
    queued_remove_contacts_.reset(r.release());
  }
}

void ContactManager::CommitQueuedRemoveContacts(bool success) {
  CHECK(queued_remove_contacts_.get());
  if (!queued_remove_contacts_.get()) {
    // Silence the code analyzer.
    return;
  }
  DBHandle updates(state_->NewDBTransaction());
  const vector<string>& ids = queued_remove_contacts_->server_contact_ids;
  for (int i = 0; i < ids.size(); i++) {
    updates->Delete(DBFormat::contact_remove_queue_key(ids[i]));
  }
  if (!success) {
    LOG("contact: failed to remove contacts on server; will not retry");
  }
  updates->Commit();
  queued_remove_contacts_.reset(NULL);
}

void ContactManager::Validate(const ContactSelection& cs, const DBHandle& updates) {
  ContactSelection existing;
  if (updates->GetProto(kContactSelectionKey, &existing)) {
    if (cs.start_key() <= existing.start_key()) {
      updates->Delete(kContactSelectionKey);
    } else {
      existing.set_start_key(cs.start_key());
      updates->PutProto(kContactSelectionKey, existing);
    }
  }
}

void ContactManager::Invalidate(const ContactSelection& cs, const DBHandle& updates) {
  ContactSelection existing;
  if (updates->GetProto(kContactSelectionKey, &existing)) {
    existing.set_start_key(std::min<string>(existing.start_key(), cs.start_key()));
  } else {
    existing.set_start_key(cs.start_key());
  }
  if (cs.all()) {
    // The server has garbage collected its removed-contact tombstones so we must wipe our local
    // contact database (except for local contacts we have yet to upload) and re-download everything.
    StringSet pending_uploads;
    for (DB::PrefixIterator iter(updates, DBFormat::contact_upload_queue_key("")); iter.Valid(); iter.Next()) {
      pending_uploads.insert(RemovePrefix(iter.key(), DBFormat::contact_upload_queue_key("")).as_string());
    }

    for (DB::PrefixIterator iter(updates, DBFormat::contact_key("")); iter.Valid(); iter.Next()) {
      const Slice contact_id = RemovePrefix(iter.key(), DBFormat::contact_key(""));
      if (!ContainsKey(pending_uploads, contact_id.as_string())) {
        RemoveContact(contact_id.as_string(), false, updates);
      }
    }

    // Note that the all flag itself is not persisted.
    existing.set_start_key("");
  }
  updates->PutProto(kContactSelectionKey, existing);
}

void ContactManager::InvalidateAll(const DBHandle& updates) {
  ContactSelection all;
  all.set_start_key("");
  updates->PutProto(kContactSelectionKey, all);
}

void ContactManager::InvalidateUser(const UserSelection& us, const DBHandle& updates) {
  updates->Put(DBFormat::user_queue_key(us.user_id()), string());
}

bool ContactManager::GetInvalidation(ContactSelection* cs) {
  return state_->db()->GetProto(kContactSelectionKey, cs);
}

bool ContactManager::LookupUser(int64_t user_id, ContactMetadata* c) const {
  return LookupUser(user_id, c, state_->db());
}

bool ContactManager::LookupUser(int64_t user_id, ContactMetadata* c, const DBHandle& db) const {
  MutexLock lock(&cache_mu_);

  if (ContainsKey(user_cache_, user_id)) {
    c->CopyFrom(*user_cache_[user_id]);
    if (!c->has_merged_with()) {
      return true;
    }
    // Fall through if this is a merged user.
  } else if (!db->GetProto(DBFormat::user_id_key(user_id), c)) {
    // LOG("contacts: %d unable to find contact", user_id);
    return false;
  }
  if (c->has_merged_with()) {
    // TODO(spencer): we don't cache this case. Maybe we should.
    ContactMetadata merged_with_contact;
    if (db->GetProto(DBFormat::user_id_key(c->merged_with()),
                     &merged_with_contact)) {
      c->CopyFrom(merged_with_contact);
      return true;
    }
  }

  // Add fetched value to cache.
  user_cache_[user_id] = new ContactMetadata;
  user_cache_[user_id]->CopyFrom(*c);
  if (user_cache_.size() % 100 == 0) {
    LOG("contact: lookup cache at %d entries", user_cache_.size());
  }
  return true;
}

bool ContactManager::LookupUserByIdentity(const string& identity, ContactMetadata* c) const {
  return LookupUserByIdentity(identity, c, state_->db());
}

bool ContactManager::LookupUserByIdentity(const string& identity, ContactMetadata* c,
                                          const DBHandle& db) const {
  int64_t user_id = db->Get<int64_t>(DBFormat::user_identity_key(identity), -1);
  if (user_id <= 0) {
    return false;
  }
  return LookupUser(user_id, c, db);
}

void ContactManager::ResolveContact(const string& identity) {
  {
    MutexLock lock(&cache_mu_);
    if (ContainsKey(resolving_contacts_, identity)) {
      return;
    }
    resolving_contacts_.insert(identity);
  }
  state_->net_manager()->ResolveContact(identity);
}

bool ContactManager::IsRegistered(const ContactMetadata& c) {
  return c.has_user_id() && c.label_registered();
}

bool ContactManager::IsProspective(const ContactMetadata& c) {
  return c.has_user_id() && !c.label_registered();
}

bool ContactManager::IsResolvableEmail(const Slice& email) {
  return RE2::FullMatch(email, *kEmailFullRE);
}

bool ContactManager::GetEmailIdentity(const ContactMetadata& c, string* identity) {
  // The primary identity should be found in the identities list below, but since
  // the order of identities is not guaranteed explicitly check the primary first.
  if (IdentityManager::IsEmailIdentity(c.primary_identity())) {
    if (identity) {
      *identity = c.primary_identity();
    }
    return true;
  }
  for (int i = 0; i < c.identities_size(); ++i) {
    if (IdentityManager::IsEmailIdentity(c.identities(i).identity())) {
      if (identity) {
        *identity = c.identities(i).identity();
      }
      return true;
    }
  }
  // Last ditch effort is to get email from the contact directly.
  if (c.has_email()) {
    if (identity) {
      *identity = IdentityManager::IdentityForEmail(c.email());
    }
    return true;
  }
  return false;
}

bool ContactManager::GetPhoneIdentity(const ContactMetadata& c, string* identity) {
  // The primary identity should be found in the identities list below, but since
  // the order of identities is not guaranteed explicitly check the primary first.
  if (IdentityManager::IsPhoneIdentity(c.primary_identity())) {
    if (identity) {
      *identity = c.primary_identity();
    }
    return true;
  }
  for (int i = 0; i < c.identities_size(); ++i) {
    if (IdentityManager::IsPhoneIdentity(c.identities(i).identity())) {
      if (identity) {
        *identity = c.identities(i).identity();
      }
      return true;
    }
  }
  if (c.has_phone()) {
    if (identity) {
      *identity = IdentityManager::IdentityForPhone(c.phone());
    }
    return true;
  }
  return false;
}

string ContactManager::FormatName(
    const ContactMetadata& c, bool shorten, bool always_include_full) {
  if (shorten) {
    if (!c.nickname().empty()) {
      return c.nickname();
    } else if (c.has_first_name()) {
      return c.first_name();
    } else if (c.has_name()) {
      return c.name();
    } else if (c.has_email()) {
      return c.email();
    } else {
      string email;
      if (ContactManager::EmailForContact(c, &email)) {
        return email;
      }
      string phone;
      if (ContactManager::PhoneForContact(c, &phone)) {
        return phone;
      }
    }
  } else {
    string name;
    if (c.has_name()) {
      name = c.name();
    } else if (c.has_first_name()) {
      name = c.first_name();
    } else if (c.has_email()) {
      name = c.email();
    } else {
      string email;
      if (ContactManager::EmailForContact(c, &email)) {
        name = email;
      } else {
        string phone;
        if (ContactManager::PhoneForContact(c, &phone)) {
          name = phone;
        }
      }
    }
    if (!name.empty()) {
      if (!c.nickname().empty()) {
        if (always_include_full) {
          return Format("%s (%s)", c.nickname(), name);
        } else {
          return c.nickname();
        }
      } else {
        return name;
      }
    }
  }

  return "(Pending Invite)";
}

bool ContactManager::FetchFacebookContacts(
    const string& access_token, FetchCallback done) {
  return state_->net_manager()->FetchFacebookContacts(
      access_token, [this, done](const string& op_id) {
        WatchForFetchContacts(op_id, done);
      });
}

bool ContactManager::FetchGoogleContacts(
    const string& refresh_token, FetchCallback done) {
  return state_->net_manager()->FetchGoogleContacts(
      refresh_token, [this, done](const string& op_id) {
        WatchForFetchContacts(op_id, done);
      });
}

void ContactManager::ClearFetchContacts() {
  // Clear (finish) any outstanding fetch contacts operations as we're skipping
  // notification processing.
  VLOG("contacts: clearing fetch callbacks");
  MutexLock lock(&fetch_ops_mu_);
  FetchContactsMap old_fetch_ops;
  pending_fetch_ops_.swap(old_fetch_ops);
  for (FetchContactsMap::iterator iter(old_fetch_ops.begin());
       iter != old_fetch_ops.end();
       ++iter) {
    auto ops = iter->second;
    for (int i = 0; i < ops.size(); i++) {
      state_->async()->dispatch_main(ops[i]);
    }
  }
  FetchContactsList old_fetch_ops_list;
  completed_fetch_ops_.swap(old_fetch_ops_list);
  for (int i = 0; i < old_fetch_ops_list.size(); i++) {
    state_->async()->dispatch_main(old_fetch_ops_list[i]);
  }
}

bool ContactManager::SetMyName(
    const string& first, const string& last, const string& name) {
  LOG("contact: setting my name to first=\"%s\", last=\"%s\", name=\"%s\"",
      first, last, name);

  const string normalized_first = NormalizeWhitespace(first);
  const string normalized_last = NormalizeWhitespace(last);
  const string normalized_name = NormalizeWhitespace(name);
  if (first != normalized_first) {
    LOG("contact: first name was changed by normalization: [%s] vs [%s]",
        first, normalized_first);
   }
  if (last != normalized_last) {
    LOG("contact: last name was changed by normalization: [%s] vs [%s]",
        last, normalized_last);
  }
  if (name != normalized_name) {
    LOG("contact: name was changed by normalization: [%s] vs [%s]",
        name, normalized_name);
  }
  if (normalized_first.empty() && normalized_last.empty()) {
    LOG("contact: normalized name is empty; not saving");
    return false;
  }

  ContactMetadata new_metadata, metadata;
  new_metadata.set_first_name(normalized_first);
  new_metadata.set_last_name(normalized_last);
  new_metadata.set_name(normalized_name);

  // Set the necessary flags so the new metadata is recognized as authoritative in the merge.
  new_metadata.set_user_id(state_->user_id());

  LookupUser(state_->user_id(), &metadata);

  if (new_metadata.first_name() == metadata.first_name() &&
      new_metadata.last_name() == metadata.last_name()) {
    LOG("contact: normalized name unchanged; not saving");
    return true;
  }

  DBHandle updates = state_->NewDBTransaction();
  SaveUser(new_metadata, WallTime_Now(), updates);
  updates->Commit();

  QueueUpdateSelf();
  return true;
}

void ContactManager::SetFriendNickname(int64_t user_id, const string& nickname) {
  LOG("contact: setting friend (%d) nickname to \"%s\"", user_id, nickname);

  const string normalized = NormalizeWhitespace(nickname);
  if (nickname != normalized) {
    LOG("contact: nickname was changed by normalization: [%s] vs [%s]",
        nickname, normalized);
  }

  ContactMetadata metadata;
  if (!LookupUser(user_id, &metadata)) {
    LOG("contact: unable to find contact: %d", user_id);
    return;
  }

  if (metadata.nickname() == nickname) {
    // The nickname is unchanged.
    return;
  }

  metadata.set_nickname(normalized);

  DBHandle updates = state_->NewDBTransaction();
  SaveUser(metadata, WallTime_Now(), updates);
  updates->Commit();

  QueueUpdateFriend(user_id);
}

int ContactManager::CountContactsForSource(const string& source) {
  int count = 0;
  for (DB::PrefixIterator iter(state_->db(), DBFormat::contact_key(source));
       iter.Valid();
       iter.Next()) {
    count++;
  }
  return count;
}

int ContactManager::CountViewfinderContactsForSource(const string& source) {
  int count = 0;
  for (DB::PrefixIterator iter(state_->db(), DBFormat::contact_key(source));
       iter.Valid();
       iter.Next()) {
    const Slice value = iter.value();
    ContactMetadata c;
    if (c.ParseFromArray(value.data(), value.size())) {
      for (int i = 0; i < c.identities_size(); ++i) {
        const string& identity = c.identities(i).identity();
        int64_t user_id = state_->db()->Get<int64_t>(DBFormat::user_identity_key(identity));
        if (user_id) {
          ContactMetadata cm;
          if (LookupUser(user_id, &cm) &&
              IsViewfinderUser(cm)) {
            count++;
          };
          break;
        }
      }
    }
  }
  return count;
}

WallTime ContactManager::GetLastImportTimeForSource(const string& source) {
  ContactSourceMetadata metadata;
  if (state_->db()->GetProto(DBFormat::contact_source_key(source), &metadata)) {
    return metadata.last_import_timestamp();
  }
  return 0;
}

void ContactManager::SetLastImportTimeForSource(const string& source, WallTime timestamp) {
  ContactSourceMetadata metadata;
  metadata.set_last_import_timestamp(timestamp);
  state_->db()->PutProto(DBFormat::contact_source_key(source), metadata);
}

string ContactManager::ConstructFullName(const string& first, const string& last) {
  // TODO(spencer): this needs to be localized.
  if (first.empty()) {
    return last;
  }
  if (last.empty()) {
    return first;
  }
  return Format("%s %s", first, last);
}

void ContactManager::QueueUpdateSelf() {
  // Queue the update on the current thread to ease testing.
  MutexLock l(&queue_mu_);

  queued_update_self_ = true;

  // Persist this flag to the database so that if the app crashes before
  // the network operation completes, we'll try again later.
  state_->db()->Put<bool>(kQueuedUpdateSelfKey, true);

  // Note that we intentionally do not call dispatch_main() here as we want the
  // stack to unwind and locks to be released before Dispatch() is called.
  state_->async()->dispatch_main_async([this] {
      state_->net_manager()->Dispatch();
    });
  // TODO(marc): maybe we should look for notifications after this, although
  // we're the device changing the settings, so we don't need them right away.
}

void ContactManager::CommitQueuedUpdateSelf() {
  MutexLock l(&queue_mu_);
  queued_update_self_ = false;
  state_->db()->Delete(kQueuedUpdateSelfKey);
}

void ContactManager::QueueUpdateFriend(int64_t user_id) {
  // Queue the update on the current thread to ease testing.
  MutexLock l(&queue_mu_);
  if (user_id != 0) {
    state_->db()->Put(DBFormat::user_update_queue_key(user_id), 0);
  }

  if (queued_update_friend_ == 0) {
    // We do not have a friend update currently queued. Find the first
    // friend update and queue it.
    for (DB::PrefixIterator iter(state_->db(), DBFormat::user_update_queue_key());
         iter.Valid();
         iter.Next()) {
      const Slice key = iter.key();
      if (!RE2::FullMatch(key, *kUpdateQueueRE, &queued_update_friend_)) {
        DCHECK(false);
        state_->db()->Delete(key);
        continue;
      }
      break;
    }
  }

  if (queued_update_friend_ != 0) {
    // Note that we intentionally do not call dispatch_main() here as we want the
    // stack to unwind and locks to be released before Dispatch() is called.
    state_->async()->dispatch_main_async([this] {
        state_->net_manager()->Dispatch();
      });
  }
}

void ContactManager::CommitQueuedUpdateFriend() {
  {
    MutexLock l(&queue_mu_);
    state_->db()->Delete(DBFormat::user_update_queue_key(queued_update_friend_));
    queued_update_friend_ = 0;
  }
  QueueUpdateFriend(0);
}

bool ContactManager::EmailForContact(const ContactMetadata& c, string* email) {
  string email_identity;
  if (ContactManager::GetEmailIdentity(c, &email_identity)) {
    *email = IdentityManager::IdentityToName(email_identity);
    return true;
  }
  *email = "";
  return false;
}

bool ContactManager::PhoneForContact(const ContactMetadata& c, string* phone) {
  string phone_identity;
  if (ContactManager::GetPhoneIdentity(c, &phone_identity)) {
    *phone = IdentityManager::IdentityToName(phone_identity);
    return true;
  }
  *phone = "";
  return false;
}

int ContactManager::Reachability(const ContactMetadata& c) {
  int reachability = 0;

  if (ContactManager::GetEmailIdentity(c, NULL)) {
    reachability |= REACHABLE_BY_EMAIL;
  }
  if (ContactManager::GetPhoneIdentity(c, NULL)) {
    reachability |= REACHABLE_BY_SMS;
  }
  return reachability;
}

bool ContactManager::ParseFullName(
    const string& full_name, string* first, string* last) {
  if (full_name.empty()) {
    *first = "";
    *last = "";
    return false;
  }
  Slice src(full_name);
  string part;
  if (!RE2::FindAndConsume(&src, *kWordUnicodeRE, &part)) {
    LOG("contacts: unable to parse name: '%s'", full_name);
    *first = "";
    *last = "";
    return false;
  }
  *first = part;
  RE2::FindAndConsume(&src, *kWhitespaceUnicodeRE, &part);
  *last = src.ToString();
  return true;
}

bool ContactManager::NameLessThan(const Slice& a, const Slice& b) {
  // Sort empty names after everything else.
  if (a.empty()) {
    return false;
  }
  if (b.empty()) {
    return true;
  }
  // Sort letters before anything else.
  const bool a_isalpha = IsAlphaUnicode(utfnext(a));
  const bool b_isalpha = IsAlphaUnicode(utfnext(b));
  if (a_isalpha != b_isalpha) {
    return a_isalpha;
  }
  return LocalizedCaseInsensitiveCompare(a, b) < 0;
}

bool ContactManager::ContactNameLessThan(
    const ContactMetadata& a, const ContactMetadata& b) {
  // Some of this logic is duplicated in ContactMatchNameLess for speed.
  const string a_name = ContactNameForSort(a);
  const string b_name = ContactNameForSort(b);
  if (a_name != b_name) {
    return ContactManager::NameLessThan(a_name, b_name);
  }
  return a.primary_identity() < b.primary_identity();
}

void ContactManager::MaybeParseFirstAndLastNames(ContactMetadata* c) {
  if (!c->has_first_name() || !c->has_last_name()) {
    string first, last;
    if (ParseFullName(c->name(), &first, &last)) {
      if (!c->has_first_name()) {
        c->set_first_name(first);
      }
      if (!c->has_last_name()) {
        c->set_last_name(last);
      }
    }
  }
}

void ContactManager::SaveUser(const ContactMetadata& new_metadata, WallTime now, const DBHandle& updates) {
  CHECK(new_metadata.user_id());
  const int64_t user_id = new_metadata.user_id();

  ContactMetadata old_metadata;
  const bool existing = updates->GetProto(DBFormat::user_id_key(user_id), &old_metadata);

  ContactMetadata merged;
  if (existing && new_metadata.need_query_user()) {
    // The new metadata is tentative, and we have some existing metadata.
    if (old_metadata.need_query_user()) {
      // If the old metadata was also tentative, combine it with the new.
      merged.CopyFrom(old_metadata);
      merged.MergeFrom(new_metadata);
    } else {
      // The old metadata is a full user record, so don't clobber it with a tentative one (except for merging
      // identities)
      LOG("contact: attempting to overwrite full user record with tentative data: %s vs %s",
          old_metadata, new_metadata);
      merged.CopyFrom(old_metadata);
    }
    if (new_metadata.label_registered() && !old_metadata.label_registered()) {
      merged.clear_creation_timestamp();  // Will be reset below.
    }
  } else {
    // If the new metadata is not tentative, most fields of the new record clobber the old.
    merged.CopyFrom(new_metadata);
    // The old nickname is carried forward if the new metadata doesn't replace it.
    if (old_metadata.has_nickname() && !new_metadata.has_nickname()) {
      merged.set_nickname(old_metadata.nickname());
    }
  }

  if (!merged.has_creation_timestamp()) {
    merged.set_creation_timestamp(now);
  }

  // The identities are merged separately from the protobuf CopyFrom/MergeFrom operations.
  merged.clear_identities();
  merged.clear_primary_identity();

  if (old_metadata.has_primary_identity()) {
    merged.set_primary_identity(old_metadata.primary_identity());
  }

  // TODO(ben): need some way to remove identities.
  std::unordered_set<string> identities;
  for (int i = 0; i < old_metadata.identities_size(); i++) {
    identities.insert(old_metadata.identities(i).identity());
  }
  merged.mutable_identities()->CopyFrom(old_metadata.identities());

  // Ensure that the primary identity is always present in identities().
  if (!old_metadata.primary_identity().empty() &&
      !ContainsKey(identities, old_metadata.primary_identity())) {
    identities.insert(old_metadata.primary_identity());
    AddIdentityAndSave(&merged, old_metadata.primary_identity(), updates);
  }

  for (int i = 0; i < new_metadata.identities_size(); i++) {
    const ContactIdentityMetadata& identity = new_metadata.identities(i);
    if (ContainsKey(identities, identity.identity())) {
      continue;
    }
    identities.insert(identity.identity());
    AddIdentityAndSave(&merged, identity.identity(), updates);
    merged.mutable_identities(merged.identities_size() - 1)->CopyFrom(identity);
  }

  if (!new_metadata.primary_identity().empty() &&
      !ContainsKey(identities, new_metadata.primary_identity())) {
    identities.insert(new_metadata.primary_identity());
    AddIdentityAndSave(&merged, new_metadata.primary_identity(), updates);
  }

  // Add a notice when a contact becomes a registered user.  This applies when either a user with identities
  // transitions from unregistered to registered.
  // Skip this step until the first refresh has completed so we don't show all contacts as new when
  // an existing user syncs a new device.
  if (user_id != state_->user_id() &&
      merged.identities_size() > 0 &&
      merged.label_registered() &&
      !old_metadata.label_registered() &&
      state_->refresh_completed()) {
    updates->Put(DBFormat::new_user_key(user_id), "");
  }

  // If we're saving a new user (whether the user became new in this transaction or an earlier one),
  // trigger a rescan of dashboard notices to ensure we're displaying the correct name.
  // (Prospective users often get updated in two stages: first a query_contacts binds the identity,
  // and then query_users gets the name and other information).
  if (updates->Exists(DBFormat::new_user_key(user_id))) {
    updates->AddCommitTrigger(kNewUserCallbackTriggerKey, [this] {
        new_user_callback_.Run();
      });
  }

  // Split up the name field if necessary.
  MaybeParseFirstAndLastNames(&merged);

  merged.clear_indexed_names();
  if (existing) {
    merged.mutable_indexed_names()->CopyFrom(old_metadata.indexed_names());
  }
  UpdateTextIndex(&merged, user_index_.get(), updates);

  updates->PutProto(DBFormat::user_id_key(user_id), merged);

  if (user_id != state_->user_id()) {
    if (existing && IsViewfinderUser(old_metadata)) {
      viewfinder_count_--;
    }
    if (IsViewfinderUser(merged)) {
      viewfinder_count_++;
    }
  }

  // If the user has been merged with another, we may need to fetch that user too.
  if (merged.has_merged_with()) {
    MaybeQueueUser(merged.merged_with(), updates);
  }

  // If the user was terminated, make sure that we remove user id from
  // all viewpoint follower lists.
  if (merged.label_terminated()) {
    vector<int64_t> viewpoint_ids;
    state_->viewpoint_table()->ListViewpointsForUserId(user_id, &viewpoint_ids, updates);
    for (int i = 0; i < viewpoint_ids.size(); ++i) {
      ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(viewpoint_ids[i], updates);
      if (vh.get()) {
        vh->Lock();
        vh->RemoveFollower(user_id);
        vh->SaveAndUnlock(updates);
      }
    }
  }

  {
    // If this user is cached, update the value.
    MutexLock lock(&cache_mu_);
    if (ContainsKey(user_cache_, user_id)) {
      user_cache_[merged.user_id()]->CopyFrom(merged);
    }
    updates->Delete(DBFormat::user_queue_key(user_id));

    state_->day_table()->InvalidateUser(user_id, updates);
  }

  updates->AddCommitTrigger(Format("SaveUser:%s", user_id), [this] {
      contact_changed_.Run();
    });
}

string ContactManager::SaveContact(const ContactMetadata& m, bool upload, WallTime now, const DBHandle& updates) {
  ContactMetadata metadata(m);
  CHECK(!metadata.has_user_id());
  CHECK(metadata.has_contact_source());

  StringSet identities;
  for (int i = 0; i < metadata.identities_size(); i++) {
    const ContactIdentityMetadata& ci = metadata.identities(i);
    DCHECK(!ci.identity().empty());
    if (ci.identity().empty()) {
      LOG("not saving empty identity %s from contact %s", ci, metadata);
      continue;
    }
    identities.insert(ci.identity());

    if (ci.has_user_id()) {
      // TODO(ben): it would be more efficent when there are multiple identities to make all the
      // changes at once (assuming all the identities are bound to the same user, which is expected
      // but not guaranteed).
      LinkUserIdentity(ci.user_id(), ci.identity(), metadata, updates);
      MaybeQueueUser(ci.user_id(), updates);
      metadata.mutable_identities(i)->clear_user_id();
    }
  }

  if (metadata.primary_identity().empty()) {
    ChoosePrimaryIdentity(&metadata);
  } else {
    CHECK(ContainsKey(identities, m.primary_identity()));
  }

  if (!metadata.has_creation_timestamp()) {
    metadata.set_creation_timestamp(now);
  }

  const string new_contact_id = ComputeContactId(metadata);
  metadata.set_contact_id(new_contact_id);

  ContactMetadata old_metadata;
  const bool exists = updates->GetProto(DBFormat::contact_key(new_contact_id), &old_metadata);
  if (exists) {
    // Contacts are addressed by a hash of their contents, so if we have a match the new should be the
    // same as the old, with the possible exception of the addition of a server id.
    DCHECK_EQ(old_metadata.name(), metadata.name());
    DCHECK_EQ(old_metadata.first_name(), metadata.first_name());
    DCHECK_EQ(old_metadata.last_name(), metadata.last_name());
    DCHECK_EQ(old_metadata.nickname(), metadata.nickname());
    DCHECK_EQ(old_metadata.rank(), metadata.rank());
    DCHECK_EQ(old_metadata.contact_source(), metadata.contact_source());

    if (!metadata.has_server_contact_id() ||
        old_metadata.server_contact_id() == metadata.server_contact_id()) {
      return new_contact_id;
    }
    // Continue to add the server id to the existing proto.
    // Server contact ids are only supplied by the server, so if we're adding one we shouldn't
    // be asked to reupload the same contact.
    DCHECK(!upload);
  }

  if (!exists) {
    // No need to update the text index if we're just adding a server contact id.
    UpdateTextIndex(&metadata, contact_index_.get(), updates);
    count_++;
  }

  updates->PutProto(DBFormat::contact_key(new_contact_id), metadata);
  if (metadata.has_server_contact_id()) {
    updates->Put(DBFormat::server_contact_id_key(metadata.server_contact_id()), new_contact_id);
  }

  const string remove_queue_key = DBFormat::contact_remove_queue_key(new_contact_id);
  if (updates->Exists(remove_queue_key)) {
    updates->Delete(remove_queue_key);
  }

  if (upload && IsUploadableContactSource(metadata.contact_source())) {
    updates->Put(DBFormat::contact_upload_queue_key(new_contact_id), "");
  }

  updates->AddCommitTrigger(Format("SaveContact:%s", new_contact_id), [this] {
      contact_changed_.Run();
    });

  return new_contact_id;
}

void ContactManager::ReindexContact(ContactMetadata* m, const DBHandle& updates) {
  UpdateTextIndex(m, contact_index_.get(), updates);
  updates->PutProto(DBFormat::contact_key(m->contact_id()), *m);
}

void ContactManager::RemoveContact(const string& contact_id, bool upload, const DBHandle& updates) {
  ContactMetadata m;
  if (updates->GetProto(DBFormat::contact_key(contact_id), &m)) {
    contact_index_->RemoveTerms(m.mutable_indexed_names(), updates);

    // Cancel any pending upload.
    updates->Delete(DBFormat::contact_upload_queue_key(m.contact_id()));

    if (!m.server_contact_id().empty()) {
      updates->Delete(DBFormat::server_contact_id_key(m.server_contact_id()));
      if (upload) {
        updates->Put(DBFormat::contact_remove_queue_key(m.server_contact_id()), "");
      }
    }
  }
  updates->Delete(DBFormat::contact_key(contact_id));
}

void ContactManager::RemoveServerContact(const string& server_contact_id, const DBHandle& updates) {
  string contact_id;
  if (updates->Get(DBFormat::server_contact_id_key(server_contact_id), &contact_id)) {
    RemoveContact(contact_id, false, updates);
  }
}

void ContactManager::RemoveUser(int64_t user_id, const DBHandle& updates) {
  ContactMetadata m;
  if (updates->GetProto(DBFormat::user_id_key(user_id), &m)) {
    user_index_->RemoveTerms(m.mutable_indexed_names(), updates);
  }
  updates->Delete(DBFormat::user_id_key(user_id));
}

void ContactManager::ResetAll() {
  DBHandle updates = state_->NewDBTransaction();
  ContactSelection nuclear;
  nuclear.set_all(true);
  Invalidate(nuclear, updates);
  updates->Commit();
  state_->async()->dispatch_main_async([this] {
      state_->net_manager()->Dispatch();
    });
}

void ContactManager::GetNewUsers(ContactVec* new_users) {
  for (DB::PrefixIterator iter(state_->db(), DBFormat::new_user_key());
       iter.Valid();
       iter.Next()) {
    int64_t user_id;
    if (!DecodeNewUserKey(iter.key(), &user_id)) {
      continue;
    }
    ContactMetadata m;
    if (LookupUser(user_id, &m)) {
      new_users->push_back(m);
    }
  }
}

void ContactManager::ResetNewUsers(const DBHandle& updates) {
  for (DB::PrefixIterator iter(state_->db(), DBFormat::new_user_key());
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  updates->AddCommitTrigger(kNewUserCallbackTriggerKey, [this] {
      new_user_callback_.Run();
    });
}

string ContactManager::FormatUserToken(int64_t user_id) {
  return Format("%s%d_", kUserTokenPrefix, user_id);
}

int64_t ContactManager::ParseUserToken(const Slice& token) {
  int64_t user_id = 0;
  RE2::FullMatch(token, *kUserTokenRE, &user_id);
  return user_id;
}

void ContactManager::GetAutocompleteUsers(const Slice& query, FullTextIndex* index,
                                          vector<AutocompleteUserInfo>* results) {
  // Find all the matching contacts.
  vector<ContactMetadata> contact_vec;
  std::unordered_map<int64_t, const ContactMetadata*> contacts;
  state_->contact_manager()->Search(
      query.as_string(), &contact_vec, NULL,
      ContactManager::SORT_BY_RANK | ContactManager::VIEWFINDER_USERS_ONLY | ContactManager::PREFIX_MATCH);
  for (int i = 0; i < contact_vec.size(); i++) {
    contacts[contact_vec[i].user_id()] = &contact_vec[i];
  }

  // Cross-reference the matching contacts with the user tokens.  This lets us retrieve ranking information
  // on the same scale as the other terms, as well as exclude users who have not posted any photos (
  // since we are only looking at the episode index and not the viewpoint index).
  // TODO(ben): it's still possible for contacts to appear in the autocomplete but have no results (if the
  // episodes they match are not in the library).  We could fix this by creating separate indexes for library
  // and non-library episodes.
  FullTextIndex::SuggestionResults user_tokens;
  index->GetSuggestions(state_->db(), ContactManager::kUserTokenPrefix, &user_tokens);
  for (int i = 0; i < user_tokens.size(); i++) {
    const int64_t user_id = ParseUserToken(user_tokens[i].second);
    if (ContainsKey(contacts, user_id)) {
      results->push_back({FormatName(*contacts[user_id], false),
                          user_id,
                          user_tokens[i].first});
    }
  }
}

void ContactManager::LinkUserIdentity(int64_t user_id, const string& identity,
                                      const ContactMetadata& contact_template, const DBHandle& updates) {
  ContactMetadata m;
  if (!updates->GetProto(DBFormat::user_id_key(user_id), &m)) {
    // If we haven't seen the user before, create it.
    m.MergeFrom(contact_template);
    m.set_need_query_user(true);
    m.set_user_id(user_id);
    m.clear_indexed_names();
    m.clear_contact_id();
    m.clear_rank();
    m.clear_contact_source();
    // The identity to be linked will be merged in at the end of this method.
    m.clear_primary_identity();
    m.clear_identities();
  } else {
    // The user exists.  We've had bugs that cause user data to get lost, so merge basic information
    // from the contact if it's available on the contact and not the user.
    if (m.need_query_user()) {
      if (m.name().empty() && !contact_template.name().empty()) {
        m.set_name(contact_template.name());
      }
      if (m.first_name().empty() && !contact_template.first_name().empty()) {
        m.set_first_name(contact_template.first_name());
      }
      if (m.last_name().empty() && !contact_template.last_name().empty()) {
        m.set_last_name(contact_template.last_name());
      }
    }
  }
  m.add_identities()->set_identity(identity);
  SaveUser(m, WallTime_Now(), updates);
}

void ContactManager::UnlinkIdentity(const string& identity, const DBHandle& updates) {
  ContactMetadata m;
  if (!LookupUserByIdentity(identity, &m, updates)) {
    return;
  }

  CHECK(m.has_user_id());

  google::protobuf::RepeatedPtrField<ContactIdentityMetadata> identities;
  for (int i = 0; i < m.identities_size(); i++) {
    if (m.identities(i).identity() != identity) {
      identities.Add()->CopyFrom(m.identities(i));
    }
  }
  m.mutable_identities()->Swap(&identities);

  if (m.primary_identity() == identity) {
    m.clear_primary_identity();
    if (m.identities_size() > 0) {
      ChoosePrimaryIdentity(&m);
    }
  }

  // SaveUser will attempt to merge the given metadata with what's already on disk, so we
  // must first delete the existing data by hand.
  updates->Delete(DBFormat::user_identity_key(identity));
  updates->PutProto(DBFormat::user_id_key(m.user_id()), m);

  // Now call SaveUser to update the full-text index and the in-memory cache.
  SaveUser(m, WallTime_Now(), updates);
}

void ContactManager::WatchForFetchContacts(const string& op_id, FetchCallback done) {
  if (op_id.empty()) {
    state_->async()->dispatch_main(done);
    return;
  }
  MutexLock lock(&fetch_ops_mu_);
  VLOG("contacts: enqueuing fetch callback for op %s", op_id);
  pending_fetch_ops_[op_id].push_back(done);

  state_->async()->dispatch_main([this] {
      state_->net_manager()->Refresh();
    });
}

void ContactManager::MaybeRunFetchCallbacksLocked() {
  fetch_ops_mu_.AssertHeld();
  ContactSelection cs;
  if (GetInvalidation(&cs)) {
    // We still have contacts to fetch.
    return;
  }
  vector<int64_t> user_ids;
  ListQueryUsers(&user_ids, 1);
  if (user_ids.size()) {
    // We still have users to fetch.
    return;
  }

  // We're all caught up; run the callbacks.
  FetchContactsList callbacks;
  callbacks.swap(completed_fetch_ops_);
  if (callbacks.size()) {
    VLOG("contacts: finished querying contacts; running %d fetch callbacks",
         callbacks.size());
  }
  for (int i = 0; i < callbacks.size(); i++) {
    dispatch_main(callbacks[i]);
  }
}

void ContactManager::UpdateTextIndex(ContactMetadata* c, FullTextIndex* index, const DBHandle& updates) {
  string key;
  if (index == contact_index_.get()) {
    CHECK(!c->contact_id().empty());
    key = c->contact_id();
  } else {
    CHECK(c->user_id());
    key = ToString(c->user_id());
  }

  vector<FullTextIndexTerm> index_terms;
  int pos = 0;

  for (int i = 0; i < c->identities_size(); i++) {
    const string identity_name = IdentityManager::IdentityToName(c->identities(i).identity());
    if (!identity_name.empty()) {
      pos = index->ParseIndexTerms(pos, identity_name, &index_terms);
    }
  }

  // Only index the name if it's a "real" name, and not just the identity.
  if (!c->name().empty() &&
      c->name() != IdentityManager::IdentityToName(c->primary_identity())) {
    pos = index->ParseIndexTerms(pos, c->name(), &index_terms);
  }
  if (!c->nickname().empty()) {
    pos = index->ParseIndexTerms(pos, c->nickname(), &index_terms);
  }

  index->UpdateIndex(index_terms, key, "", c->mutable_indexed_names(), updates);
}

void ContactManager::MergeResolvedContact(const ContactMetadata& c, const DBHandle& updates) {
  SaveUser(c, WallTime_Now(), updates);
  // resolve_contact currently only returns a subset of the user fields; schedule a fetch
  // to get the rest.
  QueueUser(c.user_id(), updates);
}

bool ContactManager::GetCachedResolvedContact(const string& identity, ContactMetadata* metadata) {
  MutexLock lock(&cache_mu_);
  const ContactMetadata* resolved = FindOrNull(resolved_contact_cache_, identity);
  if (resolved) {
    metadata->CopyFrom(*resolved);
    return true;
  }
  return false;
}

string ContactManager::GetContactSourceForIdentity(const string& identity) {
  if (IdentityManager::IsEmailIdentity(identity)) {
    return kContactSourceGmail;
  } else if (IdentityManager::IsFacebookIdentity(identity)) {
    return kContactSourceFacebook;
  } else if (IdentityManager::IsPhoneIdentity(identity)) {
    return kContactSourceIOSAddressBook;
  } else {
    return kContactSourceManual;
  }
}

void ContactManager::ChoosePrimaryIdentity(ContactMetadata* m) {
  if (!m->primary_identity().empty()) {
    // Primary identity is already set.
    return;
  }
  int best_score = -1;
  int best_pos = -1;
  for (int i = 0; i < m->identities_size(); i++) {
    const int score = PrimaryIdentityPriority(m->identities(i).identity());
    if (score > best_score) {
      best_score = score;
      best_pos = i;
      m->set_primary_identity(m->identities(i).identity());
    }
  }
  CHECK_GE(best_pos, 0);
  if (best_pos != 0) {
    // Put the newly-chosen primary identity first in the list.
    m->mutable_identities()->SwapElements(0, best_pos);
  }
}

string ContactManager::ContactNameForSort(const ContactMetadata& m) {
  if (!m.nickname().empty()) {
    return m.nickname();
  } else if (!m.name().empty()) {
    return m.name();
  } else if (!m.primary_identity().empty()) {
    return IdentityManager::IdentityToName(m.primary_identity());
  } else if (!m.email().empty()) {
    return m.email();
  } else if (!m.phone().empty()) {
    return FormatPhoneNumberPrefix(m.phone(), GetPhoneNumberCountryCode());
  } else {
    return "";
  }
}

// local variables:
// mode: c++
// end:
