viewfinder.test = {};
viewfinder.test.ident = {};

(function(ident) {
  function sendRequest(url, request) {
    return $.ajax({
      headers : {"X-Xsrftoken": _vf_xsrf_token},
      url : url,
      type : 'POST',
      processData : false,
      data : JSON.stringify(request),
      contentType : 'application/json; charset=UTF-8',
      dataType : 'json',
    });
  }
  
  function getAssetIds(prefix_list) {
    var request = {
      headers : {
        version : viewfinder.messageVersion
      },
      
      asset_types : prefix_list
    };
    
    return sendRequest('/service/allocate_ids', request);
  }
  
  ident.register = function (email, first, last, password) {
    password = password || 'testpass';
    
    var request = {
      headers: {
        version: viewfinder.messageVersion
      },
      
      auth_info : {
        identity : 'Email:' + email,
        name : first + ' ' + last,
        given_name : first,
        family_name : last, 
        password : password
      }
    };
    
    sendRequest('/register/fakeviewfinder', request)
      .done(function(){
        window.location = '/';
      });
  };

  ident.login = function (email) {
    var request = {
      headers: {
        version: viewfinder.messageVersion
      },
      auth_info : {
        identity : 'Email:' + email
      }
    };
    
    sendRequest('/login/fakeviewfinder', request)
      .done(function(){
        window.location = '/';
      });
  };
  
  viewfinder.test.ident.addProspectiveFollower = function (email, name, viewpoint_id, asset_ids) {
    function addFollower (asset_ids) {
      var request = {
        headers : {
          version: viewfinder.messageVersion,
          op_id: asset_ids.op_id,
          op_timestamp: asset_ids.timestamp
        },
        activity : {
          activity_id : asset_ids.activity_id,
          timestamp: asset_ids.timestamp
        },
        viewpoint_id : viewpoint_id,
        contacts : [{ 
          identity : 'Email:' + email,
          name: name
        }]
      };
      
      console.log(asset_ids);
      
      sendRequest('/service/add_followers', request);
    }
    
    if (!asset_ids) {
       getAssetIds(['o', 'a']).pipe(function (result) {
         addFollower({
           op_id : result.asset_ids[0],
           activity_id : result.asset_ids[1],
           timestamp : result.timestamp
         });
       });
    } else {
      addFollower(asset_ids);
    } 
  };
})(viewfinder.test.ident);
