// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_SCOPED_NOTIFICATION_H
#define VIEWFINDER_SCOPED_NOTIFICATION_H

#import <Foundation/Foundation.h>

// Helper class for simplifying usage of NSNotificationCenter. Usage:
//
//   ScopedNotification will_show_keyboard;
//   will_show_keyboard.Init(
//       UIKeyboardWillShowNotification,
//       ^(NSNotification* n) {
//         // Handle notification
//       });
//   ...
//   will_show_keyboard.Clear();
class ScopedNotification {
 public:
  ScopedNotification()
      : observer_id_(NULL){
  }
  ScopedNotification(NSString* name, void (^callback)(NSNotification* n))
      : observer_id_(NULL) {
    Init(name, callback);
  }
  ~ScopedNotification() {
    Clear();
  }

  void Clear() {
    Init(NULL, NULL);
  }

  void Init(NSString* name, void (^callback)(NSNotification* n));
  void Init(NSString* name, id object, void (^callback)(NSNotification*));

  id get() const {
    return observer_id_;
  }

 private:
  id observer_id_;
};

#endif  // VIEWFINDER_SCOPED_NOTIFICATION_H
