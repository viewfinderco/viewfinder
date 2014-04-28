// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_DB_H
#define VIEWFINDER_DB_H

#import <functional>
#import <leveldb/slice.h>
#import <leveldb/iterator.h>
#import "Callback.h"
#import "ScopedHandle.h"
#import "StringUtils.h"
#import "ScopedPtr.h"

namespace google {
namespace protobuf {
class MessageLite;
}  // namespace protobuf
}  // namespace google

inline Slice ToSlice(const leveldb::Slice& s) {
  return Slice(s.data(), s.size());
}

class DB {
  friend class ScopedHandle<DB>;

 public:
  // Facilitates iteration over subset of keys matching specified prefix.
  class PrefixIterator {
   public:
    PrefixIterator(const ScopedHandle<DB>& db, const Slice& prefix) {
      iter_.reset(db->NewIterator());
      prefix_ = prefix.as_string();
      iter_->Seek(leveldb::Slice(prefix.data(), prefix.size()));
    }

    // An iterator is either positioned at a key/value pair or the
    // iteration is complete. This method returns false iff the iteration is complete.
    bool Valid() const {
      return iter_->Valid() && iter_->key().starts_with(leveldb::Slice(prefix_));
    }

    // Moves to the next entry in the source.  After this call, done() is
    // true iff the iterator was positioned at the last entry in the source.
    void Next() { iter_->Next(); }

    // Return the key for the current entry.  The underlying storage for
    // the returned slice is valid only until the next modification of
    // the iterator.
    Slice key() const { return ToSlice(iter_->key()); }

    // Return the value for the current entry.  The underlying storage for
    // the returned slice is valid only until the next modification of
    // the iterator.
    Slice value() const { return ToSlice(iter_->value()); }

   private:
    ScopedPtr<leveldb::Iterator>  iter_;
    string                        prefix_;
  };

protected:
 public:
  virtual bool Open(int cache_size) = 0;
  virtual void Close() = 0;

  // Creates a transactional database which batches all writes
  // into an atomic update. The contents may be committed or
  // abandoned by calling Commit() or Abandon() respectively.
  //
  // Writes and deletions to the underlying database done as part of
  // this batch are visible to all read methods (e.g., Get, Exists,
  // & iterators).
  //
  // NOTE: The isolation level of the returned database is
  // "read-committed". Repeated reads of the same key may yield
  // different values in the case of concurrent writers.
  //
  // The returned DB is NOT thread-safe.
  virtual ScopedHandle<DB> NewTransaction() = 0;

  // Creates a snapshot of the underlying database.
  //
  // The returned database is thread-safe and read-only.
  virtual ScopedHandle<DB> NewSnapshot() = 0;

  virtual bool IsTransaction() const = 0;
  virtual bool IsSnapshot() const = 0;

  virtual bool Put(const Slice& key, const Slice& value) = 0;
  virtual bool PutProto(const Slice& key,
                        const google::protobuf::MessageLite& message) = 0;
  bool Put(const Slice& key, const string& value) {
    return Put(key, Slice(value));
  }
  template <typename T>
  bool Put(const Slice& key, const T& value) {
    return Put(key, ToString<T>(value));
  }
  template <typename T>
  bool Put(const string& key, const T& value) {
    return Put(Slice(key), value);
  }

  virtual bool Get(const Slice& key, string* value) = 0;
  bool Get(const string& key, string* value) {
    return Get(Slice(key), value);
  }

  virtual bool GetProto(const Slice& key,
                        google::protobuf::MessageLite* message) = 0;

  template <typename T>
  T Get(const Slice& key, const T& default_value = T()) {
    string value;
    if (!Get(key, &value)) {
      return default_value;
    }
    T res;
    FromString(value, &res);
    return res;
  }
  template <typename T>
  T Get(const string& key, const T& default_value = T()) {
    return Get<T>(Slice(key), default_value);
  }
  template <typename T>
  T Get(const char* key, const T& default_value = T()) {
    return Get<T>(Slice(key), default_value);
  }

  virtual bool Exists(const Slice& key) = 0;
  bool Exists(const string& key) {
    return Exists(Slice(key));
  }
  virtual bool Delete(const Slice& key) = 0;
  bool Delete(const string& key) {
    return Delete(Slice(key));
  }

  virtual leveldb::Iterator* NewIterator() = 0;

  // Abandons pending changes. Clears all commit triggers.
  virtual void Abandon(bool verbose_logging = false) = 0;

  // Commits pending changes. Invokes all commit triggers and
  // clears the callback set.
  virtual bool Commit(bool verbose_logging = true) = 0;

  // Commits all pending changes to the database without running commit callbacks.
  // This is useful to break up large writes, which are inefficient in leveldb.
  // However, calling Flush() gives up transactional atomicity - each flush
  // is a separate write which will be visible to other threads while the
  // transaction continues.
  virtual bool Flush(bool verbose_logging = true) = 0;

  // Trigger callbacks to invoke on Commit(). These are not called on
  // Abandon(). Triggers are invoked only once, on first commit. Only
  // the latest trigger callback for a specified "key" is retained and
  // invoked on commit. Returns true if the trigger was added; false
  // otherwise. If "key" is empty, all trigger callbacks are retained.
  typedef Callback<void ()> TriggerCallback;
  virtual bool AddCommitTrigger(const string& key, TriggerCallback trigger) = 0;

  // Returns the number of operations currently pending.
  virtual int tx_count() const = 0;

  virtual int64_t DiskUsage() = 0;

  virtual const string& dir() const = 0;

  // Prepares for a possible shutdown by writing in-memory data to
  // disk in an efficiently-loadable form.  Writes are always
  // persisted to disk as they happen, but in a log form that requires
  // some work to recover at the next launch.  Calling MinorCompaction
  // before shutting down will speed up the next launch of the app.
  virtual void MinorCompaction() { };

 protected:
  virtual ~DB() {}

 private:
  void Ref() {
    refcount_.Ref();
  }

  void Unref() {
    if (refcount_.Unref()) {
      delete this;
    }
  }

 private:
  AtomicRefCount refcount_;
};

typedef ScopedHandle<DB> DBHandle;

// Creates database using specified directory for data.
DBHandle NewDB(const string& dir);

#endif // VIEWFINDER_DB_H
