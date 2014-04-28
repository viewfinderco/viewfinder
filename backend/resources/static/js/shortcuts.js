// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview Handle keyboard shortcuts in the constext of multiple
 *  overlays (e.g. episode overlay + photo popup).
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.shortcuts = {};
viewfinder.shortcuts.EVENT_NAME = 'keydown.shortcuts';

/**
 * Implements a stack for document keydown event handlers.
 */
function ShortcutsStack() {
  this.handlerStack_ = [];
}
ShortcutsStack.prototype.constructor = ShortcutsStack;

/**
 * Adds a handler to the stack.
 * @param {function} handler keydown event handler.
 */
ShortcutsStack.prototype.push = function(handler) {
  this.handlerStack_.push(handler);
  $(document).unbind(viewfinder.shortcuts.EVENT_NAME);
  $(document).bind(viewfinder.shortcuts.EVENT_NAME, handler);
  //console.log('shortcuts stack: ' + this.handlerStack_.length);
};

ShortcutsStack.prototype.pop = function() {
  assert(this.handlerStack_.length > 0, 'handler stack should not be empty');
  $(document).unbind(viewfinder.shortcuts.EVENT_NAME);
  this.handlerStack_.pop();
  if (this.handlerStack_.length > 0) {
    $(document).bind(viewfinder.shortcuts.EVENT_NAME,
                     this.handlerStack_[this.handlerStack_.length - 1]);
  }
  //console.log('shortcuts stack: ' + this.handlerStack_.length);
};

viewfinder.shortcuts.singleton_ = new ShortcutsStack();

