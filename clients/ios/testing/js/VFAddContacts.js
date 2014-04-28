/**
 * The addContacts object which handles any actions stemming from the AddContacts screen
 * @class VFAddContacts
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The addContacts object which handles any actions stemming from the AddContacts screen
 * @author: Greg Vandenberg
 *
 */
var VFAddContacts = function(_nav) {
  var nav = _nav;
  var util = new VFUtils(nav);
  return {
    gotoContacts: function() {
      util.pollUntilButtonVisibleTap(BUTTON_TB_BACK, 'navbar', 5);
      return new VFContacts(nav);
    }
  }
};
