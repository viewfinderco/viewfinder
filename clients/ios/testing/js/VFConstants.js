/**
 * Constants
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description All constants go here
 * @author Greg Vandenberg
 *
 */

var curl_path = '/usr/bin/curl';

var DEBUG = 0;

var STANDARD_TIMEOUT_IN_SECONDS = 1;

var GMAIL_TEST_USERNAME = "viewfindertester@emailscrubbed.com";
var GMAIL_TEST_PASSWORD = "suds4me!";

var FACEBOOK_TEST_USERNAME = "tester@emailscrubbed.com";
var FACEBOOK_TEST_PASSWORD = "suds4me!";

var TEST_PASSWORD = "testPa$$w0rd";
var TEST_MOBILE = '2065551212';
var TEST_FIRST_NAME = 'William';
var LOGGED_IN_USERID = 0;
// User emails used for tests
var TEST_USER = function( _firstname, _lastname, _email, _password, _mobile) {
  this.firstname = typeof _firstname !== 'undefined' ? _firstname : 'William';
  this.lastname = _lastname;
  this.email = _email;
  this.password = typeof _password !== 'undefined' ? _password : 'testPa$$w0rd';
  this.mobile = typeof _mobile !== 'undefined' ? _mobile : '+12065551212';
};

var TEST_USERS = [
  new TEST_USER('William', 'Smith0', 'tester_0@emailscrubbed.com'),
  new TEST_USER('William', 'Smith1', 'tester_1@emailscrubbed.com'),
  new TEST_USER('William', 'Smith2', 'tester_2@emailscrubbed.com'),
  new TEST_USER('William', 'Smith3', 'tester_3@emailscrubbed.com'),
  new TEST_USER('William', 'Smith4', 'tester_4@emailscrubbed.com')

];

var SETTINGS_PAGE_FAQ = "FAQ";
var SETTINGS_PAGE_FEEDBACK = "Send Feedback";
var SETTINGS_PAGE_TOS = "Terms of Service";
var SETTINGS_PAGE_PRIVACY = "Privacy Policy";
var SETTINGS_PAGE_CLOUD_STORAGE = "Cloud Storage";

var target = UIATarget.localTarget();
target.setTimeout(0);

// runState enum
var runStateEnum = {
  ONBOARDING : 0, // provides a login, terminate and register
  DASHBOARD : 1, // provides a login, terminate, register and navigates ui to dashboard
}

var main = {
  DASHBOARD : 0,
  LIBRARY : 1,
  INBOX : 2
}

var BUTTON_ADD_EMAIL_MOBILE = "Add Email or Mobile";

/*
 * Application button labels
 * nav.refresh('main_window');
 */
var BUTTON_ADD = "Add";
var BUTTON_OK = "OK";
var BUTTON_BACK = "Back";
var BUTTON_DONE = "Done";
var BUTTON_SIGNUP = "Sign Up";
var BUTTON_CANCEL = "Cancel";
var BUTTON_LOGIN = "Log In";
var BUTTON_CREATE_ACCOUNT = "Create Account";
var BUTTON_CONTINUE = "Continue";
var BUTTON_SEND_CODE_AGAIN = "Send code again?";
var BUTTON_FORGOT_PASSWORD = "Forgot your password?";
var BUTTON_SUBMIT = "Submit";
var BUTTON_SWIPE_TUTORIAL = "swipe to navigate dashboard";

/*
 * nav.refresh('navbar');
 */
var BUTTON_START = "Start";

/*
 * nav.refresh('navbar');
 */
var BUTTON_DISMISS_DIALOG = "dismiss dialog";
var BUTTON_TB_BACK_NAV = "toolbar back nav";
var BUTTON_TB_ADD_CONTACT = "toolbar add contact";

var BUTTON_DELETE_DRAFT = "Delete Draft";
/*
 * nav.refresh('main');
 */
var BUTTON_ADD_CONTACTS = "Add Your Contacts";
var BUTTON_ADD_PEOPLE = "Add People";
var BUTTON_ADD_PHOTOS = "Add Photos";
var BUTTON_CONTACTS = "Contacts";
var BUTTON_CONTINUE = "Continue";
var BUTTON_CONVO = "Conversation Feed";
var BUTTON_MYINFO = "My Info"
var BUTTON_LIBRARY = "Personal Library";
var BUTTON_SETTINGS = "Settings";
var BUTTON_EXIT = "Exit";
var BUTTON_SEARCH = "Search";
var BUTTON_SEND = "Send";
var BUTTON_CAMERA = "Camera";
var BUTTON_COMPOSE = "Compose";
var BUTTON_ACTION = "Action";
var BUTTON_EXPORT = "Export";
var BUTTON_SHARE = "Share";
var BUTTON_DASHBOARD_ID = BUTTON_CONTACTS;
var BUTTON_IMPORT_CONTACTS_1 = "Import Phone Contacts";
var BUTTON_IMPORT_CONTACTS_2 = "Import Address Book";
var BUTTON_IMPORT_GMAIL = "Import Gmail Contacts";
var BUTTON_IMPORT_FACEBOOK_1 = "Import Facebook Friends";
var BUTTON_IMPORT_FACEBOOK_2 = "Find Facebook Friends";
var BUTTON_SHOW_LIBRARY = "Show Library";
/*
 * nav.refresh('unlink');
 */
var BUTTON_UNLINK = "Unlink iPhone from Viewfinder";
var BUTTON_UNLINK_IPHONE = "Unlink iPhone";

var Exception = function(msg) {
  this.message = msg;
};
