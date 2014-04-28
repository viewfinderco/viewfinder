// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_SERVER_ID_H
#define VIEWFINDER_SERVER_ID_H

#import "WallTime.h"

// Provides a mapping from the local ids to server ids and back.
//
// Server ids are typically composed of a globally-unique device id,
// established with the server on initial device registration, and
// a device-unique local id created by the allocating device for each
// asset class.
//
// Many server ids, such as photos, episodes, comments and activities,
// also contain a timestamp prefix. For photos, episodes and
// activities, the timestamp is reverse ordered so the most recently
// created assets sort first. Comments, by contrast, sort from least
// recent to most recent.

string EncodeActivityId(int64_t device_id, int64_t local_id, WallTime timestamp);
string EncodeCommentId(int64_t device_id, int64_t local_id, WallTime timestamp);
string EncodeEpisodeId(int64_t device_id, int64_t local_id, WallTime timestamp);
string EncodePhotoId(int64_t device_id, int64_t local_id, WallTime timestamp);

string EncodeOperationId(int64_t device_id, int64_t local_id);
string EncodeViewpointId(int64_t device_id, int64_t local_id);

bool DecodeActivityId(const Slice& server_id, int64_t* device_id,
                      int64_t* local_id, WallTime* timestamp);
bool DecodeCommentId(const Slice& server_id, int64_t* device_id,
                     int64_t* local_id, WallTime* timestamp);
bool DecodeEpisodeId(const Slice& server_id, int64_t* device_id,
                     int64_t* local_id, WallTime* timestamp);
bool DecodePhotoId(const Slice& server_id, int64_t* device_id,
                   int64_t* local_id, WallTime* timestamp);

bool DecodeOperationId(const Slice& server_id, int64_t* device_id, int64_t* local_id);
bool DecodeViewpointId(const Slice& server_id, int64_t* device_id, int64_t* local_id);

#endif  // VIEWFINDER_SERVER_ID_H

// local variables:
// mode: c++
// end:
