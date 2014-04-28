package com.hello;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.util.Log;

import com.google.android.gcm.GCMBaseIntentService;
import com.google.android.gcm.GCMRegistrar;

public class GCMIntentService extends GCMBaseIntentService {
//  static final String SERVER_URL = "http://192.168.1.10:8080/gcm-demo";
  public static final String SENDER_ID = "1068184763319";

  public GCMIntentService() {
    super(SENDER_ID);
  } 

  protected void onRegistered(Context context, String registrationId) {
    Log.i(HelloActivity.TAG, "Device registered: regId = " + registrationId);
    Utils.savePreference(getApplicationContext(), "gcm_id", registrationId);
  }

  protected void onUnregistered(Context context, String registrationId) {
    Log.i(HelloActivity.TAG, "Device unregistered: regId = " + registrationId);
  }

  protected void onMessage(Context context, Intent intent) {
    Log.i(HelloActivity.TAG, "Received message: " + intent.getExtras().toString());
  }

  public void onError(Context context, String errorId) {
    Log.i(HelloActivity.TAG, "Received error: " + errorId);
  }

  protected boolean onRecoverableError(Context context, String errorId) {
    Log.i(HelloActivity.TAG, "Received recoverable error: " + errorId);
    return false;
  }
}
