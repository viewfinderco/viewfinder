// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <unordered_set>
#import <UIKit/UIKit.h>
#import <re2/re2.h>
#import "Utils.h"

class UIAppState;
class ContactMetadata;
class FollowerGroup;
@class TextLayer;

typedef void (^EditEmailCallback)(string);

enum ContactType {
  CONTACT_TYPE_UNKNOWN_EMAIL,
  CONTACT_TYPE_UNKNOWN_SMS,
  CONTACT_TYPE_PROSPECTIVE_EMAIL,
  CONTACT_TYPE_PROSPECTIVE_SMS,
  CONTACT_TYPE_VIEWFINDER,
  CONTACT_TYPE_GROUP,
};

@interface ContactsTableViewCell : UITableViewCell<UITextFieldDelegate> {
 @private
  UIScrollView* scroll_view_;
  TextLayer* label_;
  TextLayer* sublabel_;
  UIImageView* gradient_;
  UIImageView* detail_;
  UIButton* prospective_invite_;
  float table_width_;
  float right_margin_;
  bool center_alignment_;
  UIView* email_field_view_;
  UITextField* email_field_;
  ContactType contact_type_;
  EditEmailCallback email_callback_;
}

@property (nonatomic, readonly) bool editingEmailAddress;

- (id)initWithReuseIdentifier:(NSString*)identifier
                   tableWidth:(float)table_width;
- (void)setCenteredRow:(NSAttributedString*)s;
- (void)setContactRow:(const ContactMetadata&)m
         searchFilter:(RE2*)search_filter
        isPlaceholder:(bool)is_placeholder
           showInvite:(bool)show_invite;
- (void)setFollowerGroupRow:(const FollowerGroup&)group
                  withState:(UIAppState*)state
             excludingUsers:(const std::unordered_set<int64_t>&)exclude;
- (void)setDummyRow;
- (void)startEditingEmailAddress:(EditEmailCallback)email_callback;
- (void)finishEditingEmailAddress;

+ (int)rowHeight;

@end  // ContactsTableViewCell

// local variables:
// mode: objc
// end:
