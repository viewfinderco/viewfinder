// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <re2/re2.h>
#import "ActivityTable.h"
#import "AppState.h"
#import "CommentTable.h"
#import "DayTable.h"
#import "FullTextIndex.h"
#import "LazyStaticPtr.h"
#import "StringUtils.h"

namespace {

const DBRegisterKeyIntrospect kCommentKeyIntrospect(
    DBFormat::comment_key(), NULL, [](Slice value) {
      return DBIntrospect::FormatProto<CommentMetadata>(value);
    });

const DBRegisterKeyIntrospect kCommentServerKeyIntrospect(
    DBFormat::comment_server_key(), NULL, [](Slice value) {
      return value.ToString();
    });

LazyStaticPtr<RE2, const char*> kDocIDRE = { "([0-9]+),([0-9]+)" };

const string kCommentIndexName = "com";

}  // namespace

////
// Comment

CommentTable_Comment::CommentTable_Comment(
    AppState* state, const DBHandle& db, int64_t id)
    : state_(state),
      db_(db) {
  mutable_comment_id()->set_local_id(id);
}

void CommentTable_Comment::MergeFrom(const CommentMetadata& m) {
  // Some assertions that immutable properties don't change.
  if (viewpoint_id().has_server_id() && m.viewpoint_id().has_server_id()) {
    DCHECK_EQ(viewpoint_id().server_id(), m.viewpoint_id().server_id());
  }
  if (has_user_id() && m.has_user_id()) {
    DCHECK_EQ(user_id(), m.user_id());
  }
  if (has_timestamp() && m.has_timestamp()) {
    DCHECK_LT(fabs(timestamp() - m.timestamp()), 0.000001);
  }

  CommentMetadata::MergeFrom(m);
}

void CommentTable_Comment::MergeFrom(const ::google::protobuf::Message&) {
  DIE("MergeFrom(Message&) should not be used");
}

void CommentTable_Comment::SaveHook(const DBHandle& updates) {
  // Invalidate the activity which posted this comment, so that any
  // saved changes are updated in the relevant conversation.
  if (comment_id().has_server_id()) {
    ActivityHandle ah = state_->activity_table()->GetCommentActivity(
        comment_id().server_id(), updates);
    if (ah.get()) {
      state_->day_table()->InvalidateActivity(ah, updates);
    }
  }
}

////
// CommentTable

CommentTable::CommentTable(AppState* state)
    : ContentTable<Comment>(
        state, DBFormat::comment_key(), DBFormat::comment_server_key()),
      comment_index_(new FullTextIndex(state_, kCommentIndexName)) {
}

CommentTable::~CommentTable() {
}

CommentHandle CommentTable::LoadComment(const CommentId& id, const DBHandle& db) {
  CommentHandle ch;
  if (id.has_local_id()) {
    ch = LoadComment(id.local_id(), db);
  }
  if (!ch.get() && id.has_server_id()) {
    ch = LoadComment(id.server_id(), db);
  }
  return ch;
}

void CommentTable::SaveContentHook(Comment* comment, const DBHandle& updates) {
  vector<FullTextIndexTerm> terms;
  comment_index_->ParseIndexTerms(0, comment->message(), &terms);
  // Inline the viewpoint id into our "docid" so we can use this index to find viewpoints
  // without extra database lookups.
  const string docid(Format("%d,%d", comment->viewpoint_id().local_id(), comment->comment_id().local_id()));
  comment_index_->UpdateIndex(terms, docid, FullTextIndex::TimestampSortKey(comment->timestamp()),
                              comment->mutable_indexed_terms(), updates);
}

void CommentTable::DeleteContentHook(Comment* comment, const DBHandle& updates) {
  comment_index_->RemoveTerms(comment->mutable_indexed_terms(), updates);
}

void CommentTable::Search(const Slice& query, CommentSearchResults* results) {
  ScopedPtr<FullTextQuery> parsed_query(FullTextQuery::Parse(query));
  for (ScopedPtr<FullTextResultIterator> iter(comment_index_->Search(state_->db(), *parsed_query));
       iter->Valid();
       iter->Next()) {
    const Slice docid = iter->doc_id();
    Slice viewpoint_id_slice, comment_id_slice;
    CHECK(RE2::FullMatch(docid, *kDocIDRE, &viewpoint_id_slice, &comment_id_slice));
    const int64_t viewpoint_id = FastParseInt64(viewpoint_id_slice);
    const int64_t comment_id = FastParseInt64(comment_id_slice);
    results->push_back(std::make_pair(viewpoint_id, comment_id));
  }
}

// local variables:
// mode: c++
// end:
