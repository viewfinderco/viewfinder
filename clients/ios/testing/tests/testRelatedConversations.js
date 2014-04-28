/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: From an unlinked state, start a conversation, access related conversation from library
 * covers issue #461
 * @author: Greg Vandenberg
 *
 */

VFRunTest("testRelatedConversations", runStateEnum.DASHBOARD, function(testname, util, log) {
  var dash = util.gotoDashboard();
  var nav = util.getNav();
  var user = new VFUser();
  var t = TEST_USERS[1];

  log.debug("------------------------------------");
  log.debug("Import phonebook contacts");
  log.debug("------------------------------------");
  var contacts = dash.gotoContacts()
  contacts.importPhoneContacts();
  util.screenCapture("at_import_contacts");

  contacts.selectBackNav();
  util.dismissAlert("View All");
  contacts.gotoDashboard();


  // goto conversation
  var convo = dash.gotoConversations();

  log.debug("------------------------------------");
  log.debug("Create a new conversation.");
  log.debug("------------------------------------");
  // compose new convo
  convo.selectCompose();

  log.debug("------------------------------------");
  log.debug("Add people to conversation.");
  log.debug("------------------------------------");
  // add people to convo
  convo.selectAddPeople();
  convo.setPerson(t.firstname + " " + t.lastname + "\n");

  //set title
  var convo_title = 'Test Conversation';
  convo.setTitle(convo_title);

  util.screenCapture('set_person_title');

  //Work around for issue #415
  //convo.selectAddPeople();

  log.debug("------------------------------------");
  log.debug("Add photo to conversation.");
  log.debug("------------------------------------");
  // add photo to convo
  convo.selectAddPhotos();
  convo.selectNumImages(3);
  convo.selectAddPhotosNav();
  convo.selectStart();
  util.screenCapture('convo_started_1');

  convo.selectBack();
  util.gotoDashboard();
  var library = dash.gotoLibrary();
  log.debug("------------------------------------");
  log.debug("Share 5 photos.");
  log.debug("------------------------------------");
  library.selectActionButton();
  target.delay(2); // for accurate screen shot
  util.screenCapture('library_action');

  library.selectNumImages(5);
  library.selectShareButton();
  library.selectNewConversation();
  //convo.selectAddPeople();
  convo.setPerson(t.firstname + " " + t.lastname + "\n");
  //set title
  var convo_title = 'Another Conversation';
  convo.setTitle(convo_title);
  convo.selectStart();
  util.screenCapture('convo_started_2');

  convo.selectBack();
  util.gotoDashboard();

  log.debug("------------------------------------");
  log.debug("Select Related Conversation.");
  log.debug("------------------------------------");
  var library = dash.gotoLibrary();
  library.selectRelatedConversation(0);
  util.screenCapture('select_related_conversation');
  library.selectConversation();
  util.screenCapture('show_conversation');
  convo.selectBack();
  util.gotoDashboard();
  //target.frontMostApp().mainWindow().scrollViews()[0].scrollViews()[1].buttons()["library related convos anchor"].tap();
  util.screenCapture('dashboard_1_convo');

});
