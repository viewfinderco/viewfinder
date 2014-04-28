// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview Model structures for Viewfinder website.
 *
 * @author matt@emailscrubbed.com (Matt Tracy)
 */

/** @namespace */
viewfinder.models = {};

(function($, namespace){ 
  
  // **********************************************************************************************
  //                            ABSTRACT MODELS AND COLLECTIONS
  // **********************************************************************************************

  /**
   * Base model type for Viewfinder data objects.  Extends the basic backbone model with methods
   * that support the viewfinder data model.
   * 
   * @private
   * @class
   */
  var ViewfinderDataModel = Backbone.Model.extend(/** @lends ViewfinderDataModel */{
    /**
     * Prunes keys from the given object which are not relevant to this specific model. 
     * The list of relevant keys is white-listed via the 'metadataKeys' attribute of a model.
     * 
     * @param {metadata} Object to be pruned.  The original object will not be modified.
     * @returns A new object cloned from the original, but with any irrelevant  keys removed.
     */
    pickMetadata : function (metadata) {
      return this.metadataKeys ? _(metadata).pick(this.metadataKeys) : metadata;
    },
    
    /**
     * Retrieve the current metadata scope for this object.
     * 
     * @returns {ViewfinderScope} A scope object.
     */
    scope : function () {
      return this.collection.scope();
    },
    
    /**
     * Returns true if this object is a placeholder.  Placeholders are created when one
     * object is referenced by another, but the referenced object has not yet been loaded
     * from the server.
     */
    isPlaceholder : function () {
      return this._placeholder || false;
    },

    // Private method to clear a placeholder flag.
    _clearPlaceholder : function () {
      this._placeholder = null;
    },

    // Helper function - 'forwards' common events from a child collection by triggering
    // an event on the parent.
    _forwardCollectionEvents : function (collection, modelName) {
      collection.on('change', function (model) {
        this.trigger('change:' + modelName, this, model);
      }, this);

      collection.on('add', function (model) {
        this.trigger('add:' + modelName, this, model);
      }, this);
    },

    // Forwards a single event from another object by triggering the same event on
    // this object.
    _forwardEvent : function (source, event, forwardEvent) {
      forwardEvent = forwardEvent || event;
      source.on(event, function (model) {
        this.trigger(forwardEvent, this, model);
      }, this);
    },

    /**
     * Override of backbone's built in sync() method.  Since viewfinder does  not use the sync
     * functionality, it is a n-op.
     */
    sync : function () {}
  });
  

  /**
   * Extension of ViewfinderDataModel for data objects which have an associated parent.
   * 
   * @private
   * @extends ChildDataModel
   * @class
   */
  var ChildDataModel = ViewfinderDataModel.extend(/** @lends ChildDataModel */{
    /**
     * Retrieves the id of an object's parent.
     * 
     * @returns the unique id of this object's parent.
     */
    parentId : function () {
      return this.parentIdAttribute ? this.get(this.parentIdAttribute) : undefined;
    }
  });


  /**
   * Base data collection for viewfinder collection objects.  Extends the basic collection
   * type with methods that support the viewfinder data model.
   * 
   * @private
   * @class
   */
  var ViewfinderDataCollection = Backbone.Collection.extend(/** @lends ViewfinderDataCollection */ {
    /**
     * Based on a metadata object, either create a new model in this collection
     * or update the existing object which matches the metadata.  An existing
     * model is matched if it shares the same idAttribute value as the metadata.
     * 
     * @param {Object} metadata An object describing the properties of a model in this collection.
     * @returns {ViewfinderDataModel} The model which was either created or updated.
     */
    createOrUpdate : function (metadata) { 
      var m = this.get(metadata[this.model.prototype.idAttribute]);
      if (_.has(this.model.prototype, 'metadataKeys')) {
        metadata = this.model.prototype.pickMetadata(metadata);
      }
      
      if (m) {
        m.set(metadata);
        m.save();
      } else {
        m = this.create(metadata);
      }
      
      return m;
    },
    
    /**
     * Gets the object with the given Id from this collection if it exists.  If it does
     * not exist, creates that object using the given default metadata and returns it.
     * 
     * @param {String} id The id of the object to retrieve or create.
     * @param {Object} defaultMetadata Default metadata to apply to the object.  Note that this metadata
     *   should not include the id attribute for the model type of this collection - that property
     *   will be automatically set.
     * 
     * @returns {viewfinderDataModel} The model which was either created or retrieved.
     */
    setDefault : function (id, defaultMetadata) {
      var obj = this.get(id);
      if (!obj) {
        defaultMetadata = defaultMetadata || {};
        defaultMetadata[this.model.prototype.idAttribute] = id;
        obj = this.createOrUpdate(defaultMetadata);
      }
      
      return obj;
    },
    
    /**
     * Gets the object with the given id in this collection, if it exists.  If it does not
     * exist, create a placeholder object with the given id.  The placeholder object's isPlaceholder()
     * method will return true - it will become a 'real' object as soon as any metadata is updated.
     *
     * Placeholders are needed when one object from the server has a peer-level reference to
     * another object which is not yet loaded - for example, an activity referencing an episode.
     */
    getPlaceholder : function (id, defaultMetadata) {
      var obj = this.get(id);
      if (!obj) {
        defaultMetadata = defaultMetadata || {};
        defaultMetadata[this.model.prototype.idAttribute] = id;
        obj = this.create(defaultMetadata);
        obj._placeholder = true;
        obj.once('change', obj._clearPlaceholder, obj);
      }
      
      return obj;
    },
  
    /**
     * Retrieve the current metadata scope for this object.
     * 
     * @returns A scope object.
     */
    scope : function () {
      return this._scope;
    },
    
    /**
     * Method called when this collection is added to a metadata scope.  Intended to be overridden
     * in derived classes.
     */
    onScope : function (scope) {},
    
    sync : function () {}
  });
  
  
  /**
   * Base data collection for viewfinder collections for which the underlying
   * models have an associated parent object.  Designed to be encapsulated by
   * the model for the parent object.
   * 
   * @private
   * @extends ViewfinderDataCollection
   * @class
   */
  var ChildDataCollection = ViewfinderDataCollection.extend(
  /** @lends ChildDataCollection */
  {    
    /**
     * Initialization function - derives comparator field from the model.
     */
    initialize : function (models, options) {
      this.parent = options.parent;
    },

    /**
     * Child data collections just inherit their parent's scope.
     */
    scope : function () {
      return this.parent.scope();
    }
  });
  
  // **********************************************************************************************
  //                                    MODEL TYPES
  // **********************************************************************************************
  
  function getLocationFromPlacemark(placemark) {
     var parts = [];
     if (placemark) {
       !placemark.locality || parts.push(placemark.locality);
       !placemark.state || parts.push(placemark.state);
       parts.length == 2 || !placemark.country || parts.push(placemark.country);
     }
     
     if (parts.length > 0) {
       return parts.join(', ');
     }
     
     return null;
  }


  /**
   * Photo model - represents an individual photo.  In addition to server metadata, provides
   * insight into whether the image is in the user's local cache or not.
   * 
   * @memberOf viewfinder.models
   * @extends ViewfinderDataModel
   * @class
   */
  var PhotoModel = namespace.PhotoModel = ViewfinderDataModel.extend(/** @lends PhotoModel */{
    idAttribute : 'photo_id',
    
    // Unique object value to represent missing images.
    MISSING_IMAGE : {},
    
    metadataKeys : [
      'photo_id', 'user_id', 'timestamp', 'aspect_ratio', 'location', 
      'placemark', 'caption', 'parent_id', 'full_get_url', 'med_get_url', 'tn_get_url'
    ],
    
    defaults : {
      cached_full : null,
      cached_med : null,
      cached_tn : null
    },
    
    cached : function (size) {
      var prop = 'cached_' + size;
      var value = this.get(prop);
      if (!value || value === this.MISSING_IMAGE) return value;
      return value.cloneNode();
    },
    
    loadImage : function (size) {
      var photo = this; 
      if (photo.cached(size)) return;
      if (this['_loading' + size]) return;  // Send maximum one request per image.
      
      // Create a list of potential URLs from which to load the image.  
      var urls = [];
      
      // Start with a cached URL for this photo.  Urls are signed, and therefore vary for the same image 
      // between page loads.  To utilize the clients image cache, we cache signed URLs in local storage.
      // When loading the same image in a later browser session, we can thus use an older URL which has
      // already been cached.
      if (!this._static) {
        var cachedUrl = this._cacheUrl(size);
        if (cachedUrl) urls.push(cachedUrl);
      }
      
      // * Second is the signed URL for the preferred size.
      urls.push(this.get(size + '_get_url'));
      
      // * Lastly, signed URLs for any alternate acceptable size if the preferred size is missing.
      if (size === 'med') {
        urls.push(this.get('full_get_url'));
      }
      
      // Attempt to load the image from the first URL that gives a valid response.
      this['_loading' + size] = true;
      photo = this;
      this._loadImageHelper(size, urls).done(function (image) {
        if (!image) image = photo.MISSING_IMAGE;
        photo.set('cached_' + size, image);
        photo['_loading' + size] = false;
      });
    },

    getLocationString : function () {
      var location = getLocationFromPlacemark(this.get('placemark'));
      return location || 'Location Unknown';
    },

    // Private function - helps load and cache an image from a set of urls.
    _loadImageHelper : function (size, urls) {
      var deferred = $.Deferred();
      var piped = deferred;
      var photo = this;
      
      // Create a piped promise which will resolve with the
      // first image to properly load, or null if all image urls fail.
      _(urls).each(function (url) {
        piped = piped.pipe(function (image) {
          if (image) return image;
          
          var innerDeferred = $.Deferred();
          var img = new Image();
          img.src = url;
          img.onload = function () {
            photo._cacheUrl(size, url);
            innerDeferred.resolve(img);
          };
          img.onerror = function () {
            innerDeferred.resolve(null);
          };
          
          return innerDeferred;
        });
      });
      
      // Start the pipe.
      deferred.resolve(null);
      return piped;
    },

    // Private function - gets or sets a cached photo URL from local storage.
    _cacheUrl : function (size, url) {
      if (this._static) return null;
      if (!localStorage.getItem) return null;
      
      var storageKey = this.get('photo_id') + '.' + size;
      if (_.isUndefined(url)) return localStorage.getItem(storageKey);
      
      try {
        localStorage.setItem(storageKey, url);
      } catch (e) {
        if (e === QUOTA_EXCEEDED_ERR) {
          localStorage.clear();
          localStorage.setItem(storageKey, url);
        }
      }  

      return null;
    }
  } , {
    createStatic : function (url, med_url) {
      var photo = new this({
        full_get_url : url,
        med_get_url : med_url || url
      });
      
      photo._static = true;
      return photo;
    }
  });  


  /**
   * Collection of photos.
   * 
   * @memberOf viewfinder.models
   * @extends ViewfinderDataCollection     
   * @class
   */
  var PhotoCollection = namespace.PhotoCollection = ViewfinderDataCollection.extend({
    model : PhotoModel
  });
  

  /**
   * User model - represents a single user in the Viewfinder system.
   * 
   * @memberOf viewfinder.models
   * @extends ViewfinderDataModel
   * @class
   */
  var UserModel = namespace.UserModel = ViewfinderDataModel.extend(/** @lends UserModel */{
    idAttribute: 'user_id',
    
    metadataKeys : [
      'user_id', 'name', 'email', 'given_name', 'last_name', 'picture', 'labels', 'merged_with'
    ],
    
    /**
     * Retrieves the display name for this User.  This is based on the information in
     * the user model, but may be overridden by contact data.
     * 
     * @returns {String} The display name.
     */
    getDisplayName : function (firstOnly) {
      if (this.get('merged_with')) {
        var newUser = this.collection.getPlaceholder(this.get('merged_with'));
        return newUser.getDisplayName(firstOnly);
      }

      if (this.get('user_id') === viewfinder.own_user.user_id) return 'You';
      if (this.isPlaceholder()) return 'User #' + this.id;
      if (firstOnly) return this.get('given_name') || this.get('email') || '(Pending Invite)';
      return this.get('name') || this.get('email') || '(Pending Invite)';
    },
    
    /**
     * Retrieves the user's full name, without display optimizations (such as using only
     * the first name, or replacing the logged-in user's name with 'You'.
     */
    getFullName : function () {
      if (this.isPlaceholder()) return "User #" + this.id;
      return this.get('name') || this.get('email') || '(Pending Invite)';
    },
    
    isActive : function () {
      var labels = this.get('labels');
      return !labels || !_(labels).contains('terminated');
    }
  });


  /**
   * Collection of users.
   * 
   * @memberOf viewfinder.models
   * @extends ViewfinderDataCollection     
   * @class
   */
  var UserCollection = namespace.UserCollection = ViewfinderDataCollection.extend({
    model : UserModel
   });  


  /**
   * Photo post model - associates a photo with a specific episode.  Each post is the child
   * of a single episode.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataModel
   * @class
   */
  var PostModel = namespace.PostModel = ChildDataModel.extend(/** @lends PostModel */{
    idAttribute : 'post_id',
    
    metadataKeys : ['post_id', 'photo_id', 'episode_id', 'labels' ],
    
    getPhoto : function () {
      return this.scope().photos.getPlaceholder(this.get('photo_id'));     
    },

    isDisplayable : function (share_timestamp) {
      var labels = this.get('labels');
      
      // If post has the 'Removed' label, then post is not displayable.
      if (labels && _(labels).contains('removed')) return false;
     
      // If post has been unshared and reshared, only display if this share is more recent than the
      // last unshare.
      var last_unshare_timestamp = this.get('last_unshare_timestamp');
      return !last_unshare_timestamp || 
        (share_timestamp == true) || 
        share_timestamp > last_unshare_timestamp;
    }
  });


  /**
   * Collection of posts.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataCollection     
   * @class
   */
  var PostCollection = namespace.PostCollection = ChildDataCollection.extend({
    model: PostModel,

    getDisplayablePosts : function (share_timestamp) {
      return this.filter(function (post) {
        return post.isDisplayable(share_timestamp);
      });
    },
    
    getDisplayablePhotos : function (share_timestamp) {
      return _(this.getDisplayablePosts(share_timestamp)).map(function (post) {
        return post.getPhoto();
      });
    }
  });


  /**
   * Episode model - represents a single viewfinder episode.  Each episode is the child
   * of a single viewpoint.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataModel
   * @class
   */
  var EpisodeModel = namespace.EpisodeModel = ViewfinderDataModel.extend(/** @lends EpisodeModel */{
    idAttribute : 'episode_id',
    
    metadataKeys : [
      'episode_id', 'viewpoint_id', 'labels', 'user_id', 'timestamp', 
      'title', 'description', 'location', 'placemark'
    ],

    initialize : function () {
      this.posts = new PostCollection([], { parent : this });
    },
    
    /**
     * Retrieves a properly formatted location string for this episode.
     * 
     * @returns {String}
     */
    getLocationString: function () {
      var location = getLocationFromPlacemark(this.get('placemark'));
      return location || "Unknown";
    },
        
    /**
     * Gets the user who posted this activity. 
     * 
     * @returns {UserModel} Model for the posting user.
     */
    getUser : function () {
      return this.scope().users.getPlaceholder(this.get('user_id'));
    }
  });


  /**
   * Collection of episodes.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataCollection     
   * @class
   */
  var EpisodeCollection = namespace.EpisodeCollection = ViewfinderDataCollection.extend({
    model : EpisodeModel
  }); 
  
  
  /**
   * Follower model - associates a viewfinder user with a viewpoint.  Each follower is the
   *  child of a single viewpoint.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataModel
   * @class
   */
  var FollowerModel = namespace.FollowerModel = ChildDataModel.extend(/** @lends FollowerModel */{
    idAttribute : 'follower_id',
    
    metadataKeys : [
      'follower_id', 'viewpoint_id', 'user_id'
    ], 

    initialize : function () {
      var user = this.getUser();
      this._forwardEvent(user, 'change', 'change:user');
    },
   
    /**
     * Retrieve the user associated with this follower.
     * 
     * @returns {UserModel} The associated user.
     */
    getUser : function () {
      return this.scope().users.getPlaceholder(this.get('user_id'));
    }
  });
 

  /**
   * Collection of followers.  A follower is a many-to-many association between viewpoints and users.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataCollection     
   * @class
   */
  var FollowerCollection = namespace.FollowerCollection = ChildDataCollection.extend({
    model : FollowerModel,

    getActiveUsers : function () {
      return this.chain()
        .map(function (f) {
          return f.getUser();
        })
        .filter(function (u) {
          return u.isActive();
        })
        .value();
    }
  });

 
  /**
   * Comment model - represents a single viewfinder comment.  Each comment is the child
   * of a single viewpoint.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataModel
   * @class
   */
  var CommentModel = namespace.CommentModel = ChildDataModel.extend(/** @lends CommentModel */{
    idAttribute : 'comment_id',
    
    metadataKeys : [
      'viewpoint_id', 'comment_id', 'asset_id', 'timestamp', 'message', 'user_id'
    ],

    /**
     * Retrieve the user who posted this comment.
     * 
     * @returns {UserModel} The posting user.
     */
    getUser : function () {
      return this.scope().users.getPlaceholder(this.get('user_id'));
    },
    
    /**
     * Retrive the highlighted photo for this comment, if any exists.
     */
    getHighlightPhoto : function () {
      var assetId = this.get('asset_id');
      if (!assetId) return undefined;
      return this.scope().photos.getPlaceholder(assetId);
    }
  });
  

  /**
   * Collection of comments.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataCollection     
   * @class
   */
  var CommentCollection = namespace.CommentCollection = ChildDataCollection.extend({
    model : CommentModel
  });

  
  /**
   * Activity model - represents a single viewfinder activity.  Each activity is the child
   * of a single viewpoint.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataModel
   * @class
   */
  var ActivityModel = namespace.ActivityModel = ChildDataModel.extend(/** @lends ActivityModel */{
    idAttribute : 'activity_id',
    
    metadataKeys : [
      'activity_id', 'viewpoint_id', 'timestamp', 'user_id', 'update_seq', 'type', 'properties'
    ],

    initialize : function () {
      var comment = this.getComment();
      if (comment) {
        this._forwardEvent(comment, 'change', 'change:comment');
      }

      var user = this.getPostingUser();
      this._forwardEvent(user, 'change', 'change:user');

      var episodes = this.getSharedEpisodes();
      if (episodes) {
        var i = 0;
        var type = this.get('type');
        if (type !== 'unshare') {
          for (i = 0; i < episodes.length; i++) {
            this._forwardEvent(episodes[i].episode.posts, 'add', 'add:post');
            this._forwardEvent(episodes[i].episode.posts, 'change', 'change:post');
            this._forwardEvent(episodes[i].episode, 'change', 'change:episode');
          }
        } else {
          // If a photo is reshared after unsharing it from a viewpoint, multiple activities 
          // will reference the same episode and post, and the post will no longer have an unshared
          // label.
          // In order to prevent photos that are reshared from being duplicated, we need
          // to move information about Unshares activities directly onto the posts they effect.
          var unshare_timestamp = this.get('timestamp');
          for (i = 0; i < episodes.length; i++) {
            var episode = episodes[i].episode;
            var photo_ids = episodes[i].photos;
            for (var j = 0; j < photo_ids.length; j++) {
              var post_id = episode.id + '+' + photo_ids[j];
              var post = episode.posts.getPlaceholder(post_id);
              var last_unshare_timestamp = post.get('last_unshare_timestamp');
              if (!last_unshare_timestamp || unshare_timestamp > last_unshare_timestamp) {
                post.set({
                  episode_id : episode.id,
                  last_unshare_timestamp : unshare_timestamp
                });
              }
            }
          }
        }
      }
    },

    /**
     * Gets the user who posted this activity. 
     * 
     * @returns {UserModel} Model for the posting user.
     */
    getPostingUser : function () {
      return this.scope().users.getPlaceholder(this.get('user_id'));
    },
    
    /**
     * If this activity shares episodes, returns the metadata related to those shares. 
     * 
     * @returns {Object[] | null} An array of objects each containing an episode and a list
     * of photo ids - the activity may only reference a subset of photos from an episode.
     * Returns null if no episodes were shared by this activity.
     */
    getSharedEpisodes : function () {
      var episodeData = null;
      var type = this.get('type');
      if (type === 'share_new' || type === 'share_existing' || type === 'unshare') {
        episodeData = this.get('properties').episodes;
      } else if (type === 'upload_episode') {
        episodeData = [this.get('properties')];
      } else {
        return null;
      }
  
      var activity = this;
      var viewpoint_id = this.get('viewpoint_id');
      var episodes = activity.scope().episodes;
      
      // Sharing photos from multiple episodes in one activity is allowed.
      return _(episodeData).map(function (ed) {
        // Because the activity can be received before the episodes it references, use getPlaceholder
        // in order to create an empty episode model.  This will allow views or materialized models
        // to subscribe to events for that episode.
        var episode = episodes.getPlaceholder(ed.episode_id);
        return { episode: episode, photos: ed.photo_ids };
      });
    },
    
    getPhotoCount : function () {
      var count = 0;
      this.visitPhotos(function (ep, photo) { count += 1; });
      return count;
    },

    getSharedPhotos : function () {
      var photos = [];
      this.visitPhotos(function (episode, photo) {
        photos.push(photo);
      });

      return photos;
    },

    getLocationString : function () {
      var episodeToLocation = {};
      var locationToCount = {};
      this.visitPhotos(function (ep, photo) {
        if (!episodeToLocation[ep.id]) {
          episodeToLocation[ep.id] = ep.getLocationString();
        }
        
        var location = episodeToLocation[ep.id];

        if (!locationToCount[location]) {
          locationToCount[location] = 1;
        } else {
          locationToCount[location] += 1;
        }
      });

      var locationCount = _(locationToCount).keys().length;
      if (locationCount  === 0) {
        // We shouldn't be calling this if there are no shared episodes.
        return undefined;
      } else if (locationCount === 1) {
        var location = _(episodeToLocation).values()[0];
        if (location === 'Unknown') {
          return 'Shared ' + locationToCount[location] + ' photos without location.';
        } else {
          return location;
        }
      } else {
        // Use the known location with the most photos.
        var primary = _(locationToCount).chain()
              .keys()
              .reject(function (loc) {
                return loc === 'Unknown';
              })
              .max(function (loc) {
                return locationToCount[loc];
              })
              .value();
        
        return [primary, 'and', locationCount - 1, locationCount > 2 ? 'other locations.' : 'other location.'].join(' ');
      }
    },

    // Visit photos from this episode which are currently visible.  This is complicated
    // because we have to check the post record to see if a photo has been unshared.
    visitPhotos : function (visitor) {
      var eps = this.getSharedEpisodes();
      if (eps) {
        for (var i = 0; i < eps.length; i++) {
          var ep = eps[i].episode;
          var photos = eps[i].photos;
          var epPhotos = ep.posts.getDisplayablePhotos(this.get('timestamp'));
          for (var j = 0; j < epPhotos.length; j++) {
            // Filter full list of photos from episode.
            if (_(photos).contains(epPhotos[j].id)) {
              var stop = visitor(ep, epPhotos[j], this);
              if (stop) {
                return;
              }
            }
          }
        }
      }
    },
    
    /**
     * If this activity posts a comment, retrieve the model for that comment. 
     * 
     * @returns {CommentModel | undefined} A comment model, or undefined if no comment was posted by this activity.
     */
    getComment : function () {
      if (this.get('type') !== 'post_comment') {
        return undefined;
      }
      
      var cid = this.get('properties').comment_id;

      // Because the activity can be received before the comment to which it refers, use getPlaceholder
      // in order to create an empty comment model. 
      return this.collection.parent.comments.getPlaceholder(cid);      
    },

    getViewpoint : function () {
      return this.collection.parent;
    },
    
    /**
     * If this is an "add followers" activity, returns the user models for the followers who
     * were added.  Returns undefined otherwise.
     * 
     * @returns {UserModel[] | undefined}
     */
    getAddedFollowers : function () {
      if (this.get('type') !== 'add_followers') {
        return undefined;
      }
      
      var activity = this;
      return _(activity.get('properties').follower_ids).map(function (fid) {
        return activity.scope().users.getPlaceholder(fid);
      });
    },

    // Return true if the user has previously viewed this activity.
    isViewed : function () {
      // Local web view is always viewed.
      return true;
      // var viewed = this.getViewpoint().get('viewed_seq');
      // var update = this.get('update_seq');
      // return viewed >= update;
    }
  },/** @lends ActivityModel */{
    /**
     * Array of possible activity types.
     * 
     * @static
     * @field
     */
    activityTypes : [
      'add_followers', 'post_comment', 'share_existing', 'share_new', 'upload_episode', 'unshare', 
      'update_episode', 'update_viewpoint', 'merge_accounts'
    ],
    
    /**
     * Activity metadata from the server is in an odd format in order to support server-side
     * JSON validation.  To better work with the data, we will convert the data before using it.
     * 
     * @static
     * @param {Object} serverActivityMetadata original activity metadata recieved from the server.
     * @returns {Object} An object with the converted data.
     */
    convertServerJson : function (serverActivityMetadata) {
      var converted = _(serverActivityMetadata).pick(this.prototype.metadataKeys);
      var type = _(this.activityTypes).find(function (at) { return at in serverActivityMetadata; });
      converted.type = type;
      converted.properties = serverActivityMetadata[type];
      return converted;
    }
  });

  
  /**
   * Collection of activities.
   * 
   * @memberOf viewfinder.models
   * @extends ChildDataCollection     
   * @class
   */
  var ActivityCollection = namespace.ActivityCollection = ChildDataCollection.extend({
    model : ActivityModel,

    comparator : 'timestamp'
  }); 
 
 
  /**
   * Viewpoint model - represents a single viewfinder viewpoint.
   * 
   * @memberOf viewfinder.models
   * @extends ViewfinderDataModel
   * @class
   */
  var ViewpointModel = namespace.ViewpointModel = ViewfinderDataModel.extend({
    idAttribute : 'viewpoint_id',
    
    metadataKeys : [
      'viewpoint_id', 'title', 'description', 'name', 'labels', 'cover_photo',
      'viewed_seq', 'type', 'user_id', 'update_seq', 'sharing_user_id', 'last_updated', 'folder_name'
    ],

    initialize : function () {
      this.followers = new FollowerCollection([], { parent : this });
      this.comments = new CommentCollection([], { parent : this });
      this.activities = new ActivityCollection([], { parent : this });
      this.activities.on('add', this.checkLastUpdateTime, this);
    },

    // Indicate that new content for this viewpoint has been viewed.  This is not done
    // piecemeal - it is assumed that all new content is viewed at once.
    setViewed : function () {
      var update_seq = this.get('update_seq');
      var viewed_seq = this.get('viewed_seq');
      if (update_seq > viewed_seq) {
        this.set('viewed_seq', update_seq);
        if (viewfinder.flags.isRegistered) {
          this.scope().net.updatedViewedSeq(this.id, update_seq);
        }
      }
    },
    
    // Return true if all activities in this conversation have been viewed.
    isViewed : function () {
      // Local web view is always viewed.
      return true;

      // return this.get('viewed_seq') === this.get('update_seq');
    },

    // Called when user action from the web results in incrementing the update sequence
    // of the conversation.  Increment update_seq, set viewed_seq to update_seq, and
    // return the new update_seq.
    addedUpdate : function () {
      var newseq = this.get('update_seq') + 1;
      this.set({
        update_seq : newseq, 
        viewed_seq : newseq
      });

      return newseq;
    },
    
    checkLastUpdateTime : function (timestamp_obj) {
      var activityTime = _.isNumber(timestamp_obj) ? timestamp_obj : timestamp_obj.get('timestamp');
      if (this.get('last_updated') < activityTime) {
        this.set('last_updated' , activityTime);
      }
    },
        
    getCoverPhoto : function () {
      var cover = this.get('cover_photo');
      if (!cover || !cover.photo_id) return null;
      
      // Cover photos contain enough information to display at a fixed aspect ratio.
      // Therefore, we do not need to get a placeholder.
      return this.scope().photos.setDefault(cover.photo_id, cover);
    },

    getTitle : function () {
      var title = this.get('title');
      if (!title) {
        // Attempt to synthesize a title based on the sender and location of initial share.
        // TODO(matt): This belongs in the view, but i'm not sure the best place to put it there
        // so I'm putting it here for the sake of the schedule.
        var initialActivity = this.activities.find(function (a) {
          return a.get('type') === 'share_new';
        });

        if (initialActivity) {
          var episodes = initialActivity.getSharedEpisodes();
          if (episodes.length > 0) {
            var location = episodes[0].episode.getLocationString();
            var senderName = initialActivity.getPostingUser().getDisplayName(true);
            
            title = senderName + ' shared photos from ';
            if (location !== 'Unknown') {
              title += location;
            } else {
              // use date of first photo instead of place for unknown location.
              var phototime = null;
              initialActivity.visitPhotos(function (ep, photo) {
                phototime = photo.get('timestamp');
                return true;
              });

              title += viewfinder.util.dateDiffString(new Date(phototime * 1000));
            }
          }
        }
      }

      return title || 'Untitled Conversation';
    },

    getPhotoCount : function () {
      return _(this.activities.models).sum(function (a) {
        return a.getPhotoCount();
      });
    },

    getCommentCount : function () {
      return _(this.activities.models).filter(function (a) {
        return a.get('type') == 'post_comment';
      }).length;
    },
    
    isRemoved : function () {
      var labels = this.get('labels');
      return labels && _(labels).contains('removed');  
    },
    
    // Find the first activity, if any, in which the given photo is posted.
    findActivity : function (photo) {
      var activity = null;
      for (var i = 0; i < this.activities.length; i++) {
        var thisActivity = this.activities.at(i);
        thisActivity.visitPhotos(function (ep, p) {
          if (p === photo) {
            activity = thisActivity;
            return true;
          }

          return false;
        });

        if (activity) {
          break;
        }
      }

      return activity;
    },

    loaded : function (newValue) {
      if (_.isUndefined(newValue)) {
        return this.get('loaded');
      }
      
      this.set('loaded', newValue);
      return null;
    }
  });

  
  /**
   * Collection of viewpoints.
   * 
   * @memberOf viewfinder.models
   * @extends ViewfinderDataCollection     
   * @class
   */
  var ViewpointCollection = namespace.ViewpointCollection = ViewfinderDataCollection.extend({
    model : ViewpointModel,

    initialize : function () {
      this.on('change:last_updated', this.doSort, this);
    },

    doSort : function () {
      this.sort();
    },

    getActive : function () {
      return this.filter(function (vp) {
        return !vp.isRemoved();
      });
    },

    unviewedCount : function () {
      return this.filter(function (vp) {
        return !vp.isViewed();
      }).length;
    },

    comparator : 'last_updated'
  }); 
    
  // **********************************************************************************************
  //                                    NETWORK MODEL
  // **********************************************************************************************
  
  // Class to collapse invalidations.  Multiple invalidations for a single ID will collapse into a single
  // invalidation which contains the union of all requests.
  var InvalidationCollector = function (idAttribute) {
    this.idAttribute = idAttribute;
    this.invalidations = {};
  };
  
  _.extend(InvalidationCollector.prototype, {
    // Utility to add an array of invalidations into the collector.
    addRange : function (invalidations) {
      var collector = this;
      _(invalidations).each(function (i) {
        collector.add(i);
      });
    },
    
    // Add a single invalidation to the collection.  Invalidations are collapsed additively - 
    // each invalidation may request certain data for an object via attributes of the form 'get_[data] : true'.
    // Multiple invalidations for the same object can be combined by combining these attributes in a single
    // object.
    //
    // Some invalidations also have a 'start_key' property - however, only the invalidations with the lowest
    // 'start_key' value for a given object needs to be processed.
    add : function (invalidation) {
      // If the collection has no idAttribute, then all invalidations are collapsed into one.
      var id = this.idAttribute ? invalidation[this.idAttribute] : 'singleton';
      
      if (id in this.invalidations) {
        // Get the existing invalidation for this object from the collection.
        var existing = this.invalidations[id];
        
        // Iterate through each attribute in the invalidation being added.
        _.chain(invalidation).keys().each(function (key) {
          if (key.startsWith('get_')) {
            // For attributes of the form 'get_[data]', add them to the existing invalidation unless
            // that attribute was already present.
            existing[key] = existing[key] || invalidation[key];
          } else if (key.endsWith('start_key')) {
            // For start_key attributes, overwrite the existing start_key if the new invalidation's 
            // start_key is lower.
            if (!existing[key] || invalidation[key] < existing[key]) {
              existing[key] = invalidation[key];
            }
          }
        });
      } else {
        this.invalidations[id] = invalidation;
      }
    },
    
    // Get the list of collapsed invalidations.  If an id is specified, return only the
    // invalidation for that single id (or undefined if the id is not in the collection).
    get : function (id) {
      if (id) {
        return this.invalidations[id];
      }
      
      return _(this.invalidations).values();
    },
    
    length : function () {
      return this.get().length;
    },
    
    clear : function (id) {
      if (id) {
        delete this.invalidations[id];
      } else {
        this.invalidations = {};
      }
    }
  }); 

  // Class to manage the automatic polling for notifications.  Provides a polling interval
  // with backoff, as well as a user idle timer to stop polling if the user is idle.
  var NotificationPoller = namespace.NotificationPoller = function (networkModel) {
    this.net = networkModel;
  };

  _.extend(NotificationPoller.prototype, {
    INITIAL_INTERVAL : 5000,

    MAX_INTERVAL : 60000,

    IDLE_TIME_MINS : 10,

    start : function () {
      this.running = true;
      this.idleTime = 0;
      this.queryInterval = 0;

      // Start an idleTimer.
      var poll = this;
      this.idleInterval = setInterval(function () {
        poll.idleTime = poll.idleTime + 1;
      }, 60000);

      // Start polling for notifications.
      this.pollNotifications();
    },
    
    stop : function () {
      this.running = false;
      this.wakeEvent = null;
      if (this.idleInterval) {
        clearInterval(this.idleInterval);
      }

      if (this.queryTimeout) {
        clearTimeout(this.queryTimeout);
      }
    },

    reset : function () {
      this.stop();
      this.start();
    },

    // Should be called whenever user activity is detected to reset
    // the idle timer.
    userAction : function () {
      // Reset idleTime to zero.  This will race a bit with the idle interval,
      // but this timer does not need to be exact at all.
      this.idleTime = 0;

      if (this.wakeEvent) {
        // If a wake event is set, run it and clear it.
        this.wakeEvent();
        this.wakeEvent = null;
      }
    },

    pollNotifications : function () {
      if (!this.running) {
        return;
      }

      var poll = this;
      var net = this.net;
      var currentNotification = net._lastNotification;
      net.queryNotifications();
      net.onIdle(function () {
        if (poll.queryInterval === 0 || net._lastNotification !== currentNotification) {
          // Reset interval if there were actually notifications.
          poll.queryInterval = poll.INITIAL_INTERVAL;
        } else {
          // If there were no notifications, then back off the polling interval.
          poll.queryInterval = Math.min(poll.queryInterval * 2, poll.MAX_INTERVAL);
        }

        var cb = _.bind(poll.pollNotifications, poll);
        if (poll.idleTime >= poll.IDLE_TIME_MINS) {    
          // We are idle right now, so set a wake event.
          poll.wakeEvent = cb;
        } else {
          poll.queryTimeout = setTimeout(cb, poll.queryInterval);
        }
      });      
    }
  });
  

  var LocalNetworkModel = namespace.LocalNetworkModel = Backbone.Model.extend({
    initialize: function () {
      this._inFlight = [];
    },

    scope: function () {
      return this._scope;
    },

    onScope : function (scope) {
      var net = this;
      scope.selection.on('change:viewpoint', function(selection, viewpoint) {
        if (viewpoint) {
          if (viewpoint.isPlaceholder()) {
            net.queryFollowed().pipe(function () {
              net.queryViewpoint(viewpoint.id);
            }).done(function () {
              viewpoint.loaded(true);
            });
          } else {
            net.queryViewpoint(viewpoint.id).done(function () {
              viewpoint.loaded(true);
            });
          }
        }
      });
    },

    getLastNotification : function () {
      // Do nothing
    },

    queryNotifications : function () {
      // Do nothing
    },

    _run_jsonp : function (src) {
      var deferred = $.Deferred();
      var script = document.createElement('script');
      script.type = 'text/javascript';
      script.src = src;

      var head = document.getElementsByTagName('head')[0];
      head.appendChild(script);

      script.onload = function () {
        deferred.resolve();
      };

      return deferred;
    },

    queryFollowed : function () {
      // Load all viewpoints and users.
      var net = this;
      var scope = net.scope();
      return this._run_jsonp('viewpoints.jsn').done(function () {
        var data = viewfinder.jsonp_data;
        viewfinder.jsonp_data = null;
        _(data.viewpoints).each(function (viewpointData) {
          var vp = scope.viewpoints.createOrUpdate(viewpointData);
          if (viewpointData.followers) {
            _(viewpointData.followers.followers).each(function (follower) {
              var userId = follower.follower_id;
              var id = [viewpointData.viewpoint_id, userId].join('+');
              vp.followers.createOrUpdate({
                follower_id : id,
                viewpoint_id : viewpointData.viewpoint_id,
                user_id : userId
              });
            });
          }
        });

        _(data.users).each(function (user) {
          scope.users.createOrUpdate(user);
        });
      });
      
    },

    startQueryFollowed : function () {
      this.queryFollowed();
    },

    continueQueryFollowed : function () {
      // Do nothing
    },

    queryViewpoint : function (viewpoint_id) {
      var net = this;
      var scope = net.scope();
      var url = scope.viewpoints.get(viewpoint_id).get('folder_name') + '/metadata.jsn';
      return this._run_jsonp(url)
        .done(function () {
          var viewpoint_data = viewfinder.jsonp_data;
          viewfinder.jsonp_data = null;
          var vp = scope.viewpoints.get(viewpoint_id);

          _(viewpoint_data.episodes).each(function (ep) {
            var ep_model = scope.episodes.createOrUpdate(ep);
            _(ep.photos).each(function (photo) {
              scope.photos.createOrUpdate(photo);

              photo.post_id = ep.episode_id + '+' + photo.photo_id;
              photo.episode_id = ep.episode_id;
              ep_model.posts.createOrUpdate(photo);
            });
          });

          _(viewpoint_data.comments).each(function (c) {
            vp.comments.createOrUpdate(c);
          });

          _(viewpoint_data.activities).each(function (a) {
            var converted = viewfinder.models.ActivityModel.convertServerJson(a);
            vp.activities.createOrUpdate(converted);
          });
        });
    },

    onIdle : function (f) {
      // Do nothing, nothing depends on this heavily.
    },

    updateViewedSeq : function () {
      // Do nothing
    }
  });

  /**
   * NetworkModel class - code which allows scope to query data from the Viewfinder, taking into account
   * some information provided by the user (selected conversation, etc.) 
   */
  var NetworkModel = namespace.NetworkModel = Backbone.Model.extend({
    initialize : function () { 
      this._invalidations = {
        viewpoints : new InvalidationCollector('viewpoint_id'),
        episodes : new InvalidationCollector('episode_id'),
        users : new InvalidationCollector('user_id')
      };
      
      this._inFlight = {
        followed : null,
        viewpoints : null,
        episodes : null,
        users : null,
        notifications : null
      };
      
      this._lastNotification = null;
      this._rapidLoad = true;
      this.onError = _.bind(this._onError, this);
    },
    
    scope : function () {
      return this._scope;
    },
    
    onScope : function (scope) {
      // Set up deferred loading - viewpoints are not fully loaded until selected.
      var net = this;
      scope.selection.on('change:viewpoint', function(selection, viewpoint) { 
        if (viewpoint && !viewpoint.loaded()) {
          net.invalidateViewpoint(viewpoint.id, viewpoint.isPlaceholder());
          net.onIdle(function () {
            // Synchronize loading with the cover image at this point.
            var cover = viewpoint.getCoverPhoto();
            if (!cover || !viewfinder.fx.loading || cover.cached('full')) {
              viewpoint.loaded(true);
            } else {
              cover.loadImage('full');
              cover.once('change:cached_full', function () {
                viewpoint.loaded(true);
              });
            }
          });
        }
      }); 
    },
    
    getLastNotification : function () {
      var net = this;
      net._inFlight.getLast = viewfinder.query.getLastNotificationId().done(function (id) {
        net._lastNotification = id;
      });
      
      return net._inFlight.getLast
        .fail(net.onError)
        .always(function () {
          net._inFlight.getLast = null;
        });
    },
    
    queryNotifications : function () {
      var net = this;
      var scope = this.scope();
      var vp;
      net._stopRapidLoad();
      
      function processNotification(notificationData) {
        if (notificationData.invalidate) {
          var invalidate = notificationData.invalidate;
          if (invalidate.viewpoints) {
            net._invalidations.viewpoints.addRange(invalidate.viewpoints);
          }
          
          if (invalidate.episodes) {
            net._invalidations.episodes.addRange(invalidate.episodes);
          }
        }
 
        if (notificationData.inline) {
          var inline = notificationData.inline;
          if ('comment' in inline) {
            if (inline.comment.viewpoint_id !== viewfinder.own_user.default_viewpoint_id) {
              vp = scope.viewpoints.getPlaceholder(inline.comment.viewpoint_id);
              if (vp.loaded()) {
                vp.comments.createOrUpdate(inline.comment);
              }
            }
          }

          if ('activity' in inline) {
            if (inline.activity.viewpoint_id !== viewfinder.own_user.default_viewpoint_id) {
              vp = scope.viewpoints.getPlaceholder(inline.activity.viewpoint_id);

              if (vp.loaded()) {
                var converted = viewfinder.models.ActivityModel.convertServerJson(inline.activity);
                vp.activities.createOrUpdate(converted);
              } else if (vp.isPlaceholder()) {
                // We haven't even gotten metadata for this activity, but it should now likely
                // be at the top of the inbox. We won't add this activity, but we will go ahead
                // and retrieve the viewpoint's metadata.
                net.queryViewpoint(vp.id);
              } else {
                // The VP isn't a placeholder, but also hasn't been loaded.  
                // We only need to update the lastUpdateTime on the viewpoint.
                vp.checkLastUpdateTime(inline.activity.timestamp);
              }
            }
          }

          if ('viewpoint' in inline) {
            vp = scope.viewpoints.get(inline.viewpoint.viewpoint_id);
            if (vp) {
              scope.viewpoints.createOrUpdate(inline.viewpoint);
            }
          }
        }
        
        net._lastNotification = notificationData.notification_id;
      }
      
      net._inFlight.notifications = viewfinder.query.visitNotifications(net._lastNotification, processNotification)
        .pipe(_.bind(net._processViewpoints, net))
        .pipe(_.bind(net._processEpisodes, net))
        .pipe(_.bind(net._processUsers, net))
        .fail(net.onError)
        .always(function () {
          net._inFlight.notifications = null;
          net._startRapidLoad();
        });
    },
        
    // Queries all followed viewpoints from the server.
    queryFollowed : function () {
      this._queryFollowedHelper(false, null);
    },
    
    // Queries only the first page of viewpoints from the server.  The query can be continued
    // with continueQueryFollowed.
    startQueryFollowed : function () {
      this._queryFollowedHelper(true, null);
    },
    
    // Continue queryFollowed with the last paging key returned, if it exists.
    continueQueryFollowed : function () {
      var lastKey = this.get('lastQueryFollowedKey');
      if (lastKey) this._queryFollowedHelper(true, lastKey);
    },
    
    _queryFollowedHelper : function(paged, lastKey) {
      var net = this;
      var scope = net.scope();

      net._inFlight.followed = viewfinder.query.visitFollowed(function (viewpointData) {
        if (viewpointData.viewpoint_id !== viewfinder.own_user.default_viewpoint_id) {
          scope.viewpoints.createOrUpdate(viewpointData);
          net.invalidateFollowers(viewpointData.viewpoint_id);
        }
      }, lastKey, paged)
        .fail(net.onError)
        .done(function (lastKey) {
          net.set('lastQueryFollowedKey', lastKey || null);
        })
        .always(function () {
          net._inFlight.followed = null;
        });
    },

    // Request the same data returned by query_followed, but for a single viewpoint.
    queryViewpoint : function (viewpoint_id) {
      this._invalidations.viewpoints.add({
        viewpoint_id : viewpoint_id,
        get_attributes : true,
        get_followers : true
      });

      this._rapidLoadHelper('viewpoints', this._processViewpoints);
    },
    
    invalidateViewpoint : function (viewpoint_id, get_attributes) {
      get_attributes = get_attributes || false;
      this._invalidations.viewpoints.add({
        viewpoint_id : viewpoint_id,
        get_attributes : get_attributes,
        get_episodes : true,
        get_activities : true,
        get_followers : true,
        get_comments : true
      });
      
      this._rapidLoadHelper('viewpoints', this._processViewpoints);
    },
    
    invalidateFollowers : function (viewpoint_id) {
      this._invalidations.viewpoints.add({
        viewpoint_id : viewpoint_id,
        get_attributes : false,
        get_episodes : false,
        get_activities : false,
        get_followers : true,
        get_comments : false
      });
      
      this._rapidLoadHelper('viewpoints', this._processViewpoints);
    },
    
    invalidateEpisode : function (episode_id) {
      this._invalidations.episodes.add({
        episode_id: episode_id,
        get_attributes: false,
        get_photos: true
      });
      
      this._rapidLoadHelper('episodes', this._processEpisodes);
    }, 
    
    invalidateUser : function (user_id) {
      this._invalidations.users.add({
        user_id : user_id
      });
      
      this._rapidLoadHelper('users', this._processUsers);
    },

    updateViewedSeq : function (viewpoint_id, update_seq) {
      viewfinder.query.updateViewedSeq(viewpoint_id, update_seq);
    },
    
    // Invokes the given function when the network is completely idle (all outstanding
    // paged queries have completed).
    onIdle : function (f) {
      // Create a promise which resolves when all in-flight actions have completed.
      var net = this;
      var queryComplete = $.Deferred();
      
      var checkComplete = function () {
        if (_(net._inFlight).any()) {
          // If any queries are in flight, check again when they are done.
          $.when.apply(net, _(net._inFlight).values()).done(checkComplete);
        } else {
          // If no queries are in flight, resolve the outermost promise.
          queryComplete.resolve();
        }
      };
      
      checkComplete();
      queryComplete.done(function () {
        // Although the network operations are completed at this point, there may be some amount
        // of deferred work queued afterwards.  A simple defer here places this callback at the
        // conclusion of all of that deferred work.
        _.delay(f);
      });
    },
    
    _processViewpoints : function() {
      var net = this;
      var scope = net.scope();
      var selections = net._invalidations.viewpoints.get();
      net._invalidations.viewpoints.clear();

      if (selections.length === 0) {
        return null;
      }
      
      return viewfinder.query.visitViewpoints(selections, function (viewpointData) {
        var vp = scope.viewpoints.createOrUpdate(viewpointData);
        
        if ('episodes' in viewpointData) {
          _(viewpointData.episodes).each(function (episodeData) {
            scope.episodes.createOrUpdate(episodeData);
            net.invalidateEpisode(episodeData.episode_id);
          });
        }
        
        if ('comments' in viewpointData) {
          _(viewpointData.comments).each(function (commentData) {
            vp.comments.createOrUpdate(commentData);
          });
        }
        
        if ('activities' in viewpointData) {
          _(viewpointData.activities).each(function (activityData) {
            var converted = viewfinder.models.ActivityModel.convertServerJson(activityData);
            vp.activities.createOrUpdate(converted);
          });
        }

        if ('followers' in viewpointData) {
          _(viewpointData.followers).each(function (userId) {
            var id = [viewpointData.viewpoint_id, userId].join('+');
            if (!vp.followers.get(id)) {
              vp.followers.createOrUpdate({
                follower_id : [viewpointData.viewpoint_id, userId].join('+'),
                viewpoint_id : viewpointData.viewpoint_id,
                user_id : userId
              });
              
              net.invalidateUser(userId);
            }
          });
        }
      });
    },
    
    _processEpisodes : function () {
      var net = this;
      var scope = net.scope();
      var selections = net._invalidations.episodes.get();
      net._invalidations.episodes.clear();

      if (selections.length === 0) {
        return null;
      }

      return viewfinder.query.visitEpisodes(selections, function (episodeData) {
        var ep = scope.episodes.createOrUpdate(episodeData);
        
        if ('photos' in episodeData) {
          _(episodeData.photos).each(function (photoData) {
            // The data for each photo is actually a combination of data for a photo
            // and a post of that photo to a specific episode.
            scope.photos.createOrUpdate(photoData);
            
            photoData.post_id = episodeData.episode_id + '+' + photoData.photo_id;
            photoData.episode_id = episodeData.episode_id;
            ep.posts.createOrUpdate(photoData);
          });
        }
      });
    },
    
    _processUsers : function () {
      var net = this;
      var scope = net.scope();
      var selections = _(net._invalidations.users.get()).pluck('user_id');
      net._invalidations.users.clear();

      if (selections.length === 0) {
        return null;
      }
      
      return viewfinder.query.visitUsers(selections, function (userData) {
        scope.users.createOrUpdate(userData);
      });
    },
    
    _stopRapidLoad : function () {
      this._rapidLoad = false;
    },
    
    _startRapidLoad : function () {
      this._rapidLoad = true;
      this._rapidLoadHelper('viewpoints', this._processViewpoints);
      this._rapidLoadHelper('episodes', this._processEpisodes);
      this._rapidLoadHelper('users', this._processUsers);
    },
    
    _rapidLoadHelper : function (collection, processMethod) {
      var net = this;
      if (!net._rapidLoad || net._inFlight[collection] || net._invalidations[collection].length() === 0) return;

      // Rapid load mode - automatically call the process method and add
      // a promise to the _inFlight collection.
      net._inFlight[collection] = $.Deferred();
      net._inFlight[collection].always(function () {
        net._inFlight[collection] = null;
      });
      
      var checkComplete = function () {
        if (net._invalidations[collection].length() > 0) {
          processMethod.call(net).fail(net.onError).always(checkComplete);
        } else {
          net._inFlight[collection].resolve();
        }
      };
      
      // Defer first call to checkComplete to allow any additional invalidations 
      // in the current turn to accumulate.
      _.defer(checkComplete);
    },
    
    // Make errors known to any UI element interested.
    _onError : function (textStatus) {
      this.trigger('error', textStatus);
    }
  });
  
  // **********************************************************************************************
  //                                  SELECTION AND ROUTING
  // **********************************************************************************************
  
  var SelectionModel = Backbone.Model.extend({
    initialize : function () {
      this._trySelect(null, null, null);
      
      // Selection helpers will pass on 'selected' and 'deselected' events to selected models.
      this.on('change:viewpoint', this._selectionHelper('viewpoint'));
      this.on('change:activity', this._selectionHelper('activity'));
      this.on('change:photo', this._selectionHelper('photo'));
    },
    
    scope : function () {
      return this._scope;
    },
    
    onScope : function (scope) {
      var selection = this;
      function selectMostRecent() {
        if (!selection.viewpoint() && scope.viewpoints.length > 0) {
          // Viewpoints sorted least-recently first.
          for (var i = scope.viewpoints.length - 1; i >= 0; i--) {
            var vp = scope.viewpoints.at(i);
            if (!vp.isPlaceholder() && !vp.isRemoved()) {
              selection.viewpoint(vp);
              break;
            }
          }
        }
      }
      
      // Select most recent viewpoint if the currently selected viewpoint is removed.
      scope.viewpoints.on('change:labels', function (viewpoint, labels) {
        if (viewpoint.isRemoved() && viewpoint === this.viewpoint()) {
          this.viewpoint(null);
          selectMostRecent();
        }
      }, this);
    },
    
    // Gets or sets the currently selected viewpoint.  Selecting a new viewpoint will
    // result in any selected activity or photo being deselected.
    viewpoint : function (newSelection) {
      var current = this.get('viewpoint');
      if (_.isUndefined(newSelection)) return current;
      if (current === newSelection) return current;
      
      this._trySelect(newSelection, null, null);
      return null;
    },
    
    // Gets or sets the currently selected activity.  Selecting a new activity will result in the currently
    // selected photo being deselected.
    activity : function (newSelection) {
      var current = this.get('activity');
      if (_.isUndefined(newSelection)) return current;
      if (current === newSelection) return current;
      
      this._trySelect(this.get('viewpoint'), newSelection, null);
      return null;
    },
    
    // Gets or sets the currently selected photo.
    photo : function (newSelection) {
      var current = this.get('photo');
      if (_.isUndefined(newSelection)) return current;
      if (current === newSelection) return current;
          
      this._trySelect(this.get('viewpoint'), this.get('activity'), newSelection);
      return null;
    },
    
    // Retrieves the model for the next photo chronologically in the current viewpoint, if it exists.
    nextPhoto : function () {
      var post = this._findNextPost();
      if (post) return post[1];
      return null;
    },
    
    // Moves selection to the next photo chronologically in the current viewpoint, if it exists.
    moveNextPhoto : function () {
      var post = this._findNextPost();
      if (post) {
        this.set({
          activity : post[0],
          photo : post[1],
          index : this.get('index') + 1
        });
      }
    },
    
    // Retrieves the model for the previous photo chronologically in the current viewpoint, if it exists.
    prevPhoto : function () {
      var post = this._findPrevPost();
      if (post) return post[1];
      return null;
    },
    
    // Moves selection to the previous photo chronologically in the current viewpoint, if it exists.
    movePrevPhoto : function () {
      var post = this._findPrevPost();
      if (post) {
        this.set({
          activity : post[0],
          photo : post[1],
          index : this.get('index') - 1
        });
      }
    },
    
    _findNextPost : function () {
      var viewpoint = this.get('viewpoint');
      var index = this.get('index');
      
      if (!viewpoint || index === -1) return null;
      
      var posts = this.get('posts');
      if (index + 1 < posts.length) {
        return posts[index + 1];
      }
      
      return null;
    },
    
    _findPrevPost : function () {
      var viewpoint = this.get('viewpoint');
      var index = this.get('index');
      
      if (!viewpoint || index === -1) return null;
      
      var posts = this.get('posts');
      if (index - 1 >= 0) {
        return posts[index - 1];
      }
      
      return null;
    },
    
    // Validate a potential selection set, modifying it if necessary before applying.
    // Invalid combinations will be replaced by null selections.
    _trySelect : function (viewpoint, activity, photo) {      
      var index = -1;
      var posts = this.get('posts');
      
      // Default assumptions: can't have photo without episode, or episode without viewpoint.
      if (!viewpoint) episode = null;
      if (!activity) photo = null;
      
      if (viewpoint && viewpoint != this.get('viewpoint')) {
        // Only recompute posts if a new viewpoint is available.
        posts = this._computePosts(viewpoint);
      } else if (!viewpoint) {
        posts = null;
      }
      
      // Check that the given photo and episode are valid, given the selected viewpoint.
      if (activity) {
        var obj = _(posts).find(function (post) {
          return post[0] === activity && (!photo || post[1] === photo);
        });
        
        if (obj) {
          index = _(posts).indexOf(obj);
        } else {
          photo = activity = null;
        }
      }        
      
      this.set({viewpoint : viewpoint, activity : activity, photo : photo, index : index, posts : posts});

      // Hook up callback to recompute flat post list if posts are unshared or added.
      this.stopListening();
      if (viewpoint) {
        var reselect = _.simpleDebounce(this.reselect);
        this.listenTo(viewpoint.activities, 'add add:post', reselect);
      }
    },

    reselect : function () {
      this.set('posts', this._computePosts(this.get('viewpoint')));
      this._trySelect(this.get('viewpoint'), this.get('activity'), this.get('photo'));
    },
    
    _selectionHelper : function (propertyName) {
      var selection = this;
      return function () {
        var curr = selection.get(propertyName);
        var prev = selection.previous(propertyName);
        if (prev) prev.trigger('unselected');
        if (curr) curr.trigger('selected');
      };
    },

    _computePosts : function (viewpoint) {
      var posts = [];
      viewpoint.activities.each(function (a) {
        a.visitPhotos(function (episode, photo) {
          posts.push([a, photo]);
        });
      }); 

      return posts;
    }
  });
  
  // **********************************************************************************************
  //                                    METADATA SCOPE
  // **********************************************************************************************
  
  /**
   * Viewfinder metadata scope, designed to keep several metadata collection instances tied together.
   * Each collection gets a reference to the scope object, which can be used to access the other
   * collections.
   * 
   * @class
   * @param {Object} collections An object containing a set of collections to enclose in the scope.
   */
  var ViewfinderScope = namespace.ViewfinderScope = function (collections) {
    var scope = this;
    
    // Add every key/value pair of 'collections' to the current scope - each value should
    // be a viewfinder collection object.  After adding all the keys, assign the _scope
    // property of each collection to point back to this scope object, and invoke the 
    // onScope() method of each collection.
    _.chain(scope)
      .extend(collections)
      .values()
      .each(function (collection) {
        collection._scope = scope;
        if (collection.onScope) collection.onScope(scope);
      });
  };
  
  /**
   * Create a new ViewfinderScope object containing one instance of all Viewfinder collection types.
   */
  namespace.createViewfinderScope = function () {
    return new ViewfinderScope({
      photos : new PhotoCollection(),
      episodes : new EpisodeCollection(),
      users : new UserCollection(),
      viewpoints : new ViewpointCollection(),
      selection : new SelectionModel(),
      network : new LocalNetworkModel()
    });
  };
  
  // **********************************************************************************************
  //                                    AUTHORIZATION MODEL
  // **********************************************************************************************
  
  var emailRegex = /^[\w\-]{1,}([\w\-\+.]{1,1}[\w\-]{1,}){0,}[@][\w\-]{1,}([.]([\w\-]{1,})){1,3}$/;

  // Ordered lists of countries in which a locally-formatted phone number is most likely to originate.
  var localPhoneCountries = ['US', 'CN', 'JP', 'IN', 'ID', 'BR', 'RU', 'DE', 'FR', 'GB'];
    
  var isEmail = function(maybeEmail) {
    return emailRegex.test(maybeEmail);
  };
    
  var isPhone = function (maybePhone) {
    if (phoneToE164(maybePhone)) {
      return true;
    }

    return false;
  };
    
  var phoneToE164 = function (phoneString) {
    if (isValidNumber(phoneString)) return phoneString;

    for (var i = 0; i < localPhoneCountries.length; i++) {
      var e164 = formatE164(localPhoneCountries[i], phoneString);
      if (isValidNumber(e164)) {
        return e164;
      }
    }

    return null;
  };
  
  // A model used for authorization forms.  This model stores information collected from registration
  // forms, but also maintains an internal state representing the authorization phase of the user.
  // There are several active modes which require user input:
  // * login_begin          : The user wants to log in to the server.
  // * login_success        : The user has successfully logged in.
  //
  // * register_begin       : The user is beginning to register an identity.
  // * register_token       : Collect the access token sent to the user to confirm their identity.
  // * register_success     : The user has successfully registered their account.
  //
  // * reset_begin          : The user is requesting to reset the password of their account.
  // * reset_token          : Collect the access token sent to the user.
  // * reset_password       : Accept a new password from the user.
  // * reset_success        : The user's password has been successfully reset.
  // * reset_success_merge  : The same as reset success, but returns users to the merge process.
  // 
  // * merge_begin          : Give the user the option of requesting a merge.
  // * merge_confirm        : Extra screen where user confirms that they want to merge.
  // * merge_token          : Collect the access token sent to the target account.
  // * merge_success        : Your two accounts have been merged.
  var AuthorizationModel = namespace.AuthorizationModel = Backbone.Model.extend({
    defaults : {
      keep_cookie : true
    },

    validate : function (attributes) {
      var errors = {};
      var model = this;
      attributes = _(attributes).defaults(this.attributes);
      
      function checkIdentity() {
        if (!isEmail(attributes.identity_key) && !isPhone(attributes.identity_key)) {
          if (attributes.identity_key.indexOf('@') >= 0) {
            errors.identity_key = "The <b>E-mail Address</b> specified is invalid.";
          } else if (cleanPhone(attributes.identity_key).length > 5) {
            errors.identity_key = "The <b>Phone Number</b> specified is not valid."
              + " Try using your entire number with country code, preceded by a plus. "
              + " (example: +1 555 555 5555).";
          } else {
            errors.identity_key = "We need a valid <b>E-mail Address</b> or <b>Phone Number</b>.";
          };
        }
      }

      function checkPassword() {
        if (attributes.password.length < 8) {
          errors.password = "<b>Password</b> must be at least 8 characters in length.";
        }
      }
      
      function checkNames() {
        if (!attributes.given_name || attributes.given_name.length < 1) {
          errors.given_name = "We're missing your <b>First Name</b>.";
        }
        
        if (!attributes.family_name || attributes.family_name.length < 1) {
          errors.family_name = "We're missing your <b>Last Name</b>.";
        }
      }

      function checkToken() {
        var expectedDigits = attributes.token_digits;
        if (attributes.access_token.length !== attributes.token_digits) {
          errors.access_token = '<b>Access Token</b> is not valid.';
        }
      }
      
      switch (attributes.mode) {
      case "login_begin":
      case "reset_begin":
      case "merge_begin":
        checkIdentity();
        break;
      case "register_begin":
        checkPassword();
        checkNames();
        break;
      case "reset_password":
        checkPassword();
        break;
      case 'reset_token':
      case 'merge_token':
      case 'register_token':
        checkToken();
        break;
      }
      
      if (_(errors).size() > 0) {
        return errors;
      } 
      
      return null;
    },
    
    initialize : function () {
      this._requestInProgress = false;
      this._oldAttrs = [];
      
      // Initialize any preferred identity provided by the server - this occurs when viewing the page
      // as a prospective user.
      var identity = this.get('identity');
      if (identity) {
        var identitySplit = identity.split(':', 2);
        if (identitySplit.length === 2) {
          this.set({
            identity_type : identitySplit[0],
            identity_key : identitySplit[1]
          });
        }
      }
      
      this.on('change:identity_key', this._onChangeIdentityKey, this);

      // Initialize merge_begin as if it had been triggered within our dialog.
      if (this.get('mode') === 'merge_begin') {
        this.set('mode', 'history_back');
        this.mergeMode();
      }
    },
    
    // Attempt to proceed to the next step in the authentication progress.
    proceed : function () {
      if (this.get('requestInProgress')) {
        return;
      }
      
      var auth = this;
      var mode = this.get('mode');
      var proceedFunc = this['proceed_' + mode];
      
      if (proceedFunc) {
        this.set({
          requestInProgress : true,
          errors : null
        });
        
        proceedFunc.call(this)
          .always(function () {
            auth.set('requestInProgress', false);
          })
          .fail(function (jqXhr, message) {
            auth.set('errors', auth.parseError(jqXhr, message));
          });
      }
    },

    parseError : function (jqXhr, message) {
      if (jqXhr.responseText) {
        var errorObj;

        try {
          errorObj = JSON.parse(jqXhr.responseText);
        } catch(SyntaxError) {
          // Not a JSON object, probably a simple string.
          return jqXhr.responseText;
        }

        if (!errorObj.error) {
          // Object is not from Viewfinder - just go with the default message from jQuery.
          return message;
        }

        // Parse error ID from server to determine if the default message needs to be altered.
        errorObj = errorObj.error;
        switch(errorObj.id) {
        case "NO_USER_ACCOUNT":
          if (this.get('identity_type') === 'Phone') {
            return "We can't find a Viewfinder account for this phone number."
              + " Try using your entire number with country code, preceded by a plus. "
              + " (example: +1 555 555 5555).";
          }
        }

        return errorObj.message;
      }
      
      // By default, just use jQuery's error message, which will likely be a generic
      // network error message.  This will at least give the user some sort of feedback that
      // an error occured.
      return message;
    },

    // Change to the merge workflow.
    mergeMode : function () {
      this._oldAttrs.push({ 
        mode : this.get('mode'),
        identity_key : this.get('identity_key')
      });
      
      this.set({
        mode :  'merge_begin',
        identity_key : '',
        source_identity : this.get('identity'),
        errors : null
      });
    },

    // Change to the reset password workflow.
    resetMode : function () {
      this._oldAttrs.push({
        mode : this.get('mode')
      });

      this.set({
        mode : 'reset_begin',
        errors : null
      });
    },

    // Return to the previous mode (presumably, user elected to cancel).
    prevMode : function () {
      var oldAttrs = this._oldAttrs.pop();
      this.set(oldAttrs);
      this.set('errors', null);

      if (this.get('mode') === 'history_back') {
        history.back();
      }
    },
    
    // From the logged out state, send a request to /login/viewfinder
    // to authorize the user.  Proceeds to logged_in state upon success.
    proceed_login_begin : function () {
      var auth = this;
      return viewfinder.account.login(this.get('identity'), this.get('password'), !this.get('keep_cookie'))
        .done(function () {
          auth.set('mode', 'login_success');
        });
    },
    
    // Sends an initial registration request to the server.  
    // Proceeds to the email_sent or sms_sent state on success, depending on the identity type.
    proceed_register_begin : function () {
      var auth = this;
      var promise = viewfinder.account.register(this.get('identity'), 
                                                this.get('password'), 
                                                this.get('given_name'), 
                                                this.get('family_name'));
      promise.done(function (response) {
        if (response.user_id) {
          // Registration was immediately successful.
          auth.set('mode', 'register_success');
        } else {
          // An e-mail was sent with an access token.
          auth.set({
            mode : 'register_token',
            token_digits : response.token_digits
          });
        }
      });
        
      return promise;
    },
    
    // Sends a password confirmation request to the server before redeeming the access token.
    proceed_register_token : function () {
      var auth = this;
      return viewfinder.account.verify(auth.get('identity'), auth.get('access_token'))
        .done(function () {
          auth.set('mode', 'register_success');
        });
    },

    // Requests a 'forgot password' e-mail to be dispatched from the server.
    proceed_reset_begin : function () {
      var auth = this;
      return viewfinder.account.resetPassword(this.get('identity'))
        .done(function (response) {
          auth.set({
            mode : 'reset_token',
            token_digits : response.token_digits
          });
        });
    },

    // Collect access token sent in email.
    proceed_reset_token : function () {
      var auth = this;
      return viewfinder.account.verify(this.get('identity'), this.get('access_token'))
        .done(function (response) {
          auth.set({
            resetUserId : response.user_id,
            mode : 'reset_password'
          });
        });
    },
    
    // Collects new password from user.
    proceed_reset_password : function () {
      var auth = this;
      // Verify access token first, then update the password if the verification is successful.
      return viewfinder.account.updatePassword(auth.get('password'))
        .done(function () {
          auth.prevMode();
          if (auth.get('mode') === 'merge_begin') {
            auth.set('mode', 'reset_success_merge');
          } else {
            auth.set('mode', 'reset_success');
          }
        });
    },

    // Logs in as the target account for the merge.
    proceed_merge_begin : function () {
      var auth = this;
      return viewfinder.account.login(this.get('identity'), this.get('password'))
        .pipe(function (response) {
          return viewfinder.query.visitUsers([response.user_id], function (user) {
            auth.set('given_name', user.given_name);
          });
        })
        .done(function () {
          auth.set('mode', 'merge_confirm');
        });

      
      return promise;
    },

    proceed_reset_success_merge : function () {
      var auth = this;
      return viewfinder.query.visitUsers([auth.get('resetUserId')], function (user) {
        auth.set('given_name', user.given_name);
      })
        .done(function () {
          auth.set({
            mode: 'merge_confirm',
            access_token : null
          });
        });
    },

    // Collect token sent to target account.
    proceed_merge_confirm : function () {
      var auth = this;
      var promise;

      if (this.get('merge_cookie')) {
        promise = viewfinder.account.mergeAccount(this.get('merge_cookie'))
          .done(function () {
            auth.set('mode', 'merge_success');
          });
      } else {
        promise = viewfinder.account.sendMergeToken(auth.get('source_identity'))
          .done(function (response) {
            auth.set({
              mode : 'merge_token',
              token_digits : response.token_digits
            });
          });
      }

      return promise;
    },

    // Acquire confirmed cookie for source account and perform the merge operation.
    proceed_merge_token : function () {
      var auth = this;
      return viewfinder.account.mergeIdentity(this.get('source_identity'), this.get('access_token'))
        .done(function () {
          auth.set('mode', 'merge_success');
        });
    },
    
    _getRequest : function () {
      return {
        'headers' : {
          'version' : viewfinder.messageVersion
        }
      };
    },
    
    _getAuthRequest : function () {
      var request = this._getRequest();
      request.auth_info = {
        identity : this.get('identity'),
        password : this.get('password')
      };
      
      return request;
    },
    
    _sendRequest : function (url, request) {
      return $.ajax({
        headers : {"X-Xsrftoken": _vf_xsrf_token},
        url : url,
        type : 'POST',
        processData : false,
        data : JSON.stringify(request),
        contentType : 'application/json; charset=UTF-8',
        dataType : 'json'
      });
    },
    
    _onChangeIdentityKey : function(model, identity_key) {
      if (isEmail(identity_key)) {
        this.set({
          identity_type : 'Email',
          identity : 'Email:' + identity_key.toLowerCase() 
        });
      } else if (isPhone(identity_key)) {
        this.set({
          identity_type : 'Phone',
          identity : 'Phone:' + phoneToE164(identity_key)
        });
      } else {
        // Shouldn't get to this point if form validation is being used properly.
        // However, we'll handle a bad value gracefully.
        this.set({
          identity_type : 'Unknown',
          identity : 'Unknown:' + identity_key
        });
      }
    }
  });

  //**** COMMENT MODEL ****
  var AddCommentModel = namespace.AddCommentModel = ViewfinderDataModel.extend({
    defaults : {
      viewpoint : null,
      message : '',
      asset_id : null
    },

    validate : function (attributes) {
      var errors = {};
      if (!attributes.message || attributes.message.length === 0) {
        errors.message = 'Comment text can not be blank.';
      }

      if (_(errors).size() > 0) {
        return errors;
      } 

      return null;
    },

    proceed : function () {
      var model = this;

      if (this.get('requestInProgress')) {
        return;
      }

      this.set({
        requestInProgress : true,
        errors : null
      });

      viewfinder.query.postComment(this.get('viewpoint').id, this.get('message'), this.get('asset_id'))
      .done(function (response) {
        // update_seq of the conversation was implicitly updated.
        var viewpoint = model.get('viewpoint');
        response.activity.update_seq = viewpoint.addedUpdate();
        viewpoint.comments.createOrUpdate(response.comment);
        viewpoint.activities.createOrUpdate(response.activity);
        model.set('message', '');
        model.trigger('reset');
      })
      .fail(function (jqXhr, message) {
        if (jqXhr.responseText) {
          try {
            var errorObj = JSON.parse(jqXhr.responseText);
            if (errorObj.error) {
              message = errorObj.error.message;
            }
          } catch(SyntaxError) {
            // Ignore syntax error.
          }
        }
        
        model.set('errors', message);
      })
      .always(function () {
        model.set('requestInProgress', false);
      });
    }
  });


})(jQuery, viewfinder.models);

