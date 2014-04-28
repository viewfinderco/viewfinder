// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "NetworkQueue.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class NetworkQueueTest : public Test {
 public:
  NetworkQueueTest()
      : state_(dir()) {
  }

  void Add(int priority, int value) {
    ServerOperation op;
    op.set_update_photo(value);
    DBHandle updates = state_.NewDBTransaction();
    state_.net_queue()->Add(priority, op, updates);
    updates->Commit();
  }

  void Remove(int priority, int64_t sequence) {
    DBHandle updates = state_.NewDBTransaction();
    state_.net_queue()->Remove(priority, sequence, updates);
    updates->Commit();
  }

  enum {
    UPLOAD_METADATA       = 1 << 0,
    UPLOAD_THUMBNAIL      = 1 << 1,
    UPLOAD_MEDIUM         = 1 << 2,
    UPLOAD_FULL           = 1 << 3,
    UPLOAD_ORIGINAL       = 1 << 4,
    DOWNLOAD_THUMBNAIL    = 1 << 5,
    DOWNLOAD_MEDIUM       = 1 << 6,
    DOWNLOAD_FULL         = 1 << 7,
    DOWNLOAD_ORIGINAL     = 1 << 8,
    DOWNLOAD_UI_THUMBNAIL = 1 << 9,
    DOWNLOAD_UI_FULL      = 1 << 10,
    DOWNLOAD_UI_ORIGINAL  = 1 << 11,
  };

  int64_t QueuePhoto(int64_t id, int flags) {
    DBHandle updates = state_.NewDBTransaction();
    PhotoHandle ph = state_.photo_table()->LoadPhoto(id, updates);
    if (!ph.get()) {
      ph = state_.photo_table()->NewPhoto(updates);
    }
    ph->Lock();
    if (flags & UPLOAD_METADATA) {
      ph->set_upload_metadata(true);
    } else {
      ph->clear_upload_metadata();
    }
    if (flags & UPLOAD_THUMBNAIL) {
      ph->set_upload_thumbnail(true);
    } else {
      ph->clear_upload_thumbnail();
    }
    if (flags & UPLOAD_MEDIUM) {
      ph->set_upload_medium(true);
    } else {
      ph->clear_upload_medium();
    }
    if (flags & UPLOAD_FULL) {
      ph->set_upload_full(true);
    } else {
      ph->clear_upload_full();
    }
    if (flags & UPLOAD_ORIGINAL) {
      ph->set_upload_original(true);
    } else {
      ph->clear_upload_original();
    }
    if (flags & (DOWNLOAD_THUMBNAIL | DOWNLOAD_UI_THUMBNAIL)) {
      ph->set_download_thumbnail(true);
      if (flags & DOWNLOAD_UI_THUMBNAIL) {
        ph->set_error_ui_thumbnail(true);
      }
    } else {
      ph->clear_download_thumbnail();
      ph->clear_error_ui_thumbnail();
    }
    if (flags & DOWNLOAD_MEDIUM) {
      ph->set_download_medium(true);
    } else {
      ph->clear_download_medium();
    }
    if (flags & (DOWNLOAD_FULL | DOWNLOAD_UI_FULL)) {
      ph->set_download_full(true);
      if (flags & DOWNLOAD_UI_FULL) {
        ph->set_error_ui_full(true);
      }
    } else {
      ph->clear_download_full();
      ph->clear_error_ui_full();
    }
    if (flags & (DOWNLOAD_ORIGINAL | DOWNLOAD_UI_ORIGINAL)) {
      ph->set_download_original(true);
      if (flags & DOWNLOAD_UI_ORIGINAL) {
        ph->set_error_ui_original(true);
      }
    } else {
      ph->clear_download_original();
      ph->clear_error_ui_original();
    }
    ph->SaveAndUnlock(updates);
    updates->Commit();
    return ph->id().local_id();
  }

  string List() {
    ScopedPtr<NetworkQueue::Iterator> iter(state_.net_queue()->NewIterator());
    string s("<");
    for (; !iter->done(); iter->Next()) {
      if (s.size() > 1) {
        s += " ";
      }
      s += Format("%d,%d,%d", iter->priority(), iter->sequence(),
                  iter->op().update_photo());
    }
    s += ">";
    return s;
  }

  string Stats() {
    return ToString(state_.net_queue()->stats());
  }

  int NetworkCount() {
    return state_.net_queue()->GetNetworkCount();
  }
  int DownloadCount() {
    return state_.net_queue()->GetDownloadCount();
  }
  int UploadCount() {
    return state_.net_queue()->GetUploadCount();
  }

 protected:
  TestUIAppState state_;
};

TEST(NetworkQueueTest, QueueKey) {
  struct {
    int priority;
    int64_t sequence;
  } testdata[] = {
    { 1, 1 },
    { 1, 2 },
    { 2, 1 },
    { 2, 2 },
    // Verify sequence numbers greater than 2^32 work.
    { 2, 1ULL << 35 },
    // Verify that negative sequence numbers work (should get encoded as a very
    // large positive number).
    { 2, -1 },
  };

  string last_key(DBFormat::network_queue_key(""));
  for (int i = 0; i < ARRAYSIZE(testdata); ++i) {
    const string key = EncodeNetworkQueueKey(
        testdata[i].priority, testdata[i].sequence);
    ASSERT_GT(key, last_key) << ": " << i;
    last_key = key;

    int priority;
    int64_t sequence;
    ASSERT(DecodeNetworkQueueKey(key, &priority, &sequence));
    ASSERT_EQ(testdata[i].priority, priority);
    ASSERT_EQ(testdata[i].sequence, sequence);
  }
}

TEST_F(NetworkQueueTest, Basic) {
  ASSERT_EQ("<>", List());
  Add(1, 2);
  ASSERT_EQ("<1,1,2>", List());
  Add(2, 3);
  ASSERT_EQ("<1,1,2 2,2,3>", List());
  Add(2, 4);
  ASSERT_EQ("<1,1,2 2,2,3 2,3,4>", List());
  Add(1, 5);
  ASSERT_EQ("<1,1,2 1,4,5 2,2,3 2,3,4>", List());
  Remove(2, 2);
  ASSERT_EQ("<1,1,2 1,4,5 2,3,4>", List());
  Remove(1, 1);
  ASSERT_EQ("<1,4,5 2,3,4>", List());
  Remove(1, 4);
  ASSERT_EQ("<2,3,4>", List());
  Remove(2, 3);
  ASSERT_EQ("<>", List());
}

TEST_F(NetworkQueueTest, Stats) {
  ASSERT_EQ("<>", Stats());
  Add(1, 1);
  ASSERT_EQ("<1:1>", Stats());
  Add(1, 2);
  ASSERT_EQ("<1:2>", Stats());
  Add(2, 3);
  ASSERT_EQ("<1:2 2:1>", Stats());
  Add(3, 4);
  ASSERT_EQ("<1:2 2:1 3:1>", Stats());
  Add(2, 5);
  ASSERT_EQ("<1:2 2:2 3:1>", Stats());
  Remove(1, 1);
  ASSERT_EQ("<1:1 2:2 3:1>", Stats());
  Remove(1, 2);
  ASSERT_EQ("<2:2 3:1>", Stats());
  Remove(2, 3);
  ASSERT_EQ("<2:1 3:1>", Stats());
  Remove(2, 5);
  ASSERT_EQ("<3:1>", Stats());
  Remove(3, 4);
  ASSERT_EQ("<>", Stats());
  Remove(3, 6);
  ASSERT_EQ("<>", Stats());
}

TEST_F(NetworkQueueTest, UpdatePhotoStats) {
  state_.set_network_wifi(true);
  state_.set_cloud_storage(true);
  state_.set_store_originals(true);
  const int64_t p1 = QueuePhoto(0, 0);
  EXPECT_EQ("<>", Stats());
  EXPECT_EQ(0, NetworkCount());
  QueuePhoto(p1, UPLOAD_METADATA);
  EXPECT_EQ("<400:0.25>", Stats());
  EXPECT_EQ(1, NetworkCount());
  EXPECT_EQ(0, DownloadCount());
  EXPECT_EQ(1, UploadCount());
  QueuePhoto(p1, UPLOAD_METADATA | UPLOAD_THUMBNAIL | UPLOAD_MEDIUM | UPLOAD_FULL);
  EXPECT_EQ("<400:0.75 500:0.25>", Stats());
  EXPECT_EQ(1, NetworkCount());
  EXPECT_EQ(0, DownloadCount());
  EXPECT_EQ(1, UploadCount());
  QueuePhoto(p1, UPLOAD_METADATA | UPLOAD_ORIGINAL);
  EXPECT_EQ("<400:0.25 600:1>", Stats());
  EXPECT_EQ(2, NetworkCount());
  EXPECT_EQ(0, DownloadCount());
  EXPECT_EQ(2, UploadCount());
  QueuePhoto(p1, UPLOAD_ORIGINAL);
  EXPECT_EQ("<600:1>", Stats());
  EXPECT_EQ(1, NetworkCount());
  EXPECT_EQ(0, DownloadCount());
  EXPECT_EQ(1, UploadCount());
  QueuePhoto(p1, UPLOAD_ORIGINAL | DOWNLOAD_THUMBNAIL);
  EXPECT_EQ("<550:1 600:1>", Stats());
  EXPECT_EQ(2, NetworkCount());
  EXPECT_EQ(1, DownloadCount());
  EXPECT_EQ(1, UploadCount());
  state_.set_store_originals(false);
  EXPECT_EQ(1, NetworkCount());
  EXPECT_EQ(1, DownloadCount());
  EXPECT_EQ(0, UploadCount());
  state_.set_network_wifi(false);
  EXPECT_EQ(0, NetworkCount());
  EXPECT_EQ(0, DownloadCount());
  EXPECT_EQ(0, UploadCount());
  const int64_t p2 = QueuePhoto(0, UPLOAD_METADATA | UPLOAD_THUMBNAIL);
  EXPECT_EQ("<400:0.5 550:1 600:1>", Stats());
  EXPECT_EQ(0, NetworkCount());
  EXPECT_EQ(0, DownloadCount());
  EXPECT_EQ(0, UploadCount());
  state_.set_store_originals(true);
  EXPECT_EQ(0, NetworkCount());
  EXPECT_EQ(0, DownloadCount());
  EXPECT_EQ(0, UploadCount());
  state_.set_network_wifi(true);
  EXPECT_EQ(3, NetworkCount());
  EXPECT_EQ(1, DownloadCount());
  EXPECT_EQ(2, UploadCount());
  QueuePhoto(p1, 0);
  EXPECT_EQ("<400:0.5>", Stats());
  EXPECT_EQ(1, NetworkCount());
  EXPECT_EQ(0, DownloadCount());
  EXPECT_EQ(1, UploadCount());
  QueuePhoto(p2, 0);
  EXPECT_EQ("<>", Stats());
  EXPECT_EQ(0, NetworkCount());
  EXPECT_EQ(0, DownloadCount());
  EXPECT_EQ(0, UploadCount());
  QueuePhoto(p1, DOWNLOAD_THUMBNAIL | DOWNLOAD_UI_ORIGINAL);
  EXPECT_EQ("<100:1 550:1>", Stats());
  EXPECT_EQ("<100,5,1>", List());
  QueuePhoto(p1, DOWNLOAD_THUMBNAIL | DOWNLOAD_UI_FULL);
  EXPECT_EQ("<20:1 550:1>", Stats());
  EXPECT_EQ("<20,6,1>", List());
  QueuePhoto(p1, DOWNLOAD_THUMBNAIL | DOWNLOAD_UI_THUMBNAIL);
  EXPECT_EQ("<10:1>", Stats());
  EXPECT_EQ("<10,7,1>", List());
}

TEST_F(NetworkQueueTest, InitStats) {
  state_.set_network_wifi(true);
  state_.set_cloud_storage(true);
  state_.set_store_originals(true);
  QueuePhoto(0, UPLOAD_METADATA | UPLOAD_THUMBNAIL | UPLOAD_MEDIUM | UPLOAD_FULL);
  EXPECT_EQ("<400:0.75 500:0.25>", Stats());
  EXPECT_EQ(1, NetworkCount());
  // Verify the stats are re-initialized correctly.
  ScopedPtr<NetworkQueue> net_queue(new NetworkQueue(&state_));
  EXPECT_EQ("<400:0.75 500:0.25>", ToString(net_queue->stats()));
  EXPECT_EQ(1, net_queue->GetNetworkCount());
}

// TODO(pmattis): Test {Queue,Dequeue}Photo.
// TODO(pmattis): Test {Queue,Dequeue}Activity.

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
