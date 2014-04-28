// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview Background masks for attenuating background
 *     details in favor of an overlay or popup.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.bg_mask = {};
viewfinder.bg_mask.CLICK_EVENT = 'click.bg_mask';
viewfinder.bg_mask.OVERLAY_MASK = {fade: true, css: {'z-index': 1, 'background-color': '#f4f4f4'}};
viewfinder.bg_mask.POPUP_MASK = {fade: true, css: {'z-index': 3, 'background-color': '#000000'}};

/**
 * Creates a semi-opaque darkening of the background image.
 * calling show() and hide() work via a reference count, hiding
 * the HTML div element only when the count is 0 and showing it
 * as long as the count is >= 0.
 */
function BackgroundMask() {
  this.maskStack_ = [];
}
BackgroundMask.prototype.constructor = BackgroundMask;

/**
 * Pushes a new mask onto the stack. If none existed, sets 'display: block'.
 * Sets the appropriate z-index and applies the click function, if specified.
 *
 * @param {number} mask: specify one of OVERLAY_MASK or POPUP_MASK.
 * @param {function} callback is called once mask is in place.
 * @param {function} click_func a function to call on a click to the opaque mask
 *     element. For example, to close a popup or overlay.
 */
BackgroundMask.prototype.show = function(mask, callback, click_func) {
  $('#opaque').css(mask.css);
  $('#opaque').off(viewfinder.bg_mask.CLICK_EVENT);
  $('#opaque').on(viewfinder.bg_mask.CLICK_EVENT, click_func);
  this.maskStack_.push({'mask': mask, 'click_func': click_func});
  if (this.maskStack_.length == 1) {
    if (mask.fade) {
      $('#opaque').fadeIn('fast', callback);
    } else {
      $('#opaque').show(0, callback);
    }
  } else {
    callback();
  }
  //console.log('z-index stack: ' + this.maskStack_.length);
};

/**
 * Pops the mask stack. If there are none left, hides the background mask
 * by setting 'display: none'. If there are still masks in the stack, applies
 * the appropriate z-index and set the click function, if specified.
 */
BackgroundMask.prototype.hide = function() {
  assert(this.maskStack_.length > 0, 'z-index stack should not be empty');
  this.maskStack_.pop();
  $('#opaque').off(viewfinder.bg_mask.CLICK_EVENT);
  if (this.maskStack_.length == 0) {
    $('#opaque').hide();
  } else {
    mask = this.maskStack_[this.maskStack_.length - 1];
    $('#opaque').css(mask.mask.css);
    $('#opaque').on(viewfinder.bg_mask.CLICK_EVENT, mask.click_func);
  }
  //console.log('z-index stack: ' + this.maskStack_.length);
};

viewfinder.bg_mask.singleton_ = new BackgroundMask();

