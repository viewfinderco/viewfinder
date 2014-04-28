/**
 * The VFUser object handles any actions for a Viewfinder user
 * @class VFUser
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The VFUser object handles any actions for a Viewfinder user
 * @author: Greg Vandenberg
 *
 */
var VFUser = function() {
  var vf = new Viewfinder(false);
  var util = new VFUtils();

  return {
    cleanExistingUser: function(user) {
      this.terminate(user.email);
      this.register(user);
    },
    login: function(email) {
      var resp = null;
      var login_request = util.clone(util.requestTemplate);
      login_request.auth_info = {};
      login_request.auth_info.identity = 'Email:' + email;

      var result = vf.login(login_request, null);
      UIALogger.logDebug("Successfully logged in " + email);
      resp = result.stdout;
      eval('var success = ' + resp + ';');
      util.setLoggedInUserId(success['user_id']);

      return resp;

    },
    terminateAll: function() {
      for(var i=0; i<TEST_USERS.length; i++) {
        this.terminate(TEST_USERS[i].email);
      }
    },
    terminate: function(email) {
      var resp = this.login(email);
      if (resp) {
        eval('var response = ' + resp + ';');
        var args = [ '-HX-Xsrftoken: fake_xsrf' ];
        var term_request = util.clone(util.requestTemplate);

        term_request.headers = response.headers;
        UIALogger.logDebug("Response: " + response.headers);
        // need to get an op_id for /service/terminate_account from /service/allocate_ids
        var opid = null;
        var request = util.clone(util.requestTemplate);

        request.asset_types = ['o'];
        var result = vf.allocate_ids(request, args);
        eval('var op_id = ' + result.stdout + ';');
        term_request.headers.op_id = op_id.asset_ids[0];

        vf.terminate_account(term_request, args, function(result) {
            UIALogger.logDebug("Successfully terminated account for " + email);
          }, function(result) {
            UIALogger.logDebug("Error occured while attempting to terminate account for " + email);
          }
        );
      }
      else {
        //UIALogger.logDebug('Failed Login');
      }
    },
    registerAll: function() {
      for(var i=0; i<TEST_USERS.length; i++) {
        this.register(TEST_USERS[i]);
      }
    },
    register: function(user) {
      var register_request = util.clone(util.requestTemplate);
      register_request.auth_info = {
        identity : 'Email:' + user.email,
        name : user.firstname + ' ' + user.lastname,
        given_name : user.firstname,
        family_name : user.lastname,
        password : user.password
      };

      var result = vf.register(register_request, null);
      UIALogger.logDebug("Successfully registered " + user.email);
    },
    get_access_code: function(ident) {
      var request = util.clone(util.requestTemplate);
      var access_code = null;
      request.auth_info = {
        identity : ident,
      };
      var result = null;
      try {
      result = vf.get_access_code(request, null);
      UIALogger.logDebug("Successfully retrieved access code " + result.stdout);
      }
      catch(err) {
        target.delay(1);
        UIALogger.logDebug("Error occured retrieving access code... Retrying.");
        result = vf.get_access_code(request, null);
      }
      access_code = result.stdout;
      return access_code;
    }
  }
};
