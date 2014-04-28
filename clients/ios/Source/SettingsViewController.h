// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

class UIAppState;
class UIStyle;

void AddButtonToTableCell(UIView* v, UITableViewCell* cell);

class SettingsSection {
  typedef bool (^ScopedCallback)();

 public:
  SettingsSection();
  virtual ~SettingsSection() {}

  void SetCallback(int index, ScopedCallback callback);
  bool Select(int index) const;

  virtual void InitCell(UITableViewCell* cell, int index) const = 0;
  virtual void InitBackground(UITableViewCell* cell, int index) const;

  virtual NSAttributedString* header() const { return NULL; }
  virtual NSAttributedString* footer() const { return NULL; }
  virtual NSString* cell_identifier() const = 0;
  virtual UITableViewCellStyle cell_style() const = 0;

  void update_cached_size() { cached_size_ = size(); }
  int cached_size() const { return cached_size_; }

 protected:
  NSMutableAttributedString* NewFooterString(const string& s) const;
  NSMutableAttributedString* NewHeaderString(const string& s) const;

  virtual int size() const = 0;

 private:
  vector<ScopedCallback> callbacks_;
  int cached_size_;
};

@interface SettingsViewTableController : UITableViewController {
 @protected
  vector<SettingsSection*> sections_;
}

- (id)init;
- (void)setSections:(const vector<SettingsSection*>&)new_sections;

@end  // SettingsViewTableController

@interface SettingsDisclosure : UIControl {
 @private
  UIColor* normal_;
  UIColor* highlighted_;
}

- (id)initWithColor:(UIColor*)normal
        highlighted:(UIColor*)highlighted;

@end  // SettingsDisclosure

@interface SettingsViewController
    : UINavigationController<UINavigationControllerDelegate> {
 @private
  UIAppState* state_;
  UIViewController* settings_;
}

- (id)initWithState:(UIAppState*)state;

@end  // SettingsViewController

// local variables:
// mode: objc
// end:
