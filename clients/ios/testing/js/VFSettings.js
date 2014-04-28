/**
 * @class VFSettings
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The settings object which handles any actions stemming
 * from the Settings screen
 * @author: Greg Vandenberg
 *
 */
var VFSettings = function(_nav) {
  var nav = _nav;
  var util = new VFUtils(nav);
  return {
    gotoDashboard: function() {
      util.pollUntilButtonVisibleTap(BUTTON_DISMISS_DIALOG, 'navbar', 5);
      UIALogger.logDebug("On Dashboard Screen.");
      return new VFDashboard(nav);
    },
    selectStorage: function(type) {
      var index = (type == 'local') ? 0 : 1; // not likely to see more storage types
      var cell = target.main().tableViews()["Empty list"].cells()[index];
      util.pollUntilElementVisibleTap(cell, 5);
      //cell.tap();
      //target.delay(3); // TODO: account for UI delays (spinning wheels, connecting to remote host, etc...)
    },
    getPickerOffset: function(type) {
      var wheel = target.main().pickers()[0].wheels()[0];
      var rect = wheel.rect();
      var x_offset = .5;
      var num_options = 5;
      var y_origin = rect.origin.y;
      if (DEBUG) {
        UIALogger.logDebug("origin y: " + rect.origin.y);
        UIALogger.logDebug("size height: " + rect.size.height);
      }
      var height = rect.size.height;
      var sect_height = height / num_options;
      var multi = (type) ? 3.5 : 1.5;
      if (DEBUG) {
        UIALogger.logDebug("multiple: " + multi);
        UIALogger.logDebug("sect_height: " + sect_height);
      }
      var increment = sect_height * multi;
      y_offset = (increment / rect.size.height).toFixed(2);
      var offset = {
          x : x_offset,
          y : y_offset
      }
      if (DEBUG) {
        UIALogger.logDebug("offset: {" + offset.x +":"+ offset.y + "}");
      }
      return offset;
    },
    selectPickerOptionDown: function() {
      var wheel = target.main().pickers()[0].wheels()[0];
      wheel.tapWithOptions({tapOffset:this.getPickerOffset(0)});
      target.delay(.5);
    },
    selectPickerOptionUp: function() {
      var offset = this.getPickerOffset(1);
      var wheel = target.main().pickers()[0].wheels()[0];
      wheel.tapWithOptions({tapOffset:offset});
      target.delay(.5);
    },
    selectLowestPickerOption: function() {
      for (var i=0; i<5; i++) {
        this.selectPickerOptionDown();
      }
    },
    selectHighestPickerOption: function() {
      for (var i=0; i<5; i++) {
        this.selectPickerOptionUp();
      }
    },
    selectViewfinderPlus: function() {
      var cells = target.main().tableViews()["Empty list"].cells();
      cells["5 GB, Viewfinder Plus, $1.99 / month"].vtap();
    },
    selectCloudStorage: function(state) {
      var cell_name = "Cloud Storage";
      var cell = target.main().tableViews()[1].cells()[cell_name];
      if (type(cell) == 'UIAElementNil') {
        cell = target.main().tableViews()[0].cells()[cell_name];
      }
      var active = util.pollUntilElementVisible(cell, 5);
      active.switches()[cell_name].setValue(state);
    },
    /**
     * Select a page from the Settings page
     * Possible values:
     * FAQ|Send Feedback|Terms of Service|Privacy Policy
     */
    selectSubPage: function(name) {
      var cell = this.waitUntilVisible(name, 5);
      try {
        cell.tap();
      }
      catch(err) {
        /**
         * retry upon failure.
         * I encountered an issue where the cell appeared valid
         * cell.checkIsValid() == true
         * cell.isEnabled == 1
         * cell.isVisible() == 1
         * Yet an attempted cell.tap() produced an error.
         * retry is consistently successful
         */
        cell = this.waitUntilVisible(name, 5);
        cell.tap();
      }
    },
    selectDeleteDraft: function() {
      util.pollUntilButtonVisibleTap(BUTTON_DELETE_DRAFT, 'action', 5);
    },
    selectBackNav: function() {
      util.pollUntilButtonVisibleTap(BUTTON_TB_BACK_NAV, 'navbar', 5);
    },
    waitUntilVisible: function(cell_name, timeout) {
      var cell = target.main().tableViews()[1].cells()[cell_name];
      if (type(cell) == 'UIAElementNil') {
        cell = target.main().tableViews()[0].cells()[cell_name];
      }
      UIALogger.logDebug("cell type: "+ type(cell));
      if (type(cell) == 'UIATableCell') {
        /**
         * checkIsValid will check the accessibility framework
         * for the set timeout.
         */
        target.pushTimeout(timeout);
        if (cell.checkIsValid()) {
          if (DEBUG) UIALogger.logDebug("returning visible tablecell.");
          target.popTimeout();
          return cell;
        }
        target.popTimeout();
      }
      throw new Exception("Never found specified cell: " + cell_name);
    },
  }
};
