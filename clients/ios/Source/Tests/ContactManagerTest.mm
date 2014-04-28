// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import <unordered_map>
#import "ContactManager.h"
#import "IdentityManager.h"
#import "InvalidateMetadata.pb.h"
#import "Server.pb.h"
#import "STLUtils.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class TestContacts {
  typedef std::unordered_map<string, ContactMetadata> ContactMap;

 public:
  enum {
    ALLOW_EMPTY = ContactManager::SORT_BY_RANK |
      ContactManager::ALLOW_EMPTY_SEARCH,
    SORT_BY_NAME = ContactManager::SORT_BY_NAME,
    VIEWFINDER_USERS_ONLY = ContactManager::VIEWFINDER_USERS_ONLY,
    SKIP_FACEBOOK_CONTACTS = ContactManager::SKIP_FACEBOOK_CONTACTS,
  };

 public:
  TestContacts()
      : state_(dir_.dir()) {
  }

  UIAppState* state() { return &state_; }

  void Clear() {
    DBHandle updates = state_.NewDBTransaction();
    for (DB::PrefixIterator iter(updates, DBFormat::contact_key(""));
         iter.Valid();
         iter.Next()) {
      ContactMetadata m;
      if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
        continue;
      }
      if (!m.contact_id().empty()) {
        contact_manager()->RemoveContact(m.contact_id(), false, updates);
      }
    }
    for (DB::PrefixIterator iter(updates, DBFormat::user_id_key());
         iter.Valid();
         iter.Next()) {
      int64_t user_id;
      CHECK(DecodeUserIdKey(iter.key(), &user_id));
      contact_manager()->RemoveUser(user_id, updates);
    }
    updates->Commit();
  }

  void AddContact(const string& identity, const string& name, int rank) {
    AddContactWithUser(identity, name, rank, -1);
  }

  void AddContactWithUser(const string& identity, const string& name, int rank, int user_id) {
    QueryContactsResponse r;
    ContactMetadata* m = r.add_contacts();
    if (IdentityManager::IsFacebookIdentity(identity)) {
      m->set_contact_source(ContactManager::kContactSourceFacebook);
    } else {
      m->set_contact_source(ContactManager::kContactSourceManual);
    }
    // This is not the form of a real contact id, but it works for the purposes of these tests.
    m->set_server_contact_id(Format("SCI:%s", identity));
    if (!identity.empty()) {
      m->set_primary_identity(identity);
      ContactIdentityMetadata* ci = m->add_identities();
      ci->set_identity(identity);
      if (user_id >= 0) {
        ci->set_user_id(user_id);
      }
    }
    if (!name.empty()) {
      m->set_name(name);
    }
    if (rank >= 0) {
      m->set_rank(rank);
    }
    ContactSelection cs;
    DBHandle updates = state_.NewDBTransaction();
    contact_manager()->ProcessQueryContacts(r, cs, updates);
    updates->Commit();
  }

  void RemoveServerContact(const string& server_contact_id) {
    QueryContactsResponse r;
    ContactMetadata* m = r.add_contacts();
    m->set_server_contact_id(server_contact_id);
    m->set_label_contact_removed(true);
    ContactSelection cs;
    DBHandle updates = state_.NewDBTransaction();
    contact_manager()->ProcessQueryContacts(r, cs, updates);
    updates->Commit();
  }

  void AddUser(const string& identity, int user_id, const string& name, int64_t merged_with=-1) {
    vector<int64_t> user_ids;
    user_ids.push_back(user_id);
    AddUser(identity, user_id, name, user_ids, merged_with);
  }

  void AddUser(const string& identity, int user_id, const string& name, const vector<int64_t>& user_ids,
               int64_t merged_with=-1) {
    QueryUsersResponse r;
    if (user_id >= 0) {
      ContactMetadata* m = r.add_user()->mutable_contact();
      m->set_user_id(user_id);
      m->set_name(name);
      if (merged_with >= 0) {
        m->set_merged_with(merged_with);
      }
      if (!identity.empty()) {
        m->add_identities()->set_identity(identity);
      }
      m->set_label_registered(true);
    }
    ProcessQueryUsers(r, user_ids);
  }

  void AddEmptyUser(int user_id) {
    // Simulates the empty (user-id-only) response from a query_users request for a user you're not
    // friends with.
    QueryUsersResponse r;
    ContactMetadata* m = r.add_user()->mutable_contact();
    m->set_user_id(user_id);
    m->set_need_query_user(true);
    ProcessQueryUsers(r, L(user_id));
  }

  void ImportAddressBook(const vector<ContactMetadata>& contacts) {
    DBHandle updates = state_.NewDBTransaction();
    contact_manager()->ProcessAddressBookImport(contacts, updates, ^{});
    updates->Commit();
  }

  void RawSearch(const string& query, vector<ContactMetadata>* results) {
    contact_manager()->Search(query, results, NULL);
  }

  string Search(const string& query, ScopedPtr<RE2>* re = NULL,
                int options = ContactManager::SORT_BY_RANK | ContactManager::PREFIX_MATCH) {
    vector<ContactMetadata> result;
    contact_manager()->Search(query, &result, re, options);

    string s;
    for (int i = 0; i < result.size(); ++i) {
      if (!s.empty()) {
        s += " ";
      }
      s += result[i].primary_identity();
      if (result[i].has_user_id()) {
        s += Format("[%d]", result[i].user_id());
      }
    }
    return s;
  }

  string FirstName(int64_t user_id) {
    return contact_manager()->FirstName(user_id);
  }
  string FullName(int64_t user_id) {
    return contact_manager()->FullName(user_id);
  }
  string Nickname(int64_t user_id) {
    ContactMetadata c;
    LookupUser(user_id, &c);
    return c.nickname();
  }
  vector<int64_t> ViewfinderContacts() {
    return contact_manager()->ViewfinderContacts();
  }

  bool LookupUser(int64_t user_id, ContactMetadata* c) {
    return contact_manager()->LookupUser(user_id, c);
  }

  bool LookupUserByIdentity(const string& identity, ContactMetadata* c) {
    return contact_manager()->LookupUserByIdentity(identity, c);
  }

  void MaybeQueueUser(int64_t user_id) {
    DBHandle updates = state_.NewDBTransaction();
    contact_manager()->MaybeQueueUser(user_id, updates);
    updates->Commit();
  }

  string ListQueryUsers(int limit) {
    vector<int64_t> user_ids;
    contact_manager()->ListQueryUsers(&user_ids, limit);
    return ToString(user_ids);
  }

  void Invalidate(const ContactSelection& cs) {
    DBHandle updates = state_.NewDBTransaction();
    contact_manager()->Invalidate(cs, updates);
    updates->Commit();
  }

  void Validate(const ContactSelection& cs) {
    DBHandle updates = state_.NewDBTransaction();
    contact_manager()->Validate(cs, updates);
    updates->Commit();
  }

  void InvalidateAll() {
    DBHandle updates = state_.NewDBTransaction();
    contact_manager()->InvalidateAll(updates);
    updates->Commit();
  }

  // Returns a current invalidation start key.
  string GetInvalidation() {
    ContactSelection cs;
    EXPECT(contact_manager()->GetInvalidation(&cs));
    return cs.start_key();
  }

  bool HasInvalidation() {
    ContactSelection cs;
    return contact_manager()->GetInvalidation(&cs);
  }

  ContactManager* contact_manager() {
    return state_.contact_manager();
  }
  const DBHandle& db() {
    return state_.db();
  }

  void SetUserId(int64_t user_id) {
    state_.SetUserId(user_id);
  }
  bool SetMyName(const string& first, const string& last, const string& name) {
    return contact_manager()->SetMyName(first, last, name);
  }

 private:
  void ProcessQueryUsers(const QueryUsersResponse r, const vector<int64_t>& user_ids) {
    DBHandle updates = state_.NewDBTransaction();
    contact_manager()->ProcessQueryUsers(r, user_ids, updates);
    updates->Commit();
  }

  TestTmpDir dir_;
  TestUIAppState state_;
  ContactMap contacts_;
};

TEST(ContactManagerTest, IsValidEmailAddress) {
  struct {
    const string address;
    const bool valid;
  } kTestData[] = {
    { "", false },
    { "a", false },
    { "a@", false },
    { "a@@", false },
    { "@b", false },
    { "@@b", false },
    { "@b.c", false },
    { "a@b", false },
    { "a@b.", false },
    { "a@.b", false },
    { "a@b..c", false },
    { "a@b. c", false },
    { "a@@b.c", false },
    { "a@b.c", true },
    { "a @b.c", false },
    { "a\u205F@b.c", false },  // U+205F medium mathematical space
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    string error;
    EXPECT_EQ(kTestData[i].valid,
              IsValidEmailAddress(kTestData[i].address, &error))
        << ": " << kTestData[i].address;
  }
}

TEST(ContactManagerTest, Invalidation) {
  TestContacts t;
  EXPECT(!t.HasInvalidation());

  ContactSelection cs;
  cs.set_start_key("");
  t.Invalidate(cs);
  EXPECT_EQ("", t.GetInvalidation());

  t.Validate(cs);
  EXPECT(!t.HasInvalidation());

  cs.set_start_key("a");
  t.Invalidate(cs);
  EXPECT_EQ("a", t.GetInvalidation());
  cs.set_start_key("b");
  t.Validate(cs);
  EXPECT_EQ("b", t.GetInvalidation());
  t.Validate(cs);
  EXPECT(!t.HasInvalidation());

  t.InvalidateAll();
  EXPECT_EQ("", t.GetInvalidation());
}

TEST(ContactManagerTest, LookupUserByIdentity) {
  TestContacts t;
  t.AddUser("Email:foo@bar.com", 2, "x y");
  ContactMetadata m;
  ASSERT(t.LookupUserByIdentity("Email:foo@bar.com", &m));
  EXPECT_EQ(m.name(), "x y");
}

TEST(ContactManagerTest, Search) {
  TestContacts t;

  // Add a single contact and verify we can find it.
  t.AddContact("foo@bar", "foo bar", 0);
  EXPECT_EQ("foo@bar", t.Search("f"));
  EXPECT_EQ("foo@bar", t.Search("fo"));
  EXPECT_EQ("foo@bar", t.Search("foo"));
  EXPECT_EQ("foo@bar", t.Search("b"));
  EXPECT_EQ("foo@bar", t.Search("ba"));
  EXPECT_EQ("foo@bar", t.Search("bar"));

  // Now try a single user.
  t.Clear();
  t.AddUser("foo@bar", 5, "x y z");
  EXPECT_EQ("foo@bar[5]", t.Search("x"));
  EXPECT_EQ("foo@bar[5]", t.Search("y"));
  EXPECT_EQ("foo@bar[5]", t.Search("z"));

  // Email identities are indexed.
  t.Clear();
  t.AddContact("Email:test@foo", "", 0);
  EXPECT_EQ("Email:test@foo", t.Search("t"));
  EXPECT_EQ("Email:test@foo", t.Search("foo"));
  EXPECT_EQ("Email:test@foo", t.Search("test@foo"));
  EXPECT_EQ("", t.Search("test@foobar"));

  // Facebook identities are not.
  t.Clear();
  t.AddContact("FacebookGraph:1", "", 0);
  EXPECT_EQ("", t.Search("f"));
  EXPECT_EQ("", t.Search("Facebook"));

  // Two contacts with different ranks. The higher ranked (lower rank value)
  // contact will always be returned first.
  t.Clear();
  t.AddContact("foo@rank1", "foo rank1", 1);
  t.AddContact("rank2@foo", "rank2 foo", 2);
  EXPECT_EQ("foo@rank1 rank2@foo", t.Search("foo"));
  EXPECT_EQ("foo@rank1 rank2@foo", t.Search("rank"));

  // Two users (which are not ranked) will be sorted by name.
  t.Clear();
  t.AddUser("foo@bar", 1, "foo bar");
  t.AddUser("bar@foo", 2, "bar foo");
  EXPECT_EQ("bar@foo[2] foo@bar[1]", t.Search("f"));
  EXPECT_EQ("bar@foo[2] foo@bar[1]", t.Search("b"));

  // Both filter words must match for a contact to be found.
  t.AddUser("test@foo", 5, "test foo");
  EXPECT_EQ("test@foo[5]", t.Search("t f"));
  EXPECT_EQ("bar@foo[2] foo@bar[1]", t.Search("f b"));
  EXPECT_EQ("", t.Search("t f b"));

  t.AddContact("Email:foo@baz.com", "", 0);
  EXPECT_EQ("Email:foo@baz.com", t.Search("foo@baz.com"));
  EXPECT_EQ("Email:foo@baz.com", t.Search("foo@baz"));
  EXPECT_EQ("Email:foo@baz.com", t.Search("baz.com"));

  // Two contacts, one with a rank and one without. The one without a rank will
  // always sort after the one with a rank.
  t.AddContact("x", "x y", -1);
  t.AddContact("y", "y x", 1);
  EXPECT_EQ("y x", t.Search("x"));
  EXPECT_EQ("y x", t.Search("y"));

  // Inputs are segmented: even though there is no whitespace, we can search for the second word.
  // The filter regex currently only works when word breaks are marked by whitespace or punctuation,
  // so we don't have a corresponding case in ContactManagerTest::Filter.
  t.AddUser("foo@bar", 6, "习近平");
  EXPECT_EQ("foo@bar[6]", t.Search("近平"));
}

TEST(ContactManagerTest, EmptySearch) {
  TestContacts t;
  t.AddUser("foo@bar", 1, "foo bar");
  t.AddUser("bar@foo", 2, "bar foo");
  // An empty search will return nothing by default.
  EXPECT_EQ("", t.Search(""));
  EXPECT_EQ("bar@foo[2] foo@bar[1]", t.Search("", NULL, t.ALLOW_EMPTY));
}

TEST(ContactManagerTest, SortByName) {
  TestContacts t;
  t.AddUser("foo", 1, "foo bar");
  t.AddUser("bar", 2, "bar foo");
  t.AddUser("1",   3, "1 foo");
  EXPECT_EQ("1[3] bar[2] foo[1]", t.Search("f"));
  // Note that letters are sorted before anything else.
  EXPECT_EQ("bar[2] foo[1] 1[3]",
            t.Search("f", NULL, ContactManager::SORT_BY_NAME | ContactManager::PREFIX_MATCH));
}

TEST(ContactManagerTest, ViewfinderUsersOnly) {
  TestContacts t;
  t.AddContact("not-viewfinder-user", "a", 0);
  t.AddUser("viewfinder-user", 1, "a");
  EXPECT_EQ("not-viewfinder-user viewfinder-user[1]",
            t.Search("a", NULL, t.SORT_BY_NAME));
  EXPECT_EQ("viewfinder-user[1]",
            t.Search("a", NULL, t.SORT_BY_NAME | t.VIEWFINDER_USERS_ONLY));
}

TEST(ContactManagerTest, SkipFacebookContacts) {
  TestContacts t;
  t.AddUser("Email:foo", 1, "a");
  t.AddUser("FacebookGraph:user", 2, "a");
  t.AddContact("FacebookGraph:not-a-user", "a", 0);
  EXPECT_EQ("Email:foo[1] FacebookGraph:not-a-user FacebookGraph:user[2]",
            t.Search("a", NULL, t.SORT_BY_NAME));
  EXPECT_EQ("Email:foo[1] FacebookGraph:user[2]",
            t.Search("a", NULL, t.SORT_BY_NAME | t.SKIP_FACEBOOK_CONTACTS));
}

TEST(ContactManagerTest, PrefixMatch) {
  TestContacts t;
  t.AddUser("Email:two", 2, "two");
  t.AddUser("Email:twelve", 12, "twelve");
  t.AddUser("Email:twotwo", 22, "twotwo");
  EXPECT_EQ("Email:twelve[12] Email:two[2] Email:twotwo[22]",
            t.Search("tw", NULL, ContactManager::SORT_BY_NAME | ContactManager::PREFIX_MATCH));
  EXPECT_EQ("Email:two[2] Email:twotwo[22]",
            t.Search("two", NULL, ContactManager::SORT_BY_NAME | ContactManager::PREFIX_MATCH));
  EXPECT_EQ("", t.Search("tw", NULL, ContactManager::SORT_BY_NAME));
  EXPECT_EQ("Email:two[2]", t.Search("two", NULL, ContactManager::SORT_BY_NAME));
}

TEST(ContactManagerTest, Filter) {
  TestContacts t;

  struct {
    const string identity;
    const string name;
    const string filter;
    const string expected;
  } testdata[] = {
    { "foo@bar", "foo bar", "f", "f" },
    { "foo@bar", "foo bar", "f b", "f b" },
    // The regex only matches at the beginning of words.
    { "foo@bar", "foof bar", "f", "f" },
    // Punctuation within names is allowed (and ignored if applicable).
    { "foo@bar", "foo-bar", "b", "b" },
    { "foo@bar", "foo'bar", "b", "" },
    { "foo@bar", "foo-bar", "foo-", "foo" },
    { "foo@bar", "foo-bar", "foo b", "foo b" },
    { "foo@bar", "foo'bar", "foo'", "foo" },
    { "foo@bar", "foo'bar", "foo'b", "foo'b" },
    { "foo@bar", "foo'bar", "foob", "foo'b" },
    // Leading punctuation is allowed (and ignored if applicable).
    { "foo@bar", "'Nuff Said", "n", "N" },
    { "foo@bar", "'Nuff Said", "'n", "N" },
    { "foo@bar", ":éff ing", ":é", "é" },
    { "foo@bar", ":éff ing", "é", "é" },
    { "foo@bar", ":éff ing", ":e", "é" },
    { "foo@bar", ":éff ing", "e", "é" },
    { "foo@bar", "'Nu'ff Said", "nu'ff", "Nu'ff" },
    { "foo@bar", "'Nu'ff Said", "nuff", "Nu'ff" },
    // Trailing punctuation is allowed.
    { "foo@bar", "Workin' Hard", "workin'", "Workin" },
    // The regex is case insensitive.
    { "foo@bar", "FOO BAR", "f", "F" },
    { "foo@bar", "FOO BAR", "foo", "FOO" },
    // Non-7-bit ascii characters can be searched both with
    // 8-bit and equivalent 7-bit.
    { "foo@bar", "Andréa Olausson", "andrea", "Andréa" },
    { "foo@bar", "Andréa Olausson", "andréa", "Andréa" },
    { "foo@bar", "Andréa Olausson", "Andréa", "Andréa" },
    { "foo@bar", "Jeremy O'Connor", "O'C", "O'C" },
    { "foo@bar", "Jeremy O'Connor", "oc", "O'C" },
    { "foo@bar", "Jeremy O'Connor", "OC", "O'C" },
    // Unicode characters.
    { "foo@bar", "刘京", "刘", "刘" },
    { "foo@bar", "刘 京", "刘", "刘" },
    { "foo@bar", "刘 京", "京", "京" },
    { "foo@bar", "刘京 京刘", "刘 京", "刘 京 京 刘" },
    // Transliterated unicode.
    { "foo@bar", "Владимир Путин", "vlad", "Влад"},
    { "foo@bar", "习 近平", "xi", "习" },
    { "foo@bar", "习 近平", "j", "近" },
    // Matching substring detection is a little off when asciification
    // changes the length of the string.
    { "foo@bar", "习 近平", "ji", "近平" },
    { "foo@bar", "习 近平", "jinp", "近平" },
  };

  for (int i = 0; i < ARRAYSIZE(testdata); ++i) {
    t.Clear();
    t.AddContact(testdata[i].identity, testdata[i].name, 0);
    ScopedPtr<RE2> re;
    if (testdata[i].expected.empty()) {
      EXPECT_EQ("", t.Search(testdata[i].filter, &re));
      continue;
    } else {
      EXPECT_EQ(testdata[i].identity, t.Search(testdata[i].filter, &re));
    }

    Slice s(testdata[i].name);
    string result;
    string match;
    while (RE2::FindAndConsume(&s, *re, &match)) {
      if (!result.empty()) {
        result += " ";
      }
      result += match;
    }

    EXPECT_EQ(testdata[i].expected, result);
  }
}

TEST(ContactManagerTest, Names) {
  TestContacts t;

  struct {
    string identity;
    string name;
    string first;
    string full;
  } kTestData[] = {
    { "foo1@bar", "foo bar", "foo", "foo bar" },
    { "foo2@bar", "bar foo", "bar", "bar foo" },
    { "foo3@bar", "Foo bar", "Foo", "Foo bar" },
    { "foo4@bar", "f.o.o. bar", "f.o.o.", "f.o.o. bar" },
    { "foo5@bar", "Andréa Olausson", "Andréa", "Andréa Olausson" },
    { "foo6@bar", "Jeremy O'Connor", "Jeremy", "Jeremy O'Connor" },
    { "foo7@bar", "'Nuff Said", "'Nuff", "'Nuff Said" },
    { "foo8@bar", "刘京", "刘京", "刘京" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    t.AddUser(kTestData[i].identity, i + 1, kTestData[i].name);
    EXPECT_EQ(kTestData[i].first, t.FirstName(i + 1));
    EXPECT_EQ(kTestData[i].full, t.FullName(i + 1));
  }
}

TEST(ContactManagerTest, ViewfinderContacts) {
  TestContacts t;

  const int64_t kTestData[] = { 4, 23, 1, 10, 63, 59 };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    t.AddUser(Format("%s", i), kTestData[i], Format("%s", i));
    vector<int64_t> expected(&kTestData[0], &kTestData[i + 1]);
    sort(expected.begin(), expected.end());
    EXPECT_EQ(expected, t.ViewfinderContacts());
  }
}

TEST(ContactManagerTest, QueryUsers) {
  TestContacts t;
  EXPECT_EQ("<>", t.ListQueryUsers(10));
  t.MaybeQueueUser(4);
  EXPECT_EQ("<4>", t.ListQueryUsers(10));
  t.MaybeQueueUser(8);
  EXPECT_EQ("<4 8>", t.ListQueryUsers(10));
  EXPECT_EQ("<4>", t.ListQueryUsers(1));
  t.AddUser("foo@bar", 4, "four", L(4));
  EXPECT_EQ("<8>", t.ListQueryUsers(10));
  // Query for a user that we don't have permission to query for.
  t.AddUser("foo@bar", -1, "", L(8));
  EXPECT_EQ("<>", t.ListQueryUsers(10));
}

// Verify that merged contacts are not displayed for search.
TEST(ContactManagerTest, MergedUsers) {
  TestContacts t;

  // Start with a merged contact--shouldn't show up in search.
  t.AddUser("Email:kimball.andy@emailscrubbed.com", 19, "Andrew Kimball", 11);  // merged
  EXPECT_EQ("", t.Search("andy"));
  // However, looking up the contact, as the merged user isn't available,
  // should display the original.
  ContactMetadata c;
  EXPECT(t.LookupUser(19, &c));
  EXPECT_EQ(19, c.user_id());
  EXPECT_EQ("Email:kimball.andy@emailscrubbed.com", c.primary_identity());

  // Create an unmerged contact with lesser rank. should show up in search.
  t.AddUser("Email:andy@emailscrubbed.com", 11, "Andrew Kimball", -1);  // not merged
  EXPECT_EQ("Email:andy@emailscrubbed.com[11]", t.Search("andy"));
  // Now lookup of original should return user 11.
  EXPECT(t.LookupUser(19, &c));
  EXPECT_EQ(11, c.user_id());
  EXPECT_EQ("Email:andy@emailscrubbed.com", c.primary_identity());
}

TEST(ContactManagerTest, SetMyName) {
  TestContacts t;
  t.SetUserId(1);
  EXPECT(t.SetMyName("Foo", "Bar", "Foo Bar"));
  ContactMetadata m;
  // We can't use t.FullName() and friends because they return "You" when looking up the current user.
  t.LookupUser(1, &m);
  EXPECT_EQ("Foo", m.first_name());
  EXPECT_EQ("Bar", m.last_name());
  EXPECT_EQ("Foo Bar", m.name());

  EXPECT(t.SetMyName("Foo", "Baz", "Foo Baz"));
  t.LookupUser(1, &m);
  EXPECT_EQ("Foo", m.first_name());
  EXPECT_EQ("Baz", m.last_name());
  EXPECT_EQ("Foo Baz", m.name());

  EXPECT(t.SetMyName("  asdf", "  qwer ", " asdf   qwer"));
  t.LookupUser(1, &m);
  EXPECT_EQ("asdf", m.first_name());
  EXPECT_EQ("qwer", m.last_name());
  EXPECT_EQ("asdf qwer", m.name());

  EXPECT(!t.SetMyName("", "", ""));
}

TEST(ContactManagerTest, SetFriendNickname) {
  TestContacts t;
  t.AddUser("foo", 1, "foo");
  t.AddUser("bar", 2, "bar");
  EXPECT_EQ("", t.Nickname(1));
  EXPECT_EQ("foo", t.FirstName(1));
  EXPECT_EQ("foo", t.FullName(1));
  EXPECT_EQ("", t.Nickname(2));
  EXPECT_EQ("bar", t.FirstName(2));
  EXPECT_EQ("bar", t.FullName(2));
  t.contact_manager()->SetFriendNickname(1, "Mr. Foo");
  EXPECT_EQ("Mr. Foo", t.Nickname(1));
  EXPECT_EQ("Mr. Foo", t.FirstName(1));
  EXPECT_EQ("Mr. Foo", t.FullName(1));
  EXPECT_EQ(1, t.contact_manager()->queued_update_friend());
  t.contact_manager()->SetFriendNickname(2, "Mr. Bar");
  EXPECT_EQ("Mr. Bar", t.Nickname(2));
  EXPECT_EQ("Mr. Bar", t.FirstName(2));
  EXPECT_EQ("Mr. Bar", t.FullName(2));
  EXPECT_EQ(1, t.contact_manager()->queued_update_friend());
  t.contact_manager()->CommitQueuedUpdateFriend();
  EXPECT_EQ(2, t.contact_manager()->queued_update_friend());
  t.contact_manager()->CommitQueuedUpdateFriend();
  EXPECT_EQ(0, t.contact_manager()->queued_update_friend());
}

TEST(ContactManagerTest, IsResolvableEmail) {
  EXPECT(!ContactManager::IsResolvableEmail("foo"));
  EXPECT(!ContactManager::IsResolvableEmail("foo@bar"));
  EXPECT(!ContactManager::IsResolvableEmail("foo@bar.c"));
  EXPECT(ContactManager::IsResolvableEmail("foo@bar.co"));
  EXPECT(ContactManager::IsResolvableEmail("foo@bar.com"));
  EXPECT(!ContactManager::IsResolvableEmail("foo@bar.co.u"));
  EXPECT(ContactManager::IsResolvableEmail("foo@bar.co.uk"));
}

TEST(ContactManagerTest, AddContactWithUser) {
  TestContacts t;

  t.AddContactWithUser("Email:foo@bar.com", "contact name", 0, 1);

  // Identities are transfered from the contact to the user.  Other fields are also transferred,
  // and the need_query_user flag is set.
  {
    ContactMetadata m;
    t.LookupUser(1, &m);
    EXPECT_EQ(m.primary_identity(), "Email:foo@bar.com");
    ASSERT_EQ(m.identities_size(), 1);
    EXPECT_EQ(m.identities(0).identity(), "Email:foo@bar.com");
    EXPECT_EQ(m.name(), "contact name");
    EXPECT(m.need_query_user());

    // An empty query users response doesn't change anything
    t.AddEmptyUser(1);
    ContactMetadata m2;
    t.LookupUser(1, &m2);
    m.clear_indexed_names();
    m2.clear_indexed_names();
    EXPECT_EQ(ToString(m), ToString(m2));
  }

  // The user does not yet have the registered or friend flag, so it will not show up in searches.
  EXPECT_EQ("Email:foo@bar.com", t.Search("name"));

  // query_users will fill in a name for this user and clear the need_query_user flag.
  t.AddUser("", 1, "user name");
  {
    ContactMetadata m;
    t.LookupUser(1, &m);
    EXPECT_EQ(m.primary_identity(), "Email:foo@bar.com");
    ASSERT_EQ(m.identities_size(), 1);
    EXPECT_EQ(m.identities(0).identity(), "Email:foo@bar.com");
    EXPECT_EQ(m.name(), "user name");
    EXPECT(!m.need_query_user());
  }

  // Now that the user is known, the user can be found.
  // Searches for fields common to both records will only return the user.
  EXPECT_EQ("Email:foo@bar.com[1]", t.Search("name"));
  EXPECT_EQ("Email:foo@bar.com[1]", t.Search("user"));

  // Searching for a field only in the contact won't find the user id.
  // TODO(ben): this should probably change when we implement merging.
  EXPECT_EQ("Email:foo@bar.com", t.Search("contact"));
}

TEST(ContactManagerTest, AddContactToExistingUser) {
  // Similar to the previous test, but the user comes first.
  TestContacts t;

  t.AddUser("", 1, "user name");
  t.AddContactWithUser("Phone:+14241234567", "contact name", 0, 1);

  // The identity was added but the original name remains.
  {
    ContactMetadata m;
    t.LookupUser(1, &m);
    EXPECT_EQ(m.primary_identity(), "Phone:+14241234567");
    ASSERT_EQ(m.identities_size(), 1);
    EXPECT_EQ(m.identities(0).identity(), "Phone:+14241234567");
    EXPECT_EQ(m.name(), "user name");
  }

  // Adding an additional phone number doesn't change the primary identity.
  t.AddContactWithUser("Phone:+12345678901", "contact name", 0, 1);
  {
    ContactMetadata m;
    t.LookupUser(1, &m);
    EXPECT_EQ(m.primary_identity(), "Phone:+14241234567");
    ASSERT_EQ(m.identities_size(), 2);
    EXPECT_EQ(m.identities(0).identity(), "Phone:+14241234567");
    EXPECT_EQ(m.identities(1).identity(), "Phone:+12345678901");
    EXPECT_EQ(m.name(), "user name");
  }

  // The first email identity takes over as the primary identity.
  t.AddContactWithUser("Email:ben@emailscrubbed.com", "contact name", 0, 1);
  {
    ContactMetadata m;
    t.LookupUser(1, &m);
    EXPECT_EQ(m.primary_identity(), "Email:ben@emailscrubbed.com");
    ASSERT_EQ(m.identities_size(), 3);
    EXPECT_EQ(m.identities(0).identity(), "Phone:+14241234567");
    EXPECT_EQ(m.identities(1).identity(), "Phone:+12345678901");
    EXPECT_EQ(m.identities(2).identity(), "Email:ben@emailscrubbed.com");
    EXPECT_EQ(m.name(), "user name");
  }

  // A second email doesn't change the primary.
  t.AddContactWithUser("Email:ben+test@emailscrubbed.com", "contact name", 0, 1);
  {
    ContactMetadata m;
    t.LookupUser(1, &m);
    EXPECT_EQ(m.primary_identity(), "Email:ben@emailscrubbed.com");
    ASSERT_EQ(m.identities_size(), 4);
    EXPECT_EQ(m.identities(0).identity(), "Phone:+14241234567");
    EXPECT_EQ(m.identities(1).identity(), "Phone:+12345678901");
    EXPECT_EQ(m.identities(2).identity(), "Email:ben@emailscrubbed.com");
    EXPECT_EQ(m.identities(3).identity(), "Email:ben+test@emailscrubbed.com");
    EXPECT_EQ(m.name(), "user name");
  }
}

TEST(ContactManagerTest, AddServerContactId) {
  TestContacts t;

  // Add a local contact.
  ContactMetadata m;
  m.set_name("Ben Darnell");
  m.set_primary_identity("Email:ben@emailscrubbed.com");
  m.add_identities()->set_identity("Email:ben@emailscrubbed.com");
  m.set_contact_source(ContactManager::kContactSourceManual);
  DBHandle updates = t.state()->NewDBTransaction();
  t.state()->contact_manager()->SaveContact(m, true, WallTime_Now(), updates);
  updates->Commit();

  // Search for it to get the local contact id
  vector<ContactMetadata> results;
  t.RawSearch("ben", &results);
  ASSERT_EQ(results.size(), 1);
  EXPECT_EQ(results[0].name(), "Ben Darnell");
  const string local_id = results[0].contact_id();
  ASSERT(!local_id.empty());

  // Now generate a server response for the same contact with a server contact id.
  t.AddContact("Email:ben@emailscrubbed.com", "Ben Darnell", -1);

  // Search for it and see that the server contact id was applied to the existing contact.
  results.clear();
  t.RawSearch("ben", &results);
  ASSERT_EQ(results.size(), 1);
  EXPECT_EQ(results[0].name(), "Ben Darnell");
  EXPECT_EQ(results[0].contact_id(), local_id);
  EXPECT(!results[0].server_contact_id().empty());
}

TEST(ContactManagerTest, RemoveServerContact) {
  TestContacts t;

  // Add a contact (with a server id).
  t.AddContact("Email:ben@emailscrubbed.com", "Ben Darnell", -1);

  // Search for it to get the server contact id.
  vector<ContactMetadata> results;
  t.RawSearch("ben", &results);
  ASSERT_EQ(results.size(), 1);
  EXPECT_EQ(results[0].name(), "Ben Darnell");
  ASSERT(!results[0].server_contact_id().empty());

  // Remove it via ProcessQueryContacts.
  t.RemoveServerContact(results[0].server_contact_id());

  // Search again and the contact is gone.
  results.clear();
  t.RawSearch("ben", &results);
  ASSERT_EQ(results.size(), 0);
}

TEST(ContactManagerTest, AddressBookImport) {
  TestContacts t;

  vector<ContactMetadata> addressbook(2);
  addressbook[0].set_name("Ben Darnell");
  addressbook[0].set_primary_identity("Phone:+14241234567");
  addressbook[0].add_identities()->set_identity("Phone:+14241234567");
  addressbook[0].set_contact_source(ContactManager::kContactSourceIOSAddressBook);
  addressbook[1].set_name("Peter Mattis");
  addressbook[1].set_primary_identity("Email:peter@emailscrubbed.com");
  addressbook[1].add_identities()->set_identity("Email:peter@emailscrubbed.com");
  addressbook[1].set_contact_source(ContactManager::kContactSourceIOSAddressBook);

  // Import a couple of contacts.
  t.ImportAddressBook(addressbook);

  EXPECT_EQ(t.Search("ben"), "Phone:+14241234567");
  EXPECT_EQ(t.Search("peter"), "Email:peter@emailscrubbed.com");

  // Update a contact and re-import
  addressbook[0].add_identities()->set_identity("Email:ben@emailscrubbed.com");
  addressbook[0].set_primary_identity("Email:ben@emailscrubbed.com");

  t.ImportAddressBook(addressbook);

  EXPECT_EQ(t.Search("ben"), "Email:ben@emailscrubbed.com");
  EXPECT_EQ(t.Search("peter"), "Email:peter@emailscrubbed.com");
}

TEST(ContactManagerTest, ChoosePrimaryIdentityTest) {
  // First make sure we don't break a valid contact.
  ContactMetadata m;
  m.add_identities()->set_identity("Email:foo@example.com");
  m.mutable_identities(0)->set_description("home");
  m.set_primary_identity("Email:foo@example.com");

  ContactManager::ChoosePrimaryIdentity(&m);
  EXPECT_EQ(m.identities_size(), 1);
  EXPECT_EQ(m.identities(0).identity(), "Email:foo@example.com");
  EXPECT_EQ(m.identities(0).description(), "home");
  EXPECT_EQ(m.primary_identity(), "Email:foo@example.com");

  // No primary identity set: choose the first email identity and move it to the front.
  m.Clear();
  m.add_identities()->set_identity("Phone:+14241234567");
  m.add_identities()->set_identity("Email:one@example.com");
  m.add_identities()->set_identity("Email:two@example.com");

  ContactManager::ChoosePrimaryIdentity(&m);
  EXPECT_EQ(m.primary_identity(), "Email:one@example.com");
  EXPECT_EQ(m.identities_size(), 3);
  EXPECT_EQ(m.identities(0).identity(), "Email:one@example.com");
  EXPECT_EQ(m.identities(1).identity(), "Phone:+14241234567");
  EXPECT_EQ(m.identities(2).identity(), "Email:two@example.com");
}

TEST(ContactManagerTest, NuclearInvalidate) {
  TestContacts t;
  // Create a server contact, a local contact, and a user and verify they can all be queried.
  t.AddContact("Email:server@example.com", "server name", -1);
  vector<ContactMetadata> addressbook(1);
  addressbook[0].set_name("local name");
  addressbook[0].add_identities()->set_identity("Email:local@example.com");
  addressbook[0].set_contact_source(ContactManager::kContactSourceIOSAddressBook);
  t.ImportAddressBook(addressbook);
  t.AddUser("Email:user@example.com", 1, "user name");
  EXPECT_EQ(t.Search("name"), "Email:user@example.com[1] Email:local@example.com Email:server@example.com");

  // Send an all-contacts invalidation.
  ContactSelection nuclear;
  nuclear.set_all(true);
  {
    DBHandle updates = t.state()->NewDBTransaction();
    t.contact_manager()->Invalidate(nuclear, updates);
    updates->Commit();
  }

  // The local contact was not removed because it was still pending upload.
  EXPECT_EQ(t.Search("name"), "Email:user@example.com[1] Email:local@example.com");

  // Mark all local contacts as uploaded.
  {
    DBHandle updates = t.state()->NewDBTransaction();
    t.contact_manager()->MaybeQueueUploadContacts();
    UploadContactsResponse r;
    t.contact_manager()->CommitQueuedUploadContacts(r, false);
    updates->Commit();
  }

  // Re-send the invalidation and the contacts are gone but the user remains.
  {
    DBHandle updates = t.state()->NewDBTransaction();
    t.contact_manager()->Invalidate(nuclear, updates);
    updates->Commit();
  }
  EXPECT_EQ(t.Search("name"), "Email:user@example.com[1]");
}

TEST(ContactManagerTest, UnlinkIdentity) {
  TestContacts t;

  // Create a user with two identities via contacts.
  t.AddContactWithUser("Email:one@example.com", "Test User", -1, 1);
  t.AddContactWithUser("Email:two@example.com", "Test User", -1, 1);
  // Add the user to set the registered flag and make it searchable
  t.AddUser("Email:one@example.com", 1, "Test User");

  EXPECT_EQ(t.Search("user"), "Email:one@example.com[1]");
  EXPECT_EQ(t.Search("one"), "Email:one@example.com[1]");
  EXPECT_EQ(t.Search("two"), "Email:one@example.com[1]");

  {
    // Validate the identity fields.
    ContactMetadata m;
    ASSERT(t.contact_manager()->LookupUser(1, &m));
    EXPECT_EQ(m.primary_identity(), "Email:one@example.com");
    ASSERT_EQ(m.identities_size(), 2);
    EXPECT_EQ(m.identities(0).identity(), "Email:one@example.com");
    EXPECT_EQ(m.identities(1).identity(), "Email:two@example.com");
  }

  // Unlink the first identity by reporting the contact without a user id.
  // This leaves the user with its second identity, and a separate contact with the first identity.
  t.AddContact("Email:one@example.com", "Test User", -1);
  EXPECT_EQ(t.Search("user"), "Email:two@example.com[1] Email:one@example.com");
  EXPECT_EQ(t.Search("one"), "Email:one@example.com");
  EXPECT_EQ(t.Search("two"), "Email:two@example.com[1]");

  {
    // The first identity was removed and the primary_identity reassigned.
    ContactMetadata m;
    ASSERT(t.contact_manager()->LookupUser(1, &m));
    EXPECT_EQ(m.primary_identity(), "Email:two@example.com");
    ASSERT_EQ(m.identities_size(), 1);
    EXPECT_EQ(m.identities(0).identity(), "Email:two@example.com");
  }

  // Unlink the second identity.  Since the user is not a friend, it no longer appears in search results.
  t.AddContact("Email:two@example.com", "Test User", -1);
  EXPECT_EQ(t.Search("user"), "Email:one@example.com Email:two@example.com");
  EXPECT_EQ(t.Search("one"), "Email:one@example.com");
  EXPECT_EQ(t.Search("two"), "Email:two@example.com");

  {
    // The identity fields have been cleared.
    ContactMetadata m;
    ASSERT(t.contact_manager()->LookupUser(1, &m));
    EXPECT(!m.has_primary_identity());
    ASSERT_EQ(m.identities_size(), 0);
  }
}

class ResolveContactTest : public Test {
 public:
  virtual ~ResolveContactTest() {}

  void ResolveAndWait(TestContacts* t, const ContactMetadata& m) {
    Barrier* barrier = new Barrier(1);
    ContactManager* contact_manager = t->contact_manager();
    __block int callback_id = contact_manager->contact_resolved()->Add(
        ^(const string& identity, const ContactMetadata* metadata) {
          if (identity == m.primary_identity()) {
            contact_manager->contact_changed()->Remove(callback_id);
            if (metadata) {
              resolved_metadata_.reset(new ContactMetadata(*metadata));
            } else {
              resolved_metadata_.reset(NULL);
            }
            barrier->Signal();
          }
        });

    contact_manager->ProcessResolveContact(m.primary_identity(), &m);

    barrier->Wait();
    delete barrier;
  }

 protected:
  ScopedPtr<ContactMetadata> resolved_metadata_;
};

// Create a new contact via ResolveContact
TEST_F(ResolveContactTest, ResolveNew) {
  TestContacts t;
  const string kIdentity("Email:ben@emailscrubbed.com");

  ContactMetadata m;
  m.set_primary_identity(kIdentity);
  m.set_user_id(42);
  m.set_name("Ben Darnell");

  ResolveAndWait(&t, m);

  ASSERT(resolved_metadata_.get());
  EXPECT_EQ(resolved_metadata_->primary_identity(), m.primary_identity());
  EXPECT_EQ(resolved_metadata_->user_id(), m.user_id());
  EXPECT_EQ(resolved_metadata_->name(), m.name());
}

// Resolve an unknown user; the resulting metadata does not have a user_id field.
TEST_F(ResolveContactTest, ResolveUnknown) {
  TestContacts t;
  const string kIdentity("Email:ben@emailscrubbed.com");

  ContactMetadata m;
  m.set_primary_identity(kIdentity);

  ResolveAndWait(&t, m);

  ContactMetadata queried;
  ASSERT(resolved_metadata_.get());
  EXPECT_EQ(resolved_metadata_->primary_identity(), kIdentity);
  EXPECT(!resolved_metadata_->has_user_id());
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
