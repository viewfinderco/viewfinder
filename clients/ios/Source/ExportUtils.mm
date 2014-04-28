// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <UIKit/UIActivityViewController.h>
#import "ExportUtils.h"
#import "PhotoManager.h"
#import "PhotoStorage.h"
#import "RootViewController.h"
#import "StatusBar.h"
#import "UIAppState.h"

void ShowExportDialog(UIAppState* state, const PhotoSelectionVec& selection, void (^done)(bool completed)) {
  // The photo loading code tries to fill an WxH region of the screen, so it multiplies
  // by the screen scale.  Back out that multiplier so we load exactly the full-size version
  // (since otherwise it will try to load the original, which is usually not available for
  // network photos).
  const float scale = [UIScreen mainScreen].scale;
  // Can't make this a __block because block variables need to be copyable.
  Mutex* mutex = new Mutex;
  MutexLock lock(mutex);
  __block const CGSize load_size = CGSizeMake(kFullSize / scale, kFullSize / scale);

  __block NSMutableArray* items = [NSMutableArray arrayWithCapacity:selection.size()];
  __block int count = selection.size();

  auto Finish = ^{
    {
      MutexLock lock(mutex);
      if (--count > 0) {
        return;
      }
    }
    // If we've made it this far, there are no other threads that might interfere so it's safe
    // to unlock and delete the mutex.
    delete mutex;
    for (int i = 0; i < items.count; i++) {
      if (items[i] == [NSNull null]) {
        [[[UIAlertView alloc]
               initWithTitle:@"Error loading photos"
                     message:@"There was an error loading the selected photos"
                    delegate:NULL
           cancelButtonTitle:@"OK"
           otherButtonTitles:NULL]
          show];
        if (done) {
          done(false);
        }
        return;
      }
    }
    UIActivityViewController* activity_controller = [[UIActivityViewController alloc]
                                                      initWithActivityItems:items applicationActivities:nil];
    activity_controller.completionHandler = ^(NSString* activity_type, BOOL completed) {
      LOG("export: selected activity %s (%s)", activity_type, completed ? "completed" : "incomplete");
      [state->root_view_controller().statusBar
          hideMessageType:STATUS_MESSAGE_UI
          minDisplayDuration:0.75];
      if (done) {
        done(completed);
      }
    };
    [state->root_view_controller() presentViewController:activity_controller
                                                animated:YES
                                              completion:NULL];
  };

  [state->root_view_controller().statusBar
      setMessage:Format("Exporting %d Photo%s…", selection.size(),
                        Pluralize(selection.size()))
      activity:true
      type:STATUS_MESSAGE_UI];

  for (int i = 0; i < selection.size(); i++) {
    [items addObject:[NSNull null]];
    const int64_t photo_id = selection[i].photo_id;
    state->photo_manager()->LoadLocalPhoto(photo_id, load_size, ^(Image image) {
        MutexLock lock(mutex);
        if (image) {
          items[i] = image.MakeUIImage();
          dispatch_main(Finish);
        } else {
          dispatch_main(^{
              state->photo_manager()->LoadNetworkPhoto(photo_id, load_size, ^(Image image) {
                  MutexLock lock(mutex);
                  if (image) {
                    items[i] = image.MakeUIImage();
                  }
                  // Whether we succeed or not, decrement the count.
                  dispatch_main(Finish);
                });
            });
        }
      });
  }
  CHECK_EQ(items.count, selection.size());
}
