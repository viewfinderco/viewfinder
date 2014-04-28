/**
 * The contacts object which handles any actions stemming from the Contacts screen
 * @class VFContacts
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The contacts object which handles any actions stemming from the Contacts screen
 * @author: Greg Vandenberg
 *
 */
var VFContacts = function(_nav) {
  var nav = _nav;
  var util = new VFUtils(nav);
  return {
    selectAddContacts: function() {
      //nav.tapButton(nav.getButton(BUTTON_TB_ADD_CONTACT, 'navbar'));
      target.app().tapWithOptions({tapOffset:{x:0.90, y:0.05}});
      /**
       * below is how to access the button according to logElementTree(),
       * however it does not work
       */
      //target.app().navigationBar().buttons()["toolbar add contact"].tap();
      return new VFAddContacts(nav);
    },
    selectBackNav: function() {
      // TODO: this button is elusive, find better way to get at it
      target.app().tapWithOptions({tapOffset:{x:0.10, y:0.05}});
      /**
       * below is how to access the button according to logElementTree(),
       * however it does not work
       */
      //target.frontMostApp().navigationBar().buttons()["toolbar back nav"].tap();
    },
    selectDismissDialog: function() {
      // TODO: this button is elusive, find better way to get at it
      target.app().tapWithOptions({tapOffset:{x:0.10, y:0.05}});
      /**
       * below is how to access the button according to logElementTree(),
       * however it does not work
       */
      //target.app().navigationBar().buttons()["dismiss dialog"].tap();
    },
    selectSpreadTheWord: function() {
      target.main().tableViews()["Empty list"].cells()["Spread the word"].buttons()["Spread the word"].tap();
      target.delay(2); // TODO: need a solution for determining when the next page is loaded
    },
    selectContact: function(num) {
      target.main().tableViews()["Empty list"].cells()[num].tap();
      target.delay(2); // TODO: need a solution for determining when the next page is loaded
    },
    selectAddContactField: function() {
      target.main().scrollViews()[0].images()[0].textFields()[0].tap();
    },
    selectSearchTextField: function() {
      target.main().tableViews()["Empty list"].tapWithOptions({tapOffset:{x:0.46, y:0.08}});
    },
    selectEmailSend: function() {
      target.app().navigationBar().buttons()["Send"].tap();
    },
    selectEmailCancel: function() {
      this.selectBackNav();
      util.pollUntilButtonVisibleTap(BUTTON_DELETE_DRAFT, 'action', 5);
    },
    selectSearchCancel: function() {
      target.main().buttons()["Cancel"].tap();
    },
    selectButtonAll: function() {
      util.pollUntilButtonVisibleTap("All", 'segmented', 5);
    },
    selectButtonViewfinder: function() {
      util.pollUntilButtonVisibleTap("Viewfinder", 'segmented', 5);
    },
    enterSearchTerm: function(term) {
      var cell = target.main().tableViews()["Empty list"].cells()[0];
      cell.typeString(term+'\n');
    },
    setContactEmail: function(email) {
      var textField = target.main().scrollViews()[0].images()[0].textFields()[0];
      textField.typeString(email+'\n', true);
      target.delay(1);  // this is to avoid an intermittent problem
    },
    selectAdd: function() {
      util.pollUntilButtonVisibleTap(BUTTON_ADD, 'main_window', 5);
    },
    selectContinue: function() {
      var button = util.pollUntilButtonVisible(BUTTON_CONTINUE, 'main_window', 5);
      button.tapAndWaitForInvalid();
    },
    setAccessCode: function(access_code) {
      UIALogger.logDebug("Access Code: " + access_code);
      //target.app().keyboard().typeString(access_code);
      var textField = target.main().images()[1].textFields()[0];
      textField.typeString(access_code,true);
    },
    setMobileNumber: function(number) {
      var textField = target.main().images()[1].textFields()[0];
      textField.typeString(number,true);
    },
    addMobileIdentity: function(number) {
      this.setMobileNumber(number);
      this.selectAdd();
      //util.delay(2);  // TODO:  retry in get_access_code method
      var user = new VFUser();
      var access_code2 = user.get_access_code('Phone:' + number);

      this.setAccessCode(access_code2);

      this.selectContinue();
      util.delay(2);
    },
    /**
     * The import phone contacts button showed up three different ways
     * in instruments
     */
    importPhoneContacts: function() {
      /**
       * some builds have 'Import Phone Contacts' for the 'Import Address Book' button
       * while other builds have 'Import Address Book' for the button... fun.
       */
      try {
        var button = util.pollUntilButtonVisible(BUTTON_IMPORT_CONTACTS_2, 'contacts', 5);
        button.tapAndWaitForInvalid();
      }
      catch(err) {
        var button2 = util.pollUntilButtonVisible(BUTTON_IMPORT_CONTACTS_1, 'contacts', 5);
        button2.tapAndWaitForInvalid();
      }
      this.addMobileIdentity('+12065555555');

    },
    setFacebookCredentials: function() {
      var webview = target.main().scrollViews()[1].webViews()[0];
      var textField = webview.textFields()[0];
      target.delay(1);
      textField.typeString(FACEBOOK_TEST_USERNAME);
      util.pollUntilButtonVisibleTap(BUTTON_DONE, 'toolbar', 5);

      webview.secureTextFields()[0].typeString(FACEBOOK_TEST_PASSWORD);
      util.pollUntilButtonVisibleTap(BUTTON_DONE, 'toolbar', 5);
    },
    importFacebookFriends: function() {
      var button = util.pollUntilButtonVisible(BUTTON_IMPORT_FACEBOOK_1, 'contacts', 5);
      if (typeof button == 'undefined') {
        button = util.pollUntilButtonVisible(BUTTON_IMPORT_FACEBOOK_2, 'contacts', 5);
      }
      button.tapAndWaitForInvalid();

      target.delay(2);  // TODO: need a solution for determining when the next page is loaded
      try {
        this.setFacebookCredentials();
      }
      catch(err) {
        target.delay(2);
        this.setFacebookCredentials();
      }
      util.pollUntilButtonVisibleTap(BUTTON_LOGIN, 'webview', 5);
      util.pollUntilButtonVisibleTap(BUTTON_OK, 'webview', 5);
    },
    importGmailContacts: function() {
      var button = util.pollUntilButtonVisible(BUTTON_IMPORT_GMAIL, 'contacts', 5);
      button.tapAndWaitForInvalid();
      var webview = target.main().scrollViews()[0].webViews()[0];
      var textField = util.pollUntilElementVisible(webview.textFields()["Email"], 10);
      textField.typeString(GMAIL_TEST_USERNAME);

      var done_btn1 = util.pollUntilButtonVisible(BUTTON_DONE, 'toolbar', 5);
      done_btn1.vtap();

      var passwordTextField = webview.secureTextFields()["Password"];
      passwordTextField.typeString(GMAIL_TEST_PASSWORD);
      done_btn1.vtap();

      webview.buttons()["Sign in"].tapAndWaitForInvalid();
       // loading of next screen may take a couple seconds
      target.delay(3); // TODO: need a solution for determining when the next page is loaded
      // Gmail has two possible screens here; 'Allow access' or 'Accept'
      try {
        var allow_access = webview.buttons()["Allow access"];
        allow_access.scrollToVisible();
        allow_access.tapAndWaitForInvalid();
      }
      catch (err) {
        var allow_access = webview.buttons()["Accept"];
        allow_access.scrollToVisible();
        allow_access.tapAndWaitForInvalid()
      }

    },
    gotoDashboard: function() {
      /**
       * check for dashboard id button
       */
      for (var i=0; i<5; i++) {
        this.selectBackNav();
        if (nav.getButton(BUTTON_DASHBOARD_ID,'main') != null) {
          UIALogger.logDebug("At Dashboard.");
          return new VFDashboard(nav);
        }
      }
    }
  }
};
