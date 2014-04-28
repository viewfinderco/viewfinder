/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: From an unlinked state, start a conversation, invite a
 * prospective user, register user and see change in UI
 * @author: Greg Vandenberg
 *
 */

VFRunTest("testProspectiveUser", runStateEnum.DASHBOARD, function(testname, util, log) {
  var dash = util.gotoDashboard();
  var nav = util.getNav();
  var user = new VFUser();
  var t = TEST_USERS[1];

  log.debug("------------------------------------");
  log.debug("Import phonebook contacts.");
  log.debug("------------------------------------");
  var contacts = dash.gotoContacts()
  contacts.importPhoneContacts();
  util.screenCapture("at_import_contacts");

  contacts.selectBackNav();
  util.dismissAlert("View All");
  contacts.gotoDashboard();

  log.debug("------------------------------------");
  log.debug("Create a new conversation.");
  log.debug("------------------------------------");
  // goto conversation
  var convo = dash.gotoConversations();

  // compose new convo
  convo.selectCompose();

  log.debug("------------------------------------");
  log.debug("Invite a person to conversation.");
  log.debug("------------------------------------");
  // add people to convo
  convo.selectAddPeople();
  convo.setPerson(t.firstname + " ");
  util.screenCapture('set_person_invite');
  convo.setPerson(t.lastname + "\n");
  util.screenCapture('set_person_invite_1');

  // set title
  convo.setTitle('Prospective User Test');

  // Work around for issue #415
  convo.selectAddPeople();

  // add photo to convo
  convo.selectAddPhotos();

  convo.selectNumImages(1);

  convo.selectAddPhotosNav();

  convo.selectStart();

  util.screenCapture('convo_started');

  log.debug("------------------------------------");
  log.debug("Add comment to conversation");
  log.debug("------------------------------------");
  convo.addComment('test comment');
  util.screenCapture('comment_added');

  convo.selectSend();
  convo.selectBack();
  util.gotoDashboard();
  util.screenCapture('dashboard_1_convo');

  log.debug("------------------------------------");
  log.debug("Register User " + t.email);
  log.debug("------------------------------------");
  user.register(t);

  log.debug("------------------------------------");
  log.debug("Background App to invoke query notifications");
  log.debug("------------------------------------");
  target.deactivateAppForDuration(2);

  dash.gotoConversations();

  // compose new convo
  convo.selectCompose();

  log.debug("------------------------------------");
  log.debug("Show that client recognizes registered user.");
  log.debug("------------------------------------");
  //add people to convo
  convo.selectAddPeople();
  convo.setPerson(t.firstname + " ");
  util.screenCapture('set_person_title_1');
  convo.setPerson(t.lastname + "\n");

  // set title
  convo.setTitle('Registered User Test');

  util.screenCapture('set_person_title_2');

  // Work around for issue #415
  convo.selectAddPeople();

  // add photo to convo
  convo.selectAddPhotos();

  convo.selectNumImages(2);

  convo.selectAddPhotosNav();

  convo.selectStart();

  util.screenCapture('convo_started_1');

});
