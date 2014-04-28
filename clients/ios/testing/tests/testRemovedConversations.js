/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: From an unlinked state,
 *
 *  User 1 starts a conversation,
 *  User 1 removes conversation,
 *  User 2 adds comment,
 *  Query Notifications,
 *  User 1 conversation is back in Inbox
 *
 * covers issue #461
 * @author: Greg Vandenberg
 *
 */

VFRunTest("testRemovedConversations", runStateEnum.DASHBOARD, function(testname, util, log) {
  var dash = util.gotoDashboard();
  var nav = util.getNav();
  var user = new VFUser();
  var t = TEST_USERS[1];
  user.register(t);

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
  target.delay(2);
  convo.selectActionButton();
  target.delay(2);
  log.debug("------------------------------------");
  log.debug("User 0 removes conversation.");
  log.debug("------------------------------------");
  convo.selectCard();
  convo.selectRemoveButton();
  convo.selectConfirmRemoveButton();
  util.screenCapture('convo_removed');

  log.debug("---------------------------------------------");
  log.debug("User 1 adds comment to conversation via api.");
  log.debug("---------------------------------------------");
  convo.addServerComment('another test comment');

  util.gotoDashboard();

  log.debug("---------------------------------------------");
  log.debug("Invoke Query notifications.");
  log.debug("---------------------------------------------");
  target.deactivateAppForDuration(1);
  util.screenCapture('convo_notification');

  log.debug("---------------------------------------------");
  log.debug("User 0 conversation is back in Inbox.");
  log.debug("---------------------------------------------");
  dash.gotoConversations();
  util.screenCapture('convo_has_returned');

  convo.selectCard();
  util.screenCapture('new_comment_added');
});
