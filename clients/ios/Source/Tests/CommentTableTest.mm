// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#import "CommentTable.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class CommentTableTest : public Test {
 public:
  CommentTableTest()
      : state_(dir()) {
  }

  CommentHandle NewComment() {
    DBHandle updates = state_.NewDBTransaction();
    CommentHandle h = state_.comment_table()->NewContent(updates);
    updates->Commit();
    return h;
  }

  CommentHandle LoadComment(int64_t id) {
    return state_.comment_table()->LoadContent(id, state_.db());
  }

  CommentHandle LoadComment(const string& server_id) {
    return state_.comment_table()->LoadContent(server_id, state_.db());
  }

  void SaveComment(const CommentHandle& h) {
    DBHandle updates = state_.NewDBTransaction();
    h->SaveAndUnlock(updates);
    updates->Commit();
  }

  void DeleteComment(const CommentHandle& h) {
    DBHandle updates = state_.NewDBTransaction();
    h->DeleteAndUnlock(updates);
    updates->Commit();
  }

  int referenced_comments() const {
    return state_.comment_table()->referenced_contents();
  }

  // Returns sorted comment ids (without viewpoint ids)
  vector<int64_t> Search(const Slice& query) {
    CommentTable::CommentSearchResults results;
    state_.comment_table()->Search(query, &results);
    vector<int64_t> out;
    for (int i = 0; i < results.size(); i++) {
      out.push_back(results[i].second);
    }
    std::sort(out.begin(), out.end());
    return out;
  }

 protected:
  TestUIAppState state_;
};

TEST_F(CommentTableTest, NewComment) {
  for (int i = 1; i < 10; ++i) {
    ASSERT_EQ(i, NewComment()->comment_id().local_id());
    ASSERT_EQ(0, referenced_comments());
  }
}

TEST_F(CommentTableTest, Basic) {
  // Create a new comment.
  ASSERT_EQ(0, referenced_comments());
  CommentHandle a = NewComment();
  ASSERT_EQ(1, a->comment_id().local_id());
  ASSERT_EQ(1, referenced_comments());
  // Though we never saved the comment, we can load it because there is still a
  // reference to it.
  ASSERT_EQ(a.get(), LoadComment(1).get());
  ASSERT_EQ(1, referenced_comments());
  // Release the reference.
  a.reset();
  ASSERT_EQ(0, referenced_comments());
  // We never saved the comment and there are no other references, so we won't
  // be able to load it.
  ASSERT(!LoadComment(1).get());
  ASSERT_EQ(0, referenced_comments());
  a = NewComment();
  ASSERT_EQ(2, a->comment_id().local_id());
  ASSERT_EQ(1, referenced_comments());
  // Verify we can retrieve it.
  ASSERT_EQ(a.get(), LoadComment(2).get());
  ASSERT_EQ(1, referenced_comments());
  // Verify that setting a server id sets up a mapping to the local id.
  a->Lock();
  a->mutable_comment_id()->set_server_id("a");
  SaveComment(a);
  ASSERT_EQ(a.get(), LoadComment("a").get());
  // Verify that changing the server id works properly.
  a->Lock();
  a->mutable_comment_id()->set_server_id("b");
  SaveComment(a);
  ASSERT_EQ(a.get(), LoadComment("b").get());
  ASSERT(!LoadComment("a").get());
}

TEST_F(CommentTableTest, FullText) {
  CommentHandle c1 = NewComment();
  c1->Lock();
  c1->set_message("abc def");
  SaveComment(c1);
  CommentHandle c2 = NewComment();
  c2->Lock();
  c2->set_message("ghi abc");
  SaveComment(c2);
  ASSERT_NE(c1->comment_id().local_id(), c2->comment_id().local_id());

  // Search for the two messages.
  ASSERT_EQ(Search("abc"), vector<int64_t>(L(c1->comment_id().local_id(),
                                             c2->comment_id().local_id())));
  ASSERT_EQ(Search("def"), vector<int64_t>(L(c1->comment_id().local_id())));
  ASSERT_EQ(Search("ghi"), vector<int64_t>(L(c2->comment_id().local_id())));
  ASSERT_EQ(Search("jkl"), vector<int64_t>());

  // Edit a message and see that the results are correctly updated.
  c1->Lock();
  c1->set_message("jkl def");
  SaveComment(c1);

  ASSERT_EQ(Search("abc"), vector<int64_t>(L(c2->comment_id().local_id())));
  ASSERT_EQ(Search("def"), vector<int64_t>(L(c1->comment_id().local_id())));
  ASSERT_EQ(Search("ghi"), vector<int64_t>(L(c2->comment_id().local_id())));
  ASSERT_EQ(Search("jkl"), vector<int64_t>(L(c1->comment_id().local_id())));

  // Delete a message.
  c2->Lock();
  DeleteComment(c2);

  ASSERT_EQ(Search("abc"), vector<int64_t>());
  ASSERT_EQ(Search("def"), vector<int64_t>(L(c1->comment_id().local_id())));
  ASSERT_EQ(Search("ghi"), vector<int64_t>());
  ASSERT_EQ(Search("jkl"), vector<int64_t>(L(c1->comment_id().local_id())));
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
