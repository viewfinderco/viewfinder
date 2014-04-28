// Copyright 2012 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import <UIKit/NSLayoutConstraint.h>
#import <UIKit/UILabel.h>
#import <UIKit/UISwitch.h>
#import "ContactManager.h"
#import "FindNearbyUsersController.h"
#import "Logging.h"
#import "UIAppState.h"
#import "UIView+constraints.h"

namespace {

const float kMargin = 8;

// TODO(ben): what are the rules for this string?
NSString* kServiceType = @"viewfinder";

UILabel* NewLabel(NSString* text) {
  UILabel* label = [UILabel new];
  label.text = text;
  label.translatesAutoresizingMaskIntoConstraints = NO;
  return label;
}

UISwitch* NewSwitch(id target, SEL selector) {
  UISwitch* sw = [UISwitch new];
  sw.translatesAutoresizingMaskIntoConstraints = NO;
  [sw addTarget:target
         action:selector
      forControlEvents:UIControlEventValueChanged];
  return sw;
}

}  // namespace

@implementation FindNearbyUsersController

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;
  }
  return self;
}

- (void)loadView {
  [super loadView];
  self.view = [UIView new];
  self.view.backgroundColor = [UIColor whiteColor];

  discovery_label_ = NewLabel(@"Discoverable");
  [self.view addSubview:discovery_label_];

  discovery_switch_ = NewSwitch(self, @selector(toggleDiscoverable:));
  [self.view addSubview:discovery_switch_];

  scanning_label_ = NewLabel(@"Scanning");
  [self.view addSubview:scanning_label_];

  scanning_switch_ = NewSwitch(self, @selector(toggleScanning:));
  [self.view addSubview:scanning_switch_];

  error_label_ = NewLabel(@"");
  error_label_.textColor = [UIColor redColor];
  [self.view addSubview:error_label_];

  table_ = [UITableView new];
  table_.translatesAutoresizingMaskIntoConstraints = NO;
  table_.dataSource = self;
  [self.view addSubview:table_];

  [self.view addConstraints:TopToBottom(
        self.view.anchorTop, kMargin,
        discovery_switch_, kMargin,
        scanning_switch_, kMargin,
        error_label_, kMargin,
        table_, self.view.anchorBottom)];

  [self.view addConstraints:discovery_label_.anchorCenterY == discovery_switch_.anchorCenterY];
  [self.view addConstraints:discovery_label_.anchorLeft == self.view.anchorLeft + kMargin];
  [self.view addConstraints:discovery_switch_.anchorRight == self.view.anchorRight - kMargin];

  [self.view addConstraints:scanning_label_.anchorCenterY == scanning_switch_.anchorCenterY];
  [self.view addConstraints:scanning_label_.anchorLeft == self.view.anchorLeft + kMargin];
  [self.view addConstraints:scanning_switch_.anchorRight == self.view.anchorRight - kMargin];

  [self.view addConstraints:LeftToRight(
        self.view.anchorLeft, kMargin, error_label_, kMargin, self.view.anchorRight)];

  [self.view addConstraints:LeftToRight(
        self.view.anchorLeft, table_, self.view.anchorRight)];
}

- (void)viewWillAppear:(BOOL)animated {
  ContactMetadata c;
  state_->contact_manager()->LookupUser(state_->user_id(), &c);
  my_peer_ = [[MCPeerID alloc] initWithDisplayName:NewNSString(c.name())];
  discovery_switch_.on = NO;
  scanning_switch_.on = NO;
}

- (void)viewWillDisappear:(BOOL)animated {
  [self stopAdvertising];
  [self stopBrowsing];
}

- (void)toggleDiscoverable:(UISwitch*)sw {
  if (sw.on) {
    [self startAdvertising];
  } else {
    [self stopAdvertising];
  }
}

- (void)toggleScanning:(UISwitch*)sw {
  if (sw.on) {
    [self startBrowsing];
  } else {
    [self stopBrowsing];
  }
}

- (void)startAdvertising {
  if (!advertiser_) {
    LOG("find nearby: starting advertiser");
    advertiser_ = [[MCNearbyServiceAdvertiser alloc] initWithPeer:my_peer_
                                                    discoveryInfo:NULL
                                                      serviceType:kServiceType];
    advertiser_.delegate = self;
    [advertiser_ startAdvertisingPeer];
  }
}

- (void)stopAdvertising {
  if (advertiser_) {
    LOG("find nearby: stopping advertiser");
    [advertiser_ stopAdvertisingPeer];
    advertiser_ = NULL;
  }
}

- (void)advertiser:(MCNearbyServiceAdvertiser*)advertiser didNotStartAdvertisingPeer:(NSError*)error {
  error_label_.text = error.localizedDescription;
}

- (void)advertiser:(MCNearbyServiceAdvertiser*)advertiser
didReceiveInvitationFromPeer:(MCPeerID *)peerID
       withContext:(NSData*)context
 invitationHandler:(void (^)(BOOL accept, MCSession *session))invitationHandler {
  // We only use the discovery features of MultipeerConnectivity, so decline all invitations.
  invitationHandler(NO, NULL);
}

- (void)startBrowsing {
  if (!browser_) {
    LOG("find nearby: starting browser");
    browser_ = [[MCNearbyServiceBrowser alloc] initWithPeer:my_peer_ serviceType:kServiceType];
    browser_.delegate = self;
    [browser_ startBrowsingForPeers];
  }
}

- (void)stopBrowsing {
  if (browser_) {
    LOG("find nearby: stopping browser");
    [browser_ stopBrowsingForPeers];
    browser_ = NULL;
    nearby_users_.clear();
    [table_ reloadData];
  }
}

- (void)browser:(MCNearbyServiceBrowser*)browser didNotStartBrowsingForPeers:(NSError*)error {
  error_label_.text = error.localizedDescription;
}

- (void)browser:(MCNearbyServiceBrowser*)browser
      foundPeer:(MCPeerID*)peer
withDiscoveryInfo:(NSDictionary*)info {
  LOG("found peer %s", peer.displayName);
  nearby_users_.push_back(ToString(peer.displayName));
  [table_ reloadData];
}

- (void)browser:(MCNearbyServiceBrowser*)browser lostPeer:(MCPeerID*)peer {
  LOG("lost peer %s", peer.displayName);
  for (vector<string>::iterator it = nearby_users_.begin();
       it != nearby_users_.end();
       ++it) {
    if (*it == ToString(peer.displayName)) {
      nearby_users_.erase(it);
      break;
    }
  }
  [table_ reloadData];
}

- (NSInteger)tableView:(UITableView*)view numberOfRowsInSection:(NSInteger)section {
  return nearby_users_.size();
}

- (UITableViewCell*)tableView:(UITableView*)view cellForRowAtIndexPath:(NSIndexPath*)path {
  static NSString* kIdentifier = @"FindNearbyUsersCellIdentifier";

  UITableViewCell* cell = [view dequeueReusableCellWithIdentifier:kIdentifier];
  if (!cell) {
    cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault
                                  reuseIdentifier:kIdentifier];
  }
  cell.textLabel.text = NewNSString(nearby_users_[path.row]);
  return cell;
}

@end  // FindNearbyUsersController
