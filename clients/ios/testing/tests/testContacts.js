/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: From an unlinked state, import contacts
 * @author: Greg Vandenberg
 *
 */

VFRunTest("testContacts", runStateEnum.DASHBOARD, function(testname, util, log) {

  var t = TEST_USERS[0];
  // check if you are on dashboard
  var dash = util.gotoDashboard();

  // add a contact
  log.debug("------------------------------------");
  log.debug("Import phonebook contacts");
  log.debug("------------------------------------");
  var contacts = dash.gotoContacts()

  contacts.importPhoneContacts();
  util.screenCapture("at_import_contacts");

  log.debug("------------------------------------");
  log.debug("Import Gmail contacts");
  log.debug("------------------------------------");
  contacts.importGmailContacts();
  target.delay(2); // for accurate screen shot
  util.screenCapture("at_import_gmail_contacts");

  log.debug("------------------------------------");
  log.debug("Import Facebook friends");
  log.debug("------------------------------------");
  contacts.importFacebookFriends();
  util.screenCapture("at_import_facebook_contacts");

  contacts.selectBackNav();

  log.debug("------------------------------------");
  log.debug("Search for name in All contacts");
  log.debug("------------------------------------");
  util.dismissAlert("View All");
  target.delay(1); // TODO: fix this
  contacts.selectButtonAll();
  contacts.enterSearchTerm(t.firstname);

  util.screenCapture("contacts_search_form");

  log.debug("------------------------------------");
  log.debug("Send email to contact");
  log.debug("------------------------------------");
  contacts.selectContact(1);
  contacts.selectBackNav();
  contacts.selectBackNav();

  log.debug("------------------------------------");
  log.debug("Find a contact");
  log.debug("------------------------------------");
  contacts.selectAddContacts();

  contacts.setContactEmail('asdf');

  util.dismissAlert("OK");
  contacts.setContactEmail(t.email);

  util.screenCapture("contacts_dashboard");

  // TODO: Search for VF contact
  // TODO: Search for ALL contact
  // TODO: Use right jump scroll 'w'


});
