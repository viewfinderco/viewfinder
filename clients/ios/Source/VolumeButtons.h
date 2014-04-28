// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <Foundation/Foundation.h>
#import "Callback.h"
#import "Mutex.h"

typedef void (^ButtonBlock)();

@class MPVolumeView;

@interface VolumeButtons : UIView {
 @private
  Mutex init_mu_;
  MPVolumeView* volume_view_;
  float launch_volume_;
  float reset_volume_;
  CallbackSet up_callbacks_;
  CallbackSet down_callbacks_;
  BOOL enabled_;
  BOOL audio_session_active_;
}

@property (readonly, nonatomic) CallbackSet* up;
@property (readonly, nonatomic) CallbackSet* down;
@property (nonatomic) BOOL enabled;

@end  // VolumeButtons

// local variables:
// mode: objc
// end:
