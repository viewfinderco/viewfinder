// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview class to hold information about a photo to be displayed.
 * The base class, PhotoInfo, is agnostic about what the photo represents.
 * Subclasses implement more recognizable concepts, such as an individual
 * photo, or a canonical photo to represent an episode, etc.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.photo_info = {};
viewfinder.photo_info.MONTH_ABBREVIATIONS = [
  'Jan', 'Feb', 'Mar',
  'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep',
  'Oct', 'Nov', 'Dec',
];
viewfinder.photo_info.DAY_ABBREVIATIONS = [
  'Sun', 'Mon', 'Tue', 'Wed',
  'Thu', 'Fri', 'Sat',
];


/**
 * Utility method to format date into an HTML <abbr> element. The
 * html is encapsulated in a <div/> element with style 'detail date'.
 *
 * @param {number} timestamp in UTC.
 * @param {boolean} abbreviate.
 * @return {object} jquery <div/> containing formatted date.
 */
viewfinder.photo_info.getDate = function(timestamp, abbreviate) {
  // Format the photo margin details.
  var d = new Date(Math.floor(timestamp * 1000));
  var day = d.getDate();
  var month = viewfinder.photo_info.MONTH_ABBREVIATIONS[d.getMonth()];
  var year = d.getFullYear();
  var dateStr = month + ' ' + day + ', ' + year;
  var fullStr = dateStr + ' ' + d.toLocaleTimeString();

  if (abbreviate) {
    return $('<div class="date r"/>').html(
      '<abbr title="' + fullStr + '">' + dateStr + '</abbr>');
  } else {
    return $('<div class="date r"/>').html(fullStr);
  }
};

/**
 * Utility method to format day and time into an HTML <abbr>
 * element. The html is encapsulated in a <div/> element with style
 * 'detail date'.
 *
 * @param {number} timestamp in UTC.
 * @return {object} jquery <div/> containing formatted date.
 */
viewfinder.photo_info.getDayAndTime = function(timestamp) {
  // Format the photo margin details.
  var d = new Date(Math.floor(timestamp * 1000));
  var day = viewfinder.photo_info.DAY_ABBREVIATIONS[d.getDay()];
  var dayTimeStr = day + ' ' + d.toLocaleTimeString();

  return $('<div/>').html(
    '<abbr title="' + d.toLocaleString()+ '">' + dayTimeStr + '</abbr>');
};

/**
 * Utility method to format place into an HTML <abbr> element. The
 * html is encapsulated in a <div/> element with style 'detail place'.
 *
 * @param {number} placemark; if undefined, returns an empty div.
 * @param {boolean} abbreviate.
 * @return {object} jquery <div/> containing formatted date.
 */
viewfinder.photo_info.getPlace = function(placemark, abbreviate) {
  if (typeof placemark == 'undefined') {
    return $('<div class="place"/>');
  }

  var fullStr = viewfinder.util.joinExceptNull(
    [placemark.sublocality || null, placemark.locality || null,
     placemark.state || null, placemark.country], ', ');

  var placeStr = '';
  if ('locality' in placemark && 'state' in placemark) {
    placeStr = placemark.locality + ', ' + placemark.state;
  } else if ('state' in placemark && 'country' in placemark) {
    placeStr = placemark.state + ', ' + placemark.country;
  } else if ('locality' in placemark && 'country' in placemark) {
    placeStr = placemark.locality + ', ' + placemark.country;
  }

  if (abbreviate) {
    return $('<div class="place"/>').html(
      '<abbr title="' + fullStr + '">' + placeStr + '</abbr>');
  } else {
    return $('<div class="place"/>').html(fullStr);
  }
};

/**
 * Adds time and place for an episode.
 *
 * @param {object} episode.
 * @param {object} $parent jQuery parent div element.
 * @param {function} onClick function to call if detail elements are clicked.
 */
viewfinder.photo_info.addEpisodeDetails = function(episode, $parent, onClick) {
  var $detail = $('<div class="detail spacetime"/>').appendTo($parent);
  if (episode.photoArray_.length > 0) {
    var photo = episode.photoArray_[0];
    viewfinder.photo_info.getDate(photo.timestamp, true).appendTo($detail);
    viewfinder.photo_info.getPlace(photo.placemark, false).appendTo($detail);
  }

  var $numPhotos = $('<div class="detail num-photos"/>').html('Show all &raquo;').appendTo($parent);
  if (onClick) {
    $detail.click(onClick);
    $numPhotos.click(onClick);
  }
};

/**
 * Base class for photo information. Holds jQuery Image object.
 */
function PhotoInfo() {
  this.$img = null;
};

/**
 * Returns the full image url to begin an asynchronous load.
 * @return {string} url of image resource.
 */
PhotoInfo.prototype.getFullUrl = function() {
  assert(false, 'not implemented');
};

/**
 * Callback function invoked upon completion of photo layout.
 *
 * @param {object} $img the jQuery Image element.
 */
PhotoInfo.prototype.layoutCallback = function($img) {
  assert(false, 'not implemented');
};

/**
 * Adds appropriate details about item that this photo represents
 * (e.g. whether an single photograph or a collection of photographs).
 *
 * @param {object} $photo jQuery parent object.
 */
PhotoInfo.prototype.addPhotoDetails = function($photo) {
  assert(false, 'not implemented');
};

/**
 * PhotoInfo subclass for individual photos.
 *
 * @param {object} photo metadata.
 * @param {number} the index of the photo if in a collection.
 */
function SinglePhotoInfo(photo, photoIndex) {
  PhotoInfo.call(this);
  this.photo_ = photo;
  this.photoIndex_ = photoIndex;
};

/** Inherit PhotoInfo */
SinglePhotoInfo.prototype = new PhotoInfo();
SinglePhotoInfo.prototype.constructor = SinglePhotoInfo;

SinglePhotoInfo.prototype.getFullUrl = function() {
  return this.photo_.full_get_url;
};

SinglePhotoInfo.prototype.layoutCallback = function($img) {
  var ep = viewfinder.query.episodes_[this.photo_.episode_id];
  var photoIndex = this.photoIndex_;
  this.$img = $img;
  $img.click(function() {
    viewfinder.popup.createEpisodePopup(ep, photoIndex);
    return false;
  });
};

/**
 * Adds episode details.
 *
 * @param {object} $parent jQuery html div parent element.
 * @param {boolean} showOnClick show episode overlay on click.
 */
SinglePhotoInfo.prototype.addEpisodeDetails = function($parent, showOnClick) {
  var ep = viewfinder.query.episodes_[this.photo_.episode_id];
  var onClick = null;
  if (showOnClick) {
    onClick = function() {
      viewfinder.overlay.createEpisodeOverlay(ep);
      return false;
    };
  }
  $detail = viewfinder.photo_info.addEpisodeDetails(ep, $parent, onClick);
};

SinglePhotoInfo.prototype.addPhotoDetails = function($photo) {
  var $detail = $('<div class="detail day-and-time"/>').appendTo($photo);
  viewfinder.photo_info.getDayAndTime(this.photo_.timestamp).appendTo($detail);
};

/**
 * PhotoInfo subclass for episode summary photo.
 *
 * @param {object} episode metadata.
 * @param {function} callback method on layout; invoked with $img.
 * @param {number} photoIndex starting photo index; if undefined, choice is random.
 */
function EpisodePhotoInfo(episode, photoIndex) {
  PhotoInfo.call(this);
  this.episode_ = episode;
  if (typeof photoIndex == 'undefined') {
    this.photoIndex_ = Math.floor(Math.pow(Math.random(), 2) * episode.photoArray_.length);
  } else {
    this.photoIndex_ = photoIndex;
  }
};

/** Inherit PhotoInfo */
EpisodePhotoInfo.prototype = new PhotoInfo();
EpisodePhotoInfo.prototype.constructor = EpisodePhotoInfo;

EpisodePhotoInfo.prototype.getFullUrl = function() {
  return this.episode_.photoArray_[this.photoIndex_].full_get_url;
};

EpisodePhotoInfo.prototype.layoutCallback = function($img) {
  var ep = this.episode_;
  var photoIndex = this.photoIndex_;
  this.$img = $img;
  $img.click(function() {
    viewfinder.popup.createEpisodePopup(ep, photoIndex);
    return false;
  });
};

EpisodePhotoInfo.prototype.addPhotoDetails = function($photo) {
  var $detail = $('<div class="detail spacetime"/>').appendTo($photo);
  var photo = this.episode_.photoArray_[this.photoIndex_];
  viewfinder.photo_info.getDate(photo.timestamp, true).appendTo($detail);
  viewfinder.photo_info.getPlace(photo.placemark, true).appendTo($detail);

  var $numPhotos = $('<div class="detail num-photos"/>').html('Show all &raquo;').appendTo($photo);

  var ep = this.episode_;
  $detail.click(function() {
    viewfinder.overlay.createEpisodeOverlay(ep);
    return false;
  });
  $numPhotos.click(function() {
    viewfinder.overlay.createEpisodeOverlay(ep);
    return false;
  });
};

/**
 * PhotoInfo subclass for episode popup.
 *
 * @param {object} episode metadata.
 * @param {number} photo index to display.
 * @param {function} callback to invoke upon image layout.
 */
function PopupPhotoInfo(episode, photoIndex, callback) {
  PhotoInfo.call(this);
  this.episode_ = episode;
  this.photoIndex_ = photoIndex;
  this.callback_ = callback;
};

/** Inherit PhotoInfo */
PopupPhotoInfo.prototype = new PhotoInfo();
PopupPhotoInfo.prototype.constructor = PopupPhotoInfo;

PopupPhotoInfo.prototype.getFullUrl = function() {
  return this.getPhoto().full_get_url;
};

PopupPhotoInfo.prototype.layoutCallback = function($img) {
  this.$img = $img;
  this.callback_ && this.callback_($img);
};

/**
 * Adds photo details to the popup header.
 *
 * @param {object} $header jQuery html div parent element.
 */
PopupPhotoInfo.prototype.addHeaderDetails = function($header) {
  var $detail = $('<div class="detail spacetime"/>').appendTo($header);
  var photo = this.episode_.photoArray_[this.photoIndex_];
  viewfinder.photo_info.getDate(photo.timestamp, false).appendTo($detail);
  viewfinder.photo_info.getPlace(photo.placemark, false).appendTo($detail);
};

PopupPhotoInfo.prototype.addPhotoDetails = function($photo) {
  // Do nothing.
};

/**
 * Sets the photo index. Limits the index to the available range of
 * photos.
 */
PopupPhotoInfo.prototype.setIndex = function(index) {
  this.photoIndex_ = index;
  if (this.photoIndex_ < 0) {
    this.photoIndex_ = 0;
  } else if (this.photoIndex_ >= this.episode_.photoArray_.length) {
    this.photoIndex_ = this.episode_.photoArray_.length - 1;
  }
  this.$img = null;
};

/**
 * A shortcut to the current photo.
 * @return {object} current photo metadata.
 */
PopupPhotoInfo.prototype.getPhoto = function() {
  return this.episode_.photoArray_[this.photoIndex_];
};
