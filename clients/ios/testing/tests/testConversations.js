/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: From an unlinked state, start a conversation
 * @author: Greg Vandenberg
 *
 */

VFRunTest("testConversations", runStateEnum.DASHBOARD, function(testname, util, log) {
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
  log.debug("Select Action with zero conversations.");
  log.debug("------------------------------------");
  convo.selectActionButton();
  util.screenCapture('select_action_popup');
  util.dismissAlert("Ok");

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
  convo.setTitle('Test Conversation');

  util.screenCapture('set_person_title');

  //Work around for issue #415
  convo.selectAddPeople();

  log.debug("------------------------------------");
  log.debug("Add photo to conversation.");
  log.debug("------------------------------------");
  // add photo to convo
  convo.selectAddPhotos();

  convo.selectNumImages(1);

  convo.selectAddPhotosNav();

  convo.selectStart();

  util.screenCapture('convo_started');

  log.debug("------------------------------------");
  log.debug("Add comment to conversation.");
  log.debug("------------------------------------");
  convo.addComment('test comment');
  util.screenCapture('comment_added');

  convo.selectSend();
  convo.selectBack();
  util.gotoDashboard();
  util.screenCapture('dashboard_1_convo');

});
