// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AddContactsController.h"
#import "Analytics.h"
#import "Callback.h"
#import "ContactInfoController.h"
#import "ContactManager.h"
#import "ContactMetadata.pb.h"
#import "ContactsController.h"
#import "ContactsTableViewCell.h"
#import "CppDelegate.h"
#import "DBFormat.h"
#import "ListContactsController.h"
#import "RootViewController.h"
#import "TutorialOverlayView.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

// Add a declaration to let us make ios7-compatible builds with older versions of xcode.
// TODO(ben): remove this when we switch to the final version of xcode 5.
#ifndef __IPHONE_7_0
@interface UITableView (ios7)
@property (nonatomic, retain) UIColor* sectionIndexBackgroundColor;
@end
#endif

namespace {

const int kListContactsCancelButtonPadding = 25;
const int kSearchInactiveContentInsetTop = 64;

LazyStaticHexColor kBackgroundColor = { "#ece9e9" };

// Extracts the first utf character from the name and converts it to
// uppercase. Perhaps this should be more intelligent and skip over whitespace
// and non-word characters.
string SectionTitleFromName(const Slice& name) {
  Slice mutable_name(name);
  utfnext(&mutable_name);
  return ToUppercase(name.substr(0, name.size() - mutable_name.size()));
}

}  // namespace

@implementation ListContactsController

@synthesize addContacts = add_contacts_;

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;
    if (kIOSVersion >= "7") {
      self.automaticallyAdjustsScrollViewInsets = NO;
    }
    self.title = @"Contacts";

    add_contacts_ = [[AddContactsController alloc] initWithState:state_];
  }
  return self;
}

- (void)loadView {
  self.view = [UIView new];
  self.view.autoresizesSubviews = YES;
  self.view.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  self.view.backgroundColor = UIStyle::kContactsListSearchBackgroundColor;

  table_view_ = [UITableView new];
  table_view_.autoresizesSubviews = YES;
  table_view_.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  table_view_.backgroundColor = kBackgroundColor;
  table_view_.contentInset = UIEdgeInsetsMake(kSearchInactiveContentInsetTop, 0, 0, 0);
  table_view_.delegate = self;
  table_view_.dataSource = self;
  table_view_.rowHeight = [ContactsTableViewCell rowHeight];
  table_view_.showsVerticalScrollIndicator = NO;
  if (kIOSVersion >= "6.0") {
    table_view_.sectionIndexColor =
        UIStyle::kContactsListSectionTextColor;
    table_view_.sectionIndexTrackingBackgroundColor =
        UIStyle::kContactsListIndexBackgroundColor;
  }
  if (kSDKVersion >= "7" && kIOSVersion >= "7") {
    table_view_.sectionIndexBackgroundColor = [UIColor clearColor];
  }
  [table_view_.panGestureRecognizer
      addTarget:self action:@selector(tablePanned)];
  [self.view addSubview:table_view_];

  search_view_ = [[SearchTextField alloc] initWithFrame:CGRectMake(0, 0, 0, table_view_.rowHeight)];
  search_view_.delegate = self;
  search_view_.searchField.placeholder = @"Search Contacts";
  [self addSearchFieldToTable];

  {
    // It's kind of hacky to do this here; it can't be in SearchTextField because other
    // uses of that class don't want this separator, but we need to attach it to the search view so
    // the separator follows it around as it is moved in and out of the table view.
    search_bottom_separator_ = [UIView new];
    search_bottom_separator_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    search_bottom_separator_.backgroundColor =
        UIStyle::kContactsListSeparatorColor;
    search_bottom_separator_.frameHeight = UIStyle::kDividerSize;
    search_bottom_separator_.frameBottom = search_view_.frameHeight;
    [search_view_ addSubview:search_bottom_separator_];

    search_top_separator_ = [UIView new];
    search_top_separator_.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    search_top_separator_.backgroundColor =
        UIStyle::kContactsListSeparatorColor;
    search_top_separator_.frameHeight = UIStyle::kDividerSize;
    search_top_separator_.frameTop = -search_top_separator_.frameHeight;
    // search_top_separator_.frameTop = 0;
    [search_view_ addSubview:search_top_separator_];
  }

  // TODO(peter): How to localize the selection of section titles? See
  // UILocalizedIndexedCollation.
  section_index_titles_.push_back(UITableViewIndexSearch);
  for (char c = 'A'; c <= 'Z'; ++c) {
    NSString* s = Format("%c", c);
    section_index_titles_.push_back(s);
  }
  section_index_titles_.push_back(@"#");
}

- (CGRect)tableViewFrame {
  CGRect f = self.view.bounds;
  if (keyboard_frame_.origin.y > 0) {
    f.origin.y = state_->status_bar_height();
    f.size.height -= f.origin.y;
  }
  return f;
}

- (void)viewWillAppear:(BOOL)animated {
  [super viewWillAppear:animated];

  // Reload the contact metadata.
  NSIndexPath* selected_path = [table_view_ indexPathForSelectedRow];
  if (selected_path) {
    // If there was a selected row, we are returning from a ContactInfoController, which may have
    // edited a row but could not add or delete rows.  Editing a nickname may change the sort order,
    // which would result in a jarring transition if we did a full refresh.  Instead, we update
    // the edited row in its previous (now incorrect) location until another action forces us to
    // reload the whole list.
    // This logic may need to change if it becomes possible to delete contacts, or somehow add
    // new ones, from a ContactInfoController.
    UITableViewCell* cell = [table_view_ cellForRowAtIndexPath:selected_path];
    cell.selected = NO;

    const int section = selected_path.section - 1;
    if (section >= 0 && section < sections_.size()) {
      const int contacts_index = sections_[section].first + selected_path.row;
      if (contacts_index >= 0 && contacts_index < contacts_.size()) {
        ContactMetadata* c = &contacts_[contacts_index];
        if (c->has_user_id()) {
          state_->contact_manager()->LookupUser(c->user_id(), c);
          [table_view_ reloadRowsAtIndexPaths:Array(selected_path)
                             withRowAnimation:UITableViewRowAnimationNone];
        }
      }
    }
  } else {
    // If there was no selected row, we came from a view that may have
    // added contacts, so do a full refresh.
    [self searchContactsFor:search_view_.searchField.text scrollToTop:NO];
  }

  if (!keyboard_did_show_.get()) {
    keyboard_did_show_.Init(
        UIKeyboardDidShowNotification,
        ^(NSNotification* n) {
          keyboard_ = search_view_.searchField.inputAccessoryView.superview;
        });
  }
  if (!keyboard_did_hide_.get()) {
    keyboard_did_hide_.Init(
        UIKeyboardDidHideNotification,
        ^(NSNotification* n) {
          keyboard_.hidden = NO;
          keyboard_ = NULL;
        });
  }
  if (!keyboard_will_show_.get()) {
    keyboard_will_show_.Init(
        UIKeyboardWillShowNotification,
        ^(NSNotification* n) {
          const Dict d(n.userInfo);
          keyboard_frame_ =
              d.find_value(UIKeyboardFrameEndUserInfoKey).rect_value();
          if (CGRectIsNull(keyboard_frame_)) {
            // iOS sends a keyboard will show notification when a TextView is
            // selected for copying even though the keyboard is not
            // shown.
            return;
          }

          const double duration =
              d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve =
              d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
          const int options =
              (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;

          [table_view_ reloadSectionIndexTitles];
          [search_view_ hideCancelButton];
          search_view_.cancelButtonPadding = 0;

          [UIView animateWithDuration:duration
                                delay:0
                              options:options
                           animations:^{
              [self.navigationController setNavigationBarHidden:YES animated:YES];
              table_view_.contentInset =
                  UIEdgeInsetsMake(0, 0, keyboard_frame_.size.height, 0);
              table_view_.contentOffsetY = 0;
              [search_view_ showCancelButton];
              search_top_separator_.alpha = 0;
              search_bottom_separator_.frameBottom = search_view_.frameHeight;
              [search_view_ updateSearchFieldSize];
              table_view_.frame = self.tableViewFrame;
            }
                          completion:^(BOOL finished) {
              [self removeSearchFieldFromTable];
            }];
        });
  }
  if (!keyboard_will_hide_.get()) {
    keyboard_will_hide_.Init(
        UIKeyboardWillHideNotification,
        ^(NSNotification* n) {
          if (CGRectIsNull(keyboard_frame_)) {
            return;
          }
          keyboard_frame_ = CGRectZero;

          const Dict d(n.userInfo);
          const double duration =
              d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve =
              d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
          const int options =
              (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;

          search_view_.cancelButtonPadding = kListContactsCancelButtonPadding;
          [UIView animateWithDuration:duration
                                delay:0
                              options:options
                           animations:^{
              table_view_.contentInset = UIEdgeInsetsMake(kSearchInactiveContentInsetTop, 0, 0, 0);
              if (table_view_.contentOffsetY == 0) {
                table_view_.contentOffsetY = -table_view_.contentInset.top;
              }
              table_view_.frame = self.tableViewFrame;
              [self.navigationController setNavigationBarHidden:NO animated:YES];
              [search_view_ hideCancelButton];
              CGRect f = [table_view_ convertRect:search_view_.bounds
                                           toView:self.view];
              if (f.origin.y + f.size.height >= 0) {
                search_view_.frameTop = f.origin.y;
              } else {
                // The search field would no longer be visible. Fade it out of
                // existence instead of animating it off the screen.
                search_view_.alpha = 0;
              }
              search_top_separator_.alpha = 1;
              search_bottom_separator_.frameBottom = search_view_.frameHeight;
              [search_view_ updateSearchFieldSize];
            }
                           completion:^(BOOL finished) {
              [self addSearchFieldToTable];
              [table_view_ reloadSectionIndexTitles];
            }];
        });
  }
}

- (void)viewWillDisappear:(BOOL)animated {
  [super viewWillDisappear:animated];
  [search_view_ deselect];
  keyboard_did_show_.Clear();
  keyboard_did_hide_.Clear();
  keyboard_will_show_.Clear();
  keyboard_will_hide_.Clear();
  keyboard_ = NULL;
}

- (void)viewDidLayoutSubviews {
  [super viewDidLayoutSubviews];
  [search_view_ updateSearchFieldSize];
}

- (UINavigationItem*)navigationItem {
  UINavigationItem* i = [super navigationItem];
  if (!i.leftBarButtonItem) {
    i.leftBarButtonItem = UIStyle::NewToolbarBack(
        self, @selector(toolbarBack));
    UIStyle::InitLeftBarButton(i.leftBarButtonItem);
  }
  if (!i.rightBarButtonItem) {
    i.rightBarButtonItem = UIStyle::NewToolbarAddContact(
        self, @selector(toolbarAddContacts));
    UIStyle::InitRightBarButton(i.rightBarButtonItem);
  }
  if (!i.titleView) {
    i.titleView = UIStyle::NewContactsTitleView(self.title);
  }
  return i;
}

- (NSInteger)numberOfSectionsInTableView:(UITableView*)table_view {
  // The table has 2 extra sections:
  // - A dummy first section containing a single row that is the same size as
  //   the search field.
  // - A trailing section that contains the count of the matching contacts.
  return sections_.size() + 2;
}

- (UIView*)tableHeaderView {
  UIView* v = [UIView new];
  v.backgroundColor = MakeUIColor(1, 0, 0, 0.3);
  v.frameHeight = 50;
  v.frameWidth = 320;
  return v;
}

- (NSInteger)tableView:(UITableView*)table_view
 numberOfRowsInSection:(NSInteger)section {
  if (section <= 0) {
    // The dummy search field first section.
    return 1;
  }
  --section;
  if (section >= sections_.size()) {
    // The count of matching contacts section.
    return 1;
  }
  const int end = (section + 1 >= sections_.size()) ?
      contacts_.size() :
      sections_[section + 1].first;
  return std::max(0, end - sections_[section].first);
}

- (NSString*)tableView:(UITableView*)table_view
titleForHeaderInSection:(NSInteger)section {
  if (section <= 0) {
    // The dummy search field first section.
    return NULL;
  }
  --section;
  if (section >= sections_.size()) {
    // The count of matching contacts section.
    return NULL;
  }

  return sections_[section].second;
}

- (NSArray*)sectionIndexTitlesForTableView:(UITableView*)table_view {
  if (keyboard_frame_.origin.y > 0) {
    return NULL;
  }
  return section_index_titles_;
}

- (NSInteger)tableView:(UITableView*)table_view
sectionForSectionIndexTitle:(NSString*)index_title
               atIndex:(NSInteger)index {
  if (index == 0 || sections_.empty()) {
    return 0;
  }
  for (int i = 0; i < sections_.size(); ++i) {
    NSString* section_title = sections_[i].second;
    if (ContactManager::NameLessThan(ToSlice(index_title), ToSlice(section_title))) {
      return std::max(1, i);
    }
  }
  return sections_.size();
}

- (CGFloat)tableView:(UITableView*)table_view
heightForHeaderInSection:(NSInteger)section {
  if (section <= 0) {
    // The dummy search field first section.
    return NULL;
  }
  --section;
  if (section >= sections_.size()) {
    // The count of matching contacts section.
    return 0;
  }
  return UIStyle::kContactsListSectionHeader.get().size.height;
}

- (UIView*)tableView:(UITableView*)table_view
viewForHeaderInSection:(NSInteger)section {
  if (section <= 0) {
    // The dummy search field first section.
    return NULL;
  }
  --section;
  if (section >= sections_.size()) {
    // The count of matching contacts section.
    return NULL;
  }

  UILabel* l = [UILabel new];
  l.backgroundColor = [UIColor clearColor];
  l.font = UIStyle::kContactsListSectionUIFont;
  l.text = sections_[section].second;
  l.textColor = UIStyle::kContactsListSectionTextColor;
  [l sizeToFit];
  l.frameLeft = 10;
  l.frameWidth = table_view.frameWidth - 2 * l.frameLeft;

  UIImageView* v =
      [[UIImageView alloc]
        initWithImage:UIStyle::kContactsListSectionHeader];
  v.autoresizingMask = UIViewAutoresizingFlexibleWidth;
  [v addSubview:l];
  l.frameTop = (v.frameHeight - l.frameHeight) / 2;
  return v;
}

- (NSIndexPath*)tableView:(UITableView*)table_view
  willSelectRowAtIndexPath:(NSIndexPath*)index_path {
  if (index_path.section == 0) {
    [search_view_ select];
    return NULL;
  }
  if (index_path.section >= 1 && index_path.section <= sections_.size()) {
    return index_path;
  }
  return NULL;
}

- (void)tableView:(UITableView*)table_view
didSelectRowAtIndexPath:(NSIndexPath*)index_path {
  UITableViewCell* cell = [table_view cellForRowAtIndexPath:index_path];

  const int section = index_path.section - 1;
  if (section < 0 || section >= sections_.size()) {
    cell.selected = NO;
    return;
  }
  const int contacts_index = sections_[section].first + index_path.row;
  if (contacts_index < 0 || contacts_index >= contacts_.size()) {
    cell.selected = NO;
    return;
  }

  ContactInfoController* c =
      [[ContactInfoController alloc]
        initWithState:state_
              contact:contacts_[contacts_index]];
  [self.navigationController pushViewController:c animated:YES];
}

- (UITableViewCell*)tableView:(UITableView*)table_view
        cellForRowAtIndexPath:(NSIndexPath*)index_path {
  static NSString* kIdentifier = @"ListContactsControllerCellIdentifier";

  ContactsTableViewCell* cell =
      [table_view dequeueReusableCellWithIdentifier:kIdentifier];
  if (!cell) {
    cell = [[ContactsTableViewCell alloc]
              initWithReuseIdentifier:kIdentifier
                           tableWidth:table_view_.frameWidth];
  }

  if (index_path.section <= 0) {
    // The dummy first section for the search field.
    [cell setDummyRow];
    return cell;
  }

  const int section = index_path.section - 1;
  const int row = index_path.row;
  if (section >= sections_.size()) {
    NSString* ns_str = Format("%d Contact%s", contacts_.size(),
                              Pluralize(contacts_.size()));
    NSMutableAttributedString* attr_str =
        [[NSMutableAttributedString alloc]
                       initWithString:ns_str
                           attributes:UIStyle::kContactsListLabelNormalAttributes];
    [cell setCenteredRow:attr_str];
    return cell;
  }

  const int contacts_index = sections_[section].first + row;
  CHECK_GE(contacts_index, 0);
  CHECK_LT(contacts_index, contacts_.size());
  [cell setContactRow:contacts_[contacts_index]
         searchFilter:search_filter_.get()
        isPlaceholder:false
           showInvite:false];
  return cell;
}

- (void)searchFieldDidChange:(SearchTextField*)field {
  [self searchContactsFor:field.text scrollToTop:YES];
}

- (void)searchContactsFor:(NSString*)str scrollToTop:(bool)scroll_to_top {
  if (str.length > 0) {
    state_->analytics()->ContactsSearch();
  }
  ContactManager::ContactVec old_contacts;
  old_contacts.swap(contacts_);

  const int search_options = ContactManager::SORT_BY_NAME |
                             ContactManager::ALLOW_EMPTY_SEARCH |
                             ContactManager::PREFIX_MATCH;
  const string search_text = ToString(str);
  state_->contact_manager()->Search(
      search_text, &contacts_, &search_filter_, search_options);

  ListContactsSectionVec old_sections;
  old_sections.swap(sections_);

  for (int i = 0; i < contacts_.size(); ++i) {
    const string title = SectionTitleFromName(ContactManager::ContactNameForSort(contacts_[i]));
    if (sections_.empty() ||
        title != ToSlice(sections_.back().second)) {
      sections_.push_back(std::make_pair(i, NewNSString(title)));
    }
  }

  // Remember the row we're currently looking at so we can scroll to its new location later.
  NSIndexPath* cur_path =
      [table_view_ indexPathForRowAtPoint:table_view_.contentOffset];
  CGRect cur_rect = [table_view_ rectForRowAtIndexPath:cur_path];

  [table_view_ reloadData];

  if (scroll_to_top) {
    table_view_.contentOffset = CGPointZero;
  } else {
    int cur_section = 0;
    int cur_row = 0;
    // Determine the new position of the row that is currently at the top of the table.
    if (cur_path.section >= 1 && cur_path.section <= old_sections.size()) {
      const ContactMetadata& cur_metadata =
          old_contacts[old_sections[cur_path.section - 1].first + cur_path.row];
      for (cur_row = 0; cur_row < contacts_.size(); ++cur_row) {
        if (ContactManager::ContactNameLessThan(cur_metadata, contacts_[cur_row])) {
          if (cur_row > 0) {
            --cur_row;
          }
          break;
        }
      }
      for (cur_section = 0;
           (cur_section + 1) < sections_.size() &&
               cur_row >= sections_[cur_section + 1].first;
           ++cur_section) {
      }
      cur_row -= sections_[cur_section].first;
      // Account for the dummy first section for the search field.
      ++cur_section;
    }
    if (cur_section >= 0 && cur_section <= sections_.size() && cur_row >= 0) {
      // Scroll to the point this row will move to after the data is reloaded.
      // Maintain the same offset relative to the top of the row.
      float offset = table_view_.contentOffset.y - cur_rect.origin.y;
      NSIndexPath* new_path = [NSIndexPath indexPathForRow:cur_row inSection:cur_section];
      CGRect new_rect = [table_view_ rectForRowAtIndexPath:new_path];
      table_view_.contentOffset = CGPointMake(0, new_rect.origin.y + offset);
    }
  }
}

- (void)addSearchFieldToTable {
  search_view_.alpha = 1;
  search_view_.frameTop = 0;
  search_view_.cancelButtonPadding = kListContactsCancelButtonPadding;
  [search_view_ setNeedsLayout];

  NSArray* visible_cells = table_view_.visibleCells;
  if (visible_cells.count > 0) {
    UITableViewCell* first_cell = [visible_cells objectAtIndex:0];
    // On iOS 6 the table cells are subviews of table_view_; on iOS 7 there is an intermediate view.
    [first_cell.superview insertSubview:search_view_
                           aboveSubview:first_cell];
  } else {
    [table_view_ addSubview:search_view_];
  }
}

- (void)removeSearchFieldFromTable {
  search_view_.frame = [search_view_ convertRect:search_view_.bounds
                                          toView:self.view];
  search_view_.cancelButtonPadding = 0;
  [search_view_ setNeedsLayout];
  [self.view addSubview:search_view_];
}

- (void)toolbarAddContacts {
  [search_view_ deselect];
  [self.navigationController pushViewController:add_contacts_ animated:YES];
}

- (void)toolbarBack {
  [search_view_ deselect];
  [state_->root_view_controller() dismissViewController:ControllerState()];
}

- (void)clearContacts {
  sections_.clear();
  contacts_.clear();
  [table_view_ reloadData];
}

// TODO(peter): Figure out how to share this code with CommentInput and
// TopLevelSettingsController.
- (void)tablePanned {
  if (!keyboard_ || keyboard_.hidden || !search_view_.searchField.isFirstResponder) {
    return;
  }

  UIPanGestureRecognizer* pan = table_view_.panGestureRecognizer;
  const float max_y = self.view.window.frameHeight;
  const float min_y = max_y - keyboard_.frameHeight;

  switch (pan.state) {
    case UIGestureRecognizerStateBegan:
      break;
    case UIGestureRecognizerStateChanged: {
      const CGPoint p = [pan locationInView:self.view.window];
      // Animate within a zero-duration block to prevent any implicit animation
      // on the keyboard frame from doing something else.
      [UIView animateWithDuration:0.0
                       animations:^{
          keyboard_.frameTop = std::min(std::max(p.y, min_y), max_y);
          [search_view_ fadeCancelButton:keyboard_.frameTop min:min_y max:max_y];
          [search_view_ updateSearchFieldSize];
        }];
      break;
    }
    case UIGestureRecognizerStateEnded:
      if (keyboard_.frameTop > min_y) {
        const CGPoint v = [pan velocityInView:self.view.window];
        if (v.y >= 0) {
          [UIView animateWithDuration:0.3
                                delay:0
                              options:UIViewAnimationOptionCurveEaseOut
                           animations:^{
              [self.navigationController setNavigationBarHidden:NO animated:YES];
              keyboard_.frame = CGRectOffset(
                  keyboard_frame_, 0, keyboard_frame_.size.height);
              keyboard_frame_ = CGRectZero;
              [search_view_ hideCancelButton];
              search_view_.cancelButtonPadding = kListContactsCancelButtonPadding;
              const CGRect f = [table_view_ convertRect:search_view_.bounds
                                                 toView:self.view];
              if (f.origin.y + f.size.height >= 0) {
                search_view_.frameBottom = f.origin.y + f.size.height;
              } else {
                // The search field would no longer be visible. Fade it out of
                // existence instead of animating it off the screen.
                search_view_.alpha = 0;
              }
              [search_view_ updateSearchFieldSize];
            }
                           completion:^(BOOL finished) {
              [self addSearchFieldToTable];
              // Animate within a zero-duration block to prevent any animation of
              // the keyboard.
              keyboard_.hidden = YES;
              [UIView animateWithDuration:0.0
                               animations:^{
                  [search_view_ deselect];
                }];
            }];
          } else {
            [UIView animateWithDuration:0.3
                                  delay:0
                                options:UIViewAnimationOptionCurveEaseOut
                             animations:^{
                keyboard_.frame = keyboard_frame_;
                [search_view_ showCancelButton];
                [search_view_ updateSearchFieldSize];
              }
                             completion:NULL];
        }
      }
    case UIGestureRecognizerStateCancelled:
    default:
      break;
  }
}

@end  // ListContactsController
