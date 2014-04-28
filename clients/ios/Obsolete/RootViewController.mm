// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AppState.h"
#import "CameraViewController.h"
#import "DB.h"
#import "Logging.h"
#import "PhotoViewController.h"
#import "RootViewController.h"
#import "SettingsViewController.h"
#import "WheelMenu.h"

namespace {

const string kViewIndexKey = AppState::metadata_key("root_view_index");

}  // namespace

@interface RootViewController (internal)
- (void)homeSelected;
- (void)cameraSelected;
- (void)settingsSelected;
- (void)developerSelected;
- (void)showViewController:(UIViewController*)new_view_controller;
@end  // RootViewController (internal)

@implementation RootViewController

- (id)initWithState:(AppState*)state {
  if (self = [super init]) {
    state_ = state;

    camera_view_controller_ =
        [[CameraViewController alloc] initWithState:state];
    photo_view_controller_ =
        [[PhotoViewController alloc] initWithState:state];
    settings_view_controller_ =
        [[SettingsViewController alloc] initWithState:state];

    [self addChildViewController:photo_view_controller_];
    [self addChildViewController:camera_view_controller_];
    [self addChildViewController:settings_view_controller_];

    current_view_controller_ =
        [self.childViewControllers objectAtIndex:
               state_->db()->Get<int>(kViewIndexKey)];
    if (!current_view_controller_) {
      current_view_controller_ = photo_view_controller_;
    }
    prev_view_controller_ = photo_view_controller_;
  }
  return self;
}

- (void)loadView {
  LOG("root: view load");
  self.view = [UIView new];
  self.view.autoresizesSubviews = YES;
  self.view.backgroundColor = [UIColor blackColor];
  [self.view addSubview:current_view_controller_.view];

  WheelMenu* wheel = state_->wheel_menu();
  struct {
    UIButton* button;
    SEL selector;
  } kActions[] = {
    { [wheel homeButton], @selector(homeSelected) },
    { [wheel cameraButton], @selector(cameraSelected) },
    { [wheel settingsButton], @selector(settingsSelected) },
    { [wheel developerButton], @selector(developerSelected) },
  };
  for (int i = 0; i < ARRAYSIZE(kActions); ++i) {
    [kActions[i].button addTarget:self
                           action:kActions[i].selector
                 forControlEvents:UIControlEventTouchUpInside];
  }
}

- (void)viewDidUnload {
  LOG("root: view did unload");
  [super viewDidUnload];
}

- (void)viewWillAppear:(BOOL)animated {
  LOG("root: view will appear");
  [super viewWillAppear:animated];
  current_view_controller_.view.frame = self.view.bounds;
}

- (void)viewDidAppear:(BOOL)animated {
  LOG("root: view did appear");
  [super viewDidAppear:animated];
}

- (void)viewWillDisappear:(BOOL)animated {
  LOG("root: view will disappear");
  [super viewWillDisappear:animated];
}

- (void)dismissViewControllerAnimated:(BOOL)flag
                           completion:(void (^)(void))completion {
  [self showViewController:prev_view_controller_];
}

- (void)homeSelected {
  [self showViewController:photo_view_controller_];
}

- (void)cameraSelected {
  [self showViewController:camera_view_controller_];
}

- (void)settingsSelected {
  [self showViewController:settings_view_controller_];
}

- (void)developerSelected {
}

- (void)showViewController:(UIViewController*)new_view_controller {
  if (new_view_controller == current_view_controller_) {
    // Nothing to do.
    return;
  }

  const int current_index =
      [self.childViewControllers indexOfObject:current_view_controller_];
  const int new_index =
      [self.childViewControllers indexOfObject:new_view_controller];
  const int direction = (current_index > new_index) ? 1 : -1;
  const float delta = direction * self.view.frame.size.width;
  new_view_controller.view.frame = CGRectOffset(self.view.bounds, -delta, 0);

  [self transitionFromViewController:current_view_controller_
                    toViewController:new_view_controller
                            duration:0.3
                             options:0
                          animations:^{
      [self.view addSubview:new_view_controller.view];
      new_view_controller.view.frame = self.view.bounds;
      current_view_controller_.view.frame =
          CGRectOffset(self.view.bounds, delta, 0);
    }
                          completion:^(BOOL finished){
      prev_view_controller_ = current_view_controller_;
      current_view_controller_ = new_view_controller;
      state_->db()->Put(kViewIndexKey, new_index);
    }];
}

@end  // CircularNavigationController
