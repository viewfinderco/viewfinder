// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview class to iterate over photos to display. This is left
 * intentionally vague. It can be every photo in an episode in order from
 * least to most recent. It can be a sampling of photos from each of many
 * episodes. It can be one photo from each of many episodes.
 *
 * Photos are iterated over in rows via the 'nextRow()' method and
 * within a row via the 'next()' method.
 *
 * The base class is PhotoIterator. Override 'next()' and 'nextRow()'
 * in subclasses.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */


/**
 * Base class for iteration.
 */
function PhotoIterator() {
};

/**
 * Iterates to the next photo within the current row.
 * @param {boolean} peek to fetch next photo without removal.
 * @return {object} the next PhotoInfo object in the iteration.
 */
PhotoIterator.prototype.next = function(peek) {
  assert(false, 'not implemented');
};

/**
 * Non-consuming fetch of the next element in the iteration.
 *
 * @return {object} the next PhotoInfo object in the iteration.
 */
PhotoIterator.prototype.peek = function() {
  return this.next(true);
};

/**
 * Iterates to the next row of photos.
 * @return {object} the next PhotoInfo object in the iteration.
 */
PhotoIterator.prototype.nextRow = function() {
  assert(false, 'not implemented');
};

/**
 * @return {number} the number of photos left in the iteration
 *   of the current row.
 */
PhotoIterator.prototype.remaining = function() {
  assert(false, 'not implemented');
};

/**
 * Iteration class which covers every photo in an episode.
 *
 * @param {object} episode.
 */
function EpisodeIterator(episode) {
  PhotoIterator.call(this);
  this.episode_ = episode;
  this.photoIndex_ = 0;
};

/** Inherit PhotoIterator */
EpisodeIterator.prototype = new PhotoIterator();
EpisodeIterator.prototype.constructor = EpisodeIterator;

EpisodeIterator.prototype.next = function(peek) {
  var photoInfo = null;
  if (this.photoIndex_ < this.episode_.photoArray_.length) {
    photoInfo = new SinglePhotoInfo(
      this.episode_.photoArray_[this.photoIndex_], this.photoIndex_);
    if (typeof peek == 'undefined' || !peek) {
      this.photoIndex_++;
    }
  }
  return photoInfo;
};

EpisodeIterator.prototype.nextRow = function() {
  // Does nothing.
};

EpisodeIterator.prototype.remaining = function() {
  return this.episode_.photoArray_.length - this.photoIndex_;
};

/**
 * Iteration class which yields a single PhotoInfo object for each episode.
 *
 * @param {array} episodes array.
 */
function EpisodeSummaryIterator(episodes) {
  PhotoIterator.call(this);
  this.episodes_ = episodes;
  this.index_ = this.getNextEpisode_(0);
};

/** Inherit PhotoIterator */
EpisodeSummaryIterator.prototype = new PhotoIterator();
EpisodeSummaryIterator.prototype.constructor = EpisodeSummaryIterator;

EpisodeSummaryIterator.prototype.next = function(peek) {
  var photoInfo = null;
  while (this.index_ < this.episodes_.length) {
    photoInfo = this.episodes_[this.index_].photoInfo_;
    if (typeof peek == 'undefined' || !peek) {
      this.index_ = this.getNextEpisode_(this.index_ + 1);
    }
  }
  return photoInfo;
};

EpisodeSummaryIterator.prototype.nextRow = function() {
  // Does nothing.
};

EpisodeSummaryIterator.prototype.remaining = function() {
  return this.episodes_.length - this.index_;
};

EpisodeSummaryIterator.prototype.getNextEpisode_ = function(index) {
  while (index < this.episodes_.length && this.episodes_[index].photoArray_.length == 0) {
    index += 1;
  }
  return index;
};

/**
 * Iteration class which yields between minPhotos and maxPhotos (both
 * bounded by number of photos in episode) for each episode. The 'remaining'
 * function will return the number of photos in each episode and when
 * all have been iterated, 'remaining' will show the number of photos
 * remaining in the next episode, or 0 if there are no further episodes.
 *
 * @param {array} episodes array.
 * @param {number} the minimum number of photos to display per episode.
 * @param {number} the maximum number of photos to display per episode.
 */
function EpisodePreviewIterator(episodes, minPhotos, maxPhotos) {
  PhotoIterator.call(this);
  this.episodes_ = episodes;
  this.epIndex_ = this.getNextEpisode_(0);
  this.minPhotos_ = minPhotos;
  this.maxPhotos_ = maxPhotos;
  this.photoIndex_ = 0;
  this.maxIndex_ = this.chooseMaxIndex_();
};

/** Inherit PhotoIterator */
EpisodePreviewIterator.prototype = new PhotoIterator();
EpisodePreviewIterator.prototype.constructor = EpisodePreviewIterator;

EpisodePreviewIterator.prototype.next = function(peek) {
  var photoInfo = null;
  if (this.remaining() > 0) {
    photoInfo = new SinglePhotoInfo(
      this.episodes_[this.epIndex_].photoArray_[this.photoIndex_], this.photoIndex_);
    if (typeof peek == 'undefined' || !peek) {
      this.photoIndex_ += 1;
    }
  }
  return photoInfo;
};

EpisodePreviewIterator.prototype.nextRow = function() {
  this.epIndex_ = this.getNextEpisode_(this.epIndex_ + 1);
  this.photoIndex_ = 0;
  this.maxIndex_ = this.chooseMaxIndex_();
};

EpisodePreviewIterator.prototype.remaining = function() {
  if (this.epIndex_ < this.episodes_.length) {
    if (this.maxIndex_ == -1) {
      this.epIndex_ = this.getNextEpisode_(this.epIndex_);
      this.maxIndex_ = this.chooseMaxIndex_();
    }
    return this.maxIndex_ - this.photoIndex_;
  }
  return 0;
};

EpisodePreviewIterator.prototype.chooseMaxIndex_ = function() {
  if (this.epIndex_ < this.episodes_.length) {
    var numPhotos = this.episodes_[this.epIndex_].photoArray_.length;
    var minIndex = Math.min(this.minPhotos_, numPhotos);
    var maxIndex = Math.min(this.maxPhotos_, numPhotos);
    return viewfinder.util.chooseRandomInt([minIndex, maxIndex]);
  } else {
    return -1;
  }
};

EpisodePreviewIterator.prototype.getNextEpisode_ = function(index) {
  while (index < this.episodes_.length && this.episodes_[index].photoArray_.length == 0) {
    index += 1;
  }
  return index;
};

/**
 * Iteration class which groups episodes by days. Each day may contain
 * multiple rows depending on the clusters of locations.  Separate
 * clusters of locations demand their own row(s). For each cluster, up
 * to three episodes may be displayed in a row. Each row may have up to
 * six photos. Between one and five photos from each episode are
 * displayed; two per episode is the minimum if there are two or more
 * photos in the episode.
 *
 * @param {array} episodes array.
 */
function EpisodesByDayIterator(episodes) {
  PhotoIterator.call(this);
  this.episodes_ = episodes;
  this.epIndex_ = this.getNextEpisode_(0);
  this.photoIndex_ = 0;
  this.maxIndex_ = this.chooseMaxIndex_();
  this.MIN_PHOTOS = 2;
};

/** Inherit PhotoIterator */
EpisodesByDayIterator.prototype = new PhotoIterator();
EpisodesByDayIterator.prototype.constructor = EpisodesByDayIterator;

EpisodesByDayIterator.prototype.next = function(peek) {
  var photoInfo = null;
  if (this.remaining() > 0) {
    photoInfo = new SinglePhotoInfo(
      this.episodes_[this.epIndex_].photoArray_[this.photoIndex_], this.photoIndex_);
    if (typeof peek == 'undefined' || !peek) {
      this.photoIndex_ += 1;
    }
  }
  return photoInfo;
};

EpisodesByDayIterator.prototype.nextRow = function() {
  this.epIndex_ = this.getNextEpisode_(this.epIndex_ + 1);
  this.photoIndex_ = 0;
};

EpisodesByDayIterator.prototype.remaining = function() {
  if (this.epIndex_ < this.episodes_.length) {
    if (this.maxIndex_ == -1) {
      this.epIndex_ = this.getNextEpisode_(this.epIndex_);
      this.maxIndex_ = this.chooseMaxIndex_();
    }
    return this.maxIndex_ - this.photoIndex_;
  }
  return 0;
};

EpisodesByDayIterator.prototype.chooseMaxIndex_ = function() {
  if (this.epIndex_ < this.episodes_.length) {
    var numPhotos = this.episodes_[this.epIndex_].photoArray_.length;
    var minIndex = Math.min(this.MIN_PHOTOS, numPhotos);
    return viewfinder.util.chooseRandomInt([minIndex, numPhotos]);
  } else {
    return -1;
  }
};

EpisodesByDayIterator.prototype.getNextEpisode_ = function(index) {
  while (index < this.episodes_.length && this.episodes_[index].photoArray_.length == 0) {
    index += 1;
  }
  return index;
};
