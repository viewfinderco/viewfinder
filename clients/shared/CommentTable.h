// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_COMMENT_TABLE_H
#define VIEWFINDER_COMMENT_TABLE_H

#import "CommentMetadata.pb.h"
#import "ContentTable.h"
#import "WallTime.h"

class FullTextIndex;

// The CommentTable class maintains the mappings:
//   <device-comment-id> -> <CommentMetadata>
//   <server-comment-id> -> <device-comment-id>

class CommentTable_Comment : public CommentMetadata {
 public:
  virtual void MergeFrom(const CommentMetadata& m);
  // Unimplemented; exists to get the compiler not to complain about hiding the base class's overloaded MergeFrom.
  virtual void MergeFrom(const ::google::protobuf::Message&);

 protected:
  bool Load() { return true; }
  void SaveHook(const DBHandle& updates);
  void DeleteHook(const DBHandle& updates) {}

  int64_t local_id() const { return comment_id().local_id(); }
  const string& server_id() const { return comment_id().server_id(); }

  CommentTable_Comment(AppState* state, const DBHandle& db, int64_t id);

 protected:
  AppState* state_;
  DBHandle db_;
};

class CommentTable : public ContentTable<CommentTable_Comment> {
  typedef CommentTable_Comment Comment;

 public:
  CommentTable(AppState* state);
  virtual ~CommentTable();

  ContentHandle NewComment(const DBHandle& updates) {
    return NewContent(updates);
  }
  ContentHandle LoadComment(int64_t id, const DBHandle& db) {
    return LoadContent(id, db);
  }
  ContentHandle LoadComment(const string& server_id, const DBHandle& db) {
    return LoadContent(server_id, db);
  }
  ContentHandle LoadComment(const CommentId& id, const DBHandle& db);

  void SaveContentHook(Comment* comment, const DBHandle& updates);
  void DeleteContentHook(Comment* comment, const DBHandle& updates);

  // List of (viewpoint_id, comment_id) pairs.
  typedef vector<pair<int64_t, int64_t> > CommentSearchResults;
  void Search(const Slice& query, CommentSearchResults* results);

  FullTextIndex* comment_index() const { return comment_index_.get(); }

 private:
  ScopedPtr<FullTextIndex> comment_index_;
};

typedef CommentTable::ContentHandle CommentHandle;

#endif  // VIEWFINDER_COMMENT_TABLE_H

// local variables:
// mode: c++
// end:
