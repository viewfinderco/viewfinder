// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview Implementation of K-nearest means for geographic
 *               coordinates.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.k_nearest_means = {};
viewfinder.k_nearest_means.THRESHOLD_DISTANCE = 25000;  // 25km

/**
 * A cluster of episodes. Contains an array of episodes and a cluster
 * location & placemark. The location of the cluster is simply the
 * location of the episode which is closest to the cluster's geographic
 * centroid.
 *
 * If no episode in the cluster has a location, location_ and placemark_
 * will be null.
 */
function EpisodeCluster(episodes) {
  this.episodes_ = episodes;
  this.centroid_ = viewfinder.k_nearest_means.ComputeCentroid_(episodes);
  var episode = viewfinder.k_nearest_means.FindNearest(this.centroid_, episodes);
  if (episode) {
    this.location_ = episode.location_;
    this.placemark_ = episode.placemark_;
  } else {
    this.location_ = null;
    this.placemark_ = null;
  }
}
EpisodeCluster.prototype.constructor = EpisodeCluster;

//EpisodeCluster.prototype.show = function(mask, callback, click_func) {


/**
 * A geographic centroid is computed for each micro-episode by
 * consulting the available photos. The location of the episode itself
 * is used if no locations are available on the photos in the episode's
 * photoArray_ (this is augmented server-side as photos are posted to
 * the episode). If no location can be determined whatsoever for an
 * episode, it is not used in the algorithm.
 *
 * Splits the supplied episodes into clusters. The episodes within each
 * cluster must be no more than THRESHOLD_DISTANCE meters away from
 * the cluster centroid. No episode may be within THRESHOLD_DISTANCE
 * meters of any cluster except the one it's been assigned to.
 *
 * The common case is a single cluster. There can be at most N clusters,
 * where N is the number of episodes. After all episodes with determinable
 * locations have been clustered, the remaining episodes are clustered
 * according to the following algorithm:
 *
 *   - If the user_id of the episode matches the user id of a clustered
 *     episode, then the episode is clustered with the most
 *     temporally-proximate episode from the same user id.
 *   - Otherwise, the episode is added to an "unlocated" cluster.
 *
 * Returns an array of episode clusters, sorted by the timestamp of the
 * earliest-occuring episode of each cluster.
 *
 * @param {array} episodes is an array of episodes to cluster.
 * @return {array} clusters is an array of episode clusters.
 */
viewfinder.util.computeKNearestMeans = function(episodes) {
  var clusters = [];
  return clusters;
};


/**
 * Find the centroid for a group of episodes by averaging the latitudes
 * and longitudes of each episode with location defined. If no episodes
 * have location defined, return null.
 */
viewfinder.k_nearest_means.ComputeCentroid_ = function(episodes) {
};


/**
 * Find the nearest episode to the specified 'centroid'. Returns null
 * if there are no episodes with locations or if centroid is null.
 */
viewfinder.k_nearest_means.FindNearest_ = function(centroid, episodes) {
  if (!centroid) {
    return null;
  }
  var nearest = null;
  episodes.forEach(function(ep) {
    console.log(ep);
  });
  return nearest;
};


