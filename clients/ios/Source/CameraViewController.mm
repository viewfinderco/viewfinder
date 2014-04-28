// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <AssetsLibrary/AssetsLibrary.h>
#import <GLKit/GLKit.h>
#import <ImageIO/ImageIO.h>
#import "Analytics.h"
#import "Appearance.h"
#import "AssetsManager.h"
#import "Breadcrumb.pb.h"
#import "CameraGridView.h"
#import "CameraViewController.h"
#import "DB.h"
#import "EpisodeTable.h"
#import "ExpandyMenu.h"
#import "FileUtils.h"
#import "Image.h"
#import "LayoutController.h"
#import "LocationTracker.h"
#import "Logging.h"
#import "Matrix.h"
#import "OutlinedLabel.h"
#import "PhotoTable.h"
#import "RootViewController.h"
#import "RotatingView.h"
#import "ScopedRef.h"
#import "SummaryLayoutController.h"
#import "Timer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"
#import "UIViewController+viewfinder.h"
#import "Utils.h"
#import "ValueUtils.h"
#import "Vector.h"
#import "VolumeButtons.h"

namespace {

// TODO(peter): need to put an exclamation point over the camera
//   icon after any image is taken without location services enabled.
//   Popup the unauthorized dialog if the user clicks the icon.
/*
void LocationServicesUnauthorized() {
  NSString* message = Format(
      "Location services are not authorized (Settings > %sLocation Services). "
      "This tells your photos, \"Hey, I was taken at (cool place). Don't "
      "forget.\" Might want to turn them on.",
      (kIOSVersion >= "6.0") ? "Privacy > " : "");
  UIAlertView* alert =
      [[UIAlertView alloc]
          initWithTitle:@"Hmmm…"
                message:message
               delegate:nil
        cancelButtonTitle:@"OK"
        otherButtonTitles:nil];
  [alert show];
}
*/

void* kCapturingStillImageContext =
    const_cast<char*>("AVCaptureStillImageIsCapturingStillImageContext");
const string kDeviceKey = DBFormat::metadata_key("camera_device");
const string kFlashModeKey = DBFormat::metadata_key("camera_flash_mode");
const string kGridVisibleKey = DBFormat::metadata_key("grid_visible");

const float kPreviewFinalScale = 0.65;

NSString* kCapturingStillImagePath = @"capturingStillImage";

enum {
  EXIF_0ROW_TOP_0COL_LEFT     = 1,
  EXIF_0ROW_TOP_0COL_RIGHT    = 2,
  EXIF_0ROW_BOTTOM_0COL_RIGHT = 3,
  EXIF_0ROW_BOTTOM_0COL_LEFT  = 4,
  EXIF_0ROW_LEFT_0COL_TOP     = 5,
  EXIF_0ROW_RIGHT_0COL_TOP    = 6,
  EXIF_0ROW_RIGHT_0COL_BOTTOM = 7,
  EXIF_0ROW_LEFT_0COL_BOTTOM  = 8
};

#if !(TARGET_IPHONE_SIMULATOR)

int GetExifDeviceOrientation(
    bool front_camera, UIInterfaceOrientation orientation) {
  if (front_camera) {
    switch (orientation) {
      case UIInterfaceOrientationPortraitUpsideDown:
        return EXIF_0ROW_LEFT_0COL_BOTTOM;
      case UIInterfaceOrientationLandscapeLeft:
        return EXIF_0ROW_TOP_0COL_LEFT;
      case UIInterfaceOrientationLandscapeRight:
        return EXIF_0ROW_BOTTOM_0COL_RIGHT;
      case UIInterfaceOrientationPortrait:
      default:
        return EXIF_0ROW_RIGHT_0COL_TOP;
    }
  } else {
    switch (orientation) {
      case UIInterfaceOrientationPortraitUpsideDown:
        return EXIF_0ROW_LEFT_0COL_BOTTOM;
      case UIInterfaceOrientationLandscapeLeft:
        return EXIF_0ROW_BOTTOM_0COL_RIGHT;
      case UIInterfaceOrientationLandscapeRight:
        return EXIF_0ROW_TOP_0COL_LEFT;
      case UIInterfaceOrientationPortrait:
      default:
        return EXIF_0ROW_RIGHT_0COL_TOP;
    }
  }
}

NSString* AVCaptureFlashModeToString(AVCaptureFlashMode flash_mode) {
  switch (flash_mode) {
    case AVCaptureFlashModeAuto:
      return @"Auto";
    case AVCaptureFlashModeOn:
      return @"On";
    case AVCaptureFlashModeOff:
      return @"Off";
  }
  return NULL;
}

AVCaptureFlashMode StringToAVCaptureFlashMode(NSString* ns_str) {
  const Slice s(ToSlice(ns_str));
  if (s == "Auto") {
    return AVCaptureFlashModeAuto;
  } else if (s == "On") {
    return AVCaptureFlashModeOn;
  } else if (s == "Off") {
    return AVCaptureFlashModeOff;
  }
  return AVCaptureFlashModeOff;
}

#endif  // !(TARGET_IPHONE_SIMULATOR)

class GLKViewFrameBuffer : public GLFrameBuffer {
 public:
  GLKViewFrameBuffer(GLKView* view)
      : view_(view) {
  }

  void Activate() {
    [view_ bindDrawable];
  }

  GLint width() const {
    return view_.drawableWidth;
  }
  GLint height() const {
    return view_.drawableHeight;
  }

private:
  GLKView* const view_;
};

const float kNavbarHeight = 50;
const float kNavbarButtonWidth = 80;

LazyStaticImage kCameraButton(@"camera-button.png");
LazyStaticImage kCameraButtonActive(@"camera-button-highlighted.png");
LazyStaticImage kCameraNavbar(@"camera-navbar.png");
LazyStaticImage kCameraNavbarLeft(
    @"camera-navbar-left.png", UIEdgeInsetsMake(0, 2, 0, 2));
LazyStaticImage kCameraNavbarLeftActive(
    @"camera-navbar-left-active.png", UIEdgeInsetsMake(0, 2, 0, 2));
LazyStaticImage kCameraNavbarRight(
    @"camera-navbar-right.png", UIEdgeInsetsMake(0, 2, 0, 2));
LazyStaticImage kCameraNavbarRightActive(
    @"camera-navbar-right-active.png", UIEdgeInsetsMake(0, 2, 0, 2));

LazyStaticUIFont kCameraNavbarFont = {
  kProximaNovaSemibold, 19
};

LazyStaticHexColor kCameraNavbarColor = { "#ffffffff" };
LazyStaticHexColor kCameraNavbarActiveColor = { "#ffffff7f" };

UIButton* NewCameraButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.showsTouchWhenHighlighted = NO;
  b.frameSize = CGSizeMake(kCameraButton.get().size.width,
                           kCameraButton.get().size.height);
  [b setImage:kCameraButton forState:UIControlStateNormal];
  [b setImage:kCameraButtonActive forState:UIControlStateHighlighted];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

UIButton* NewCameraNavbarLeftButton(NSString* title, float width, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.showsTouchWhenHighlighted = NO;
  b.frameSize = CGSizeMake(width, kNavbarHeight);
  [b setTitle:title forState:UIControlStateNormal];
  [b setTitleColor:kCameraNavbarColor
          forState:UIControlStateNormal];
  [b setTitleColor:kCameraNavbarActiveColor
          forState:UIControlStateHighlighted];
  [b setBackgroundImage:kCameraNavbarLeft forState:UIControlStateNormal];
  [b setBackgroundImage:kCameraNavbarLeftActive forState:UIControlStateHighlighted];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

}  // namespace

@interface CameraViewController (internal)
- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer;
- (void)handleDoubleTap:(UITapGestureRecognizer*)recognizer;
- (void)handleLongPress:(UILongPressGestureRecognizer*)recognizer;
- (void)setupGL;
- (void)setupAV;
#if !(TARGET_IPHONE_SIMULATOR)
- (BOOL)setupCaptureDevice:(int)device_index;
#endif // !(TARGET_IPHONE_SIMULATOR)
- (void)tearDownGL;
- (void)tearDownAV;
- (void)setupTextures:(CMSampleBufferRef)sample_buffer;
- (void)cleanUpTextures;
- (void)showPreview:(int)exif_orientation;
- (void)toggleCamera;
- (void)toggleFlash;
- (void)showMessage:(const string&)text;
- (void)clearMessage;
- (void)clearFocusCrosshairs;
- (void)makeFocusCrosshairsAtPoint:(CGPoint)p mode:(AVCaptureFocusMode)mode;
- (void)focusAtPoint:(CGPoint)p
                mode:(AVCaptureFocusMode)mode
            animated:(BOOL)animated;
- (Matrix4f)transformForConnection:(AVCaptureConnection*)conn;
- (CGPoint)viewCoordinateToVideoCoordinate:(CGPoint)p;
- (Image)snapshotGLView;
@end  // CameraViewController (internal)

@implementation CameraViewController

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;
    self.wantsFullScreenLayout = YES;

    glk_view_controller_ = [GLKViewController new];
    glk_view_controller_.delegate = self;
    glk_view_controller_.paused = YES;
    glk_view_controller_.pauseOnWillResignActive = NO;
    glk_view_controller_.preferredFramesPerSecond = 30;
    glk_view_controller_.resumeOnDidBecomeActive = NO;

    [[NSNotificationCenter defaultCenter]
      addObserverForName:UIApplicationWillResignActiveNotification
                  object:nil
                   queue:[NSOperationQueue mainQueue]
              usingBlock:^(NSNotification* notification){
        [self applicationWillResignActive];
      }];

    current_device_ = state_->db()->Get<int>(kDeviceKey);
    aspect_fit_zoom_ = aspect_fill_zoom_ = prev_zoom_ = zoom_ = -1;
  }
  return self;
}

- (void)applicationWillResignActive {
  glk_view_controller_.paused = YES;
}

- (bool)statusBarHidden {
  return true;
}

- (void)loadView {
  context_ = [[EAGLContext alloc] initWithAPI:kEAGLRenderingAPIOpenGLES2];

  self.view = [UIView new];
  self.view.backgroundColor = [UIColor blackColor];
  self.view.autoresizesSubviews = YES;
  self.view.autoresizingMask =
      UIViewAutoresizingFlexibleHeight |
      UIViewAutoresizingFlexibleWidth;

  // TODO(pmattis):
  // volume_buttons_ = [VolumeButtons new];
  // volume_buttons_.up->Add(^{
  //     [self navbarCamera:NULL];
  //   });
  // [self.view addSubview:volume_buttons_];

  GLKView* glk_view =
      [[GLKView alloc] initWithFrame:CGRectZero context:context_];
  glk_view.delegate = self;
  glk_view.autoresizesSubviews = YES;
  glk_view.contentScaleFactor = [UIScreen mainScreen].scale;
  glk_view_controller_.view = glk_view;
  [self.view addSubview:glk_view];

  grid_view_ = [[CameraGridView alloc] initWithGridSize:3];
  grid_view_.autoresizingMask =
      UIViewAutoresizingFlexibleHeight |
      UIViewAutoresizingFlexibleWidth;
  grid_view_.frame = glk_view.bounds;
  grid_view_.hidden = !state_->db()->Get<bool>(kGridVisibleKey, false);
  [glk_view addSubview:grid_view_];

  rotating_view_ = [RotatingView new];
  rotating_view_.frame = glk_view.bounds;
  [self.view addSubview:rotating_view_];

  navbar_ = [UIView new];
  navbar_.autoresizesSubviews = YES;
  navbar_.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleTopMargin;
  navbar_.frameHeight = kNavbarHeight;
  navbar_.frameBottom = self.view.boundsHeight;
  [self.view addSubview:navbar_];

  UIImageView* navbar_bg = [[UIImageView alloc] initWithImage:kCameraNavbar];
  navbar_bg.autoresizingMask = UIViewAutoresizingFlexibleWidth;
  [navbar_ addSubview:navbar_bg];

  UIButton* done = NewCameraNavbarLeftButton(
      @"Close", kNavbarButtonWidth, self, @selector(navbarDone));
  done.autoresizingMask = UIViewAutoresizingFlexibleRightMargin;
  done.frameBottom = navbar_.boundsHeight;
  [navbar_ addSubview:done];

  UIButton* camera = NewCameraButton(self, @selector(navbarCamera:));
  camera.autoresizingMask =
      UIViewAutoresizingFlexibleLeftMargin |
      UIViewAutoresizingFlexibleRightMargin |
      UIViewAutoresizingFlexibleBottomMargin;
  [navbar_ addSubview:camera];

  preview_ = [UIButton buttonWithType:UIButtonTypeCustom];
  preview_.autoresizingMask =
      UIViewAutoresizingFlexibleRightMargin |
      UIViewAutoresizingFlexibleTopMargin;
  preview_.backgroundColor = [UIColor grayColor];
  preview_.hidden = YES;
  preview_.layer.shadowOffset = CGSizeMake(0, 0);
  preview_.layer.shadowRadius = 5.0;
  preview_.layer.shadowColor = [UIColor blackColor].CGColor;
  preview_.layer.anchorPoint = CGPointMake(0, 1);
  [preview_ addTarget:self
               action:@selector(previewTapped)
     forControlEvents:UIControlEventTouchUpInside];
  [rotating_view_ addSubview:preview_];

  message_ = [OutlinedLabel new];
  message_.autoresizingMask =
      UIViewAutoresizingFlexibleBottomMargin |
      UIViewAutoresizingFlexibleWidth;
  message_.hidden = YES;
  message_.font = kCameraMessageFont;
  message_.textAlignment = NSTextAlignmentCenter;
  message_.textColor = [UIColor whiteColor];
  message_.shadowColor = [UIColor blackColor];
  message_.backgroundColor = [UIColor clearColor];
  message_.frame = CGRectMake(0, 8, 1, message_.font.lineHeight);
  [rotating_view_ addSubview:message_];

  UITapGestureRecognizer* single_tap_recognizer =
      [[UITapGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleSingleTap:)];
  single_tap_recognizer.delegate = self;
  single_tap_recognizer.numberOfTapsRequired = 1;
  [self.view addGestureRecognizer:single_tap_recognizer];

  UITapGestureRecognizer* double_tap_recognizer =
      [[UITapGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleDoubleTap:)];
  double_tap_recognizer.delegate = self;
  double_tap_recognizer.numberOfTapsRequired = 2;
  [self.view addGestureRecognizer:double_tap_recognizer];

  [single_tap_recognizer
    requireGestureRecognizerToFail:double_tap_recognizer];

  UILongPressGestureRecognizer* long_press_recognizer =
      [[UILongPressGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleLongPress:)];
  long_press_recognizer.delegate = self;
  long_press_recognizer.minimumPressDuration = 1.0;
  [self.view addGestureRecognizer:long_press_recognizer];

  UIPinchGestureRecognizer* pinch_recognizer =
      [[UIPinchGestureRecognizer alloc]
        initWithTarget:self action:@selector(handlePinch:)];
  pinch_recognizer.delegate = self;
  [self.view addGestureRecognizer:pinch_recognizer];

  [self setupGL];
  [self setupAV];
}

- (void)viewDidUnload {
  [self tearDownAV];
  [self tearDownGL];
  flash_menu_ = NULL;
  message_ = NULL;
  rotating_view_ = NULL;
  flash_view_ = NULL;
  grid_view_ = NULL;
  context_ = NULL;
  volume_buttons_ = NULL;
  glk_view_controller_.view = NULL;
  [super viewDidUnload];
}

- (void)viewWillAppear:(BOOL)animated {
  // LOG("camera: view will appear");
  [super viewWillAppear:animated];

  // Start the capture on a separate thread to avoid blocking the main thread.
#if !(TARGET_IPHONE_SIMULATOR)
  dispatch_high_priority(^{
      [session_ startRunning];
    });
#else  // (TARGET_IPHONE_SIMULATOR)
  y_texture_.reset(GLTextureLoader::LoadFromFile("test-photo.jpg"));
  y_texture_->mutable_transform()->scale(
      y_texture_->width(), -y_texture_->height(), 1);
#endif // (TARGET_IPHONE_SIMULATOR)

  // Check whether there are any valid photos after possible deletes
  // in the case where the user had tapped the preview button and
  // is now returning to the camera.
  vector<PhotoHandle> photo_handles;
  [self assetUrlsToPhotoHandleVec:&photo_handles];
  if (photo_handles.empty()) {
    preview_.hidden = YES;
  }

  [self viewDidLayoutSubviews];

  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  [rotating_view_ willAppear];
  [CATransaction commit];
}

- (void)viewDidAppear:(BOOL)animated {
  // LOG("camera: view did appear");
  [super viewDidAppear:animated];

  // Make sure the location manager is enabled.
  [state_->location_tracker() ensureInitialized];
  [state_->location_tracker() start];

  [self focusAtPoint:glk_view_controller_.view.center
                mode:AVCaptureFocusModeContinuousAutoFocus
            animated:YES];
  volume_buttons_.enabled = YES;
  glk_view_controller_.paused = YES;
}

- (void)viewWillDisappear:(BOOL)animated {
  // LOG("camera: view will disappear");
  [self cleanUpTextures];
#if !(TARGET_IPHONE_SIMULATOR)
  [session_ stopRunning];
#endif // !(TARGET_IPHONE_SIMULATOR)

  [state_->location_tracker() stop];
  volume_buttons_.enabled = NO;
  glk_view_controller_.paused = YES;

  // Release GL state.
  GLKView* glk_view = (GLKView*)glk_view_controller_.view;
  [glk_view deleteDrawable];
  [self cleanUpTextures];

  [rotating_view_ willDisappear];

  [super viewWillDisappear:animated];
}

- (void)viewDidDisappear:(BOOL)animated {
  [super viewDidDisappear:animated];
}

- (void)viewDidLayoutSubviews {
  [super viewDidLayoutSubviews];
  glk_view_controller_.view.frame = self.view.bounds;
  rotating_view_.frame =
      CGRectMake(0, 0, self.view.boundsWidth, self.view.boundsHeight - kNavbarHeight);
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
  // Make sure the preview button isn't being tapped.
  UIView* v = [self.view hitTest:[recognizer locationInView:self.view] withEvent:NULL];
  if ([v isKindOfClass:[UIControl class]]) {
    return NO;
  }
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)recognizer
       shouldReceiveTouch:(UITouch*)touch {
  return touch.view == self.view || touch.view == grid_view_ ||
      touch.view == rotating_view_;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)a
shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer*)b {
  return YES;
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
#if (TARGET_IPHONE_SIMULATOR)
  if (filter_manager_.get()) {
    [self showMessage:filter_manager_->NextFilter()];
  }
#else // !(TARGET_IPHONE_SIMULATOR)
  [self focusAtPoint:[recognizer locationInView:glk_view_controller_.view]
                mode:AVCaptureFocusModeAutoFocus
            animated:YES];
#endif // !(TARGET_IPHONE_SIMULATOR)
}

- (void)handleDoubleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  [self focusAtPoint:[recognizer locationInView:glk_view_controller_.view]
                mode:AVCaptureFocusModeContinuousAutoFocus
            animated:YES];
}

- (void)handleLongPress:(UILongPressGestureRecognizer*)recognizer {
  switch (recognizer.state) {
    case UIGestureRecognizerStateBegan: {
      const CGPoint p = [recognizer locationInView:glk_view_controller_.view];
      const AVCaptureFocusMode mode =
          AVCaptureFocusModeContinuousAutoFocus;
      [self showMessage:"AE/AF acquiring"];
      [self focusAtPoint:p mode:mode animated:NO];
      [self makeFocusCrosshairsAtPoint:p mode:mode];
      void (^block)() = ^{
        focus_crosshairs_.transform = CGAffineTransformMakeScale(1.5, 1.5);
        [UIView animateWithDuration:0.3
                              delay:0.0
                            options:
                  UIViewAnimationOptionRepeat |
                  UIViewAnimationOptionCurveEaseOut
                         animations:^{
            [UIView setAnimationRepeatCount:2];
            focus_crosshairs_.transform = CGAffineTransformIdentity;
          }
                         completion:NULL];
      };
      dispatch_after_main(1, block);
      break;
    }
    case UIGestureRecognizerStateEnded:
      [self showMessage:"AE/AF lock"];
      [self clearFocusCrosshairs];
      [self focusAtPoint:glk_view_controller_.view.center
                    mode:AVCaptureFocusModeLocked
                animated:NO];
      break;
    default:
      break;
  }
}

- (void)handlePinch:(UIPinchGestureRecognizer*)recognizer {
  if (zoom_ < 0) {
    // We haven't rendered a single frame from the camera yet.
    return;
  }

  AVCaptureConnection* const conn =
      [still_output_ connectionWithMediaType:AVMediaTypeVideo];
  const float max_zoom =
      std::min<float>(4 * aspect_fill_zoom_, conn.videoMaxScaleAndCropFactor);
  const float new_zoom = prev_zoom_ * recognizer.scale;
  zoom_ = std::min<float>(max_zoom, std::max<float>(aspect_fit_zoom_, new_zoom));
  // Snap any zoom that is within 5% of the aspect-fill-zoom to the
  // aspect-fill-zoom.
  if (fabs(zoom_ - aspect_fill_zoom_) <= 0.05) {
    zoom_ = aspect_fill_zoom_;
  }

  if (recognizer.state == UIGestureRecognizerStateBegan) {
    [self focusAtPoint:glk_view_controller_.view.center
                  mode:AVCaptureFocusModeContinuousAutoFocus
              animated:NO];
  }
  if (recognizer.state == UIGestureRecognizerStateEnded) {
    prev_zoom_ = zoom_;
    message_.hidden = YES;
  } else {
    // The zoom value presented to the user is the relative zoom from the
    // aspect-fill-zoom value. That is, aspect-fill-zoom is considered 1X zoom.
    message_.text =
        Format("%.1fX zoom", self.normalizedZoom);
    message_.hidden = NO;
  }
}

- (float)normalizedZoom {
  return std::max<float>(1, zoom_ / aspect_fill_zoom_);
}

- (void)setupGL {
  [EAGLContext setCurrentContext:context_];
  image_pipeline_.reset(new ImagePipeline);
  filter_manager_.reset(new FilterManager(image_pipeline_.get()));
}

- (void)setupAV {
  texture_cache_.reset(new GLTextureCache);

#if !(TARGET_IPHONE_SIMULATOR)
  session_ = [AVCaptureSession new];
  [session_ beginConfiguration];
  [session_ setSessionPreset:AVCaptureSessionPresetPhoto];

  // Create a video device and input from that device. Add the input to the
  // capture session.
  [self setupCaptureDevice:current_device_];

  // Create the output for the capture session. We want 4:2:0 y'cbcr.
  video_output_ = [AVCaptureVideoDataOutput new];
  [video_output_ setAlwaysDiscardsLateVideoFrames:YES];
  [video_output_ setVideoSettings:
                   Dict(kCVPixelBufferPixelFormatTypeKey,
                        kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange)];

  // We want our dispatch to be on the main thread so OpenGL can do things
  // with the data.
  [video_output_ setSampleBufferDelegate:self queue:dispatch_get_main_queue()];
  if ([session_ canAddOutput:video_output_]) {
    [session_ addOutput:video_output_];
  } else {
    LOG("unable to add video output");
  }

  still_output_ = [AVCaptureStillImageOutput new];
  [still_output_ addObserver:self
                  forKeyPath:kCapturingStillImagePath
                     options:NSKeyValueObservingOptionNew
                     context:kCapturingStillImageContext];
  if ([session_ canAddOutput:still_output_]) {
    [session_ addOutput:still_output_];
  } else {
    LOG("unable to add still image output");
  }
  [still_output_ setOutputSettings:Dict(AVVideoCodecKey, AVVideoCodecJPEG)];

  [session_ commitConfiguration];

  NSArray* capture_devices =
      [AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo];
  if (capture_devices.count > 1) {
    UIButton* toggle_button =
        UIStyle::NewCameraToggle(self, @selector(toggleCamera));
    toggle_button.autoresizingMask =
        UIViewAutoresizingFlexibleBottomMargin |
        UIViewAutoresizingFlexibleLeftMargin;
    toggle_button.frame = CGRectMake(
        -8 - toggle_button.frame.size.width, 8,
        toggle_button.frame.size.width, toggle_button.frame.size.height);
    [rotating_view_ addSubview:toggle_button];
  }
#endif  // !(TARGET_IPHONE_SIMULATOR)
}

#if !(TARGET_IPHONE_SIMULATOR)
- (BOOL)setupCaptureDevice:(int)device_index {
  NSArray* capture_devices =
      [AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo];
  AVCaptureDevice* device = [capture_devices objectAtIndex:device_index];

  NSError* error;
  AVCaptureDeviceInput* video_input =
      [AVCaptureDeviceInput deviceInputWithDevice:device error:&error];
  if (error) {
    LOG("unable to create video input: %@", error);
    return NO;
  } else if ([session_ canAddInput:video_input]) {
    [session_ addInput:video_input];
  } else {
    LOG("unable to add video input");
    return NO;
  }

  state_->analytics()->CameraPage(ToString(device.localizedName));

  [flash_menu_ removeFromSuperview];

  if (device.hasFlash) {
    AVCaptureFlashMode kPossibleModes[] = {
      AVCaptureFlashModeAuto,
      AVCaptureFlashModeOn,
      AVCaptureFlashModeOff,
    };
    NSMutableArray* modes = [NSMutableArray arrayWithCapacity:3];
    for (int i = 0; i < ARRAYSIZE(kPossibleModes); ++i) {
      if ([device isFlashModeSupported:kPossibleModes[i]]) {
        [modes addObject:AVCaptureFlashModeToString(kPossibleModes[i])];
      }
    }

    if (modes.count >= 1) {
      UIImageView* title =
          [[UIImageView alloc] initWithImage:UIStyle::kCameraFlash];
      flash_menu_ = [[ExpandyMenu alloc]
                      initWithPoint:CGPointMake(8, 8)
                              title:title
                        buttonNames:modes];
      [flash_menu_ setAutoresizingMask:
          UIViewAutoresizingFlexibleRightMargin |
          UIViewAutoresizingFlexibleBottomMargin];
      for (UILabel* label in [flash_menu_ labels]) {
        label.tag = StringToAVCaptureFlashMode(label.text);
        DCHECK_EQ(ToSlice(label.text),
                  ToSlice(AVCaptureFlashModeToString(static_cast<AVCaptureFlashMode>(label.tag))));
      }
      [flash_menu_ addTarget:self
                      action:@selector(toggleFlash)
            forControlEvents:UIControlEventValueChanged];

      const int flash_item = state_->db()->Get(
          Format("%s/%d", kFlashModeKey, device_index),
          -1);
      if (flash_item >= 0 && flash_item < modes.count) {
        [flash_menu_ setSelectedItem:flash_item];
      } else {
        NSString* name = AVCaptureFlashModeToString(device.flashMode);
        if (name != NULL) {
          [flash_menu_ setSelectedItem:[modes indexOfObject:name]];
        }
      }
      [self toggleFlash];

      [rotating_view_ addSubview:flash_menu_];
    }
  }

  if (kIOSVersion >= "6.0" && device.lowLightBoostSupported) {
    if ([device lockForConfiguration:&error]) {
      device.automaticallyEnablesLowLightBoostWhenAvailable = YES;
      [device unlockForConfiguration];
    }
  }

  aspect_fit_zoom_ = aspect_fill_zoom_ = prev_zoom_ = zoom_ = -1;
  focus_needed_ = true;
  return YES;
}
#endif  // !(TARGET_IPHONE_SIMULATOR)

- (void)tearDownGL {
  filter_manager_.reset(NULL);
  image_pipeline_.reset(NULL);
  [EAGLContext setCurrentContext:context_];
  if ([EAGLContext currentContext] == context_) {
    [EAGLContext setCurrentContext:nil];
  }
}

- (void)tearDownAV {
  [self cleanUpTextures];

  texture_cache_.reset(NULL);

  [still_output_ removeObserver:self forKeyPath:kCapturingStillImagePath];
  still_output_ = NULL;
  video_output_ = NULL;
#if !(TARGET_IPHONE_SIMULATOR)
  session_ = NULL;
#endif  // !(TARGET_IPHONE_SIMULATOR)
}

- (void)setupTextures:(CMSampleBufferRef)sample_buffer {
  CVImageBufferRef buffer = CMSampleBufferGetImageBuffer(sample_buffer);
  const int width = CVPixelBufferGetWidth(buffer);
  const int height = CVPixelBufferGetHeight(buffer);

  // Y-plane
  glActiveTexture(GL_TEXTURE0);
  y_texture_.reset(texture_cache_->CreateTextureFromImage(
                       buffer, GL_TEXTURE_2D, GL_RED_EXT,
                       width, height, GL_RED_EXT,
                       GL_UNSIGNED_BYTE, 0));
  if (!y_texture_.get()) {
    return;
  }

  // UV-plane
  glActiveTexture(GL_TEXTURE1);
  uv_texture_.reset(texture_cache_->CreateTextureFromImage(
                        buffer, GL_TEXTURE_2D, GL_RG_EXT,
                        width / 2, height / 2, GL_RG_EXT,
                        GL_UNSIGNED_BYTE, 1));
}

- (void)cleanUpTextures {
  y_texture_.reset(NULL);
  uv_texture_.reset(NULL);

  // Periodic texture cache flush every frame
  texture_cache_->Flush();
}

// Sets the list of photos in state->current_photos.
- (void)prepareDone:(ControllerState*)state {
  // Set the current crop of photos as current_photo in the pop state.
  vector<PhotoHandle> photo_handles;
  [self assetUrlsToPhotoHandleVec:&photo_handles];
  state->current_photos.photo_ids.clear();
  for (int i = 0; i < photo_handles.size(); ++i) {
    const PhotoHandle& ph = photo_handles[i];
    state->current_photos.photo_ids.push_back(
        std::make_pair(ph->id().local_id(),
                       ph->episode_id().local_id()));
    // Set current_episode to the largest (most recent) episode_id. This will
    // ensure the row containing this episode is visible when we transition to
    // the library.
    state->current_episode = std::max(
        state->current_episode, ph->episode_id().local_id());
  }

  // Clear the list of taken asset urls.
  asset_keys_.clear();

  // Hide the preview.
  preview_.hidden = YES;
}

- (void)navbarDone {
  if (acquisition_count_) {
    exit_pending_ = true;
    return;
  }
  exit_pending_ = false;
  ControllerState pop_controller_state =
      [state_->root_view_controller() popControllerState];

  [self prepareDone:&pop_controller_state];

  [state_->root_view_controller() dismissViewController:pop_controller_state];
}

- (void)navbarCamera:(id)sender {
  if (!state_->ui_application_active()) {
    return;
  }

  state_->analytics()->CameraTakePicture();

#if TARGET_IPHONE_SIMULATOR
  Image image([self snapshotGLView]);
  NSData* png_data = image.CompressPNG(NULL);
  const string path = state_->photo_dir() + "/capture.png";
  CHECK(WriteDataToFile(path, png_data));
  LOG("wrote %s: %d", path, [png_data length]);
#else // !(TARGET_IPHONE_SIMULATOR)
  ++acquisition_count_;
  WallTimer timer;

  // Determine the exif orientation.
  const int exif_orientation = self.currentExifOrientation;

  // Set the orientation on the capture connection so that the correct
  // orientation is populated by captureStillImageAsynchronouslyFromConnection.
  AVCaptureConnection* conn =
      [still_output_ connectionWithMediaType:AVMediaTypeVideo];
  conn.videoOrientation = static_cast<AVCaptureVideoOrientation>(rotating_view_.orientation);
  conn.videoScaleAndCropFactor = self.normalizedZoom;

  [still_output_
    captureStillImageAsynchronouslyFromConnection:conn
                                completionHandler:
      ^(CMSampleBufferRef sample_buffer, NSError* error) {
      if (error) {
        LOG("take picture failed: %s", error);
        return;
      }

      NSDictionary* raw_attachments =
          (__bridge_transfer NSDictionary*)CMCopyDictionaryOfAttachments(
              NULL, sample_buffer, kCMAttachmentMode_ShouldPropagate);

      Dict attachments(NULL);
      attachments.acquire(
          [[NSMutableDictionary alloc] initWithDictionary:raw_attachments]);

      // Add the timestamp of when the photo was taken.
      NSDate* now = [NSDate date];
      Dict exif(attachments.find_dict(kCGImagePropertyExifDictionary));
      Dict tiff(attachments.find_dict(kCGImagePropertyTIFFDictionary));
      exif.insert(kCGImagePropertyExifDateTimeOriginal, now);
      tiff.insert(kCGImagePropertyTIFFDateTime, now);

      // Add location data.
      const Breadcrumb b = state_->location_tracker().breadcrumb;
      Dict gps(kCGImagePropertyGPSTimeStamp, b.timestamp());
      if (b.location().latitude() < 0) {
        gps.insert(kCGImagePropertyGPSLatitudeRef, "S");
        gps.insert(kCGImagePropertyGPSLatitude, -b.location().latitude());
      } else {
        gps.insert(kCGImagePropertyGPSLatitudeRef, "N");
        gps.insert(kCGImagePropertyGPSLatitude, b.location().latitude());
      }
      if (b.location().longitude() < 0) {
        gps.insert(kCGImagePropertyGPSLongitudeRef, "W");
        gps.insert(kCGImagePropertyGPSLongitude, -b.location().longitude());
      } else {
        gps.insert(kCGImagePropertyGPSLongitudeRef, "E");
        gps.insert(kCGImagePropertyGPSLongitude, b.location().longitude());
      }
      gps.insert(kCGImagePropertyGPSDOP, b.location().accuracy());
      gps.insert(kCGImagePropertyGPSAltitude, b.location().altitude());
      attachments.insert(kCGImagePropertyGPSDictionary, gps);

      // Set the attachments back on the sample buffer.
      CMSetAttachments(sample_buffer, attachments,
                       kCMAttachmentMode_ShouldPropagate);

      int width = exif.find_value(
          kCGImagePropertyExifPixelXDimension).int_value();
      int height = exif.find_value(
          kCGImagePropertyExifPixelYDimension).int_value();
      switch (exif_orientation) {
        case 5:  // UIImageOrientationLeftMirrored
        case 6:  // UIImageOrientationRight
        case 7:  // UIImageOrientationRightMirrored
        case 8:  // UIImageOrientationLeft
          std::swap(width, height);
          break;
      }

      NSData* jpeg_data =
          [AVCaptureStillImageOutput
                           jpegStillImageNSDataRepresentation:sample_buffer];
      state_->AddAsset(jpeg_data, attachments, ^(string asset_url, string asset_key) {
          dispatch_main(^{
              asset_keys_.push_back(asset_key);
              if (!--acquisition_count_) {
                if (exit_pending_) {
                  [self navbarDone];
                } else if (preview_pending_) {
                  [self previewTapped];
                }
              }
            });
        });

      LOG("camera: captured photo: %dx%d: %d bytes: %.3f ms",
          width, height, jpeg_data.length, timer.Milliseconds());
    }];
#endif // !(TARGET_IPHONE_SIMULATOR)
}

- (void)assetUrlsToPhotoHandleVec:(vector<PhotoHandle>*)photo_handles {
  photo_handles->clear();
  for (int i = asset_keys_.size() - 1; i >= 0; --i) {
    PhotoHandle ph = state_->photo_table()->LoadAssetPhoto(asset_keys_[i], state_->db());
    if (!ph.get()) {
      continue;
    }
    // Need to explicitly verify that the photo is still posted to the
    // episode, as with the asset key we will ALWAYS be able to load
    // the photo. This is because we maintain the fingerprint => photo
    // mapping forever.
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(ph->episode_id(), state_->db());
    if (eh.get() && eh->IsPosted(ph->id().local_id())) {
      photo_handles->push_back(ph);
    }
  }
}

- (void)setCurrentPhotos {
  ControllerState controller_state =
      [state_->root_view_controller() photoLayoutController].controllerState;
  CurrentPhotos* cp = &controller_state.current_photos;
  cp->prev_callback = NULL;
  cp->next_callback = NULL;
  PhotoIdVec* v = &cp->photo_ids;
  v->clear();

  vector<PhotoHandle> photo_handles;
  [self assetUrlsToPhotoHandleVec:&photo_handles];
  for (int i = 0; i < photo_handles.size(); ++i) {
    v->push_back(std::make_pair(photo_handles[i]->id().local_id(),
                                photo_handles[i]->episode_id().local_id()));
  }

  cp->refresh_callback = ^{
    [self setCurrentPhotos];
  };

  [state_->root_view_controller() photoLayoutController].controllerState = controller_state;
}

- (void)previewTapped {
  if (acquisition_count_) {
    preview_pending_ = true;
    return;
  }
  preview_pending_ = false;
  preview_.transform = CGAffineTransformMakeScale(kPreviewFinalScale, kPreviewFinalScale);
  [state_->root_view_controller() photoLayoutController].controllerState = ControllerState();
  [self setCurrentPhotos];
  ControllerState photo_controller_state =
      [state_->root_view_controller() photoLayoutController].controllerState;
  [state_->root_view_controller() showPhoto:ControllerTransition(photo_controller_state)];
}

- (void)showPreview:(int)exif_orientation {
  [CATransaction begin];
  [CATransaction setValue:(id)kCFBooleanTrue forKey:kCATransactionDisableActions];

  // First, stop any existing animation and clear any existing review image (to
  // free up its memory).
  [preview_.layer removeAllAnimations];
  preview_.layer.shadowOpacity = 0;
  [preview_ setImage:NULL forState:UIControlStateNormal];
  [preview_ setImage:NULL forState:UIControlStateHighlighted];

  // Create the thumbnail image by snapshotting the most recent camera preview
  // textures.
  Image thumbnail([self snapshotGLView]);
  thumbnail.set_exif_orientation(exif_orientation);

  // Determine the target review size by performing an aspect-fit scaling of
  // the thumbnail image.
  const float target_size = 120;
  const float scale = std::min(target_size / thumbnail.width(),
                               target_size / thumbnail.height());
  const int preview_width = static_cast<int>(thumbnail.width() * scale);
  const int preview_height = static_cast<int>(thumbnail.height() * scale);

  // Initialize the preview button.
  UIImage* image = thumbnail.MakeUIImage();
  const CGSize s = preview_.superview.bounds.size;
  const CGRect f = CGRectMake(
      8, s.height - preview_height - 8, preview_width, preview_height);

  [preview_ setImage:image forState:UIControlStateNormal];
  [preview_ setImage:image forState:UIControlStateHighlighted];
  preview_.frame = preview_.superview.bounds;
  preview_.transform = CGAffineTransformIdentity;
  preview_.hidden = NO;
  [CATransaction commit];

  // Animate the preview button into its final location.
  [UIView animateWithDuration:0.35
                        delay:0.15
                      options:UIViewAnimationOptionCurveEaseOut
                   animations:^{
      preview_.frame = f;
    }
                   completion:^(BOOL finished) {
      if (!finished) {
        return;
      }
      preview_.layer.shadowOpacity = 1;
      // Fade out the review button after 5 seconds.
      dispatch_after_main(5, ^{
          [UIView animateWithDuration:0.35
                                delay:0.00
                              options:UIViewAnimationOptionCurveEaseOut
                           animations:^{
              preview_.transform = CGAffineTransformMakeScale(
                  kPreviewFinalScale, kPreviewFinalScale);
            }
                           completion:NULL];
        });
    }];
}

- (void)toggleCamera {
#if !(TARGET_IPHONE_SIMULATOR)
  NSArray* capture_devices =
      [AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo];
  if (capture_devices.count > 1) {
    const int old_device = current_device_;
    current_device_ = (current_device_ + 1) % capture_devices.count;
    [session_ beginConfiguration];
    AVCaptureDeviceInput* old_input = [[session_ inputs] objectAtIndex:0];
    [session_ removeInput:old_input];
    if ([self setupCaptureDevice:current_device_]) {
      state_->db()->Put(kDeviceKey, current_device_);
    } else {
      current_device_ = old_device;
      [session_ addInput:old_input];
    }
    [session_ commitConfiguration];
  }
#endif // !(TARGET_IPHONE_SIMULATOR)
}

- (void)showMessage:(const string&)text {
  message_.text = NewNSString(text);
  message_.hidden = NO;
  message_display_time_ = WallTime_Now();
  dispatch_after_main(2, ^{
      [self clearMessage];
    });
}

- (void)clearMessage {
  const double kMinMessageDisplay = 1.5;
  const double elapsed = WallTime_Now() - message_display_time_;
  if (elapsed >= kMinMessageDisplay) {
    message_.hidden = YES;
    return;
  }

  dispatch_after_main(kMinMessageDisplay - elapsed, ^{
      message_.hidden = YES;
    });
}

- (void)clearFocusCrosshairs {
  [focus_crosshairs_ removeFromSuperview];
  focus_crosshairs_ = NULL;
}

- (void)makeFocusCrosshairsAtPoint:(CGPoint)p
                              mode:(AVCaptureFocusMode)mode {
  UIImage* images[2];
  if (mode == AVCaptureFocusModeAutoFocus) {
    // Regular autofocus.
    images[0] = UIStyle::kCameraAutofocusSmall0;
    images[1] = UIStyle::kCameraAutofocusSmall1;
  } else {
    // Continuous autofocus.
    images[0] = UIStyle::kCameraAutofocus0;
    images[1] = UIStyle::kCameraAutofocus1;
  }
  focus_crosshairs_ =
      [[UIImageView alloc] initWithImage:images[0]];
  [focus_crosshairs_ setAnimationImages:Array(images[0], images[1])];
  [focus_crosshairs_ setAnimationDuration:0.3];
  focus_crosshairs_.center = p;
  [glk_view_controller_.view addSubview:focus_crosshairs_];
  [focus_crosshairs_ startAnimating];
}

- (void)focusAtPoint:(CGPoint)p
                mode:(AVCaptureFocusMode)mode
            animated:(BOOL)animated {
#if !(TARGET_IPHONE_SIMULATOR)
  if (!y_texture_.get()) {
    return;
  }

  const CGPoint v = [self viewCoordinateToVideoCoordinate:p];
  // LOG("focus at point: %.2f", v);

  NSArray* capture_devices =
      [AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo];
  AVCaptureDevice* device = [capture_devices objectAtIndex:current_device_];
  NSError* error;
  if (![device lockForConfiguration:&error]) {
    LOG("device configuration failed: %s", error);
    return;
  }

  if ([device isFocusPointOfInterestSupported] &&
      [device isFocusModeSupported:mode]) {
    if (mode != AVCaptureFocusModeLocked) {
      [device setFocusPointOfInterest:v];
    }
    [device setFocusMode:mode];
  }
  if ([device isExposurePointOfInterestSupported] &&
      [device isExposureModeSupported:AVCaptureExposureModeAutoExpose]) {
    if (mode != AVCaptureFocusModeLocked) {
      [device setExposurePointOfInterest:v];
    }
    [device setExposureMode:AVCaptureExposureModeAutoExpose];
  }
  [device unlockForConfiguration];

  [self clearFocusCrosshairs];

  if (animated) {
    if (mode == AVCaptureFocusModeAutoFocus) {
      [self showMessage:"focusing"];
    } else {
      [self showMessage:"continuous focus"];
    }

    [self makeFocusCrosshairsAtPoint:p mode:mode];
    [focus_crosshairs_ setTransform:CGAffineTransformMakeScale(2.0, 2.0)];
    [UIView animateWithDuration:0.2
                     animations:^{
        [focus_crosshairs_ setTransform:CGAffineTransformIdentity];
      }];
    if (mode == AVCaptureFocusModeContinuousAutoFocus) {
      dispatch_after_main(1, ^{
          [self clearFocusCrosshairs];
          [self clearMessage];
        });
    };
  }
#endif // !(TARGET_IPHONE_SIMULATOR)
}

- (int)currentExifOrientation {
#if TARGET_IPHONE_SIMULATOR
  return EXIF_0ROW_TOP_0COL_LEFT;
#else  // !TARGET_IPHONE_SIMULATOR
  AVCaptureDeviceInput* input = [[session_ inputs] objectAtIndex:0];
  return GetExifDeviceOrientation(
      (input.device.position == AVCaptureDevicePositionFront),
      rotating_view_.orientation);
#endif // !TARGET_IPHONE_SIMULATOR
}

- (Matrix4f)transformForConnection:(AVCaptureConnection*)conn {
  Matrix4f m;
  switch (conn.videoOrientation) {
    case AVCaptureVideoOrientationPortrait:
      break;
    case AVCaptureVideoOrientationPortraitUpsideDown:
      break;
    case AVCaptureVideoOrientationLandscapeRight:
      m.rotate(kPi / 2, 0, 0, 1);   // 90 cw
      m.scale(1, -1, 1);
      break;
    case AVCaptureVideoOrientationLandscapeLeft:
      m.rotate(-kPi / 2, 0, 0, 1);  // 90 ccw
      break;
  }
  return m;
}

- (void)toggleFlash {
#if !(TARGET_IPHONE_SIMULATOR)
  NSArray* capture_devices =
      [AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo];
  AVCaptureDevice* device = [capture_devices objectAtIndex:current_device_];

  UILabel* label =
      [[flash_menu_ labels] objectAtIndex:[flash_menu_ selectedItem]];
  AVCaptureFlashMode flash_mode = static_cast<AVCaptureFlashMode>(label.tag);
  if (flash_mode != device.flashMode) {
    switch (flash_mode) {
      case AVCaptureFlashModeOff:
        state_->analytics()->CameraFlashOff();
        break;
      case AVCaptureFlashModeOn:
        state_->analytics()->CameraFlashOn();
        break;
      case AVCaptureFlashModeAuto:
        state_->analytics()->CameraFlashAuto();
        break;
    }

    if ([device lockForConfiguration:NULL]) {
      [device setFlashMode:flash_mode];
      [device unlockForConfiguration];
      state_->db()->Put(Format("%s/%d", kFlashModeKey, current_device_),
                           [flash_menu_ selectedItem]);
    }
  }
#endif // !(TARGET_IPHONE_SIMULATOR)
}

- (CGPoint)viewCoordinateToVideoCoordinate:(CGPoint)p {
  const float w = glk_view_controller_.view.frame.size.width;
  const float h = glk_view_controller_.view.frame.size.height;
  Matrix4f m(image_pipeline_->InitMVP(y_texture_->transform(), w, h, zoom_));
  // Apply the glViewport() transformation.
  m.translate(1, 1, 0);
  m.scale(w / 2, h / 2, 1);
  // Invert the model-view-projection matrix to get a transformation from
  // screen coordinates back to normalized world coordinates.
  bool invertible;
  m.invert(&invertible);
  CHECK(invertible);
  // Transform the normalized world coordinates into video coordinates.
  m.scale(-0.5, 0.5, 1);
  m.translate(0.5, 0.5, 0);
  const Vector4f v(m * Vector4f(p));
  return CGPointMake(v.x(), v.y());
}

- (Image)snapshotGLView {
  if (!state_->ui_application_active()) {
    return Image();
  }

  if (!y_texture_.get()) {
    LOG("unable to initialize y/uv textures");
    return Image();
  }

#if (TARGET_IPHONE_SIMULATOR)
  const int width = y_texture_->width();
  const int height = y_texture_->height();
#else // !(TARGET_IPHONE_SIMULATOR)
  const int width = y_texture_->width() / 2;
  const int height = y_texture_->height() / 2;
  y_texture_->mutable_transform()->identity();
  y_texture_->mutable_transform()->scale(width, height, 1);
#endif // !(TARGET_IPHONE_SIMULATOR)

  ScopedRef<CVPixelBufferRef> render_target;
  CVReturn err = CVPixelBufferCreate(
      kCFAllocatorDefault, width, height,
      kCVPixelFormatType_32BGRA,
      Dict(kCVPixelBufferIOSurfacePropertiesKey, Dict()),
      render_target.mutable_ptr());
  if (err != kCVReturnSuccess) {
    LOG("CVPixelBufferCreate() failed: %d", err);
    return Image();
  }

  ScopedPtr<GLTexture2D> render_texture(
      texture_cache_->CreateTextureFromImage(
          render_target, GL_TEXTURE_2D, GL_RGBA,
          width, height, GL_BGRA,
          GL_UNSIGNED_BYTE, 0));
  if (!render_texture.get()) {
    return Image();
  }

  {
    ScopedPtr<GLTexture2DFrameBuffer> frame_buffer(
        new GLTexture2DFrameBuffer(render_texture.get()));
    [self renderFramebuffer:frame_buffer.get()
                       zoom:self.normalizedZoom];
    glFlush();
  }

  return Image(render_target);
}

- (void)glkView:(GLKView*)view drawInRect:(CGRect)rect {
  glClearColor(0, 0, 0, 1);
  glClear(GL_COLOR_BUFFER_BIT);

  if (!y_texture_.get()) {
    return;
  }

  GLKViewFrameBuffer frame_buffer(view);
  if (aspect_fit_zoom_ < 0) {
    // Determine the transformed width and height of our input texture.
    const Vector4f v = y_texture_->transform() * Vector4f(1, 1, 0, 1);
    const float tw = fabs(v.x());
    const float th = fabs(v.y());
    // The zoom scale to perform an aspect-fit.
    aspect_fit_zoom_ =
        std::min(frame_buffer.width() / tw, frame_buffer.height() / th);
    // The zoom scale to perform an aspect-fill.
    aspect_fill_zoom_ = prev_zoom_ = zoom_ =
        std::max(frame_buffer.width() / tw, frame_buffer.height() / th);
  }

  [self renderFramebuffer:&frame_buffer zoom:zoom_];
}

- (void)glkViewControllerUpdate:(GLKViewController*)controller {
#if !(TARGET_IPHONE_SIMULATOR)
  NSArray* capture_devices =
      [AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo];
  AVCaptureDevice* device = [capture_devices objectAtIndex:current_device_];
  if (focus_crosshairs_ != NULL &&
      device.focusMode == AVCaptureFocusModeLocked) {
    [self clearFocusCrosshairs];
    [self clearMessage];
  }
  if (focus_needed_ && y_texture_.get()) {
    focus_needed_= false;
    [self focusAtPoint:glk_view_controller_.view.center
                  mode:AVCaptureFocusModeContinuousAutoFocus
              animated:YES];
  }
#endif // !(TARGET_IPHONE_SIMULATOR)
}

- (void)renderFramebuffer:(GLFrameBuffer*)frame_buffer
                     zoom:(float)zoom {
#if (TARGET_IPHONE_SIMULATOR)
  if (y_texture_.get()) {
    image_pipeline_->Run(frame_buffer, *y_texture_, zoom);
  }
#else // !(TARGET_IPHONE_SIMULATOR)
  if (y_texture_.get() && uv_texture_.get()) {
    image_pipeline_->Run(
        frame_buffer, *y_texture_, *uv_texture_, true, zoom);
  }
#endif // !(TARGET_IPHONE_SIMULATOR)
}

- (void)captureOutput:(AVCaptureOutput*)capture_output
didOutputSampleBuffer:(CMSampleBufferRef)sample_buffer
       fromConnection:(AVCaptureConnection*)conn {
  if (!state_->ui_application_active()) {
    return;
  }
  if (!texture_cache_.get()) {
    LOG("No video texture cache");
    return;
  }

  [self cleanUpTextures];
  [self setupTextures:sample_buffer];

  CVImageBufferRef buffer = CMSampleBufferGetImageBuffer(sample_buffer);
  y_texture_->mutable_transform()->identity();
  y_texture_->mutable_transform()->scale(
      CVPixelBufferGetWidth(buffer), CVPixelBufferGetHeight(buffer), 1);
  *y_texture_->mutable_transform() *= [self transformForConnection:conn];

  // Manually draw a frame of video output.
  [(GLKView*)glk_view_controller_.view display];
}

- (void)observeValueForKeyPath:(NSString*)keyPath
                      ofObject:(id)object
                        change:(NSDictionary*)change
                       context:(void*)context {
  if (context == kCapturingStillImageContext) {
    const bool is_capturing_still_image =
        [[change objectForKey:NSKeyValueChangeNewKey] boolValue];
    if (is_capturing_still_image) {
      [self showPreview:self.currentExifOrientation];

      // Do flash bulb-like animation.
      flash_view_ = [[UIView alloc]
                      initWithFrame:glk_view_controller_.view.frame];
      [flash_view_ setBackgroundColor:[UIColor whiteColor]];
      [flash_view_ setAlpha:0];
      [self.view addSubview:flash_view_];

      [UIView animateWithDuration:0.3
                       animations:^{
          [flash_view_ setAlpha:1];
        }];
    } else {
      [UIView animateWithDuration:0.3
                       animations:^{
          [flash_view_ setAlpha:0];
        }
                       completion:^(BOOL finished){
          [flash_view_ removeFromSuperview];
          flash_view_ = NULL;
        }];
    }
  }
}


@end  // CameraViewController
