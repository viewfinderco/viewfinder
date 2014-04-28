// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview photo layout routines for episodes.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.view = {};

viewfinder.view.PIXELS_PER_GROUP = 300;
viewfinder.view.MARGIN = 35;
viewfinder.view.SCRAPBOOK_LAYOUT = 'scrapbook';
viewfinder.view.GALLERY_LAYOUT = 'gallery';
viewfinder.view.FRAMED_STYLESHEET = 'framed';
viewfinder.view.PHOTO_APPEAR_SCALE = 4.0;
viewfinder.view.MORE_APPEAR_SCALE = 1.0;

viewfinder.view.FULL_TEMPLATE = {
  prob: 0.20, photos: 1, width: 2, class: 'left picture wide tall', children: []
};

viewfinder.view.TEMPLATES = [
  // 780-width templates.
  {prob: 0.125, photos: 2, width: 3, class: 'left', children: [
    {class: 'left picture med-wide tall', children: []},
    {class: 'left picture med-wide tall l', children: []},
  ]},
  {prob: 0.10, photos: 3, width: 3, class: 'left', children: [
    {class: 'left picture med-wide tall', children: []},
    {class: 'left l', children: [
      {class: 'picture med-wide', children: []},
      {class: 'picture med-wide t', children: []},
    ]},
  ]},
  {prob: 0.10, photos: 3, width: 3, class: 'left', children: [
    {class: 'left', children: [
      {class: 'picture med-wide', children: []},
      {class: 'picture med-wide t', children: []},
    ]},
    {class: 'left l picture med-wide tall', children: []},
  ]},
  // 580-width templates.
  viewfinder.view.FULL_TEMPLATE,
  {prob: 0.10, photos: 3, width: 2, class: 'left', children: [
    {class: 'left picture tall', children: []},
    {class: 'left l', children: [
      {class: 'picture', children: []},
      {class: 'picture t', children: []},
    ]},
  ]},
  {prob: 0.075, photos: 2, width: 2, class: 'left', children: [
    {class: 'left picture tall', children: []},
    {class: 'left picture tall l', children: []},
  ]},
  {prob: 0.075, photos: 2, width: 2, class: 'left', children: [
    {class: 'picture wide', children: []},
    {class: 'picture wide t', children: []},
  ]},
  {prob: 0.05, photos: 3, width: 2, class: 'left', children: [
    {class: 'left', children: [
      {class: 'left picture', children: []},
      {class: 'left picture l', children: []},
    ]},
    {class: 'clear', children: []},
    {class: 'left picture wide t', children: []},
  ]},
  {prob: 0.05, photos: 3, width: 2, class: 'left', children: [
    {class: 'left picture wide', children: []},
    {class: 'clear', children: []},
    {class: 'left t', children: [
      {class: 'left picture', children: []},
      {class: 'left picture l', children: []},
    ]},
  ]},
  // 280-width templates.
  {prob: 0.075, photos: 1, width: 1, class: 'left picture tall', children: []},
  {prob: 0.05, photos: 2, width: 1, class: 'left', children: [
    {class: 'picture', children: []},
    {class: 'picture t', children: []},
  ]},
];

/**
 * Display a summary view of viewfinder.query.episodes_.
 */
viewfinder.view.layoutEpisodes = function() {
  var $parent = $('#content');
  var width = $(window).width();
  var episodes = viewfinder.query.epArray_;
  var iterator;

  if (viewfinder.view.layout == viewfinder.view.SCRAPBOOK_LAYOUT) {
    iterator = new EpisodeSummaryIterator(episodes);
  } else if (viewfinder.view.layout == viewfinder.view.GALLERY_LAYOUT) {
    iterator = new EpisodePreviewIterator(episodes, 2, 5);
  } else {
    assert(false, 'unknown layout: ' + viewfinder.view.layout);
  }

  var moreCallback = moreCallback = function() {
    if ('lastEpisodeKey_' in viewfinder.query) {
      viewfinder.query.queryEpisodes(function() {
        if (iterator.remaining() > 0) {
          viewfinder.view.layoutRows_($parent, width, true, moreCallback, iterator);
        }
      });
    };
  };

  viewfinder.view.layoutRows_($parent, width, false, moreCallback, iterator);

  // Setup window resize handler.
  $(window).resize(function() {
    viewfinder.view.maybeResize_(episodes);
  });
};

/**
 * Computes the number of groups which should be placed on each row.
 * For gallery layout, max number of groups is fixed at 4 per row.
 */
viewfinder.view.computeGroupsPerRow_ = function(width, layout) {
  var groupsPerRow = Math.max(2, Math.floor(width / viewfinder.view.PIXELS_PER_GROUP));
  if (layout == viewfinder.view.GALLERY_LAYOUT) {
    groupsPerRow = Math.min(4, groupsPerRow);
  }
  return groupsPerRow;
}

/**
 * Called on window resize. If the number of groups / row has changed,
 * Re-compute layout.
 *
 * @param {array} episodes to layout.
 */
viewfinder.view.maybeResize_ = function(episodes) {
  var width = $(window).width();
  var resizeGroupsPerRow = viewfinder.view.computeGroupsPerRow_(width, viewfinder.view.layout);
  if (viewfinder.view.groupsPerRow_ != resizeGroupsPerRow) {
    viewfinder.view.groupsPerRow_ = resizeGroupsPerRow;
    var epOverlay = viewfinder.view.epOverlay_;
    viewfinder.view.epOverlay_ && viewfinder.view.epOverlay_.close(true);
    viewfinder.view.epPopup_ && viewfinder.view.epPopup_.detach();

    $('#content').empty();
    viewfinder.view.layoutEpisodes();

    viewfinder.view.epOverlay_ = epOverlay;
    viewfinder.view.epOverlay_ && viewfinder.view.epOverlay_.show(true);
    viewfinder.view.epPopup_ && viewfinder.view.epPopup_.show();
  } else {
    viewfinder.view.epOverlay_ && viewfinder.view.epOverlay_.reposition(false);
    viewfinder.view.epPopup_ && viewfinder.view.epPopup_.reposition();
  }
}

/**
 * Layout photos from 'iterator' according to the configured layout.
 *
 * @param {object} $parent the parent jQuery div element.
 * @param {number} width available horizontal space.
 * @param {boolean} append if appending additional columns to layout.
 * @param {function} moreCallback fetches additional photos (if not null).
 * @param {function} iterator returns photos to display in a template
 *    layout group while there are photos in the iteration; null otherwise.
 */
viewfinder.view.layoutRows_ = function(
  $parent, width, append, moreCallback, iterator) {
  if (iterator.remaining() == 0 && !append) {
    $parent.append($('<div id="noepisodes"/>').html('No Episodes to Display'));
    return;
  }

  if (viewfinder.view.layout == viewfinder.view.SCRAPBOOK_LAYOUT) {
    viewfinder.view.layoutScrapbook_($parent, width, append, moreCallback, iterator);
  } else if (viewfinder.view.layout == viewfinder.view.GALLERY_LAYOUT) {
    viewfinder.view.layoutGallery_($parent, width, append, moreCallback, iterator);
  } else {
    assert(false, 'no layout specified for layout rows');
  }
};

/**
 * Choose scrapbook group layouts to fill up rows in
 * '$parent'. 'iterator' yields a sequence of photos. Each subsequent
 * photo is slotted into each group's layout template.
 *
 * See layoutRows_ for details on params.
 */
viewfinder.view.layoutScrapbook_ = function(
  $parent, width, append, moreCallback, iterator) {
  // Compute # of groups per row & set width.
  var groupsPerRow = viewfinder.view.computeGroupsPerRow_(width, viewfinder.view.SCRAPBOOK_LAYOUT);
  $parent.width(groupsPerRow * viewfinder.view.PIXELS_PER_GROUP - viewfinder.view.MARGIN);

  // Layout template groups into rows.
  for (var row = 0; iterator.remaining(); row++) {
    var remaining = iterator.remaining();
    var numGroups = 0;
    var groups = viewfinder.view.chooseGroups_(remaining, groupsPerRow, false);
    var $rowDiv = $('<div class="left row' + (row > 0 || append ? ' t' : '') + '"/>');
    $parent.append($rowDiv);
    for (var j = 0; j < groups.length; j++) {
      viewfinder.view.layoutGroup_($rowDiv, groups[j], iterator, 0, (j == groups.length - 1));
      // If we run out of photos while laying out groups, possibly
      // shrink the width of the parent to reflect the actual number
      // of groups laid out.
      numGroups += groups[j].width;
      if (iterator.remaining() == 0) {
        if (row == 0 && !append) {
          $parent.width(numGroups * viewfinder.view.PIXELS_PER_GROUP - viewfinder.view.MARGIN);
        }
        break;
      }
    }
    if (row == 0) {
      $rowDiv.appear(moreCallback, {scale: viewfinder.view.MORE_APPEAR_SCALE});
    }
  }
};

/**
 * Choose a gallery to fill up rows in '$parent'. 'iterator'
 * yields a sequence of photos. Each subsequent photo is slotted into
 * each group's layout template.
 *
 * See layoutRows_ for details on params.
 */
viewfinder.view.layoutGallery_ = function($parent, width, append, moreCallback, iterator) {
  // Compute # of groups per row & set width.
  var groupsPerRow = viewfinder.view.computeGroupsPerRow_(width, viewfinder.view.GALLERY_LAYOUT);
  $parent.width(groupsPerRow * viewfinder.view.PIXELS_PER_GROUP - viewfinder.view.MARGIN);

  // Layout template groups into rows.
  for (var row = 0; iterator.remaining(); row++) {
    var remaining = iterator.remaining();
    var groups = viewfinder.view.chooseGroups_(remaining, groupsPerRow, true);
    var $galleryDiv = $('<div class="gallery-header' + (row > 0 || append ? ' gallery-t' : '') + '"/>');
    $parent.append($galleryDiv);
    iterator.peek().addEpisodeDetails($galleryDiv, true);
    var $rowDiv = $('<div class="gallery clearfix row"/>');
    $parent.append($rowDiv);
    for (var j = 0; j < groups.length; j++) {
      remaining -= viewfinder.view.layoutGroup_($rowDiv, groups[j], iterator, 0, (j == groups.length - 1));
      if (remaining == 0) {
        break;
      }
    }
    if (row == 0) {
      $rowDiv.appear(moreCallback, {scale: viewfinder.view.MORE_APPEAR_SCALE});
    }
    iterator.nextRow();
  }
};

/**
 * Choose templates for photo layout, selecting 'numGroups' templates
 * from TEMPLATES. Each template counts as either one or two groups,
 * depending on layout. Additional effort is expended when the number
 * of photos is small enough to cause empty groups in the layout
 * either in this row, or in the next row. If there are not enough
 * photos for the chosen layout, the layout is retried until a maximum
 * retry count is exceeded or until a perfect fit is achieved.
 *
 * There is some complexity at the point where only two rows or less
 * of layout are left. In this case, we try to avoid packing too many
 * photos into the penultimate row and instead split them roughly
 * equally.
 *
 * @param {number} numPhotos the remaining number of photos to layout.
 * @param {number} numGroups the total width in groups.
 * @param {boolean} mustFit is true if all 'numPhotos' must fit in numGroups.
 * @return a list of group templates from left to right.
 */
viewfinder.view.chooseGroups_ = function(numPhotos, numGroups, mustFit) {
  // Try a maximum number of times to fit constraints.
  // TODO(spencer): do something more elegant here.
  var avgPhotosPerRow = numGroups;
  var bestPhotoCount = 0;
  var bestGroups = null;

  for (var attempts = 0; attempts < 50; attempts++) {
    var groupCount = 0;
    var photoCount = 0;
    var groups = [];

    while (groupCount < numGroups) {
      var template = viewfinder.view.chooseGroup_();
      var countsAs = template.width;
      if (groupCount + countsAs <= numGroups) {
        groups.push(template);
        groupCount += countsAs;
        photoCount += template.photos;
      }
    }

    // Perfection!
    if (photoCount == numPhotos) {
      return groups;
    } else if (photoCount > numPhotos) {
      // If we used up all of the photos, determine whether we can
      // fill up the groups. If not, specify all double-wide
      // groups. Otherwise, retry and keep track of the best groups.
      if (numPhotos * 2 < numGroups) {
        groups = [];
        for (var i = 0; i < numPhotos; i++) {
          groups.push(viewfinder.view.FULL_TEMPLATE);
        }
        return groups;
      }
      if (bestGroups == null || photoCount < bestPhotoCount) {
        bestPhotoCount = photoCount;
        bestGroups = groups;
      }
    } else if (avgPhotosPerRow / numPhotos <= 1/3 && !mustFit) {
      return groups;
    } else if (avgPhotosPerRow / numPhotos <= 2/3 && !mustFit) {
      // If we're near the end of photos available for layout, make sure not
      // to use too many.
      numPhotos = Math.floor(numPhotos / 2);
      bestGroups = null;
    } else {
      // Best group is group with least photos in this row so we have
      // more with which to balance the next row.
      if (bestGroups == null || photoCount < bestPhotoCount) {
        bestPhotoCount = photoCount;
        bestGroups = groups;
      }
    }
  }
  return bestGroups;
};

/**
 * Templates are chosen with weighted probabilities according to the
 * 'prob' setting in each template object.
 *
 * @return {object} a template.
 */
viewfinder.view.chooseGroup_ = function() {
  var value = Math.random();
  for (var i = 0, cum_prob = 0.0; i < viewfinder.view.TEMPLATES.length; i++) {
    var template = viewfinder.view.TEMPLATES[i];
    cum_prob += template.prob;
    assert(cum_prob <= 1.0, 'cumulative probability exceeded 1.0');
    if (value < cum_prob) {
      return template;
    }
  }
  assert(false, 'not reached');
}

/**
 * Layout a group of photos according to a hierarchical layout
 * template. The layout is a nested collection of HTML '<div/>'
 * elements.
 *
 * @param {object} $parent jquery div element.
 * @param {object} group layout template.
 * @param {function} an iterator over photos.
 * @param {number} level the depth of recursion.
 * @param {boolean} last true if this is the last group in a row.
 * @return {number} count of photos added to layout.
 */
viewfinder.view.layoutGroup_ = function($parent, group, iterator, level, last) {
  if (iterator.peek() == null) {
    return 0;
  }
  var $div = $('<div class="' + group.class + (!last && level==0 ? ' r' : '') + '"/>');
  $parent.append($div);
  if (group.class.indexOf('picture') == -1) {
    // This is a layout-only div. Recurse into the group.
    var count = 0;
    for (var i = 0; i < group.children.length; i++) {
      count += viewfinder.view.layoutGroup_($div, group.children[i], iterator, level + 1, last);
    }
    return count;
  }

  var photoInfo = iterator.next();
  var $blocking = viewfinder.view.layoutFrame_($div);
  viewfinder.view.layoutPhoto_($div, $blocking, photoInfo, false);
  return 1;
};

/**
 * Layout a frame. Constructs the frame, blocking & glass html div
 * elements.
 *
 * @param {object} $parent the jQuery parent element.
 * @return {object} the blocking jQuery div, to which the photo should be appended.
 */
viewfinder.view.layoutFrame_ = function($parent) {
  var $frame = $('<div class="frame fullnest"/>').appendTo($parent);
  $('<div class="glass fullnest"/>').appendTo($frame);
  var $blocking = $('<div class="blocking fullnest"/>').appendTo($frame);
  return $blocking;
};

/**
 * Layout a photo. Constructs photo div and begins async image load.
 *
 * @param {object} $picture the overall picture jquery div element.
 * @param {object} $blocking the parent jquery div element for the photo.
 * @param {object} photoInfo object.
 * @param {boolean} loadNow true to load photo now; false to wait for it to appear.
 */
viewfinder.view.layoutPhoto_ = function($picture, $blocking, photoInfo, loadNow) {
  var $photo = $('<div class="photo"/>').appendTo($blocking);
  if (photoInfo.$img != null) {
    viewfinder.view.layoutImage_($photo, photoInfo.$img);
    photoInfo.addPhotoDetails($picture);
    photoInfo.layoutCallback(photoInfo.$img);
  } else {
    // Set 'loading' as class of enclosing div.
    $photo.addClass('loading');
    var showFunc = function() {
      // Create new image object, set url & handle on-load.
      var $img = $(new Image());
      $img.load(function() {
        $img.origWidth = $(this)[0].width;
        $img.origHeight = $(this)[0].height;
        $photo.removeClass('loading');
        viewfinder.view.layoutImage_($photo, $img);
        photoInfo.addPhotoDetails($picture);
        photoInfo.layoutCallback($img);
      }).addClass('img').attr('src', photoInfo.getFullUrl());
    };
    if (loadNow) {
      showFunc();
    } else {
      $photo.appear(showFunc, {scale: viewfinder.view.PHOTO_APPEAR_SCALE});
    }
  }
  return $photo;
};

/**
 * Adds the image to the parent element then scales and appropriately
 * centers the content.
 *
 * @param {string} $photo is the photo div element that will contain the image.
 * @param {object} $img the jquery image element.
 */
viewfinder.view.layoutImage_ = function($photo, $img) {
  var width = $photo.width() == 0 ? $img.origWidth : $photo.width();
  var height = $photo.height() == 0 ? $img.origHeight : $photo.height();
  $img.css(viewfinder.util.computeImageXYWH(width, height, $img));
  $photo.append($img);
};
