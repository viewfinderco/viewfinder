// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <unordered_map>
#import <UIKit/UIMenuController.h>
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "ScopedNotification.h"

namespace {

class NotificationNameToObjectMap {
  typedef std::unordered_map<NSString*, id, HashObjC> NameToObjectMap;

 public:
  NotificationNameToObjectMap() {
    InitApplication();
    InitKeyboard();
    InitMenuController();
  }

  id Lookup(NSString* name) const {
    return FindOrNull(m_, name);
  }

 private:
  void Init(NSString* name, id object) {
    m_[name] = object;
  }

  void InitApplication() {
    // Note, since the object for these notifications is NULL we don't have to
    // add it to the map.

    // m_[UIApplicationWillResignActiveNotification] = NULL;
    // m_[UIApplicationDidBecomeActiveNotification] = NULL;
    // m_[UIApplicationWillEnterForegroundNotification] = NULL;
    // m_[UIApplicationDidEnterBackgroundNotification] = NULL;
    // m_[UIApplicationWillTerminateNotification] = NULL;
    // m_[UIApplicationDidReceiveMemoryWarningNotification] = NULL;
  }

  void InitKeyboard() {
    // Note, since the object for these notifications is NULL we don't have to
    // add it to the map.

    // m_[UIKeyboardWillShowNotification] = NULL;
    // m_[UIKeyboardDidShowNotification] = NULL;
    // m_[UIKeyboardWillHideNotification] = NULL;
    // m_[UIKeyboardDidHideNotification] = NULL;
  }

  void InitMenuController() {
    id obj = [UIMenuController sharedMenuController];
    m_[UIMenuControllerWillShowMenuNotification] = obj;
    m_[UIMenuControllerDidShowMenuNotification] = obj;
    m_[UIMenuControllerWillHideMenuNotification] = obj;
    m_[UIMenuControllerDidHideMenuNotification] = obj;
    m_[UIMenuControllerMenuFrameDidChangeNotification] = obj;
  }

 private:
  NameToObjectMap m_;
};

LazyStaticPtr<NotificationNameToObjectMap> name_to_object;

}  // namespace

void ScopedNotification::Init(
    NSString* name, void (^callback)(NSNotification* n)) {
  Init(name, NULL, callback);
}

void ScopedNotification::Init(
    NSString* name, id object, void (^callback)(NSNotification* n)) {
  if (observer_id_) {
    [[NSNotificationCenter defaultCenter] removeObserver:observer_id_];
    observer_id_ = NULL;
  }

  if (!object) {
    object = name_to_object->Lookup(name);
  }

  if (name) {
    observer_id_ =
        [[NSNotificationCenter defaultCenter]
          addObserverForName:name
                      object:object
                       queue:[NSOperationQueue mainQueue]
                  usingBlock:callback];
  }
}
