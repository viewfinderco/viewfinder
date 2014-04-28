// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "ContactMetadata.pb.h"
#import "ContactTrapdoorsView.h"
#import "ScopedNotification.h"
#import "ScopedPtr.h"
#import "SettingsViewController.h"

class AddIdentitySettingsSection;
class BasicInfoSettingsSection;
class NicknameSettingsSection;
class PasswordSettingsSection;
class ShowConversationsSettingsSection;
@class DashboardCardContainer;

@interface ContactInfoController :
    SettingsViewTableController<ContactTrapdoorsEnv> {
 @private
  UIAppState* state_;
  int contact_changed_id_;
  int settings_changed_id_;
  ContactMetadata metadata_;
  ScopedPtr<AddIdentitySettingsSection> add_identity_;
  ScopedPtr<BasicInfoSettingsSection> basic_info_;
  ScopedPtr<NicknameSettingsSection> nickname_;
  ScopedPtr<PasswordSettingsSection> password_;
  ScopedPtr<ShowConversationsSettingsSection> show_conversations_;
  bool show_compose_button_;
  UIBarButtonItem* back_button_item_;
  UIBarButtonItem* cancel_button_item_;
  UIBarButtonItem* compose_button_item_;
  UIBarButtonItem* done_button_item_;
  UIView* editing_overlay_;
  ScopedNotification keyboard_will_show_;
  DashboardCardContainer* card_container_;
  ContactTrapdoorsView* contact_trapdoors_;
}

- (id)initWithState:(UIAppState*)state
            contact:(const ContactMetadata&)metadata;

@end  // ContactInfoController

// local variables:
// mode: objc
// end:
