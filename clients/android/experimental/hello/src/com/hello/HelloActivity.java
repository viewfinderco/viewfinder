package com.hello;

import android.app.Activity;
import android.app.ListFragment;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.ListView;
import java.io.File;

import com.google.android.gcm.GCMRegistrar;

import com.hello.LocalDB;

public class HelloActivity extends Activity {
  static {
    System.loadLibrary("native_hello");
    System.loadLibrary("native_cpp_hello");
    System.loadLibrary("localdb");
  }

  public static final String TAG = "HelloActivity";
  public static final String[] ACTIONS = {
    "JSON HTTPS Post",
    "Capture Photo",
    "Settings",
    "View FAQ (external)",
    "Log with native C",
    "Dynamic List",
    "Try LevelDB",
  };

  /** Called when the activity is first created. */
  @Override
  public void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.menu_layout);

    // Verify GCM setup and register.
    GCMRegistrar.checkDevice(this);
    GCMRegistrar.checkManifest(this);
    Log.i(HelloActivity.TAG, "Registering with GCM");
    final String regId = GCMRegistrar.getRegistrationId(this);
    if (regId.equals("")) {
      GCMRegistrar.register(this, GCMIntentService.SENDER_ID);
    } else {
      Log.i(HelloActivity.TAG, "Already registered, ID: " + regId);
      Utils.savePreference(getApplicationContext(), "gcm_id", regId);
    }
  }

  public static class MenuFragment extends ListFragment {
    @Override
    public void onActivityCreated(Bundle savedInstanceState) {
      super.onActivityCreated(savedInstanceState);
      setListAdapter(new ArrayAdapter<String>(getActivity(),
                     android.R.layout.simple_list_item_activated_1, HelloActivity.ACTIONS));
    }

    @Override
    public void onListItemClick(ListView l, View v, int position, long id) {
      Log.i(HelloActivity.TAG, "Got list click: " + position + " ID: " + id);
      Intent intent = new Intent();
      if (position == 0) {
        intent.setClass(getActivity(), HttpsFetchActivity.class);
      } else if (position == 1) {
        intent.setClass(getActivity(), CapturePhotoActivity.class);
      } else if (position == 2) {
        intent.setClass(getActivity(), SettingsActivity.class);
      } else if (position == 3) {
        Uri uri = Uri.parse("https://www.viewfinder.co/faq");
        intent.setAction(Intent.ACTION_VIEW);
        intent.setData(uri);
      } else if (position == 4) {
        nativeLog("Logging this using native C code");
        nativeCPPLog("Logging this using native C++ code");
        return;
      } else if (position == 5) {
        intent.setClass(getActivity(), DynamicListActivity.class);
      } else if (position == 6) {
        // Init and test calls to LocalDB here.
        LocalDB localdb = null;
        try {
          localdb = new LocalDB(getActivity().getApplicationContext().getFilesDir() + "/Database");
          localdb.SetValue("timer0", "is_it_time0");
          localdb.SetValue("timer5", "is_it_time5");
          localdb.SetValue("timer7", "is_it_time7");
          localdb.SetValue("timer13", "is_it_time13");
          String s = localdb.GetValue("timer4");
          if (s == null) {
            System.out.println("null value returned");
          } else {
            System.out.println("Value returned: " + s);
          }
          localdb.DumpValues();
        } catch (LocalDB.LoadFailedException e) {
          System.out.println("LocalDB.LoadFailedException");
        } finally {
          if (localdb != null)
            localdb.dispose();
        }
    	  return;
      }
      startActivity(intent);
    }
  }

  // Implemented in jni/native.c
  private static native void nativeLog(String logThis);
  // Implemented in jni/native_cpp.cpp
  private static native void nativeCPPLog(String logThis);
}
