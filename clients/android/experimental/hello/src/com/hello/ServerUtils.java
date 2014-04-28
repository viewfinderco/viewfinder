package com.hello;

import android.content.Context;
import org.json.JSONObject;
import org.json.JSONException;

public class ServerUtils {
  public static JSONObject getHeaders() throws JSONException {
    JSONObject obj = new JSONObject();
    obj.put("version", 15);
    return obj;
  }

  public static JSONObject getDeviceDict(Context context) throws JSONException {
    JSONObject obj = new JSONObject();
    obj.put("platform", Utils.deviceMakeModel());
    obj.put("os", Utils.osRelease());
    String gcm_id = Utils.loadPreference(context, "gcm_id");
    if (gcm_id != null && !"".equals(gcm_id)) {
      obj.put("push_token", "gcm:" + gcm_id);
    }
    int device_id = Utils.loadIntPreference(context, "device_id");
    if (device_id > 0) {
      obj.put("device_id", device_id);
    }
    String device_uuid = Utils.loadPreference(context, "device_uuid");
    if (device_uuid != null && !"".equals(device_uuid)) {
      obj.put("device_uuid", device_uuid);
    }
    return obj;
  }

  public static JSONObject getPingRequest(Context context) throws JSONException {
    JSONObject obj = new JSONObject();
    obj.put("headers", getHeaders());
    obj.put("device", getDeviceDict(context));
    return obj;
  }

  public static JSONObject getLoginRequest(Context context, String email) throws JSONException {
    JSONObject obj = new JSONObject();
    obj.put("headers", getHeaders());
    obj.put("device", getDeviceDict(context));
    JSONObject auth_obj = new JSONObject();
    auth_obj.put("identity", "Email:" + email);
    obj.put("auth_info", auth_obj);
    return obj;
  }

  public static JSONObject getVerifyRequest(Context context, String email, String access_token) throws JSONException {
    JSONObject obj = new JSONObject();
    obj.put("headers", getHeaders());
    obj.put("identity", "Email:" + email);
    obj.put("access_token", access_token);
    return obj;
  }

  public static JSONObject getQueryNotificationsRequest(Context context) throws JSONException {
    JSONObject obj = new JSONObject();
    obj.put("headers", getHeaders());
    return obj;
  }
}
