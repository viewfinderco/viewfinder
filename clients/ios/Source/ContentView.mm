// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <QuartzCore/QuartzCore.h>
#import "ContentView.h"
#import "Logging.h"
#import "PhotoView.h"
#import "UIStyle.h"

namespace {

NSString* const kBorderWidthKey = @"border_width";

}  // namespace

////
// ContentView

@implementation ContentView

@synthesize episodeId = episode_id_;
@synthesize photoId = photo_id_;
@synthesize viewpointId = viewpoint_id_;

- (id)init {
  return [super init];
}

+ (ContentView*)findPhotoId:(int64_t)photo_id
                     inView:(UIView*)view
                    withTag:(int)tag {
  // If the provided view is a content view and matches the
  // criteria, return it.
  if ([view isKindOfClass:[ContentView class]]) {
    ContentView* content_view = (ContentView*)view;
    if (content_view.photoId == photo_id &&
        (tag == 0 || tag == content_view.tag)) {
      return content_view;
    }
  }
  // Recurse to subviews.
  for (UIView* v in view.subviews) {
    ContentView* cv = [ContentView findPhotoId:photo_id inView:v withTag:tag];
    if (cv) return cv;
  }
  return NULL;
}

+ (ContentView*)findViewpointId:(int64_t)viewpoint_id
                         inView:(UIView*)view
                        withTag:(int)tag {
  // If the provided view is a content view and matches the
  // criteria, return it.
  if ([view isKindOfClass:[ContentView class]]) {
    ContentView* content_view = (ContentView*)view;
    if (content_view.viewpointId == viewpoint_id &&
        (tag == 0 || tag == content_view.tag)) {
      return content_view;
    }
  }
  // Recurse to subviews.
  for (UIView* v in view.subviews) {
    ContentView* cv = [ContentView findViewpointId:viewpoint_id inView:v withTag:tag];
    if (cv) return cv;
  }
  return NULL;
}

+ (std::vector<PhotoView*>)findPhotoViewsInView:(UIView*)view
                                        withTag:(int)tag {
  std::vector<PhotoView*> photo_views;
  if ([view isKindOfClass:[PhotoView class]] &&
      (tag == 0 || view.tag == tag)) {
    photo_views.push_back((PhotoView*)view);
    return photo_views;
  }
  // Recurse to subviews.
  for (UIView* v in view.subviews) {
    std::vector<PhotoView*> sub_photo_views =
        [ContentView findPhotoViewsInView:v withTag:tag];
    photo_views.insert(photo_views.end(), sub_photo_views.begin(), sub_photo_views.end());
  }

  return photo_views;
}

@end  // ContentView

// local variables:
// mode: objc
// end:
