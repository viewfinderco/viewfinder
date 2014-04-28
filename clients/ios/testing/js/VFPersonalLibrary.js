/**
 * The library object which handles any actions stemming from the Personal Library
 * @class VFPersonalLibrary
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The library object which handles any actions stemming from the Personal Library
 * @author: Greg Vandenberg
 *
 */
var VFPersonalLibrary = function(_nav) {
  var nav = _nav;
  var util = new VFUtils(_nav);

  return {
    /**
     * Retrieve all the images that are visible
     * @method getImages
     */
    selectNumImages: function(num) {
      var sv = target.main().scrollViews()[0].scrollViews()[1];
      var images = util.getImages(sv.images());
      var image = null;
      if (images.length >= num) {
        for (var i=0; i<num; i++) {
          image = images[i];
          util.selectImage(image, target.main().scrollViews()[0]);
        }
      }
    },
    // select show library
    selectShowLibrary: function() {
      util.pollUntilButtonVisibleTap(BUTTON_SHOW_LIBRARY, 'main', 5);
    },
    // select action button
    selectActionButton: function() {
      var button_action = target.main().buttons().firstWithName('Action');
      button_action.vtap();
    },
    // select exit button
    selectExitButton: function() {
      var button = util.pollUntilButtonVisible(BUTTON_EXIT, 'main', 5);
      return nav.tapButton(button);
    },
    // select back button
    selectBackButton: function(_type) {
      var type = typeof _type !== 'undefined' ? _type : 'main';
      var button = util.pollUntilButtonVisible(BUTTON_BACK, type, 5);
      return nav.tapButton(button);
    },
    // select share
    selectShareButton: function() {
      var button = util.pollUntilButtonVisible(BUTTON_SHARE, 'main_window', 5);
      return nav.tapButton(button);
    },
    selectNewConversation: function() {
      var button = util.pollUntilButtonVisible('New Conversation', 'action', 5);
      return nav.tapButton(button);
    },
    selectRelatedConversation: function(pos) {
      var buttons = target.main().scrollViews()[0].scrollViews()[1].buttons();
      var button = buttons[pos];
      button.vtap();
      button.waitForInvalid();
    },
    selectConversation: function() {
      // TODO: abstract this
      target.main().scrollViews()[1].scrollViews()[2].tapWithOptions({tapOffset:{x:0.30, y:0.45}});
    },
    selectConfirmExport: function() {
      var button = target.app().actionSheet().buttons().firstWithName('Export');
      button.vtap();
    },
    // select export
    selectExportButton: function() {
      var button = target.main().buttons().firstWithName('Export');
      button.vtap();
    },
    // select remove
    selectRemoveButton: function() {
      var button = target.main().buttons().firstWithName('Remove');
      button.vtap();
    },
    selectConfirmRemove: function() {
      var button = target.app().actionSheet().buttons().firstWithName('Remove Photo');
      button.vtap();
    },
    gotoDashboard: function() {
      return util.gotoDashboard();
    }
  }
};
