// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_SERVER_UTILS_H
#define VIEWFINDER_SERVER_UTILS_H

#import "JsonUtils.h"
#import "Server.pb.h"

bool IsS3RequestTimeout(int status, const Slice& data);

string EncodeAssetKey(const Slice& url, const Slice& fingerprint);
bool DecodeAssetKey(Slice key, Slice* url, Slice* fingerprint);

bool ParseAuthResponse(
    AuthResponse* r, const string& data);
bool ParseErrorResponse(
    ErrorResponse* r, const string& data);
bool ParsePingResponse(
    PingResponse* p, const string& data);
bool ParseQueryContactsResponse(
    QueryContactsResponse* r, ContactSelection* cs,
    int limit, const string& data);
bool ParseQueryEpisodesResponse(
    QueryEpisodesResponse* r, vector<EpisodeSelection>* v,
    int limit, const string& data);
bool ParseQueryFollowedResponse(
    QueryFollowedResponse* r, const string& data);
bool ParseQueryNotificationsResponse(
    QueryNotificationsResponse* r, NotificationSelection* ns,
    int limit, const string& data);
bool ParseQueryUsersResponse(
    QueryUsersResponse* r, const string& data);
bool ParseQueryViewpointsResponse(
    QueryViewpointsResponse* r, vector<ViewpointSelection>* v,
    int limit, const string& data);
bool ParseResolveContactsResponse(
    ResolveContactsResponse* r, const string& data);
bool ParseServerSubscriptionMetadata(
    ServerSubscriptionMetadata* sub, const JsonRef& dict);
bool ParseUploadContactsResponse(
    UploadContactsResponse* r, const string& data);
bool ParseUploadEpisodeResponse(
    UploadEpisodeResponse* r, const string& data);

#endif // VIEWFINDER_SERVER_UTILS_H
