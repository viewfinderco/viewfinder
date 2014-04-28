/**
 *
 * Copyright 2013 Viewfinder Inc. All Rights Reserved.
 * Description: Single image view in the Library.
 * Author: Greg Vandenberg
 *
 */

VFRunTest("testSingleImagePortraitView", runStateEnum.DASHBOARD, function(testname, util, log) {

  var dash = new VFDashboard();
  var user = new VFUser();
  var t = TEST_USERS[1];
  var nav = util.getNav();

  log.debug("------------------------------------");
  log.debug("Import phonebook contacts");
  log.debug("------------------------------------");
  var contacts = dash.gotoContacts()
  contacts.importPhoneContacts();
  util.screenCapture("at_import_contacts");

  contacts.selectBackNav();
  util.dismissAlert("View All");
  contacts.gotoDashboard();

  log.debug("------------------------------------");
  log.debug("Go to Library.");
  log.debug("------------------------------------");
  var library = dash.gotoLibrary();
  target.delay(2); // for accurate screen shot
  util.screenCapture('personal_library');

  log.debug("------------------------------------");
  log.debug("Select 1 image.");
  log.debug("------------------------------------");
  library.selectNumImages(1);


  log.debug("------------------------------------");
  log.debug("Portrait single image view.");
  log.debug("------------------------------------");
  target.delay(2);
  target.setDeviceOrientation(UIA_DEVICE_ORIENTATION_PORTRAIT);
  util.screenCapture('single_image_portrait_view');

  // swipe right x images
  while(1) {
    nav.swipeRightToLeft();
    var sText = target.main().scrollViews()[0].staticTexts()[" 9:17 PM - Sun, December 23, 2012"];
    var rect = null;
    if (util.type(sText) != 'UIAElementNil') {
      if (sText.isVisible()) {
        UIALogger.logDebug("Found image.");
        break;
      }
    }
  }

  log.debug("------------------------------------");
  log.debug("Remove Tesla Model S image.");
  log.debug("------------------------------------");
  target.delay(2);
  library.selectRemoveButton();
  library.selectConfirmRemove();

  target.delay(2);
  //target.logElementTree();

  log.debug("------------------------------------");
  log.debug("Share image from single image view.");
  log.debug("------------------------------------");
  // start conversation from portrait single image view
  library.selectShareButton();
  var convo = new VFConversation(nav);
  //add people to convo
  convo.selectAddPeople();
  convo.setPerson(t.email + "\n");

  //set title
  convo.setTitle('Test Conversation');

  util.screenCapture('set_person_title');

  //Work around for issue #415
  convo.selectAddPeople();
  convo.selectStart();
  target.delay(1);
  util.screenCapture('convo_started');

  convo.selectBack();

  library.selectBackButton('main_window');

  util.gotoDashboard();
  util.screenCapture('dashboard_1_convo');


});
