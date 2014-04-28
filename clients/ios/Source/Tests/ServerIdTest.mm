// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#import "ServerId.h"
#import "Testing.h"
#import "TestUtils.h"
#import "WallTime.h"

namespace {

// All example ids are taken from output of backend/db/test/id_test.py.

TEST(ServerIdTest, ActivityIds) {
  struct {
    WallTime ts;
    int64_t device_id;
    int64_t local_id;
    string server_id;
  } inputs[] = {
    { 0, 0, 0, "azzzzzk--" },
    { 1234234.123423, 127, 128, "azyoelMy--F" },
    { 1347060002.422321, 128, 127, "afvKyrN-0Uk" },
    { 1347060002.422411, 128, 128, "afvKyrN-0V-3" },
    { 1347060002.422492, 123512341234, 827348273422, "afvKyrU94cszB-suHgsu95-" },
  };

  for (int i = 0; i < ARRAYSIZE(inputs); ++i) {
    ASSERT_EQ(EncodeActivityId(inputs[i].device_id, inputs[i].local_id, inputs[i].ts),
              inputs[i].server_id);
    int64_t device_id;
    int64_t local_id;
    WallTime ts;
    ASSERT(DecodeActivityId(inputs[i].server_id, &device_id, &local_id, &ts));
    ASSERT_EQ(device_id, inputs[i].device_id);
    ASSERT_EQ(local_id, inputs[i].local_id);
    ASSERT_EQ(ts, int(inputs[i].ts));
  }
}

TEST(ServerIdTest, CommentIds) {
  struct {
    WallTime ts;
    int64_t device_id;
    int64_t local_id;
    string server_id;
  } inputs[] = {
    { 0, 0, 0, "c--------" },
    { 1234234.123423, 127, 128, "c-0AKDby--F" },
    { 1347060002.422744, 128, 127, "cJ3e07c-0Uk" },
    { 1347060002.422793, 128, 128, "cJ3e07c-0V-3" },
    { 1347060002.422839, 123512341234, 827348273422, "cJ3e07j94cszB-suHgsu95-" },
  };

  for (int i = 0; i < ARRAYSIZE(inputs); ++i) {
    ASSERT_EQ(EncodeCommentId(inputs[i].device_id, inputs[i].local_id, inputs[i].ts),
              inputs[i].server_id);
    int64_t device_id;
    int64_t local_id;
    WallTime ts;
    ASSERT(DecodeCommentId(inputs[i].server_id, &device_id, &local_id, &ts));
    ASSERT_EQ(device_id, inputs[i].device_id);
    ASSERT_EQ(local_id, inputs[i].local_id);
    ASSERT_EQ(ts, int(inputs[i].ts));
  }
}

TEST(ServerIdTest, EpisodeIds) {
  struct {
    WallTime ts;
    int64_t device_id;
    int64_t local_id;
    string server_id;
  } inputs[] = {
    { 0, 0, 0, "ezzzzzk--" },
    { 1234234.123423, 127, 128, "ezyoelMy--F" },
    { 1347060002.423026, 128, 127, "efvKyrN-0Uk" },
    { 1347060002.423068, 128, 128, "efvKyrN-0V-3" },
    { 1347060002.423112, 123512341234, 827348273422, "efvKyrU94cszB-suHgsu95-" },
  };

  for (int i = 0; i < ARRAYSIZE(inputs); ++i) {
    ASSERT_EQ(EncodeEpisodeId(inputs[i].device_id, inputs[i].local_id, inputs[i].ts),
              inputs[i].server_id);
    int64_t device_id;
    int64_t local_id;
    WallTime ts;
    ASSERT(DecodeEpisodeId(inputs[i].server_id, &device_id, &local_id, &ts));
    ASSERT_EQ(device_id, inputs[i].device_id);
    ASSERT_EQ(local_id, inputs[i].local_id);
    ASSERT_EQ(ts, int(inputs[i].ts));
  }
}

TEST(ServerIdTest, OperationIds) {
  struct {
    int64_t device_id;
    int64_t local_id;
    string server_id;
  } inputs[] = {
    { 0, 0, "o---" },
    { 127, 128, "oUs-0" },
    { 128, 127, "oV-4z" },
    { 128, 128, "oV-5--F" },
    { 123512341234, 827348273422, "owcLYYwk2Yd9nYccN" },
  };

  for (int i = 0; i < ARRAYSIZE(inputs); ++i) {
    ASSERT_EQ(EncodeOperationId(inputs[i].device_id, inputs[i].local_id),
              inputs[i].server_id);
    int64_t device_id;
    int64_t local_id;
    ASSERT(DecodeOperationId(inputs[i].server_id, &device_id, &local_id));
    ASSERT_EQ(device_id, inputs[i].device_id);
    ASSERT_EQ(local_id, inputs[i].local_id);
  }
}

TEST(ServerIdTest, PhotoIds) {
  struct {
    WallTime ts;
    int64_t device_id;
    int64_t local_id;
    string server_id;
  } inputs[] = {
    { 0, 0, 0, "pzzzzzk--" },
    { 1234234.123423, 127, 128, "pzyoelMy--F" },
    { 1347060002.423472, 128, 127, "pfvKyrN-0Uk" },
    { 1347060002.423514, 128, 128, "pfvKyrN-0V-3" },
    { 1347060002.423558, 123512341234, 827348273422, "pfvKyrU94cszB-suHgsu95-" },
  };

  for (int i = 0; i < ARRAYSIZE(inputs); ++i) {
    ASSERT_EQ(EncodePhotoId(inputs[i].device_id, inputs[i].local_id, inputs[i].ts),
              inputs[i].server_id);
    int64_t device_id;
    int64_t local_id;
    WallTime ts;
    ASSERT(DecodePhotoId(inputs[i].server_id, &device_id, &local_id, &ts));
    ASSERT_EQ(device_id, inputs[i].device_id);
    ASSERT_EQ(local_id, inputs[i].local_id);
    ASSERT_EQ(ts, int(inputs[i].ts));
  }
}

TEST(ServerIdTest, ViewpointIds) {
  struct {
    int64_t device_id;
    int64_t local_id;
    string server_id;
  } inputs[] = {
    { 0, 0, "v---" },
    { 127, 128, "vUs-0" },
    { 128, 127, "vV-4z" },
    { 128, 128, "vV-5--F" },
    { 123512341234, 827348273422, "vwcLYYwk2Yd9nYccN" },
  };

  for (int i = 0; i < ARRAYSIZE(inputs); ++i) {
    ASSERT_EQ(EncodeViewpointId(inputs[i].device_id, inputs[i].local_id),
              inputs[i].server_id);
    int64_t device_id;
    int64_t local_id;
    ASSERT(DecodeViewpointId(inputs[i].server_id, &device_id, &local_id));
    ASSERT_EQ(device_id, inputs[i].device_id);
    ASSERT_EQ(local_id, inputs[i].local_id);
  }
}

TEST(ServerIdTest, NewLocalOperationIds) {
  TestTmpDir dir;
  TestUIAppState state(dir.dir());

  int64_t last_id = 0;
  for (int i = 0; i < 10; ++i) {
    int64_t id = state.NewLocalOperationId();
    CHECK_LT(last_id, id);
    last_id = id;
  }
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
