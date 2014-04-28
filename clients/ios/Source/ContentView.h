// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <vector>
#import <UIKit/UIKit.h>

@class PhotoView;

// ContentView provides a mechanism for views to report information
// about Viewfinder content referenced by the view or subviews.
// For example, PhotoView overrides the photoId and episodeId
// properties.
//
// ContentView propagates calls to hitTest to subviews. If returned
//   subview is also a ContentView, the subview is returned; any other
//   subview class is ignored and this view is returned.
@interface ContentView : UIView {
 @protected
  int64_t episode_id_;
  int64_t photo_id_;
  int64_t viewpoint_id_;
}

- (id)init;

+ (ContentView*)findPhotoId:(int64_t)photo_id
                     inView:(UIView*)view
                    withTag:(int)tag;
+ (ContentView*)findViewpointId:(int64_t)viewpoint_id
                         inView:(UIView*)view
                        withTag:(int)tag;
+ (std::vector<PhotoView*>)findPhotoViewsInView:(UIView*)view
                                        withTag:(int)tag;

@property (nonatomic, assign) int64_t episodeId;
@property (nonatomic, assign) int64_t photoId;
@property (nonatomic, assign) int64_t viewpointId;

@end  // ContentView

// local variables:
// mode: objc
// end:
