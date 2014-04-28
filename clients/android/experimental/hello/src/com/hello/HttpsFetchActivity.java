package com.hello;

import com.hello.Utils;

import android.app.Activity;
import android.content.Context;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;
import java.util.ArrayList;
import java.util.List;
import org.apache.http.NameValuePair;
import org.apache.http.message.BasicNameValuePair;
import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONException;
import org.json.JSONTokener;


public class HttpsFetchActivity extends Activity implements DownloadCaller {
  // Called when the activity is first created.

  public static final int PING_REQUEST = 1;
  public static final int LOGIN_REQUEST = 2;
  public static final int VERIFY_REQUEST = 3;
  public static final int QUERY_NOTIFICATIONS_REQUEST = 4;

  public void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.https_fetch);

    // Log device info.
    Log.i(HelloActivity.TAG, "OS version: " + Utils.osRelease());
    Log.i(HelloActivity.TAG, "Device: " + Utils.deviceMakeModel());
    Log.i(HelloActivity.TAG, "Host: " + Utils.deviceHost());
  }

  private String getBoxContent(int box_id, String description) {
    EditText editText = (EditText) findViewById(box_id);
    if (editText == null) {
      Log.w(HelloActivity.TAG, "No EditText view with id " + box_id + " desc: " + description);
      Toast.makeText(getApplicationContext(), "No box with id " + box_id + " desc: " + description,
                     Toast.LENGTH_SHORT).show();
      return null;
    }
    String content = editText.getText().toString();
    // "".equals returns true for both null and empty string. It's like "not X" in python.
    if ("".equals(content)) {
      Log.w(HelloActivity.TAG, "Empty EditText view with id " + box_id + " desc: " + description);
      Toast.makeText(getApplicationContext(), "Empty box with id " + box_id + " desc: " + description,
                     Toast.LENGTH_SHORT).show();
      return null;
    }
    Log.i(HelloActivity.TAG, "EditText with id " + box_id + " desc: " + description + ": " + content);
    return content;
  }

  public void clickButton(View view) {
    String url = getBoxContent(R.id.url_box, "url");
    if (url == null) {
      return;
    }

    if (!connectionDescription()) {
      Toast.makeText(getApplicationContext(), "No network connection", Toast.LENGTH_SHORT).show();
      return;
    }

    if (view.getId() == R.id.ping_button) {
      JSONObject req;
      try {
        req = ServerUtils.getPingRequest(getApplicationContext());
      } catch (JSONException e) {
        Log.w(HelloActivity.TAG, "Error formatting request" + e.toString());
        return;
      }
      new Download(getApplicationContext(), PING_REQUEST, url + "/ping", req, this).execute();
    } else if (view.getId() == R.id.login_button) {
      String email = getBoxContent(R.id.email_box, "email");
      if (email == null) {
        return;
      }
      JSONObject req;
      try {
        req = ServerUtils.getLoginRequest(getApplicationContext(), email);
      } catch (JSONException e) {
        Log.w(HelloActivity.TAG, "Error formatting request" + e.toString());
        return;
      }
      new Download(getApplicationContext(), LOGIN_REQUEST, url + "/login/viewfinder", req, this).execute();
    } else if (view.getId() == R.id.verify_button) {
      String email = getBoxContent(R.id.email_box, "email");
      String token = getBoxContent(R.id.access_token_box, "access token");
      if (email == null || token == null) {
        return;
      }
      JSONObject req;
      try {
        req = ServerUtils.getVerifyRequest(getApplicationContext(), email, token);
      } catch (JSONException e) {
        Log.w(HelloActivity.TAG, "Error formatting request" + e.toString());
        return;
      }
      new Download(getApplicationContext(), VERIFY_REQUEST, url + "/verify/viewfinder", req, this).execute();
    } else if (view.getId() == R.id.query_notifications_button) {
      JSONObject req;
      try {
        req = ServerUtils.getQueryNotificationsRequest(getApplicationContext());
      } catch (JSONException e) {
        Log.w(HelloActivity.TAG, "Error formatting request" + e.toString());
        return;
      }
      new Download(getApplicationContext(), QUERY_NOTIFICATIONS_REQUEST,
                   url + "/service/query_notifications", req, this).execute();
    } else {
      Log.i(HelloActivity.TAG, "Got other id: " + view.getId());
    }
  }

  // From DownloadCaller interface.
  public void downloadFinished(Download download_task) {
    Toast.makeText(getApplicationContext(), "HTTP Response: " + download_task.responseCode(),
                   Toast.LENGTH_SHORT).show();
    if (download_task.responseCode() != 200) {
      return;
    }
    int id = download_task.id();
    if (id == PING_REQUEST || id == LOGIN_REQUEST) {
      return;
    } else if (id == VERIFY_REQUEST) {
      try {
        JSONTokener tokenizer = new JSONTokener(download_task.result());
        JSONObject obj = (JSONObject) tokenizer.nextValue();
        Log.i(HelloActivity.TAG, "JSON Object: " + obj.toString());
        int user_id = obj.getInt("user_id");
        int device_id = obj.getInt("device_id");
        Utils.saveIntPreference(getApplicationContext(), "user_id", user_id);
        Utils.saveIntPreference(getApplicationContext(), "device_id", device_id);
      } catch (JSONException e) {
        Log.w(HelloActivity.TAG, "Error parsing request" + e.toString());
        return;
      }
    } else if (id == QUERY_NOTIFICATIONS_REQUEST) {
      try {
        JSONTokener tokenizer = new JSONTokener(download_task.result());
        JSONObject obj = (JSONObject) tokenizer.nextValue();
        Log.i(HelloActivity.TAG, "JSON Object: " + obj.toString());
        String last_key = obj.getString("last_key");
        JSONArray notifications = obj.getJSONArray("notifications");
        Log.i(HelloActivity.TAG, "Last key: " + last_key + " num_notifications: " + notifications.length());
      } catch (JSONException e) {
        Log.w(HelloActivity.TAG, "Error parsing request" + e.toString());
        return;
      }
    }
  }

  public boolean connectionDescription() {
    // Requires:
    // <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    ConnectivityManager connMgr = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
    NetworkInfo info = connMgr.getActiveNetworkInfo();
    if (info == null) {
      return false;
    }
    String ret = "Connected: " + info.isConnected();
    if (info.isConnected()) {
      ret += " type: " + info.getTypeName();
    }
    // Log levels: Log.v() Log.d() Log.i() Log.w() and Log.e() 
    Log.i(HelloActivity.TAG, ret);
    return info.isConnected();
  }
}
