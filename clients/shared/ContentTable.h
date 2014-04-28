// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_CONTENT_TABLE_H
#define VIEWFINDER_CONTENT_TABLE_H

#import <unordered_map>
#import <leveldb/iterator.h>
#import "AppState.h"
#import "DB.h"
#import "Mutex.h"
#import "ScopedHandle.h"
#import "ScopedPtr.h"
#import "ServerId.h"
#import "STLUtils.h"
#import "StringUtils.h"

string EncodeContentKey(const string& prefix, int64_t local_id);
string EncodeContentServerKey(const string& prefix, const string& server_id);

// ContentTable is thread-safe and ContentHandle is thread-safe, but
// individual Content objects are not.
template <typename T>
class ContentTable {
 public:
  // Content is a subclass of the templated metadata plus in-memory
  // state, such as uncommitted changes. The Content class is
  // reference counted and ContentTable guarantees there is only one
  // Content object for each content id.
  class Content : public T {
    friend class ContentTable;
    friend class ScopedHandle<Content>;

   public:
    // Saves the content to the database, but maintains lock
    // for further modifications.
    void Save(const DBHandle& updates) {
      CHECK(locked_);
      CHECK_EQ(disk_local_id_, this->local_id());

      if (disk_server_id_ != this->server_id()) {
        if (!disk_server_id_.empty()) {
          updates->Delete(table_->content_server_key(disk_server_id_));
        }
        disk_server_id_ = this->server_id();
        if (!disk_server_id_.empty()) {
          updates->Put(table_->content_server_key(disk_server_id_), disk_local_id_);
        }
      }

      // Call table's save hook.
      // NOTE: do not change the ordering here, as EpisodeTable relies on the
      //   table save hook being called before the superclass save.
      table_->SaveContentHook(this, updates);

      // Call superclass save.
      T::SaveHook(updates);

      // The superclass save might have changed "this", so output it last.
      updates->PutProto(table_->content_key(disk_local_id_), *this);
    }

    // Deletes the content from the database and releases lock.
    void DeleteAndUnlock(const DBHandle& updates) {
      CHECK(locked_);
      deleted_ = true;

      updates->Delete(table_->content_server_key(disk_server_id_));

      // Call table's delete hook.
      table_->DeleteContentHook(this, updates);

      // Call superclass save.
      T::DeleteHook(updates);

      // The superclass save might have changed "this", so output it last.
      updates->Delete(table_->content_key(disk_local_id_));

      Unlock();
    }

    // Save the content to the database and unlock.
    void SaveAndUnlock(const DBHandle& updates) {
      Save(updates);
      Unlock();
    }

    void Lock() {
      CHECK(!this->db_->IsSnapshot());
      mu_.Lock();
      locked_ = true;
    }
    void Unlock() {
      CHECK(!this->db_->IsSnapshot());
      locked_ = false;
      mu_.Unlock();
    }

   protected:
    // Contents cannot be created or destroyed directly by the end user. Use
    // ContentTable::{New,Load}Content().
    Content(ContentTable* table, const DBHandle& db, int64_t id)
        : T(table->state_, db, id),
          table_(table),
          locked_(false),
          deleted_(false),
          disk_local_id_(id) {
    }
    ~Content() {}

    // Type T needs to implement these methods:
    // int64_t local_id() const;
    // const string& server_id() const;

   private:
    // Loads the content from the database.
    bool Load() {
      const string key = table_->content_key(disk_local_id_);
      if (!this->db_->GetProto(key, this)) {
        if (!this->db_->Exists(key)) {
          return false;
        }
        string contents;
        if (!this->db_->Get(key, &contents)) {
          LOG("unable to load key %s", key);
        } else {
          LOG("content key %s corrupt: %s", key, contents);
        }
        return false;
      }
      if (disk_local_id_ != this->local_id()) {
        LOG("protobuf local id mismatch %d != %d for key %s",
            disk_local_id_, this->local_id(), key);
        return false;
      }
      disk_server_id_ = this->server_id();
      // Call superclass load.
      return T::Load();
    }

    // Increments the content reference count. Only used by ContentHandle.
    void Ref() {
      refcount_.Ref();
    }

    // Calls content table to decrement reference count and delete the content
    // if this is the last remaining reference. Only used by ContentHandle.
    void Unref() {
      table_->ReleaseContent(this);
    }

   private:
    ContentTable* const table_;
    AtomicRefCount refcount_;
    Mutex mu_;
    bool locked_;
    bool deleted_;
    // The local id as stored on disk.
    const int64_t disk_local_id_;
    // The server id as stored on disk.
    string disk_server_id_;
  };

  typedef ScopedHandle<Content> ContentHandle;
  friend class Content;

  // Subclasses should override the UpdateState() method to return False
  // when the iteration is done.
  class ContentIterator {
   public:
    virtual ~ContentIterator() {}

    // Advance the iterator. Sets done() to true if the end of the contents has
    // been reached.
    void Next() {
      CHECK(!reverse_);
      while (!done_) {
        iter_->Next();
        if (UpdateState()) {
          break;
        }
      }
    }

    void Prev() {
      CHECK(reverse_);
      while (!done_) {
        iter_->Prev();
        if (UpdateState()) {
          break;
        }
      }
    }

    Slice key() const { return ToSlice(iter_->key()); }
    Slice value() const { return ToSlice(iter_->value()); }
    bool done() const { return done_; }

   protected:
    ContentIterator(leveldb::Iterator* iter, bool reverse)
        : reverse_(reverse),
          done_(false),
          iter_(iter) {
    }

    // Position the iterator at the specified key. Sets done() to
    // true if the end of the contents has been reached.
    void Seek(const string& key) {
      done_ = false;
      iter_->Seek(key);
      // Reverse iterators are a special case. If the seek takes us
      // past the valid range of the iterator, seek to the last
      // position instead.
      if (reverse_) {
        if (!iter_->Valid()) {
          iter_->SeekToLast();
        }
        if (iter_->Valid() && ToSlice(iter_->key()) > key) {
          iter_->Prev();
        }
      }
      while (!UpdateState()) {
        if (reverse_) {
          iter_->Prev();
        } else {
          iter_->Next();
        }
      }
    }

    bool UpdateState() {
      if (!iter_->Valid()) {
        done_ = true;
        return true;
      }
      if (IteratorDone(key())) {
        done_ = true;
        return true;
      }
      return UpdateStateHook(key());
    }

    // Returns true if the iterator is finished.
    virtual bool IteratorDone(const Slice& key) { return false; }
    // Returns true if the key is valid and represents an item
    // in the iteration. False to skip.
    virtual bool UpdateStateHook(const Slice& key) { return true; }

   protected:
    const bool reverse_;

   private:
    bool done_;
    ScopedPtr<leveldb::Iterator> iter_;
  };

 public:
  // Create a new content, allocating a new local content id.
  ContentHandle NewContent(const DBHandle& updates) {
    MutexLock l(&mu_);

    const int64_t id = state_->NewLocalOperationId();

    Content*& a = contents_[id];
    if (!a) {
      a = new Content(this, updates, id);
    }
    return ContentHandle(a);
  }

  // Load the specified content, from disk if necessary.
  ContentHandle LoadContent(int64_t id, const DBHandle& db) {
    MutexLock l(&mu_);
    Content* snapshot_content = NULL;
    // If a snapshot database, return a new instance.
    Content*& a = db->IsSnapshot() ? snapshot_content : contents_[id];
    if (a && a->deleted_) {
      // Once the content is deleted, it never transitions back to the
      // non-deleted state.
      return ContentHandle();
    }
    if (!a) {
      a = new Content(this, db, id);
      // The content has not been initialized yet. Do so now.
      if (!a->Load()) {
        delete a;
        if (!db->IsSnapshot()) {
          contents_.erase(id);
        }
        return ContentHandle();
      }
    }
    return ContentHandle(a);
  }

  ContentHandle LoadContent(const string& server_id, const DBHandle& db) {
    const int64_t id = ServerToLocalId(server_id, db);
    if (id == -1) {
      return ContentHandle();
    }
    return LoadContent(id, db);
  }

  bool Exists(int64_t id, const DBHandle& db) {
    return db->Exists(this->content_key(id));
  }

  // Return a count of the number of referenced contents.
  int referenced_contents() const {
    MutexLock l(&mu_);
    return contents_.size();
  }

  // Lookup the local content id associated with a server content id. Returns
  // -1 if no mapping is found.
  int64_t ServerToLocalId(const string& server_id, const DBHandle& db) {
    return db->Get<int64_t>(content_server_key(server_id), -1);
  }

  // Decode content key to local id.
  int64_t DecodeContentKey(const Slice& key) {
    return FromString<int64_t>(key.substr(content_key_prefix_.size()), 0);
  }

  // Decode content server key to server id.
  string DecodeContentServerKey(const Slice& key) {
    return key.substr(content_server_key_prefix_.size());
  }

  // Database integrity check. Returns whether any repairs were made.
  virtual bool FSCK(
      bool force, ProgressUpdateBlock progress_update, const DBHandle& updates) {
    const int cur_fsck_version = updates->Get<int>(fsck_version_key_, 0);
    if (force ||
        (!fsck_version_key_.empty() &&
         fsck_version_ > cur_fsck_version)) {
      if (progress_update) {
        progress_update("Repairing Any Bad Data");
      }
      updates->Put<int>(fsck_version_key_, fsck_version_);
      FSCKImpl(cur_fsck_version, updates);
      return true;
    }
    return false;
  }

  AppState* state() const { return state_; }

 protected:
  ContentTable(AppState* state,
               const string& content_key_prefix,
               const string& content_server_key_prefix,
               const int fsck_version = 0,
               const string& fsck_version_key = "")
      : state_(state),
        content_key_prefix_(content_key_prefix),
        content_server_key_prefix_(content_server_key_prefix),
        fsck_version_(fsck_version),
        fsck_version_key_(fsck_version_key) {
    // The DB might not have been opened at this point, so don't access it yet.
  }
  virtual ~ContentTable() {
    CHECK_EQ(0, contents_.size());
  }

  virtual void SaveContentHook(T* content, const DBHandle& updates) {
    // Does nothing by default.
  }

  virtual void DeleteContentHook(T* content, const DBHandle& updates) {
    // Does nothing by default.
  }

  virtual bool FSCKImpl(int prev_fsck_version, const DBHandle& updates) {
    // Does nothing by default.
    return false;
  }

 private:
  void ReleaseContent(Content* content) {
    MutexLock l(&mu_);
    // The reference count must be unref'd while the mutex is held.
    if (content->refcount_.Unref()) {
      // If not from a snapshot database, remove from the singleton table.
      if (!content->db_->IsSnapshot()) {
        contents_.erase(content->disk_local_id_);
      }
      delete content;
    }
  }

  string content_key(int64_t local_id) const {
    return EncodeContentKey(content_key_prefix_, local_id);
  }
  string content_server_key(const string& server_id) {
    return EncodeContentServerKey(content_server_key_prefix_, server_id);
  }

 protected:
  AppState* const state_;

 private:
  const string content_key_prefix_;
  const string content_server_key_prefix_;
  const int fsck_version_;
  const string fsck_version_key_;
  mutable Mutex mu_;
  // Map of in-memory contents.
  std::unordered_map<int64_t, Content*> contents_;
};

#endif  // VIEWFINDER_CONTENT_TABLE_H

// local variables:
// mode: c++
// end:
