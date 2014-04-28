/**
 * The conversation object which handles any actions stemming from the Conversation Feed
 * @class VFConversation
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The conversation object which handles any actions stemming from the Conversation Feed
 * @author: Greg Vandenberg
 *
 */
var VFConversation = function(_nav) {
  var nav = _nav;
  var vf = new Viewfinder(false);
  var util = new VFUtils(_nav);
  var user = new VFUser();

  return {
    selectNumImages: function(num) {
      var sv = target.main().scrollViews()[0];
      var images = util.getImages(sv.images());
      var image = null;
      if (images.length >= num) {
        for (var i=0; i<num; i++) {
          image = images[i];
          util.selectImage(image, target.main().scrollViews()[1].scrollViews()[0]);
        }
      }
    },
    // select action button
    selectActionButton: function() {
      var button = target.main().buttons().firstWithName("Action");
      //var button = target.main().buttons()[7];
      return nav.tapButton(button);
    },

    // select share
    selectShareButton: function() {
      var button = util.pollUntilButtonVisible(BUTTON_SHARE, 'main', 5);
      return nav.tapButton(button);
    },
    // select export
    selectExportButton: function() {
      var button = util.pollUntilButtonVisible(BUTTON_EXPORT, 'main', 5);
      return nav.tapButton(button);
    },
    selectCard: function() {
      // TODO:  abstract
      target.main().scrollViews()[0].scrollViews()[2].tapWithOptions({tapOffset:{x:0.50, y:0.19}});
    },
    selectCompose: function() {
      target.delay(2); // TODO: poll
      target.main().buttons().firstWithName("Compose").tap();
    },
    setTitle: function(title) {
      target.main().scrollViews()[0].scrollViews()[0].textViews()[0].tap();
      target.app().keyboard().typeString(title);
    },
    setPerson: function(name) {
      target.app().keyboard().typeString(name);
    },
    selectAddPeople: function() {
      util.pollUntilButtonVisibleTap(BUTTON_ADD_PEOPLE, 'main', 5);
    },
    selectAddPhotos: function() {
      util.pollUntilButtonVisibleTap(BUTTON_ADD_PHOTOS, 'main', 5);
    },
    selectAddPhotosNav: function() {
      target.main().buttons()["Add Photos"].tap();
    },
    selectBack: function() {
      util.pollUntilButtonVisibleTap(BUTTON_BACK, 'main_window', 5);
    },
    selectSend: function() {
      util.pollUntilButtonVisibleTap(BUTTON_SEND, 'main_window', 5);
    },
    selectStart: function() {
      var button = util.pollUntilButtonVisible(BUTTON_SEND, 'toolbar', 5);
      button.vtap();
      button.waitForInvalid();
    },
    addServerComment: function(comment) {

      var resp = user.login(TEST_USERS[1].email);
      if (resp) {
        eval('var response = ' + resp + ';');
        var args = [ '-HX-Xsrftoken:fake_xsrf' ];

        var post_request = util.clone(util.requestTemplate);
        post_request.headers = response.headers;

        var request = util.clone(util.requestTemplate);
        request.limit = 1;
        var viewpoints = null;
        var query_result = vf.query_followed(request, args);
        eval('viewpoints = ' + query_result.stdout + ';');
        var viewpoint_id = viewpoints.viewpoints[0]['viewpoint_id'];
        var timestamp = viewpoints.viewpoints[0]['timestamp'];

        UIALogger.logDebug("Viewpoint ID: " + viewpoint_id);

        request = util.clone(util.requestTemplate);
        request.asset_types = ['a','c','o'];
        result = vf.allocate_ids(request, args);
        eval('var ids = ' + result.stdout + ';');
        UIALogger.logDebug("Result activity_id: " + ids.asset_ids[0]);
        UIALogger.logDebug("Result comment_id: " + ids.asset_ids[1]);
        UIALogger.logDebug("Result op_id: " + ids.asset_ids[2]);
        post_request.activity = {};
        post_request.activity.activity_id = ids.asset_ids[0];
        post_request.activity.timestamp = timestamp;
        post_request.comment_id = ids.asset_ids[1];
        post_request.message = comment;
        post_request.timestamp = timestamp;
        post_request.viewpoint_id = viewpoint_id;
        post_request.headers.op_id = ids.asset_ids[2];
        var comment = vf.post_comment(post_request, args);
      }
      else {
        UIALogger.logDebug("Login failed.");
      }
    },
    // select remove
    selectRemoveButton: function() {
      target.delay(2);
      var button = target.main().buttons().firstWithName('Remove');
      button.vtap();
    },
    selectConfirmRemoveButton: function() {
      util.pollUntilButtonVisibleTap("Remove conversation", 'action', 5);
    },
    addComment: function(comment) {
      var textView = this.findFirstTextView(target.main().images());
      textView.typeString(comment);
    },
    findFirstTextView: function(images) {
      for (var i=0; i<images.length; i++) {
        try {
          var textView = images[i].textViews()[0];
          if (type(textView) == "UIATextView") {
            return textView;
          }
        }
        catch(err) {
          UIALogger.logDebug("Error: " + err);
        }
      }
      return null;
    }
  }
};
