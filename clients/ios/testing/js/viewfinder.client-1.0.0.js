
  var Viewfinder = function() {
    var baseUrl = 'https://www.goviewfinder.com:8443';

    return {
      send_ajax: function (path, request, args, successCallback, errorCallback) {

        $.ajax({
          // TODO: apply args here
          Accept : "application/json; charset=utf-8",
          url : path,
          processData : false,
          type : 'POST',
          data : JSON.stringify(request),
          contentType : 'application/json; charset=UTF-8',
          dataType : 'json',
          success: function (result) {
            successCallback(result);
          },
          error: function (xhr, ajaxOptions, thrownError) {
            errorCallback(xhr, ajaxOptions, thrownError);
          }
        });
      },
      send: function(path, request, args) {
        url = baseUrl + path;
        var target = UIATarget.localTarget();
        target.setTimeout(0);
        var host = target.host();
        var json_request = [];
        if (args) {
          for (var i=0; i<args.length; i++) {
            json_request.push(args[i]);
          }
        }
        var count = json_request.length;
        json_request[count++] = '-HAccept-Encoding: application/json';
        json_request[count++] = '-HContent-type: application/json';
        json_request[count++] = '-HX-XSRFToken: fake_xsrf';
        json_request[count++] = '-XPOST';
        json_request[count++] = '-bdata/cookies.txt';
        json_request[count++] = '-cdata/cookies.txt';
        json_request[count++] = '-b_xsrf=fake_xsrf';
        json_request[count++] = '-f';
        json_request[count++] = '-d'+JSON.stringify(request);
        json_request[count++] = '-k';
        json_request[count++] = url;

        var result = host.performTaskWithPathArgumentsTimeout(curl_path, json_request, 10);

        // handle success
        if (result.exitCode == 0) {
          return result;
        }
        else {
          throw new Exception("An error occured contacting server.");
        }
      },
      md5: function(path) {
        var target = UIATarget.localTarget();
        target.setTimeout(0);
        var host = target.host();
        var args = [path];
        var result = host.performTaskWithPathArgumentsTimeout('/sbin/md5', args, 5);
        result.hash = null;
        if (result.exitCode == 0) {
          result.hash = result.stdout.split("=")[1].trim();
        }
        return result;
      },
      stringify: function(request) {
        return JSON.stringify(request);
      },
      register: function(request, args) {
        return this.send('/register/fakeviewfinder', request, args);
      },
      login: function(request, args) {
        return this.send('/login/fakeviewfinder', request, args);
      },
      copy_image: function(request, args) {
        return this.send('/testing/hook/copy', request, args);
      },
      copy_image_ajax: function(request, args, success, error) {
        this.send_ajax('/testing/hook/copy', request, args, success, error);
      },
      delete_image: function(request, args) {
        return this.send('/testing/hook/delete', request, args);
      },
      add_followers:  function(request, args) {
        return this.send('/service/add_followers', request, args);
      },
      allocate_ids:  function(request, args) {
        return this.send('/service/allocate_ids', request, args);
      },
      verify:  function(request, args) {
        return this.send('/verify/viewfinder', request, args);
      },
      post_comment:  function(request, args) {
        return this.send('/service/post_comment', request, args);
      },
      query_followed:  function(request, args) {
        return this.send('/service/query_followed', request, args);
      },
      merge_accounts:  function(request, args) {
        return this.send('/service/merge_accounts', request, args);
      },
      terminate_account: function(request, args) {
        return this.send('/service/terminate_account', request, args);
      },
      get_opid: function(request, args) {
        return this.send('/testing/hook/getopid', request, args);
      },
      get_access_code: function(request, args) {
        return this.send('/testing/hook/token', request, args);
      },
      is_image_equal: function(request, args) {
        return this.send('/testing/hook/image', request, args);
      },
    };

  };





