// Copyright 2012 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import <MultipeerConnectivity/MCNearbyServiceAdvertiser.h>
#import <MultipeerConnectivity/MCNearbyServiceBrowser.h>
#import <UIKit/UITableView.h>
#import <UIKit/UIViewController.h>
#import "Utils.h"

class UIAppState;
@class UILabel;
@class UISwitch;

@interface FindNearbyUsersController : UIViewController<MCNearbyServiceAdvertiserDelegate,
                                                        MCNearbyServiceBrowserDelegate,
                                                        UITableViewDataSource> {
  UIAppState* state_;

  UILabel* discovery_label_;
  UISwitch* discovery_switch_;
  UILabel* scanning_label_;
  UISwitch* scanning_switch_;
  UILabel* error_label_;

  UITableView* table_;

  MCPeerID* my_peer_;

  MCNearbyServiceAdvertiser* advertiser_;
  MCNearbyServiceBrowser* browser_;

  vector<string> nearby_users_;
}

- (id)initWithState:(UIAppState*)state;

@end  // FindNearbyUsersController
