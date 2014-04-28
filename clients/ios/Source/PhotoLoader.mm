// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Logging.h"
#import "PhotoLoader.h"
#import "PhotoManager.h"
#import "PhotoView.h"
#import "Timer.h"
#import "UIAppState.h"

namespace {

// A marker used to indicate a thumbnail is being loaded.
Image* kThumbnailLoadingMarker = (Image*)0x1;

}  // namespace

PhotoQueue::~PhotoQueue() {
  if (loader) {
    DCHECK(dispatch_is_main_thread());
    loader->CancelLoadPhotos(this);
    loader = NULL;
  }
}

PhotoLoader::PhotoLoader(UIAppState* state)
    : state_(state),
      local_load_in_progress_(0),
      network_load_in_progress_(0) {
}

PhotoLoader::~PhotoLoader() {
  CHECK_EQ(local_load_in_progress_, 0);
  CHECK_EQ(network_load_in_progress_, 0);
}

void PhotoLoader::WaitThumbnailsLocked(
    const vector<PhotoView*>& views, WallTime delay) {
  // WallTimer timer;

  if (delay > 0) {
    // Only wait if there is a non-zero delay.
    mu_.TimedWait(delay, ^{
        for (int i = 0; i < views.size(); ++i) {
          PhotoView* view = views[i];
          CHECK(view != NULL);
          if (!view) {
            // Silence the code analyzer.
            continue;
          }
          if (!view.thumbnail.get() ||
              view.thumbnail.get() == kThumbnailLoadingMarker) {
            return false;
          }
        }
        return true;
      });
  }

  // Set the loaded thumbnails.
  for (int i = 0; i < views.size(); ++i) {
    SetThumbnailLocked(views[i]);
  }

  // LOG("photo: loaded %d image%s: %.03f ms",
  //     views.size(), Pluralize(views.size()),
  //     timer.Milliseconds());
}

void PhotoLoader::LoadThumbnailLocked(PhotoView* view) {
  CHECK(view != NULL);
  if (!view) {
    // Silence the code analyzer.
    return;
  }

  // Kick off loading of the thumbnail image.
  view.thumbnail.reset(kThumbnailLoadingMarker);

  void (^completion)(Image) = ^(Image image) {
    // We set the thumbnail on the current (low priority) thread to provide
    // immediate access for anyone blocked in WaitThumbnailsLocked() on the
    // main thread. We can't just call SetThumbnailLocked() from this thread
    // because UIKit calls must be performed on the main thread.
    mu_.Lock();
    view.thumbnail.release();
    view.thumbnail.reset(new Image(image));
    mu_.Unlock();

    dispatch_main(^{
        MutexLock l(&mu_);
        SetThumbnailLocked(view);
      });
  };

  // LOG("photo: %s: loading local thumbnail", view.photoId);
  state_->photo_manager()->LoadLocalThumbnail(
      view.photoId, ^(Image image){
        if (!image) {
          // Local loading failed. Load from the network.
          state_->photo_manager()->LoadNetworkThumbnail(
              view.photoId, completion);
          return;
        }

        completion(image);
      });
}

void PhotoLoader::LoadPhotos(PhotoQueue* photo_queue) {
  // Push to front of deque to prioritize most recent requests.
  photo_queue->loader = this;
  AddPhotoQueue(photo_queue);
  ProcessLoadQueue();
}

void PhotoLoader::LoadPhotosDelayed(WallTime t, PhotoQueue* photo_queue) {
  photo_queue->loader = this;
  const int64_t load_seq = ++pending_queues_[photo_queue];
  dispatch_after_main(t, ^{
      if (load_seq != pending_queues_[photo_queue]) {
        // A subsequent LoadPhotosDelayed call cancelled this one.
        return;
      }
      AddPhotoQueue(photo_queue);
      ProcessLoadQueue();
    });
}

void PhotoLoader::CancelLoadPhotos(const PhotoQueue* photo_queue) {
  RemovePhotoQueue(photo_queue);
}

void PhotoLoader::AddPhotoQueue(const PhotoQueue* photo_queue) {
  RemovePhotoQueue(photo_queue);
  load_queue_.push_front(photo_queue);
}

void PhotoLoader::RemovePhotoQueue(const PhotoQueue* photo_queue) {
  ++pending_queues_[photo_queue];
  for (LoadQueue::iterator iter = load_queue_.begin();
       iter != load_queue_.end();
       ++iter) {
    if (*iter == photo_queue) {
      load_queue_.erase(iter);
      return;
    }
  }
}

void PhotoLoader::ProcessLoadQueue() {
  if (local_load_in_progress_) {
    return;
  } else if (load_queue_.empty()) {
    return;
  }

  vector<PhotoView*> q;
  while (!load_queue_.empty()) {
    load_queue_.front()->block(&q);
    if (!q.empty()) {
      //LOG("processing load queue %s", load_queue_.front()->name);
      break;
    }
    load_queue_.pop_front();
  }

  // Find the first photo that is not queued for network loading.
  PhotoView* view = NULL;
  for (int i = 0; i < q.size(); ++i) {
    PhotoView* v = q[i];
    if (ContainsKey(network_loads_, v)) {
      continue;
    }
    view = v;
    break;
  }
  if (!view) {
    return;
  }

  // Kick off the loading of the photo. We load the photo on a low priority
  // background thread, then jump back to the main thread in order to perform
  // UIKit manipulation.
  // LOG("photo: %s: loading local photo: %.0f", view.photoId, view.frame.size);
  ++local_load_in_progress_;

  state_->photo_manager()->LoadLocalPhoto(
      view.photoId, view.frame.size, ^(Image image){
        // The photo has been loaded (or an error) occurred. Jump back
        // onto the main thread to perform UIKit manipulation.
        dispatch_main(^{
            // Mark the load as being finished.
            CHECK_GT(local_load_in_progress_, 0);
            --local_load_in_progress_;
            if (image) {
              view.image = image.MakeUIImage();
              view.loadSize = view.frame.size;
            } else {
              // Local loading failed.
              QueueNetworkPhoto(view);
            }
            ProcessLoadQueue();
          });
      });
}

void PhotoLoader::QueueNetworkPhoto(PhotoView* view) {
  if (ContainsKey(network_loads_, view)) {
    return;
  }
  network_loads_.insert(view);
  network_queue_.push_back(view);
  DispatchNetworkLoad();
}

void PhotoLoader::DispatchNetworkLoad() {
  if (network_load_in_progress_ || network_queue_.empty()) {
    return;
  }

  PhotoView* view = network_queue_.front();
  network_queue_.pop_front();

  // LOG("photo: %s: loading network photo: %.0f", view.photoId, view.frame.size);
  ++network_load_in_progress_;

  state_->photo_manager()->LoadNetworkPhoto(
      view.photoId, view.frame.size, ^(Image image){
        // The photo has been loaded (or an error) occurred. Jump back
        // onto the main thread to perform UIKit manipulation.
        dispatch_main(^{
            CHECK_GT(network_load_in_progress_, 0);
            --network_load_in_progress_;
            network_loads_.erase(view);
            if (image) {
              view.image = image.MakeUIImage();
            } else {
              // Network loading failed, the photo will have been quarantined,
              // but it won't be removed from the UI until the next day table
              // refresh.
              if (!view.image) {
                view.image = MakeSolidColorImage(MakeUIColor(0, 0, 0, 1));
              }
            }
            // Set the load size such that PhotoLoader will not try and load
            // the photo again.
            view.loadSize = view.frame.size;
            DispatchNetworkLoad();
          });
      });
}

void PhotoLoader::SetThumbnailLocked(PhotoView* view) {
  if (!view.thumbnail.get() ||
      view.thumbnail.get() == kThumbnailLoadingMarker) {
    return;
  }
  ScopedPtr<Image> image(view.thumbnail.release());
  if (!*image) {
    // Loading failed.
    return;
  }
  view.image = image->MakeUIImage();
  view.loadSize = CGSizeMake(image->width(), image->height());
}
