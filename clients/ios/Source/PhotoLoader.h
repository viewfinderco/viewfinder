// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_PHOTO_LOADER_H
#define VIEWFINDER_PHOTO_LOADER_H

#import <deque>
#import "Callback.h"
#import "Mutex.h"
#import "STLUtils.h"

@class PhotoView;

class UIAppState;
class PhotoLoader;

typedef void (^PhotoQueueBlock)(vector<PhotoView*>* q);
struct PhotoQueue {
  PhotoQueueBlock block;
  string name;
  PhotoLoader* loader;

  PhotoQueue()
      : loader(NULL) {
  }
  ~PhotoQueue();
};

class PhotoLoader {
  typedef std::unordered_set<PhotoView*, HashObjC> PhotoViewSet;
  typedef std::deque<const PhotoQueue*> LoadQueue;
  typedef std::unordered_map<const PhotoQueue*, int64_t> QueueSeqMap;

 public:
  PhotoLoader(UIAppState* state);
  ~PhotoLoader();

  void WaitThumbnailsLocked(const vector<PhotoView*>& views, WallTime delay);
  void LoadThumbnailLocked(PhotoView* view);
  void LoadPhotos(PhotoQueue* photo_queue);
  void LoadPhotosDelayed(WallTime t, PhotoQueue* photo_queue);
  void CancelLoadPhotos(const PhotoQueue* photo_queue);

  Mutex* mutex() { return &mu_; }

 private:
  void AddPhotoQueue(const PhotoQueue* photo_queue);
  void RemovePhotoQueue(const PhotoQueue* photo_queue);
  void ProcessLoadQueue();
  void QueueNetworkPhoto(PhotoView* view);
  void DispatchNetworkLoad();
  void SetThumbnailLocked(PhotoView* view);

 private:
  UIAppState* const state_;
  Mutex mu_;
  CallbackSet thumbnail_loaded_;
  LoadQueue load_queue_;
  QueueSeqMap pending_queues_;
  int local_load_in_progress_;
  int network_load_in_progress_;
  std::deque<PhotoView*> network_queue_;
  PhotoViewSet network_loads_;
};

#endif  // VIEWFINDER_PHOTO_LOADER_H
