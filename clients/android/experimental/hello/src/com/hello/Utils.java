package com.hello;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Looper;
import android.util.Log;
import java.lang.Thread;

public class Utils {
  public static String osRelease() { 
    return Build.VERSION.RELEASE;
  }

  public static String deviceMakeModel() {
    return Build.MANUFACTURER + " " + Build.MODEL;
  }

  public static String deviceHost() {
    return Build.HOST;
  }

  public static void savePreference(Context context, String name, String value) {
    SharedPreferences settings = context.getSharedPreferences(SettingsActivity.PREFS_NAME, 0);
    SharedPreferences.Editor editor = settings.edit();
    editor.putString(name, value);
    Log.i(HelloActivity.TAG, "Saving setting: " + name + "=" + value);

    editor.commit();
  }

  public static String loadPreference(Context context, String name) {
    SharedPreferences settings = context.getSharedPreferences(SettingsActivity.PREFS_NAME, 0);
    String value = settings.getString(name, null);
    Log.i(HelloActivity.TAG, "Loading setting: " + name + "=" + value);
    return value;
  }

  public static void saveIntPreference(Context context, String name, int value) {
    SharedPreferences settings = context.getSharedPreferences(SettingsActivity.PREFS_NAME, 0);
    SharedPreferences.Editor editor = settings.edit();
    editor.putInt(name, value);
    Log.i(HelloActivity.TAG, "Saving setting: " + name + "=" + value);

    editor.commit();
  }

  public static int loadIntPreference(Context context, String name) {
    SharedPreferences settings = context.getSharedPreferences(SettingsActivity.PREFS_NAME, 0);
    int value = settings.getInt(name, -1);
    Log.i(HelloActivity.TAG, "Loading setting: " + name + "=" + value);
    return value;
  }

  public static void assertIsUIThread() {
    assert Looper.getMainLooper().getThread() == Thread.currentThread();
  }
}
