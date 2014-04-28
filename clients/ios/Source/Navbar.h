// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>
#import "ValueUtils.h"
#import "ViewpointTable.h"

extern const int kAddPhotosButtonIndex;

@class BadgeView;
class UIAppState;

@protocol NavbarEnv
@optional
- (void)navbarAction;
- (void)navbarAddPhotos;
- (void)navbarAutoSuggest;
- (void)navbarBack;
- (void)navbarDial;
- (void)navbarExit;
- (void)navbarRelatedConvos;
- (void)navbarActionBack;
- (void)navbarActionExit;
- (void)navbarActionExport;
- (void)navbarActionMute;
- (void)navbarActionRemove;
- (void)navbarActionRemoveConvo;
- (void)navbarActionShare;
- (void)navbarActionShareNew;
- (void)navbarActionShareExisting;
- (void)navbarActionUnmute;
- (void)navbarActionUnshare;
@end  // NavbarEnv

struct ButtonDefinition {
  enum ButtonType {
    COMPOSE,
    ICON,
    ICON_TEXT,
    GREY_ACTION,
    GREEN_ACTION,
    RED_ACTION,
  };
  ButtonType type;
  UIImage* image;
  NSString* title;
  SEL selector;

  ButtonDefinition()
      : type(ICON), image(NULL), title(NULL), selector(NULL) {
  }
  ButtonDefinition(ButtonType ty, UIImage* i, NSString* t, SEL s)
      : type(ty), image(i), title(t), selector(s) {
  }
};

enum NavbarState {
  NAVBAR_UNINITIALIZED = 0,
  NAVBAR_CAMERA_PHOTO,
  NAVBAR_COMPOSE,
  NAVBAR_CONVERSATIONS_PHOTO,
  NAVBAR_PROFILE_PHOTO,
};

typedef std::unordered_map<int, UIView*> ButtonTrayMap;

@interface SpacerView : UIImageView {
}

- (id)initWithImage:(UIImage*)image;

@end  // SpacerView

@interface Navbar : UIView {
 @private
  __weak id<NavbarEnv> env_;

  NavbarState navbar_state_;
  UIView* current_tray_;
  ButtonTrayMap tray_map_;
  CGRect tray_frame_;

  // These buttons are used in the floating navbar over non-modal views.
  ButtonDefinition navbar_auto_suggest_def_;
  ButtonDefinition navbar_export_def_;
  ButtonDefinition navbar_forward_def_;
  ButtonDefinition navbar_mute_def_;
  ButtonDefinition navbar_related_convos_def_;
  ButtonDefinition navbar_remove_convos_def_;
  ButtonDefinition navbar_remove_photos_def_;
  ButtonDefinition navbar_share_def_;
  ButtonDefinition navbar_share_new_def_;
  ButtonDefinition navbar_share_existing_def_;
  ButtonDefinition navbar_unmute_def_;
  ButtonDefinition navbar_unshare_def_;
}

@property (nonatomic, weak) id<NavbarEnv> env;
@property (nonatomic, readonly) NavbarState navbarState;
@property (nonatomic, readonly) float intrinsicHeight;

- (id)init;
- (void)show;
- (void)hide;
- (void)showCameraPhotoItems;
- (void)showComposeItems;
- (void)showConversationsPhotoItems;
- (void)showProfilePhotoItems;

@end  // Navbar

// local variables:
// mode: objc
// end:
