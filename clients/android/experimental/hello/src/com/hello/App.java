package com.hello;

import android.app.Application;
import android.graphics.Typeface;
import android.util.Log;
import java.util.UUID;

public class App extends Application {
  private String deviceUUID;
  private static final String kProximaNovaRegularFile = "fonts/ProximaNovaAlt-Reg-Mod.ttf";
  private static final String kProximaNovaBoldFile = "fonts/ProximaNovaAlt-Bold-Mod.ttf";
  private Typeface kProximaNovaRegularTypeface = null;
  private Typeface kProximaNovaBoldTypeface = null;

  private PhotoTable photoTable;

  public void onCreate() {
    super.onCreate();
    deviceUUID = Utils.loadPreference(getApplicationContext(), "device_uuid");
    if (deviceUUID == null) {
      deviceUUID = UUID.randomUUID().toString();
      Utils.savePreference(getApplicationContext(), "device_uuid", deviceUUID);
    }
    loadFonts();
    loadPhotos();
  }

  public String getDeviceUUID() {
    return deviceUUID;
  }

  private void loadFonts() {
    kProximaNovaRegularTypeface = Typeface.createFromAsset(getAssets(), kProximaNovaRegularFile);
    kProximaNovaBoldTypeface = Typeface.createFromAsset(getAssets(), kProximaNovaBoldFile);
  }

  private void loadPhotos() {
    photoTable = new PhotoTable(getApplicationContext());
    // Scans photos in background.
    photoTable.execute();
  }

  public PhotoTable getPhotoTable() {
    return photoTable;
  }

  public Typeface getProximaNovaRegularTypeface() {
    return kProximaNovaRegularTypeface;
  }

  public Typeface getProximaNovaBoldTypeface() {
    return kProximaNovaBoldTypeface;
  }
}
