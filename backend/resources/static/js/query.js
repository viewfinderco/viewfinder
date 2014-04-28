// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview Functions for querying data from the viewfinder service.
 *
 * @author matt@emailscrubbed.com (Matt Tracy)
 */

/** @namespace */
viewfinder.query = {};
viewfinder.account = {};

(function($, query, account) { 
  var requestTemplate = {
    'headers': {
      'version': viewfinder.messageVersion
    }
  };
  
  // Limit on the number of data selections which can be processed in a single
  // request.  This is independent of the 'limit' key passed with queries, which
  // affects the maximum size of collections returned for each selection.
  var requestSelectionLimit = 30;
  
  // Approximate number for the total number of objects returned by a query.
  // This includes objects in the collections for each selection - for instance, 
  // the episodes returned for a viewpoint.  This does not create a hard limit, 
  // but is rather used as a general guideline.
  var requestTotalObjectsLimit = 1000;
  
  // The maximum value for the collection size limit on a single request.
  var requestCollectionMax = 100;
  
  // A mapping between viewpoint metadata categories and their paging keys.
  var viewpointPagingKeys = {
    followers: 'follower_last_key',
    activities: 'activity_last_key',
    episodes: 'episode_last_key',
    comments: 'comment_last_key'
  };
  
  // A mapping between episode metadata categories and their paging keys.
  var episodePagingKeys = {
    photos: 'photo_last_key'
  };
  
  /**
   * Queries the service for a list of viewpoints followed by the current user and
   * invokes the visitor function once for each viewpoint.  Paging is handled
   * transparently by this function.
   *
   * @memberof viewfinder.query
   * @param {Function} vistor Visitor function which will be invoked once for each viewpoint
   *  followed by the current user.
   * @param {String} startKey Optional starting key for the first viewpoint query.
   * @param {Boolean} paged If true, visitFollowed will only query the server a single time.  If there
   *  are still viewpoints remaining after the initial query, the deferred will be resolved with the
   *  last key returned by that query.  This allows for explicit control of paging.
   * 
   * @returns {jQuery.Deferred} A jQuery deferred object which will resolve when all followed viewpoints 
   *  have been visited.
   */
  function visitFollowed(visitor, startKey, paged) {  
    var deferred = $.Deferred();
    var request = _(requestTemplate).clone();
    request.limit = 25;
    if (startKey) {
      request.start_key = String(startKey);
    }
    
    // Dispatches a single query to the server.  
    function sendQuery() {
      serviceRequest('query_followed', request).done(doneQuery).fail(failQuery);
    }
    
    // Invokes the callback with the result of a completed query.  If there are 
    // more results on the server which were paged, creates a continuation function
    // which will query the next page and returns it.
    function doneQuery(response) {
      _(response.viewpoints).each(visitor);
      
      if (response.viewpoints.length >= request.limit) {
        if (paged) {
          deferred.resolve(response.last_key);
        } else {
          request.start_key = response.last_key;
          sendQuery();
        }
      } else {
        deferred.resolve();
      }
    }
    
    function failQuery(jqHxr, textStatus) {
      deferred.reject("Error from visitfollowed: " + textStatus);
    }
    
    sendQuery();
    return deferred;
  }
  
  /**
   * Queries the service for a list of notifications for the current user and invokes the given
   * callback once for each notification.  Only notifications occurring after the given startKey 
   * are queried.
   *
   * @memberof viewfinder.query
   * @param {String|Number} startKey Starting key for the notification query.  Only notifications newer than the
   *  given key will be visited.
   * @param {Function}  Visitor function which will be invoked once for each viewpoint
   *  followed by the current user.
   * 
   * @returns {jQuery.Deferred} A jQuery deferred object which will resolve when all notifications
   *  have been visited.
   */
  function visitNotifications(startKey, visitor) {
    var deferred = $.Deferred();
    var request = _(requestTemplate).clone();
    request.limit = 50;
    if (startKey) {
      request.start_key = String(startKey);
    }
    
    // Dispatches a single query to the server.  
    function sendQuery() {
      serviceRequest('query_notifications', request).done(doneQuery).fail(failQuery);
    }
    
    // Invokes the callback with the result of a completed query.  If there are 
    // more results on the server which were paged, creates a continuation function
    // which will query the next page and returns it.
    function doneQuery(response) {
      var isLastQuery = (response.notifications.length < request.limit);
      
      // Send out request for the next page of data, if it exists.
      if (!isLastQuery) {
        request.start_key = response.last_key;
        sendQuery();
      } 
      
      // Invoke the visitor on each notification received.
      _(response.notifications).each(visitor);
      
      // If this was the last page of the query, resolve this method's promise.
      if (isLastQuery) deferred.resolve();
    }
    
    function failQuery(jqHxr, textStatus) {
      deferred.reject("Error from visitNotifications: " + textStatus);
    }
    
    sendQuery();
    return deferred;
  }
  
  /**
   * Queries the service for the Id of the last notification available for the user.  This is intended
   * to establish a high water mark before 'manually' invalidating the user's data.
   *
   * @memberof viewfinder.query
   * @returns {jQuery.Deferred} A jQuery deferred object which will resolve with the notification Id when 
   * all notifications for the user have been visited.
   */
  function getLastNotificationId() {
    var deferred = $.Deferred();
    var request = _(requestTemplate).clone();
    request.scan_forward = false;
    request.limit = 1;
   
    // Dispatches a single query to the server.  
    function sendQuery() {
      serviceRequest('query_notifications', request).done(doneQuery).fail(failQuery);
    }
    
    // Resolves the returned Deferred promise with the last notification id, or 0 if no notifications
    // are returned.
    function doneQuery(response) {
      if (response.notifications.length === 0) {
        deferred.resolve(0);
      } else {
        deferred.resolve(response.notifications[0].notification_id);
      }
    }
    
    function failQuery(jqHxr, textStatus) {
      deferred.reject("Error from visitNotifications: " + textStatus);
    }
    
    sendQuery();
    return deferred;
  }
  
  
  /**
   * Queries the service for information on one or more viewpoints, and invokes the 
   * provided visitor callback with the data returned for each viewpoint.  
   *
   * @memberof viewfinder.query
   * @param {Object[]} viewpointSelections A list of viewpoint 'selections', each of which represents
   *   a request for a subset of information about a single viewpoint.
   * @param {Function} visitor A Visitor function which will be invoked one or more times for each viewpoint
   *   selection.  The visitor is invoked multiple times for a single viewpoint in the case where 
   *   the data requested for that viewpoint is paged by the server - each invocation a unique 
   *   subset of the requested data.
   * 
   * @returns {jQuery.Deferred} A jQuery Deferred object which will resolve when all requested data has
   *  been retrieved and visited.
   */
  function visitViewpoints(viewpointSelections, visitor) {
    var deferred = $.Deferred();
    var selections = viewpointSelections.slice(0);  // Shallow copy.
    var request = _(requestTemplate).clone();
    
    // Dispatches a single query to the server.
    function sendQuery() {
      // Split the array in two pieces - splice() mutates the original array.
      request.viewpoints = selections.splice(0, requestSelectionLimit);
      
      // Some math to determine the 'Limit' property, which the limits the size of collections returned
      // for a single selection within a request. 
      // 
      // We divide the total object limit by the number of selections in order to get this limit. 
      // For example, if there were 10 selections we might allow 10 objects per collection for each 
      // selection, but if there is only 1 selection we will allow 100 objects per collection.
      // 
      // The collection limit has a maximum value.
      var collectionsLimit = Math.floor(requestTotalObjectsLimit / request.viewpoints.length);
      request.limit = Math.min(requestCollectionMax, collectionsLimit);
      serviceRequest('query_viewpoints', request).done(doneQuery).fail(failQuery);
    }
    
    // Successful completion of a single query.
    function doneQuery(response) {
      _(response.viewpoints).each(function(v) {
        // Determine if the data was paged - if so, create a new selection for the
        // next page of data and add it to the beginning of the queued selections.
        var wasPaged = false;    
      	var newSelection = { viewpoint_id: v.viewpoint_id, get_attributes: false };
      	_(viewpointPagingKeys).each(function (key, category){
    		  if (category in v && v[category].length >= request.limit) {
    		    wasPaged = true;
    		    startKey = key.replace('_last_key', '_start_key');
  		      newSelection['get_' + category] = true;
  		      newSelection[startKey] = v[key];
  		    } else {
  		      newSelection['get_' + category] = false;
  		    }
  		  });
  		  
        wasPaged && selections.unshift(newSelection);
      });
      
      var isLastQuery = (selections.length === 0);
      
      // Send out request for the next page of data, if it exists.
      if (!isLastQuery) sendQuery();
      
      // Invoke the visitor with the returned data for this viewpoint.
      _(response.viewpoints).each(visitor);
           
      // If this was the last page of the query, resolve this method's promise.
      if (isLastQuery) deferred.resolve();
    }
    
    // Failure of a query.
    function failQuery(jqHxr, textStatus) {
      deferred.reject("Error from visitViewpoints: " + textStatus);
    }
    
    sendQuery();
    return deferred;
  }
  
  //
  // TODO(Matt) : visitViewpoints and visitEpisodes are very similar and can likely be refactored
  //   significantly to take advantage of common code.
  //
  
  /**
   * Queries the service for information on one or more episodes, and invokes the 
   * provided visitor callback with the data returned for each episode.  
   *
   * @memberof viewfinder.query
   * @param {Object[]} episodeSelections A list of episode 'selections', each of which represents
   *   a request for a subset of information about a single episode.
   * @param {Function} visitor A visitor function which will be invoked one or more times for each episode
   *   selection.  The visitor is invoked multiple times for a single episode in the case where 
   *   the data requested for that episode is paged by the server - each invocation a unique 
   *   subset of the requested data.
   * 
   * @returns {jQuery.Deferred} A jQuery Deferred object which will resolve when all requested data has
   *  been retrieved and visited.
   */
  function visitEpisodes(episodeSelections, visitor) {
    var deferred = $.Deferred();
    var selections = episodeSelections.slice(0);  // Shallow copy.
    var request = _(requestTemplate).clone();
    
    // Dispatches a single query to the server.
    function sendQuery() {
      // Split the array in two pieces - splice() mutates the original array.
      request.episodes = selections.splice(0, requestSelectionLimit);
      
      // Some math to determine the 'Limit' property, which the limits the size of collections returned
      // for a single selection within a request. 
      // 
      // We divide the total object limit by the number of selections in order to get this limit. 
      // For example, if there were 10 selections we might allow 10 objects per collection for each 
      // selection, but if there is only 1 selection we will allow 100 objects per collection.
      // 
      // The collection limit has a maximum value.
      var collectionsLimit = Math.floor(requestTotalObjectsLimit / request.episodes.length);
      request.photo_limit = Math.min(requestCollectionMax, collectionsLimit);
      serviceRequest('query_episodes', request).done(doneQuery).fail(failQuery);
    }
    
    // Successful completion of a single query.
    function doneQuery(response) {
      _(response.episodes).each(function(e) {
        // Determine if the data was paged - if so, create a new selection for the
        // next page of data and add it to the beginning of the queued selections.
        var wasPaged = false;    
        var newSelection = { episode_id: e.episode_id, get_attributes: false };
        _(episodePagingKeys).each(function (key, category){
          if (category in e && e[category].length >= request.limit) {
            wasPaged = true;
            startKey = key.replace('_last_key', '_start_key');
            newSelection['get_' + category] = true;
            newSelection[startKey] = e[key];
          } else {
            newSelection['get_' + category] = false;
          }
        });
        
        wasPaged && selections.unshift(newSelection);
      });
      
      var isLastQuery = (selections.length === 0);
      
      // Send out request for the next page of data, if it exists.
      if (!isLastQuery) sendQuery();
      
      // Invoke the visitor with the returned data for this viewpoint.
      _(response.episodes).each(visitor);
           
      // If this was the last page of the query, resolve this method's promise.
      if (isLastQuery) deferred.resolve();
    }
    
    // Failure of a query.
    function failQuery(jqHxr, textStatus) {
      deferred.reject("Error from visitEpisodes: " + textStatus);
    }
    
    // Build basic request.
    sendQuery();
    return deferred;
  }
  
  
  /**
   * Queries the service for user metadata and invokes the visitor function once with each 
   * user returned.  Paging is handled transparently by this function.
   *
   * @memberof viewfinder.query
   * @param {Number[]} userIds A list of viewfinder UserIds for which metadata is desired.
   * @param {Function} visitor A visitor function which will be invoked once for each user
   *   returned by the query.
   * 
   * @returns {jQuery.Deferred} A jQuery deferred object which will resolve when all user data has
   *   been visited.
   */
  function visitUsers(userIds, visitor) {
    var deferred = $.Deferred();
    var users = userIds.splice(0);
    var request = _(requestTemplate).clone();
    
    function sendQuery() {
      request.user_ids = users.splice(0, requestCollectionMax);
      serviceRequest('query_users', request).done(doneQuery).fail(failQuery);
    }
    
    function doneQuery(response) {
      var isLastQuery = (users.length === 0);
      
      // Send out request for the next page of data, if it exists.
      if (!isLastQuery) sendQuery();
      
      // Invoke the visitor with the returned data for this viewpoint.
      _(response.users).each(visitor);
      
      // If this was the last page of the query, resolve this method's promise.
      if (isLastQuery) deferred.resolve();
    }
    
    function failQuery(jqHxr, textStatus) {
      deferred.reject('Error from visitUsers: ' + textStatus);
    }
    
    sendQuery();
    return deferred;
  }
  
  
  /**
   * Queries the service for contact metadata and invokes the visitor function once with each 
   * contact returned.  Paging is handled transparently by this function.
   *
   * @memberof viewfinder.query
   * @param {Object} contactSelection A viewfinder contact invalidation.
   * @param {Function} visitor A visitor function which will be invoked once for each user
   *   returned by the query.
   * 
   * @returns {jQuery.Deferred} A jQuery deferred object which will resolve when all user data has
   *   been visited.
   */
  function visitContacts(contactSelection, visitor) {
    var deferred = $.Deferred();
    var request = _(requestTemplate).clone();
    if (contactSelection.start_key) {
      request.start_key = contactSelection.start_key;
    }
    request.limit = requestSelectionLimit;
    
    function sendQuery() {
      serviceRequest('query_contacts', request).done(doneQuery).fail(failQuery);
    }
    
    function doneQuery(response) {
      var isLastQuery = (response.contacts.length < requestSelectionLimit);
      
      // Send out request for the next page of data, if it exists.
      if (!isLastQuery) {
        request.start_key = response.last_key;
        sendQuery();
      }
      
      // Invoke the visitor with the returned data for this viewpoint.
      _(response.contacts).each(function (c) {
        if ('contact_user_id' in c) {
          // For the sake of consistent ids, change 'contact_user_id' to 'user_id'. 
          c.user_id = c.contact_user_id;
          delete c.contact_user_id;
        }
        
        visitor(c);
      });
      
      // If this was the last page of the query, resolve this method's promise.
      if (isLastQuery) deferred.resolve();
    }
    
    function failQuery(jqHxr, textStatus) {
      deferred.reject('Error from visitContacts: ' + textStatus);
    }
    
    sendQuery();
    return deferred;
  }

  function updateViewedSeq(viewpoint_id, viewed_seq) {
    function doUpdate(asset_id_response) {
      var request = getRequestTemplate();
      request.headers.op_id = asset_id_response.asset_ids[0];
      request.headers.op_timestamp = asset_id_response.timestamp;

      request.follower = {
        viewpoint_id : viewpoint_id,
        viewed_seq : viewed_seq
      };

      return serviceRequest('update_follower', request);
    }

    return getAssetIds(['o']).pipe(doUpdate);
  }

  function postComment(viewpoint_id, message, asset_id) {
    function doPost(asset_id_response) {
      var request = getRequestTemplate();
      request.headers.op_id = asset_id_response.asset_ids[0];
      request.headers.op_timestamp = asset_id_response.timestamp;
      request.activity = {
        activity_id : asset_id_response.asset_ids[1],
        timestamp : asset_id_response.timestamp
      };
      request.viewpoint_id = viewpoint_id;
      request.comment_id = asset_id_response.asset_ids[2];
      request.timestamp = asset_id_response.timestamp;
      request.message = message;
      if (asset_id) {
        request.asset_id = asset_id;
      }

      return serviceRequest('post_comment', request).pipe(function () {
        return {
          comment: {
            viewpoint_id : viewpoint_id,
            comment_id : request.comment_id,
            asset_id : request.asset_id,
            timestamp : request.timestamp,
            message : request.message,
            user_id : viewfinder.own_user.user_id
          },
          activity : {
            type : 'post_comment',
            viewpoint_id : viewpoint_id,
            activity_id : request.activity.activity_id,
            timestamp : request.activity.timestamp,
            user_id : viewfinder.own_user.user_id,
            properties : {
              comment_id : request.comment_id
            }
          }
        };
      });
    }

    return getAssetIds(['o', 'a', 'c']).pipe(doPost);
  }
  
  // *****************************
  //    ACCOUNT MANAGEMENT
  // *****************************
  function login(identity, password, use_session_cookie) {
    var request = getRequestTemplate();
    request.auth_info = {
      identity : identity,
      password : password
    };

    if (use_session_cookie) {
      request.use_session_cookie = true;
    }
    
    return sendRequest('/login/viewfinder', request);
  }
  
  function register(identity, password, given_name, family_name) {
    var request = getRequestTemplate();
    request.auth_info = {
      identity : identity,
      password : password,
      name : given_name + ' ' + family_name,
      given_name : given_name,
      family_name : family_name
    };
    
    return sendRequest('/register/viewfinder', request);
  }
  
  function verify(identity, access_token) {
    var request = getRequestTemplate();
    request.identity = identity;
    request.access_token = access_token;
    
    return sendRequest('/verify/viewfinder', request);
  }
  
  function confirmPassword(password) {
    var request = getRequestTemplate();
    request.password = password;
    
    return sendRequest(window.location.pathname, request);
  }
  
  function resetPassword(identity) {
    var request = getRequestTemplate();
    request.auth_info = { identity : identity };
    
    return sendRequest('/login_reset/viewfinder', request);
  }
  
  function updatePassword(newPassword) {
    function doUpdatePassword(asset_id_response) {
      var op_id = asset_id_response.asset_ids[0];
      var request = getRequestTemplate();
      request.headers.op_id = op_id;
      request.headers.op_timestamp = asset_id_response.timestamp;
      request.password = newPassword;
       
      return serviceRequest('update_user', request);
    }
    
    return getAssetIds(['o']).pipe(doUpdatePassword);
  }
  
  function sendMergeToken(identity) {
    var request = getRequestTemplate();
    request.identity = identity;
    
    return sendRequest('/merge_token/viewfinder', request); 
  }
  
  function mergeAccount(source_user_cookie, identity, access_token) {
    function doMergeAccount(asset_id_response) {
      var request = getRequestTemplate();
      request.headers.op_id = asset_id_response.asset_ids[0];
      request.headers.op_timestamp = asset_id_response.timestamp;
      request.activity = {
        activity_id : asset_id_response.asset_ids[1],
        timestamp : asset_id_response.timestamp
      };
        
      if (source_user_cookie) {
        request.source_user_cookie = source_user_cookie;
      } else {
        request.source_identity = {
          identity : identity, 
          access_token : access_token
        };
      }
      
      return serviceRequest('merge_accounts', request);
    }
    
    return getAssetIds(['o', 'a']).pipe(doMergeAccount);
  }

  function mergeIdentity(identity, access_token) {
    return mergeAccount(null, identity, access_token);
  }

  function requestArchive(email) {
    var request = getRequestTemplate();
    request.email = email;
    return serviceRequest('build_archive', request);
  }
  
  /**********
   * Returns a list of asset ids generated by the server.
   */
  function getAssetIds(prefix_list) {
    var request = _(requestTemplate).clone();
    request.asset_types = prefix_list;
    
    return serviceRequest('allocate_ids', request)
      .pipe(function (result) {
        return result;
      });
  }

  
  /**
   * Dispatches a single ajax POST query to the viewfinder service interface
   *
   * @private
   * @param {Function} method The viewfinder RPC method to call.
   * @param {Object} queryRequest JSON object to send as the body of the request.
   * 
   * @returns {jQuery.Deferred} A jQuery deferred object which will resolve when the request
   *   has completed.
   */
  function serviceRequest(method, queryRequest) {
    return sendRequest('/service/' + method, queryRequest);
  }

  /**
   * Dispatches a single ajax POST query to the viewfinder backend.
   *
   * @private
   * @param {Function} method The viewfinder RPC method to call.
   * @param {Object} queryRequest JSON object to send as the body of the request.
   * 
   * @returns {jQuery.Deferred} A jQuery deferred object which will resolve when the request
   *   has completed.
   */
  function sendRequest(method, queryRequest) {
    return $.ajax({
      headers : {"X-Xsrftoken": _vf_xsrf_token},
      url : method,
      type : 'POST',
      processData : false,
      data : JSON.stringify(queryRequest),
      contentType : 'application/json; charset=UTF-8',
      dataType : 'json'
    });
  }
  
  function getRequestTemplate() {
    return {
      headers : {
        version: viewfinder.messageVersion
      }
    };
  }
  
  // Publish public functions to the namespaces.
  _.extend(query, {
    visitFollowed : visitFollowed,
    visitViewpoints : visitViewpoints,
    visitEpisodes : visitEpisodes,
    visitNotifications : visitNotifications,
    getLastNotificationId : getLastNotificationId,
    visitUsers : visitUsers,
    visitContacts : visitContacts,
    updateViewedSeq : updateViewedSeq,
    postComment : postComment
  });
  
  _.extend(account, {
    login : login,
    register : register,
    verify : verify,
    confirmPassword : confirmPassword,
    resetPassword : resetPassword,
    updatePassword : updatePassword,
    sendMergeToken : sendMergeToken,
    mergeAccount : mergeAccount,
    mergeIdentity : mergeIdentity,
    requestArchive : requestArchive
  });
  
})(jQuery, viewfinder.query, viewfinder.account);

