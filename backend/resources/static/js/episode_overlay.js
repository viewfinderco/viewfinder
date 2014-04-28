// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview display all photos in an episode using view.js
 * display templates.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.overlay = {};
viewfinder.overlay.MARGIN = 0;
viewfinder.overlay.QUERY_LIMIT = 20;

/**
 * Closes any existing overlay and creates a new overlay into the
 * specified 'episode'.
 *
 * @param {object} episode.
 */
viewfinder.overlay.createEpisodeOverlay = function(episode) {
  viewfinder.view.epOverlay_ && viewfinder.view.epOverlay_.close();
  viewfinder.view.epOverlay_ = new EpisodeOverlay(episode);
};

/**
 * Expanded view of all photos in an episode, overlaid on existing
 * content. When the overlay is first viewed, most likely the
 * episode will only contain the initial set of preview images. If
 * the count of photos in the episode exceeds the number loaded and
 * the number loaded is less than viewfinder.overlay.QUERY_LIMIT, a
 * query is launched to get additional photos for display.
 *
 * $morePhotos_ is an array of additional blocks of photo content which
 * are loaded on demand.
 *
 * @param {object} episode.
 */
function EpisodeOverlay(episode) {
  this.episode_ = episode;
  this.iterator_ = null;
  this.$overlay_ = null;
  this.$innerlay_ = null;

  var epOverlay = this;
  this.moreCallback_ = function() {
    if (!('queriedAll_' in epOverlay.episode_)) {
      epOverlay.queryAdditional_();
    }
  };

  this.show();
};
EpisodeOverlay.prototype.constructor = EpisodeOverlay;

/*
 * Opens the overlay. If 'onResize' is specified, no animation effects
 * are used.
 */
EpisodeOverlay.prototype.show = function(onResize) {
  this.$overlay_ = $('<div class="overlay"/>');
  var $header = $('<div class="overlay-header"/>').appendTo(this.$overlay_);
  // Add episode photo details to header.
  this.iterator_ = new EpisodeIterator(this.episode_)
  this.iterator_.peek().addEpisodeDetails($header);

  this.$innerlay_ = $('<div class="innerlay clearfix"/>').appendTo(this.$overlay_);

  this.layoutWidth_ = $(window).width() - viewfinder.overlay.MARGIN * 2;
  viewfinder.view.layoutScrapbook_(this.$innerlay_, this.layoutWidth_,
                                   false, this.moreCallback_, this.iterator_);

  if (onResize) {
    this.reposition(true);
    this.$overlay_.appendTo($('#content'))
  } else {
    var epOverlay = this;
    viewfinder.bg_mask.singleton_.show(viewfinder.bg_mask.OVERLAY_MASK, function() {
      if (epOverlay.$overlay_) {
        epOverlay.reposition(true);
        epOverlay.$overlay_.appendTo($('#content'))
      }
    }, function() {
      epOverlay.close();
      return false;
    });
  }

  this.setupEpisodes_();
};

/**
 * Closes the overlay. If 'onResize' is specified, no animation
 * effects are used.
 */
EpisodeOverlay.prototype.close = function(onResize) {
  viewfinder.shortcuts.singleton_.pop();
  if (onResize) {
    this.$overlay_.remove();
  } else {
    this.$overlay_.remove();
    viewfinder.bg_mask.singleton_.hide();
  }
  this.$overlay_ = null;
  delete viewfinder.view.epOverlay_;
};

/**
 * Reposition the overlay so that it is centered horizontally in the
 * window. If 'vertical' is true, the overlay is vertically aligned
 * to start 1/4 of the way down the extra vertical space.
 *
 * @param {boolean} vertical true to align vertically.
 */
EpisodeOverlay.prototype.reposition = function(vertical) {
  var left = Math.floor(($(window).width() - this.$innerlay_.width()) * 0.50);
  this.$overlay_.css({left: left});
  if (vertical) {
    var top = $(window).scrollTop() + 100;
    this.$overlay_.css({top: top});
  }
};

/**
 * Query additional photos for episode. On query, lays out new
 * photos by appending to the contents of this.$innerlay_.
 */
EpisodeOverlay.prototype.queryAdditional_ = function() {
  var epOverlay = this;
  var index = this.episode_.photoArray_.length;
  viewfinder.query.queryEpisode(
    this.episode_, viewfinder.overlay.QUERY_LIMIT, function() {
      viewfinder.view.layoutScrapbook_(epOverlay.$innerlay_, epOverlay.layoutWidth_,
                                       true, epOverlay.moreCallback_, epOverlay.iterator_);
    });
};

EpisodeOverlay.prototype.setupEpisodes_ = function() {
  var epOverlay = this;
  viewfinder.shortcuts.singleton_.push(function (ep) {
    switch (ep.which) {
    case 27:   // escape
      epOverlay.close();
      break;
    default:
      return true;
    }
    return false;
  });
};
