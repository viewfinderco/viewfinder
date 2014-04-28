// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
// Author: Spencer Kimball.

#import <unordered_map>
#import <map>
#import <list>
#import <leveldb/cache.h>
#import <leveldb/db.h>
#import <leveldb/env.h>
#import <leveldb/status.h>
#import <leveldb/write_batch.h>
#import <google/protobuf/message_lite.h>
#import "DB.h"
#import "DBFormat.h"
#import "Logging.h"
#import "ScopedPtr.h"
#import "STLUtils.h"
#import "Utils.h"

namespace {

// Disable DBLOG statements in APPSTORE builds as they contain Personally
// Identifiable Information.
#ifdef APPSTORE
#define DBLOG  if (0) VLOG
#else
#define DBLOG  VLOG
#endif

const int kWriteBufferSize = 1024 * 1024;  // 1 MB

leveldb::Slice ToDBSlice(const Slice& s) {
  return leveldb::Slice(s.data(), s.size());
}

class LevelDBLogger : public leveldb::Logger {
 public:
  virtual void Logv(const char* format, va_list ap) {
    // The leveldb threads to not have an autorelease pool set up, but we're
    // going to call into logging code that potentially creates autoreleased
    // objective-c objects.
    dispatch_autoreleasepool([this, format, ap] {
        LogvImpl(format, ap);
      });
  }

 private:
  void LogvImpl(const char* format, va_list ap) {
    // First try with a small fixed size buffer.
    char space[1024];

    // It's possible for methods that use a va_list to invalidate the data in
    // it upon use. The fix is to make a copy of the structure before using it
    // and use that copy instead.
    va_list backup_ap;
    va_copy(backup_ap, ap);
    int result = vsnprintf(space, sizeof(space), format, backup_ap);
    va_end(backup_ap);

    if ((result >= 0) && (result < sizeof(space))) {
      VLOG("%s", Slice(space, result));
      return;
    }

    // Repeatedly increase buffer size until it fits.
    int length = sizeof(space);
    while (true) {
      if (result < 0) {
        // Older behavior: just try doubling the buffer size.
        length *= 2;
      } else {
        // We need exactly "result+1" characters.
        length = result+1;
      }
      char* buf = new char[length];

      // Restore the va_list before we use it again
      va_copy(backup_ap, ap);
      result = vsnprintf(buf, length, format, backup_ap);
      va_end(backup_ap);

      if ((result >= 0) && (result < length)) {
        // It fit
        VLOG("%s", Slice(buf, result));
        delete[] buf;
        return;
      }
      delete[] buf;
    }
  }
};

class LevelDBEnv : public leveldb::EnvWrapper {
  typedef leveldb::EnvWrapper EnvWrapper;
  typedef leveldb::FileLock FileLock;
  typedef leveldb::RandomAccessFile RandomAccessFile;
  typedef leveldb::SequentialFile SequentialFile;
  typedef leveldb::Status Status;
  typedef leveldb::WritableFile WritableFile;

 public:
  LevelDBEnv()
      : EnvWrapper(Env::Default()) {
  }

#define LOG_ENV_OP(name, op)             \
  Status s = op;                         \
  if (!s.ok()) {                         \
    LOG("%s: %s", name, s.ToString());   \
  }                                      \
  return s

  virtual Status NewSequentialFile(const std::string& fname,
                                   SequentialFile** result) {
    LOG_ENV_OP("NewSequentialFile",
               EnvWrapper::NewSequentialFile(fname, result));
  }
  virtual Status NewRandomAccessFile(const std::string& fname,
                                     RandomAccessFile** result) {
    LOG_ENV_OP("NewRandomAccessFile",
               EnvWrapper::NewRandomAccessFile(fname, result));
  }
  virtual Status NewWritableFile(const std::string& fname,
                                 WritableFile** result) {
    LOG_ENV_OP("NewWritableFile",
               EnvWrapper::NewWritableFile(fname, result));
  }

#undef LOG_ENV_OP
};

class Snapshot;
class Transaction;

// Read-write implementation of the DB interface.
class DBImpl : public DB {
 public:
  DBImpl(const string& dir);
  virtual ~DBImpl();

  bool Open(int cache_size);
  void Close();

  DBHandle NewTransaction();
  DBHandle NewSnapshot();

  bool IsTransaction() const { return false; }
  bool IsSnapshot() const { return false; }

  bool Put(const Slice& key, const Slice& value);
  bool PutProto(const Slice& key,
                const google::protobuf::MessageLite& message);
  bool Get(const Slice& key, string* value);
  bool GetProto(const Slice& key,
                google::protobuf::MessageLite* message);
  bool Exists(const Slice& key);
  bool Delete(const Slice& key);

  leveldb::Iterator* NewIterator();

  void Abandon(bool verbose_logging);
  bool Commit(bool verbose_logging);
  bool Flush(bool verbose_logging);
  bool AddCommitTrigger(const string& key, TriggerCallback trigger) { return false; }
  int tx_count() const { return 0; }

  int64_t DiskUsage();
  const string& dir() const { return dir_; }

  void MinorCompaction();

 private:
  friend class Snapshot;
  friend class Transaction;

  bool Get(const leveldb::ReadOptions& options,
           const Slice& key, string* value);
  bool GetProto(const leveldb::ReadOptions& options, const Slice& key,
                google::protobuf::MessageLite* message);
  bool Exists(const leveldb::ReadOptions& options, const Slice& key);
  leveldb::Iterator* NewIterator(const leveldb::ReadOptions& options);

 private:
  const string dir_;
  ScopedPtr<leveldb::Cache> cache_;
  ScopedPtr<leveldb::Env> env_;
  ScopedPtr<leveldb::Logger> logger_;
  ScopedPtr<leveldb::DB> db_;
};


// Pending update structure.
enum UpdateType {
  UPDATE_WRITE,
  UPDATE_DELETE,
};
struct Update {
  UpdateType type;
  string value;
  Update()
      : type(UPDATE_WRITE), value("") {
  }
  Update(UpdateType t, const Slice& v)
      : type(t), value(v.data(), v.size()) {
  }
};
typedef std::map<string, Update> UpdateMap;
typedef std::unordered_map<string, DB::TriggerCallback> TriggerMap;
typedef std::list<DB::TriggerCallback> TriggerList;


// Transactional implementation of the database.  TODO(spencer):
// there's no reason to use the underlying WriteBatch object if
// transaction type makes writes visible and we're keeping all of the
// writes in memory anyway.
class Transaction : public DB {
 private:
  class VisibleWritesIterator : public leveldb::Iterator {
   public:
    VisibleWritesIterator(Transaction* tx);

    virtual bool Valid() const;
    virtual void SeekToFirst();
    virtual void SeekToLast();
    virtual void Seek(const leveldb::Slice& target);
    virtual void Next();
    virtual void Prev();
    virtual leveldb::Slice key() const { return key_; }
    virtual leveldb::Slice value() const { return value_; }
    virtual leveldb::Status status() const { return db_iter_->status(); }

   private:
    void UpdateState(bool reverse, UpdateMap::const_iterator updates_iter);

   private:
    const UpdateMap& updates_;
    ScopedPtr<leveldb::Iterator> db_iter_;
    bool valid_;
    leveldb::Slice key_;
    leveldb::Slice value_;
  };

  friend class VisibleWritesIterator;


 public:
  Transaction(DBImpl* db);
  virtual ~Transaction();

  bool Open(int cache_size);
  void Close();

  DBHandle NewTransaction();
  DBHandle NewSnapshot();

  bool IsTransaction() const { return true; }
  bool IsSnapshot() const { return false; }

  bool Put(const Slice& key, const Slice& value);
  bool PutProto(const Slice& key,
                const google::protobuf::MessageLite& message);
  bool Get(const Slice& key, string* value);
  bool GetProto(const Slice& key,
                google::protobuf::MessageLite* message);
  bool Exists(const Slice& key);
  bool Delete(const Slice& key);
  leveldb::Iterator* NewIterator();

  void Abandon(bool verbose_logging);
  bool Commit(bool verbose_logging);
  bool Flush(bool verbose_logging);
  bool AddCommitTrigger(const string& key, TriggerCallback trigger);
  int tx_count() const { return tx_count_; }

  int64_t DiskUsage() {
    return db_->DiskUsage();
  }

  const string& dir() const { return db_->dir(); }

 private:
  DBImpl* db_;
  int tx_count_;
  UpdateMap updates_;
  TriggerMap triggers_;
  TriggerList anonymous_triggers_;
};


// Read-only snapshot implementation of database.
class Snapshot : public DB {
 public:
  Snapshot(DBImpl* db);
  Snapshot(const Snapshot& snapshot);
  virtual ~Snapshot();

  bool Open(int cache_size);
  void Close();

  DBHandle NewTransaction();
  DBHandle NewSnapshot();

  bool IsTransaction() const { return false; }
  bool IsSnapshot() const { return true; }

  bool Put(const Slice& key, const Slice& value);
  bool PutProto(const Slice& key,
                const google::protobuf::MessageLite& message);
  bool Get(const Slice& key, string* value);
  bool GetProto(const Slice& key,
                google::protobuf::MessageLite* message);
  bool Exists(const Slice& key);
  bool Delete(const Slice& key);
  leveldb::Iterator* NewIterator();

  void Abandon(bool verbose_logging);
  bool Commit(bool verbose_logging);
  bool Flush(bool verbose_logging);
  bool AddCommitTrigger(const string& key, TriggerCallback trigger) { return false; }
  int tx_count() const { return 0; }

  int64_t DiskUsage() {
    return db_->DiskUsage();
  }

  const string& dir() const { return db_->dir(); }

 private:
  DBImpl *db_;
  const leveldb::Snapshot* snapshot_;
};


////
// DBImpl

DBImpl::DBImpl(const string& dir)
    : dir_(dir) {
}

DBImpl::~DBImpl() {
  Close();
}

bool DBImpl::Open(int cache_size) {
  CHECK(!db_.get());
  cache_.reset(leveldb::NewLRUCache(cache_size));
  env_.reset(new LevelDBEnv());
  logger_.reset(new LevelDBLogger());

  leveldb::Options options;
  options.create_if_missing = true;
  options.write_buffer_size = kWriteBufferSize;
  options.max_open_files = 100;
  // NOTE(peter): The paranoid_checks option will cause leveldb to fail to
  // recover a log file if the tail of the log file is corrupted. And the tail
  // of a log file can be corrupted (according to the paranoid_checks
  // definition) in "normal" conditions if the app crashes while writing a
  // fragmented log record. Searching the interwebs, it looks like the
  // paranoid_checks option isn't used very often.
  options.paranoid_checks = false;
  options.block_cache = cache_.get();
  options.env = env_.get();
  options.info_log = logger_.get();

  leveldb::DB* db;
  leveldb::Status status = leveldb::DB::Open(options, dir_, &db);
  if (!status.ok()) {
    LOG("%s: unable to open: %s", dir_, status.ToString());
    return false;
  }
  db_.reset(db);

  string value;
  if (db_->GetProperty("leveldb.sstables", &value)) {
    VLOG("leveldb sstables:\n%s", value);
  }
  return true;
}

void DBImpl::Close() {
  db_.reset(NULL);
}

DBHandle DBImpl::NewTransaction() {
  return DBHandle(new Transaction(this));
}

DBHandle DBImpl::NewSnapshot() {
  return DBHandle(new Snapshot(this));
}

bool DBImpl::Put(const Slice& key, const Slice& value) {
  CHECK(db_.get());
  DBLOG("put: %s", DBIntrospect::Format(key, value));
  leveldb::Status status =
      db_->Put(leveldb::WriteOptions(), ToDBSlice(key), ToDBSlice(value));
  if (!status.ok()) {
    DIE("%s: put failed: %s", dir_, status.ToString());
  }
  return status.ok();
}

bool DBImpl::PutProto(const Slice& key,
                      const google::protobuf::MessageLite& message) {
  return Put(key, message.SerializeAsString());
}

bool DBImpl::Get(const Slice& key, string* value) {
  leveldb::ReadOptions options;
  options.fill_cache = true;
  return Get(options, key, value);
}

bool DBImpl::GetProto(const Slice& key,
                      google::protobuf::MessageLite* message) {
  leveldb::ReadOptions options;
  options.fill_cache = true;
  return GetProto(options, key, message);
}

bool DBImpl::Exists(const Slice& key) {
  leveldb::ReadOptions options;
  options.fill_cache = true;
  return Exists(options, key);
}

bool DBImpl::Delete(const Slice& key) {
  CHECK(db_.get());
  DBLOG("del: %s", DBIntrospect::Format(key));
  leveldb::Status status =
      db_->Delete(leveldb::WriteOptions(), ToDBSlice(key));
  if (!status.ok()) {
    DIE("%s: delete failed: %s", dir_, status.ToString());
  }
  return status.ok();
}

leveldb::Iterator* DBImpl::NewIterator() {
  leveldb::ReadOptions options;
  options.fill_cache = true;
  return NewIterator(options);
}

void DBImpl::Abandon(bool verbose_logging) {
  DIE("cannot commit non-transactional database");
}

bool DBImpl::Commit(bool verbose_logging) {
  DIE("cannot commit non-transactional database");
  return false;
}

bool DBImpl::Flush(bool verbose_logging) {
  DIE("cannot commit non-transactional database");
  return false;
}

int64_t DBImpl::DiskUsage() {
  leveldb::Range r;
  r.limit = "\xff";
  uint64_t size = 0;
  db_->GetApproximateSizes(&r, 1, &size);
  return size;
}

bool DBImpl::Get(const leveldb::ReadOptions& options,
                 const Slice& key, string* value) {
  CHECK(db_.get());
  leveldb::Status status = db_->Get(options, ToDBSlice(key), value);
  if (!status.ok() && !status.IsNotFound()) {
    // TODO(peter): Rather than immediately exiting, we should present a
    // helpful alert to the user and the exit. Tricky part is that we want to
    // stop DB processing while the alert is being presented.
    DIE("%s: get failed: %s", dir_, status.ToString());
  }
  return status.ok();
}

bool DBImpl::GetProto(const leveldb::ReadOptions& options, const Slice& key,
                      google::protobuf::MessageLite* message) {
  string value;
  if (!Get(options, key, &value)) {
    return false;
  }
  return message->ParseFromString(value);
}

bool DBImpl::Exists(const leveldb::ReadOptions& options, const Slice& key) {
  string tmp;
  return Get(options, key, &tmp);
}

leveldb::Iterator* DBImpl::NewIterator(const leveldb::ReadOptions& options) {
  CHECK(db_.get());
  return db_->NewIterator(options);
}

void DBImpl::MinorCompaction() {
  // NOTE(ben): CompactRange flushes the memtable to disk, but because the empty range
  // (start==end=="", which is different from using NULL pointers) contains no data
  // no other on-disk tables will be compacted.  There is a TODO in the leveldb code to
  // change this (so that the memtable will only be compacted when it contains data covered
  // by the requested range), but hopefully it won't be changed unless they add an
  // explicit API to trigger a minor compaction.
  leveldb::Slice start, end;
  db_->CompactRange(&start, &end);
}


////
// Transaction

Transaction::Transaction(DBImpl* db)
    : db_(db),
      tx_count_(0) {
}

Transaction::~Transaction() {
  CHECK_EQ(0, tx_count_);
}

bool Transaction::Open(int cache_size) {
  DIE("cannot open derivative database");
  return false;
}

void Transaction::Close() {
  DIE("cannot close derivative database");
}

DBHandle Transaction::NewTransaction() {
  return db_->NewTransaction();
}

DBHandle Transaction::NewSnapshot() {
  return db_->NewSnapshot();
}

bool Transaction::Put(const Slice& key, const Slice& value) {
  updates_[ToString(key)] = Update(UPDATE_WRITE, value);
  ++tx_count_;
  return true;
}

bool Transaction::PutProto(const Slice& key,
                           const google::protobuf::MessageLite& message) {
  return Put(key, message.SerializeAsString());
}

bool Transaction::Get(const Slice& key, string* value) {
  if (ContainsKey(updates_, ToString(key))) {
    if (updates_[ToString(key)].type == UPDATE_DELETE) {
      return false;
    }
    *value = updates_[ToString(key)].value;
    return true;
  }
  return db_->Get(key, value);
}

bool Transaction::GetProto(const Slice& key,
                           google::protobuf::MessageLite* message) {
  string value;
  if (!Get(key, &value)) {
    return false;
  }
  return message->ParseFromString(value);
}

bool Transaction::Exists(const Slice& key) {
  if (ContainsKey(updates_, ToString(key))) {
    return updates_[ToString(key)].type != UPDATE_DELETE;
  }
  return db_->Exists(key);
}

bool Transaction::Delete(const Slice& key) {
  updates_[ToString(key)] = Update(UPDATE_DELETE, "");
  ++tx_count_;
  return true;
}

leveldb::Iterator* Transaction::NewIterator() {
  return new VisibleWritesIterator(this);
}

void Transaction::Abandon(bool verbose_logging) {
  if (verbose_logging) {
    DBLOG("*** abandoning commit ***");
    for (int index = 0; !updates_.empty(); ++index) {
      UpdateMap::iterator iter = updates_.begin();
      const Update& u = iter->second;
      if (u.type == UPDATE_WRITE) {
        DBLOG("put(%d): %s", index, DBIntrospect::Format(iter->first, u.value));
      } else {
        DBLOG("del(%d): %s", index, DBIntrospect::Format(iter->first));
      }
      updates_.erase(iter);
    }
  } else {
    updates_.clear();
  }
  tx_count_ = 0;
  triggers_.clear();
  anonymous_triggers_.clear();
}

bool Transaction::Flush(bool verbose_logging) {
  leveldb::WriteBatch batch;
  for (int index = 0; !updates_.empty(); ++index) {
    UpdateMap::iterator iter = updates_.begin();
    const Update& u = iter->second;
    if (u.type == UPDATE_WRITE) {
      if (verbose_logging) {
        DBLOG("put(%d): %s", index, DBIntrospect::Format(iter->first, u.value));
      } else {
        DBLOG("put(%d): %s [%d]", index, DBIntrospect::Format(iter->first), u.value.size());
      }
      batch.Put(ToDBSlice(iter->first), ToDBSlice(u.value));
    } else {
      DBLOG("del(%d): %s", index, DBIntrospect::Format(iter->first));
      batch.Delete(ToDBSlice(iter->first));
    }
    updates_.erase(iter);
  }
  leveldb::Status status = db_->db_->Write(leveldb::WriteOptions(), &batch);
  if (!status.ok()) {
    DIE("%s: batch put failed: %s", db_->dir(), status.ToString());
    Abandon(false);
    return false;
  }
  tx_count_ = 0;
  return true;
}

bool Transaction::Commit(bool verbose_logging) {
  if (!Flush(verbose_logging)) {
    return false;
  }
  for (TriggerMap::iterator iter = triggers_.begin();
       iter != triggers_.end();
       ++iter) {
    iter->second();
  }
  triggers_.clear();
  for (TriggerList::iterator iter = anonymous_triggers_.begin();
       iter != anonymous_triggers_.end();
       ++iter) {
    (*iter)();
  }
  anonymous_triggers_.clear();
  return true;
}

bool Transaction::AddCommitTrigger(
    const string& key, TriggerCallback trigger) {
  if (!trigger) {
    return false;
  }
  if (key.empty()) {
    anonymous_triggers_.push_back(trigger);
  } else {
    triggers_[key] = trigger;
  }
  return true;
}

Transaction::VisibleWritesIterator::VisibleWritesIterator(
    Transaction* tx)
    : updates_(tx->updates_),
      db_iter_(tx->db_->NewIterator()),
      valid_(false) {
}

bool Transaction::VisibleWritesIterator::Valid() const {
  return valid_;
}

void Transaction::VisibleWritesIterator::SeekToFirst() {
  db_iter_->SeekToFirst();
  UpdateState(false, updates_.begin());
}

void Transaction::VisibleWritesIterator::SeekToLast() {
  db_iter_->SeekToLast();
  UpdateMap::const_iterator updates_iter = updates_.end();
  if (updates_iter != updates_.begin()) {
    --updates_iter;
  }
  UpdateState(true, updates_iter);
}

void Transaction::VisibleWritesIterator::Seek(const leveldb::Slice& target) {
  db_iter_->Seek(target);
  UpdateMap::const_iterator updates_iter = updates_.lower_bound(target.ToString());
  UpdateState(false, updates_iter);
}

void Transaction::VisibleWritesIterator::Next() {
  if (Valid()) {
    const string last_key = key_.ToString();
    while (db_iter_->Valid() && db_iter_->key().ToString() <= last_key) {
      db_iter_->Next();
    }
    UpdateMap::const_iterator updates_iter = updates_.upper_bound(last_key);
    UpdateState(false, updates_iter);
  }
}

void Transaction::VisibleWritesIterator::Prev() {
  if (Valid()) {
    const string last_key = key_.ToString();
    while (db_iter_->Valid() && db_iter_->key().ToString() >= last_key) {
      db_iter_->Prev();
    }
    UpdateMap::const_iterator updates_iter = updates_.lower_bound(last_key);
    if (updates_iter == updates_.end() || updates_iter->first >= last_key) {
      if (updates_iter == updates_.begin()) {
        updates_iter = updates_.end();
      } else {
        --updates_iter;
      }
    }
    UpdateState(true, updates_iter);
  }
}

void Transaction::VisibleWritesIterator::UpdateState(
    bool reverse, UpdateMap::const_iterator updates_iter) {
  do {
    if (updates_iter != updates_.end() &&
        (!db_iter_->Valid() ||
         (reverse ?
          Slice(updates_iter->first) >= ToSlice(db_iter_->key()) :
          Slice(updates_iter->first) <= ToSlice(db_iter_->key())))) {
      // Advance db iterator in case keys are equal.
      if (db_iter_->Valid() && Slice(updates_iter->first) == ToSlice(db_iter_->key())) {
        if (reverse) {
          db_iter_->Prev();
        } else {
          db_iter_->Next();
        }
      }
      const bool is_write = updates_iter->second.type == UPDATE_WRITE;
      if (is_write) {
        key_ = leveldb::Slice(updates_iter->first);
        value_ = leveldb::Slice(updates_iter->second.value);
        valid_ = true;
        break;
      } else {
        // On delete, advance iterator.
        if (reverse) {
          if (updates_iter != updates_.begin()) {
            --updates_iter;
          } else {
            updates_iter = updates_.end();
          }
        } else {
          ++updates_iter;
        }
      }
    } else if (db_iter_->Valid()) {
      key_ = db_iter_->key();
      value_ = db_iter_->value();
      valid_ = true;
      break;
    } else {
      valid_ = false;
      break;
    }
  } while (1);
}


////
// Snapshot

Snapshot::Snapshot(DBImpl* db)
    : db_(db),
      snapshot_(db_->db_->GetSnapshot()) {
  //LOG("created snapshot %p", this);
}

Snapshot::Snapshot(const Snapshot& snapshot)
    : db_(snapshot.db_),
      snapshot_(db_->db_->GetSnapshot()) {
  //LOG("created copy snapshot %p", this);
}

Snapshot::~Snapshot() {
  db_->db_->ReleaseSnapshot(snapshot_);
  //LOG("deleted snapshot %p", this);
}

bool Snapshot::Open(int cache_size) {
  DIE("cannot open derivative database");
  return false;
}

void Snapshot::Close() {
  DIE("cannot close derivative database");
}

DBHandle Snapshot::NewTransaction() {
  DIE("snapshot database does not allow transactions");
  return DBHandle();
}

DBHandle Snapshot::NewSnapshot() {
  return DBHandle(new Snapshot(*this));
}

bool Snapshot::Put(const Slice& key, const Slice& value) {
  DIE("snapshot database does not allow writes");
  return false;
}

bool Snapshot::PutProto(const Slice& key,
                        const google::protobuf::MessageLite& message) {
  DIE("snapshot database does not allow writes");
  return false;
}

bool Snapshot::Get(const Slice& key, string* value) {
  leveldb::ReadOptions options;
  options.fill_cache = true;
  options.snapshot = snapshot_;
  return db_->Get(options, key, value);
}

bool Snapshot::GetProto(const Slice& key,
                        google::protobuf::MessageLite* message) {
  leveldb::ReadOptions options;
  options.fill_cache = true;
  options.snapshot = snapshot_;
  return db_->GetProto(options, key, message);
}

bool Snapshot::Exists(const Slice& key) {
  leveldb::ReadOptions options;
  options.fill_cache = true;
  options.snapshot = snapshot_;
  return db_->Exists(options, key);
}

bool Snapshot::Delete(const Slice& key) {
  DIE("snapshot database does not allow writes");
  return false;
}

leveldb::Iterator* Snapshot::NewIterator() {
  leveldb::ReadOptions options;
  options.fill_cache = true;
  options.snapshot = snapshot_;
  return db_->NewIterator(options);
}

void Snapshot::Abandon(bool verbose_logging) {
  DIE("snapshot database does not allow writes");
}

bool Snapshot::Commit(bool verbose_logging) {
  DIE("snapshot database does not allow writes");
  return false;
}

bool Snapshot::Flush(bool verbose_logging) {
  DIE("snapshot database does not allow writes");
  return false;
}

}  // namespace


DBHandle NewDB(const string& dir) {
  return DBHandle(new DBImpl(dir));
}
