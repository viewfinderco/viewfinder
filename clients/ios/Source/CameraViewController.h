// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <AVFoundation/AVFoundation.h>
#import <GLKit/GLKit.h>
#import <TargetConditionals.h>
#import "GL.h"
#import "ImagePipeline.h"
#import "ScopedPtr.h"

class UIAppState;

@class AVCaptureSession;
@class ExpandyMenu;
@class RotatingView;
@class VolumeButtons;

#if TARGET_IPHONE_SIMULATOR
@interface CameraViewController :
    UIViewController <GLKViewDelegate,
                      GLKViewControllerDelegate,
                      UIGestureRecognizerDelegate> {
#else   // TARGET_IPHONE_SIMULATOR
@interface CameraViewController :
    UIViewController <AVCaptureVideoDataOutputSampleBufferDelegate,
                      GLKViewDelegate,
                      GLKViewControllerDelegate,
                      UIGestureRecognizerDelegate> {
#endif  // TARGET_IPHONE_SIMULATOR
 @private
  UIAppState* state_;
  int current_device_;
  bool focus_needed_;
  int acquisition_count_;
  bool exit_pending_;
  bool preview_pending_;
  double message_display_time_;
  GLKViewController* glk_view_controller_;
  VolumeButtons* volume_buttons_;
  UIView* grid_view_;
  UIView* flash_view_;
  UIImageView* focus_crosshairs_;
  RotatingView* rotating_view_;
  UIView* navbar_;
  UILabel* message_;
  UIButton* preview_;
  ExpandyMenu* flash_menu_;
  AVCaptureVideoDataOutput* video_output_;
  AVCaptureStillImageOutput* still_output_;
  EAGLContext* context_;
  float aspect_fit_zoom_;
  float aspect_fill_zoom_;
  float prev_zoom_;
  float zoom_;
  vector<string> asset_keys_;
  ScopedPtr<GLTextureCache> texture_cache_;
  ScopedPtr<GLTexture2D> y_texture_;
  ScopedPtr<GLTexture2D> uv_texture_;
  ScopedPtr<ImagePipeline> image_pipeline_;
  ScopedPtr<FilterManager> filter_manager_;
#if !(TARGET_IPHONE_SIMULATOR)
  AVCaptureSession* session_;
#endif  // !(TARGET_IPHONE_SIMULATOR)
}

- (id)initWithState:(UIAppState*)state;

@end  // CameraViewController

// local variables:
// mode: objc
// end:
