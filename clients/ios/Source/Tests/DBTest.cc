// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#import <math.h>
#import <vector>
#import <leveldb/iterator.h>
#import "DB.h"
#import "DBFormat.h"
#import "ScopedPtr.h"
#import "Testing.h"

namespace {

const double kEpsilon = 0.00001;

const DBRegisterKeyIntrospect kEmptyPrefixKeyIntrospect("/", NULL, NULL);

class DBTest : public Test {
 public:
  DBTest()
      : db_(NewDB(dir_.dir())) {
    CHECK(db_->Open(1024 * 1024));
  }

  string FullScan(const DBHandle& db) {
    string result;
    ScopedPtr<leveldb::Iterator> iter(db->NewIterator());
    for (iter->Seek(""); iter->Valid(); iter->Next()) {
      if (!result.empty()) {
        result.append(" ");
      }
      result.append(iter->key().ToString());
      result.append(":");
      result.append(iter->value().ToString());
    }
    return result;
  }

  string FullReverseScan(const DBHandle& db) {
    string result;
    ScopedPtr<leveldb::Iterator> iter(db->NewIterator());
    for (iter->SeekToLast(); iter->Valid(); iter->Prev()) {
      if (!result.empty()) {
        result.append(" ");
      }
      result.append(iter->key().ToString());
      result.append(":");
      result.append(iter->value().ToString());
    }
    return result;
  }

 protected:
  TestTmpDir dir_;
  DBHandle db_;
};

TEST_F(DBTest, GetPutInt32) {
  const int32_t a_value = 1;
  EXPECT(db_->Put(Slice("/a"), a_value));
  EXPECT_EQ(a_value, db_->Get<int32_t>("/a"));
  const int32_t def_value = 0;
  EXPECT_EQ(a_value, db_->Get<int>("/a"));
  EXPECT_EQ(a_value, db_->Get("/a", def_value));
  EXPECT_EQ(def_value, db_->Get("/b", def_value));
  const int32_t new_value = -1;
  EXPECT(db_->Put(Slice("/a"), new_value));
  EXPECT_EQ(new_value, db_->Get<int32_t>("/a"));
}

TEST_F(DBTest, GetPutInt64) {
  EXPECT(db_->Put<int64_t>(Slice("/a"), 1LL<<32));
  EXPECT_EQ(1LL<<32, db_->Get<int64_t>("/a", 0));
  EXPECT_EQ(1LL<<32, db_->Get<int64_t>("/b", 1LL<<32));
  EXPECT(db_->Put<int64_t>(Slice("/a"), -1));
  EXPECT_EQ(-1, db_->Get<int64_t>("/a", 0));
}

TEST_F(DBTest, GetPutFloat) {
  EXPECT(db_->Put(Slice("/a"), 1.1));
  // TODO(spencer): this is not equal...
  //EXPECT_EQ(1.1, db_->Get<float>("/a", 0.0));
  EXPECT(fabs(1.1 - db_->Get<float>("/a", 0.0)) < kEpsilon);
  EXPECT_EQ(1, db_->Get<float>("/b", 1));
  EXPECT(db_->Put<float>(Slice("/a"), -1.1));
  //EXPECT_EQ(-1.1, db_->Get<float>("/a", 0));
  EXPECT(fabs(-1.1 - db_->Get<float>("/a", 0.0)) < kEpsilon);
}

TEST_F(DBTest, GetPutDouble) {
  EXPECT(db_->Put<double>(Slice("/a"), 1.1));
  EXPECT_EQ(1.1, db_->Get<double>("/a", 0.0));
  EXPECT_EQ(1.1, db_->Get<double>("/b", 1.1));
  EXPECT(db_->Put<double>(Slice("/a"), -1.1));
  EXPECT_EQ(-1.1, db_->Get<double>("/a", 0.0));
}

TEST_F(DBTest, GetString) {
  EXPECT(db_->Put(Slice("/a"), "foo"));
  EXPECT_EQ("foo", db_->Get<string>("/a"));
  EXPECT_EQ("foo", db_->Get<string>("/a", "default"));
  EXPECT_EQ("default", db_->Get<string>("/b", "default"));
  EXPECT(db_->Put<string>(Slice("/a"), "bar"));
  EXPECT_EQ("bar", db_->Get<string>("/a", "foo"));
}

TEST_F(DBTest, EmptyIterator) {
  ScopedPtr<leveldb::Iterator> iter(db_->NewIterator());
  EXPECT(!iter->Valid());
  iter->SeekToFirst();
  EXPECT(!iter->Valid());
  iter->SeekToLast();
  EXPECT(!iter->Valid());
}

TEST_F(DBTest, Iterator) {
  EXPECT(db_->Put(Slice("/a"), "foo"));
  EXPECT(db_->Put(Slice("/b"), "bar"));
  EXPECT(db_->Put(Slice("/c"), "baz"));
  ScopedPtr<leveldb::Iterator> iter(db_->NewIterator());
  EXPECT(!iter->Valid());
  iter->Seek("");
  EXPECT(iter->Valid());
  EXPECT_EQ("/a", iter->key().ToString());
  EXPECT_EQ("foo", iter->value().ToString());
  iter->Next();
  EXPECT_EQ("/b", iter->key().ToString());
  EXPECT_EQ("bar", iter->value().ToString());
  iter->Next();
  EXPECT_EQ("/c", iter->key().ToString());
  EXPECT_EQ("baz", iter->value().ToString());
  iter->Next();
  EXPECT(!iter->Valid());

  iter->SeekToFirst();
  EXPECT_EQ("/a", iter->key().ToString());
  EXPECT_EQ("foo", iter->value().ToString());

  iter->SeekToLast();
  EXPECT_EQ("/c", iter->key().ToString());
  EXPECT_EQ("baz", iter->value().ToString());
  iter->Prev();
  EXPECT_EQ("/b", iter->key().ToString());
  EXPECT_EQ("bar", iter->value().ToString());
  iter->Prev();
  EXPECT_EQ("/a", iter->key().ToString());
  EXPECT_EQ("foo", iter->value().ToString());
  iter->Prev();
  EXPECT(!iter->Valid());
}

TEST_F(DBTest, Snapshot) {
  db_->Put(Slice("/a"), 1);
  db_->Put(Slice("/b"), 2);
  db_->Put(Slice("/c"), 3);
  EXPECT_EQ("/a:1 /b:2 /c:3", FullScan(db_));
  DBHandle snap = db_->NewSnapshot();
  EXPECT_EQ(1, snap->Get<int>("/a"));
  EXPECT_EQ(2, snap->Get<int>("/b"));
  EXPECT_EQ(3, snap->Get<int>("/c"));
  db_->Put(Slice("/a"), -1);
  db_->Put(Slice("/d"), 4);
  EXPECT_EQ(-1, db_->Get<int>("/a"));
  db_->Delete(Slice("/b"));
  EXPECT_EQ(0, db_->Get<int>("/b", 0));
  EXPECT_EQ(1, snap->Get<int>("/a"));
  EXPECT_EQ(2, snap->Get<int>("/b"));
  EXPECT_EQ(3, snap->Get<int>("/c"));
  EXPECT(!snap->Get<int>("/d"));
}

TEST_F(DBTest, VisibleWrites) {
  DBHandle tx = db_->NewTransaction();
  tx->Put(Slice("/a"), 1);
  EXPECT_EQ(1, tx->Get<int>("/a"));
  EXPECT(!db_->Get<int>("/a"));
  tx->Put(Slice("/b"), 2);
  EXPECT_EQ(2, tx->Get<int>("/b"));
  EXPECT(!db_->Get<int>("/b"));
  tx->Commit();
  EXPECT_EQ("/a:1 /b:2", FullScan(tx));
  EXPECT_EQ("/b:2 /a:1", FullReverseScan(tx));
  EXPECT_EQ("/a:1 /b:2", FullScan(db_));
  EXPECT_EQ("/b:2 /a:1", FullReverseScan(db_));

  tx->Put(Slice("/c"), 3);
  EXPECT_EQ(3, tx->Get<int>("/c"));
  EXPECT(!db_->Get<int>("/c"));
  tx->Abandon();
  EXPECT_EQ("/a:1 /b:2", FullScan(tx));
  EXPECT_EQ("/b:2 /a:1", FullReverseScan(tx));
  EXPECT_EQ("/a:1 /b:2", FullScan(db_));
  EXPECT_EQ("/b:2 /a:1", FullReverseScan(db_));
}

TEST_F(DBTest, VisibleWritesForeach) {
  DBHandle tx = db_->NewTransaction();
  tx->Put(Slice("/b"), 1);
  tx->Put(Slice("/d"), 2);
  tx->Put(Slice("/f"), 3);
  EXPECT_EQ("/b:1 /d:2 /f:3", FullScan(tx));
  EXPECT_EQ("/f:3 /d:2 /b:1", FullReverseScan(tx));
  EXPECT_EQ("", FullScan(db_));
  tx->Commit();

  tx->Put(Slice("/a"), 4);
  tx->Put(Slice("/c"), 5);
  tx->Put(Slice("/e"), 6);
  EXPECT_EQ("/a:4 /b:1 /c:5 /d:2 /e:6 /f:3", FullScan(tx));
  EXPECT_EQ("/f:3 /e:6 /d:2 /c:5 /b:1 /a:4", FullReverseScan(tx));
  EXPECT_EQ("/b:1 /d:2 /f:3", FullScan(db_));
  tx->Commit();
  EXPECT_EQ("/a:4 /b:1 /c:5 /d:2 /e:6 /f:3", FullScan(db_));
  EXPECT_EQ("/f:3 /e:6 /d:2 /c:5 /b:1 /a:4", FullReverseScan(db_));
}

TEST_F(DBTest, TransactionIteratorWithDelete) {
  db_->Put(Slice("/a"), 1);
  db_->Put(Slice("/b"), 2);
  db_->Put(Slice("/c"), 3);
  DBHandle tx = db_->NewTransaction();
  tx->Delete(Slice("/a"));
  ScopedPtr<leveldb::Iterator> iter(tx->NewIterator());
  iter->SeekToFirst();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/b");
  iter->Next();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/c");
  iter->Next();
  EXPECT(!iter->Valid());
  tx->Commit();
}

TEST_F(DBTest, TransactionReverseIterator) {
  db_->Put(Slice("/a"), 1);
  db_->Put(Slice("/d"), 4);
  DBHandle tx = db_->NewTransaction();
  tx->Put(Slice("/b"), 2);
  ScopedPtr<leveldb::Iterator> iter(tx->NewIterator());
  iter->Seek("/c");
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/d");
  iter->Prev();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/b");
  iter->Prev();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/a");
  tx->Commit();
}

TEST_F(DBTest, TransactionReverseIteratorWithDeleteFirstKey) {
  db_->Put(Slice("/a"), 1);
  db_->Put(Slice("/b"), 1);
  DBHandle tx = db_->NewTransaction();
  tx->Delete(Slice("/a"));
  ScopedPtr<leveldb::Iterator> iter(tx->NewIterator());
  iter->SeekToLast();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/b");
  iter->Prev();
  EXPECT(!iter->Valid());
  tx->Commit();
}

TEST_F(DBTest, TransactionReverseIteratorWithDeleteLastKey) {
  db_->Put(Slice("/a"), 1);
  db_->Put(Slice("/b"), 2);
  db_->Put(Slice("/c"), 3);
  DBHandle tx = db_->NewTransaction();
  tx->Delete(Slice("/c"));
  ScopedPtr<leveldb::Iterator> iter(tx->NewIterator());
  iter->SeekToLast();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/b");
  iter->Prev();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/a");
  iter->Prev();
  EXPECT(!iter->Valid());
  tx->Commit();
}

// Try a reverse iteration where both the updates iterator
// and db iterator have valid positions on the initial seek.
TEST_F(DBTest, TransactionReverseIteratorBothValid) {
  db_->Put(Slice("/a"), 1);
  db_->Put(Slice("/d"), 1);
  db_->Put(Slice("/h"), 1);
  DBHandle tx = db_->NewTransaction();
  tx->Put(Slice("/b"), 1);
  tx->Put(Slice("/e"), 1);
  tx->Put(Slice("/g"), 1);
  ScopedPtr<leveldb::Iterator> iter(tx->NewIterator());
  iter->Seek("/c");
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/d");
  iter->Prev();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/b");
  iter->Prev();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/a");
  iter->Prev();
  EXPECT(!iter->Valid());

  iter->Seek("/f");
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/g");
  iter->Prev();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/e");
  iter->Prev();
  EXPECT(iter->Valid());
  EXPECT_EQ(ToSlice(iter->key()), "/d");

  tx->Commit();
}

}  // namespace

#endif  // TESTING
