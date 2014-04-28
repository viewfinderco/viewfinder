// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifdef TESTING

#import <UIKit/UILabel.h>
#import <UIKit/UINavigationBar.h>
#import <UIKit/UITableViewController.h>
#import <UIKit/UITableView.h>
#import "InteractiveTestController.h"
#import "Logging.h"
#import "PhoneNumberFormatterTest.h"
#import "StringUtils.h"

namespace {

struct TestView {
  TestView(const string& n, Class c)
    : name(n),
      cls(c) {
  }

  string name;
  Class cls;
};

}  // namespace

@interface InteractiveTestTableController : UITableViewController<UITableViewDataSource, UITableViewDelegate> {
  vector<TestView> test_views_;
}

@end  // InteractiveTestTableController

@implementation InteractiveTestTableController

- (id)init {
  if (self = [super init]) {
    test_views_.push_back(TestView("PhoneNumberFormatter", [PhoneNumberFormatterTestController class]));

    self.navigationItem.title = @"Test views";
    self.tableView.dataSource = self;
    self.tableView.delegate = self;
  }
  return self;
}

- (NSInteger)tableView:(UITableView*)table_view numberOfRowsInSection:(NSInteger)section {
  CHECK_EQ(section, 0);
  return test_views_.size();
}

- (UITableViewCell*)tableView:(UITableView*)table_view cellForRowAtIndexPath:(NSIndexPath*)index_path {
  UITableViewCell* cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:nil];
  cell.textLabel.text = NewNSString(test_views_[index_path.row].name);
  return cell;
}

- (void)tableView:(UITableView *)table_view didSelectRowAtIndexPath:(NSIndexPath *)index_path {
  Class cls = test_views_[index_path.row].cls;
  [self.navigationController pushViewController:[cls new] animated:YES];
}

@end  // InteractiveTestTableController

@implementation InteractiveTestController

- (id)init {
  UITableViewController* root = [InteractiveTestTableController new];
  if (self = [super initWithRootViewController:root]) {
  }
  return self;
}


@end  // UITestController

#endif  // TESTING
