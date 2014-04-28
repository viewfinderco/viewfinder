// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <AudioToolbox/AudioToolbox.h>
#import <MediaPlayer/MediaPlayer.h>
#import "VolumeButtons.h"

@interface VolumeButtons ()
- (void)volumeChanged:(float)volume;
- (void)applicationWillResignActive;
- (void)applicationDidBecomeActive;
@end  // VolumeButtons ()

namespace {

const float kVolumeDelta = 1.0 / 131072.0;

void VolumeListenerCallback(
    void* client_data,
    AudioSessionPropertyID id,
    UInt32 data_size,
    const void* data) {
  const float* volume = reinterpret_cast<const float*>(data);
  VolumeButtons* buttons = (__bridge VolumeButtons*)(client_data);
  [buttons volumeChanged:*volume];
}

}  // namespace

@implementation VolumeButtons

@dynamic up;
@dynamic down;
@dynamic enabled;

- (id)init {
  if (self = [super initWithFrame:CGRectZero]) {
    volume_view_ = [[MPVolumeView alloc] initWithFrame:CGRectZero];
    // Disabled by default.
    volume_view_.hidden = YES;
    [self addSubview:volume_view_];

    init_mu_.Lock();
    dispatch_low_priority(^{
        // LOG("volume: init audio session");
        AudioSessionInitialize(NULL, NULL, NULL, NULL);
        AudioSessionAddPropertyListener(
            kAudioSessionProperty_CurrentHardwareOutputVolume,
            VolumeListenerCallback, (__bridge void*)self);
        const uint32_t category = kAudioSessionCategory_AmbientSound;
        OSStatus error = AudioSessionSetProperty(
            kAudioSessionProperty_AudioCategory,
            sizeof(category), &category);
        if (error != noErr) {
          LOG("volume: failed to configure audio category: %d", error);
        }
        init_mu_.Unlock();
      });

    [[NSNotificationCenter defaultCenter]
      addObserverForName:UIApplicationWillResignActiveNotification
                  object:nil
                   queue:[NSOperationQueue mainQueue]
              usingBlock:^(NSNotification* notification){
        [self applicationWillResignActive];
      }];

    [[NSNotificationCenter defaultCenter]
      addObserverForName:UIApplicationDidBecomeActiveNotification
                  object:nil
                   queue:[NSOperationQueue mainQueue]
              usingBlock:^(NSNotification *notification){
        [self applicationDidBecomeActive];
      }];

    [self applicationDidBecomeActive];
  }
  return self;
}

- (void)volumeChanged:(float)volume {
  if (!enabled_ || volume == reset_volume_) {
    return;
  }
  // LOG("volume: %s: %.6f -> %.6f",
  //     (volume > reset_volume_) ? "up" : "down", volume, reset_volume_);

  enabled_ = false;
  [MPMusicPlayerController applicationMusicPlayer].volume = reset_volume_;
  enabled_ = true;

  if (volume > reset_volume_) {
    up_callbacks_.Run();
  } else if (volume < reset_volume_) {
    down_callbacks_.Run();
  }
}

- (void)applicationDidBecomeActive {
  // Start up the audio session on a background thread as it can take a few 100
  // milliseconds of time.
  dispatch_low_priority(^{
      MutexLock l(&init_mu_);
      if (!audio_session_active_) {
        // LOG("volume: activate audio session");
        audio_session_active_ = true;
        AudioSessionSetActive(true);
      }
    });

  if (enabled_) {
    // The double dispatch_async() hack ensures that MPVolumeView is truly
    // visible before we adjust the volume.
    dispatch_async(dispatch_get_main_queue(), ^{
        dispatch_async(dispatch_get_main_queue(), ^{
            MPMusicPlayerController* music_player =
                [MPMusicPlayerController applicationMusicPlayer];
            launch_volume_ = music_player.volume;
            reset_volume_ = launch_volume_;
            if (reset_volume_ == 1.0) {
              reset_volume_ -= kVolumeDelta;
            } else if (reset_volume_ == 0.0) {
              reset_volume_ += kVolumeDelta;
            }
            music_player.volume = reset_volume_;
            // LOG("volume: init volume: launch=%.6f reset=%.6f",
            //     launch_volume_, reset_volume_);
          });
      });
  }
}

- (void)applicationWillResignActive {
  MutexLock l(&init_mu_);
  if (audio_session_active_) {
    // LOG("volume: deactivate audio session");
    audio_session_active_ = false;
    AudioSessionSetActive(false);
  }
}

- (CallbackSet*)up {
  return &up_callbacks_;
}

- (CallbackSet*)down {
  return &down_callbacks_;
}

- (BOOL)enabled {
  return enabled_;
}

- (void)setEnabled:(BOOL)enabled {
  if (enabled_ == enabled) {
    return;
  }
  if (enabled_) {
    enabled_ = false;
    [MPMusicPlayerController applicationMusicPlayer].volume = launch_volume_;
    // LOG("volume: reset to launch volume: %.6f", launch_volume_);

    // The double dispatch_async() hack ensures that the the setting of the
    // volume on the above line has had a chance to take place before we hide
    // the MPVolumeView.
    dispatch_async(dispatch_get_main_queue(), ^{
        dispatch_async(dispatch_get_main_queue(), ^{
            volume_view_.hidden = YES;
            // Deactivate the audio session.
            [self applicationWillResignActive];
          });
      });
  } else {
    enabled_ = true;
    volume_view_.hidden = NO;
    [self applicationDidBecomeActive];
  }
}

- (void)dealloc {
  AudioSessionRemovePropertyListenerWithUserData(
      kAudioSessionProperty_CurrentHardwareOutputVolume,
      VolumeListenerCallback, (__bridge void*)self);
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  if (enabled_) {
    [[MPMusicPlayerController applicationMusicPlayer] setVolume:launch_volume_];
  }
}

@end  // VolumeButtons
