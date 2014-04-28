package co.viewfinder;

import android.app.Activity;
import android.content.Context;
import android.content.BroadcastReceiver;
import android.content.Intent;
import android.util.Log;

import com.google.android.gms.gcm.GoogleCloudMessaging;

public class GCMBroadcastReceiver extends BroadcastReceiver {
  public static final String SENDER_ID = "1068184763319";
  private static final String TAG = "viewfinder.GCMBroadcastReceiver";

  @Override
  public void onReceive(Context context, Intent intent) {
    GoogleCloudMessaging gcm = GoogleCloudMessaging.getInstance(context);
    String messageType = gcm.getMessageType(intent);

    if (GoogleCloudMessaging.MESSAGE_TYPE_SEND_ERROR.equals(messageType)) {
      Log.d(TAG, "Send error: " + intent.getExtras().toString());
    } else if (GoogleCloudMessaging.MESSAGE_TYPE_DELETED.equals(messageType)) {
      Log.d(TAG, "Deleted messages on server: " + intent.getExtras().toString());
    } else {
      Log.d(TAG, "Received: " + intent.getExtras().toString());
    }
    setResultCode(Activity.RESULT_OK);
  }
}
