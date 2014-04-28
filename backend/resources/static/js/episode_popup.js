// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview episode photo popup dialog.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.popup = {};
viewfinder.popup.HEADER_HEIGHT = 80;
viewfinder.popup.POPUP_MARGIN = 50;
viewfinder.popup.QUERY_LIMIT = 20;
viewfinder.popup.THUMBNAIL_BORDER = 2;
viewfinder.popup.THUMBNAIL_WIDTH = 90;
viewfinder.popup.TOTAL_WIDTH = viewfinder.popup.THUMBNAIL_WIDTH +
  viewfinder.popup.THUMBNAIL_BORDER * 2;

/**
 * Closes any existing popup and creates a new popup into the specified
 * 'episode' starting at photo index 'photoIndex'.
 *
 * @param {object} episode.
 * @param {number} photoIndex index into episode.photoArray_[].
 */
viewfinder.popup.createEpisodePopup = function(episode, photoIndex) {
  viewfinder.view.epPopup_ && viewfinder.view.epPopup_.close();
  viewfinder.view.epPopup_ = new EpisodePopup(episode, photoIndex);
};

/**
 * A popup to cycle through photos in an episode. Thumbnails are
 * constructed and the starting image loaded asynchronously. The displayed
 * photo is controlled via the PopupPhotoInfo object.
 *
 * @param {object} episode.
 * @param {number} photoIndex is index to photoArray within episode.
 */
function EpisodePopup(episode, photoIndex) {
  this.episode_ = episode;
  this.detached_ = false;
  this.$popup_ = null;
  this.$newPopup_ = null;
  this.$tnSel_ = null;
  this.$tnBox_ = null;
  this.$thumbnails_ = [];
  this.fadeTimeout_ = null;

  var contentWidth = $('#content').width();
  this.maxThumbnails_ = Math.floor(contentWidth / viewfinder.popup.TOTAL_WIDTH);

  // Create the popup photo info with layout callback.
  var epPopup = this;
  this.photoInfo_ = new PopupPhotoInfo(episode, photoIndex, function($img) {
    epPopup.layoutCallback_($img);
  });

  this.show();
};
EpisodePopup.prototype.constructor = EpisodePopup;

EpisodePopup.prototype.show = function() {
  if (this.detached_) {
    $('#content').append(this.$popup_);
    this.detached_ = false;
    return;
  }
  assert(!this.$popup_);

  var epPopup = this;
  viewfinder.bg_mask.singleton_.show(viewfinder.bg_mask.POPUP_MASK, function() {
    epPopup.layoutPhoto_();
    if (epPopup.episode_.photoArray_.length > 1) {
      epPopup.layoutNavigation_();
      epPopup.maybeQueryAdditional_();
    }
  }, function() {
    epPopup.close();
    return false;
  });
};

EpisodePopup.prototype.detach = function() {
  this.$popup_.detach();
  this.detached_ = true;
};

/**
 * Clears the shortcuts, the bg mask, detaches all thumbnails, and
 * removes the popup jQuery HTML div element.
 */
EpisodePopup.prototype.close = function() {
  viewfinder.shortcuts.singleton_.pop();
  viewfinder.bg_mask.singleton_.hide();
  this.$popup_.remove();
  this.$popup_ = null;
  for (var i = 0; i < this.episode_.photoArray_.length; i++) {
    if ('$thumbnail' in this.episode_.photoArray_[i]) {
      delete this.episode_.photoArray_[i].$thumbnail_;
    }
  }
  delete viewfinder.view.epPopup_;
};

EpisodePopup.prototype.reposition = function() {
  var $img = this.photoInfo_.$img;
  var marginSpace = viewfinder.popup.POPUP_MARGIN * 2;
  var availWidth = $(window).width() - marginSpace;
  var availHeight = $(window).height() - marginSpace - viewfinder.popup.HEADER_HEIGHT;
  var scale = Math.min(1.0, availWidth / $img.origWidth, availHeight / $img.origHeight);
  $img.css(viewfinder.util.computeImageXYWH(
    $img.origWidth * scale, $img.origHeight * scale, $img));
  var x = Math.floor(($(window).width() - $img.width()) * 0.5);
  var y = Math.max(viewfinder.popup.HEADER_HEIGHT + 10,
                   Math.floor(($(window).height() - $img.height()) * 0.25));
  this.$popup_.css({left: x, top: y});
};

EpisodePopup.prototype.layoutPhoto_ = function() {
  this.$newPopup_ = $('<div class="popup"/>');
  var $blocking = $('<div class="blocking"/>').appendTo(this.$newPopup_);
  viewfinder.view.layoutPhoto_(this.$newPopup_, $blocking, this.photoInfo_, true);
  $('<div id="popup-header"/>').appendTo($blocking);
};

EpisodePopup.prototype.layoutCallback_ = function($img) {
  if (this.$popup_) {
    this.$newPopup_.append($('.navigation').detach());
  }

  this.$popup_ && this.$popup_.remove();
  this.$popup_ = this.$newPopup_;
  this.$popup_.appendTo($('#content'));
  this.reposition();

  // Arrow keys move through photos; escape closes popup.
  var epPopup = this;
  viewfinder.shortcuts.singleton_.push(function(ep) {
    switch (ep.which) {
    case 27:   // escape
      epPopup.close();
      break;
    case 37:   // left arrow
      epPopup.setPhotoIndex_(epPopup.photoInfo_.photoIndex_ - 1, false);
      break;
    case 39:   // right arrow
    case 32:   // space
      epPopup.setPhotoIndex_(epPopup.photoInfo_.photoIndex_ + 1, false);
      break;
    default:
      return true;
    }
    return false;
  });

  this.showNavigation_();

  // Add popup header to image.
  $('#popup-header').empty();
  this.photoInfo_.addHeaderDetails($('#popup-header'));

  // Clicking into the photo advances.
  $img.on({
    'click': function() {
      epPopup.setPhotoIndex_(epPopup.photoInfo_.photoIndex_ + 1, true);
      return false;
    },
    'mousemove': function() {
      epPopup.showNavigation_();
      return false;
    },
  });
};

/**
 * Resets the photo being viewed in the popup to the photo
 * corresponding to 'index'.
 *
 * @param {number} index.
 * @param {boolean} animate to animate movement from old position to new.
 */
EpisodePopup.prototype.setPhotoIndex_ = function(index, animate) {
  this.setThumbnailSelection_(index, this.photoInfo_.photoIndex_, animate);
  this.photoInfo_.setIndex(index);
  viewfinder.shortcuts.singleton_.pop();
  this.layoutPhoto_();
  this.maybeQueryAdditional_();
};

/**
 * Sets the offset of the thumbnail selector to center the selected
 * thumbnail. Removes the 'selected' class from the previously selected
 * thumbnail and adds 'selected' class to the current.
 *
 * @param {number} index of currently selected thumbnail.
 * @param {number} index of previously selected thumbnail, if applicable.
 * @param {boolean} animate to animate movement from old position to new.
 */
EpisodePopup.prototype.setThumbnailSelection_ = function(index, oldIndex, animate) {
  var numThumbnails = this.episode_.photoArray_.length;
  if (typeof oldIndex !== 'undefined') {
    this.$thumbnails_[oldIndex].removeClass('selected');
    this.$thumbnails_[oldIndex].addClass('deselected');
  }
  if (index < 0) index = 0;
  if (index >= numThumbnails) index = numThumbnails - 1;
  this.$thumbnails_[index].removeClass('deselected');
  this.$thumbnails_[index].addClass('selected');
  // Offset the thumbnail selector so that it's centered if smaller than the box.
  var selCenter = (index + 0.5) * viewfinder.popup.TOTAL_WIDTH;
  var left = Math.floor(this.$tnBox_.width() / 2 - selCenter);
  this.$tnSel_.stop(true);
  if (animate) {
    this.$tnSel_.animate({left: left});
  } else {
    this.$tnSel_.css({left: left});
  }
};

/**
 * Queries additional photos for episode if the edge of the
 * thumbnail selector is close to coming in from the selector box,
 * (assuming there are more to load).
 */
EpisodePopup.prototype.maybeQueryAdditional_ = function() {
  var thumbnailsToRight = this.episode_.photoArray_.length - this.photoInfo_.photoIndex_;
  if (!('queriedAll_' in this.episode_) && thumbnailsToRight <= (this.maxThumbnails_ / 2)) {
    var epPopup = this;
    viewfinder.query.queryEpisode(
      this.episode_, viewfinder.popup.QUERY_LIMIT, function() {
        epPopup.layoutThumbnailSelector_();
      });
  }
};

/**
 * Lays out image previous and next indicators and if all thumbnails
 * are loaded, the thumbnail selector.
 *
 * Loads image thumbnails from photo metadata into jQuery image elements.
 * Only loads thumbnail data which hasn't already been loaded.
 */
EpisodePopup.prototype.layoutNavigation_ = function() {
  /*
  var $previous = $('<div id="nav-previous" class="navigation"/>').
    html('&lsaquo;').appendTo(this.$newPopup_);
  var $next = $('<div id="nav-next" class="navigation"/>').
    html('&rsaquo;').appendTo(this.$newPopup_);
  var epPopup = this;
  $previous.on('click', function() {
    epPopup.setPhotoIndex_(epPopup.photoInfo_.photoIndex_ - 1, true);
    return false;
  });
  $next.on('click', function() {
    epPopup.setPhotoIndex_(epPopup.photoInfo_.photoIndex_ + 1, true);
    return false;
  });
  */

  this.layoutThumbnailSelector_();
};

/**
 * Creates a row of thumbnails along the bottom of the popup, scaled
 * to fit an identical row height within the horizontal width of the
 * popup window and centered, if applicable.
 */
EpisodePopup.prototype.layoutThumbnailSelector_ = function() {
  if (this.$tnBox_ == null) {
    this.$tnBox_ = $('<div class="thumbnail-box navigation"/>').appendTo(this.$newPopup_);
    this.$tnSel_ = $('<div class="thumbnail-selector clearfix"/>').appendTo(this.$tnBox_);
  }
  var numThumbnails = this.episode_.photoArray_.length;
  var boxWidth = this.maxThumbnails_ * viewfinder.popup.TOTAL_WIDTH;
  this.$tnBox_.width(boxWidth);
  this.$tnSel_.width(numThumbnails * viewfinder.popup.TOTAL_WIDTH);

  for (var i = this.$thumbnails_.length; i < numThumbnails; i++) {
    this.addThumbnail_(this.$tnSel_, i);
  }

  // Compute x offset as a function of thumbnail mask width and popup width.
  var x = Math.floor(($(window).width() - this.$tnBox_.width()) / 2);
  this.$tnBox_.css({left: x});
  this.setThumbnailSelection_(this.photoInfo_.photoIndex_, 0, false);
};

/**
 * Adds a <div/> element to contain a thumbnail image with
 * id="thumbnail<index>".
 *
 * @param {object} $parent the thumbnail selector.
 * @param {number} index thumbnail index.
 */
EpisodePopup.prototype.addThumbnail_ = function($parent, index) {
  this.$thumbnails_[index] = $('<div id="thumbnail' + index + '" ' +
                               'class="thumbnail deselected left"/>').appendTo($parent);
  this.loadPhotoThumbnail_(this.$thumbnails_[index], index);
  var epPopup = this;
  this.$thumbnails_[index].on('click', function() {
    epPopup.setPhotoIndex_(index, true);
  });
};

/**
 * Loads image thumbnail for episode photo 'index' and adds <img/>
 * HTML element to the provided parent '$parent' div.
 */
EpisodePopup.prototype.loadPhotoThumbnail_ = function($parent, index) {
  // If it hasn't already been done, load the thumbnail data into an
  // image element and clear the thumbnail data to save space.
  assert(this.episode_.photoArray_[index].tn_get_url, 'no thumbnail url was specified');
  $thumbnail_ = $('<img class="thumbnail-img" src="' +
                  this.episode_.photoArray_[index].tn_get_url + '"/>');
  $thumbnail_.load(function() {
    $(this).origWidth = this.width;
    $(this).origHeight = this.height;
    var imgCss = viewfinder.util.computeImageXYWH(
      viewfinder.popup.THUMBNAIL_WIDTH, viewfinder.popup.THUMBNAIL_WIDTH, $(this));
    $(this).css(imgCss);
    $parent.append($(this));
  });
};

/**
 * Fades in the thumbnail selector and image previous and next
 * graphics. Sets a timeout for the next fade-out.
 */
EpisodePopup.prototype.showNavigation_ = function() {
  if (this.episode_.photoArray_.length < 1) {
    return;
  }

  if (this.fadeTimeout_) {
    clearTimeout(this.fadeTimeout_);
    $('#popup-header').stop(true);
    $('#popup-header').fadeTo(0, 0.80);
    $('.navigation').stop(true);
    $('.navigation').fadeTo(0, 1.0);
  } else {
    if (this.episode_.photoArray_.length > 1) {
      $('.navigation').fadeIn(200);
    }
    $('#popup-header').fadeTo(200, 0.80);
  }

  var epPopup = this;
  this.fadeTimeout_ = setTimeout(function() {
    $('.navigation').fadeOut(1000, function() {
      epPopup.fadeTimeout_ = null;
    });
    $('#popup-header').fadeOut(1000);
  }, 5000);
};
