// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.ActivityManager;
import android.content.Context;
import android.util.DisplayMetrics;
import android.view.WindowManager;

import android.app.Application;
import android.content.res.XmlResourceParser;
import android.content.SharedPreferences;
import android.os.AsyncTask;
import android.os.Looper;
import android.util.Log;
import android.widget.Toast;
import java.io.IOException;
import java.io.File;
import java.io.InputStream;
import java.io.FileOutputStream;
import java.util.UUID;
import org.apache.commons.io.IOUtils;
import org.apache.commons.io.FilenameUtils;

import co.viewfinder.proto.ContactMetadataPB;
import junit.framework.Assert;

import com.google.android.gms.gcm.GoogleCloudMessaging;

/**
 * AppState holds all application global state.
 */
public class AppState extends Application {
  static {
    // TODO(marc): for gyp to generate a nicer name for this.
    System.loadLibrary("_clients_android_jni_viewfinder_gyp");
  }

  private static final String TAG = "viewfinder.AppState";
  private static final String PREFS_NAME = "ViewfinderPreferences";

  private static final String DEVICE_UUID_KEY = "device_uuid";
  private static final String OPERATION_ID_KEY = "next_operation_id";

  private static final String TEST_HOST = "www.goviewfinder.com";
  private static final String PROD_HOST = "www.viewfinder.co";

  private static final int TEST_PORT = 8443;
  private static final int PROD_PORT = 443;

  private String mAppVersion = "Unknown";
  private String mBuildTarget = "Unknown";
  private boolean mUseProductionBackend = false;
  private boolean mUnlinkAtStartup = false;
  private String mTestHost = null;
  private String mServerHost = null;
  private int mServerPort = 0;

  private long mNativeState = 0;

  private DB mDB = null;
  private ActivityTable mActivityTable = null;
  private ContactManager mContactManager = null;
  private DayTable mDayTable = null;
  private EpisodeTable mEpisodeTable = null;
  private NetworkManager mNetworkManager = null;
  private PhotoStorage mPhotoStorage = null;
  private PhotoTable mPhotoTable = null;
  private ViewpointTable mViewpointTable = null;
  private StatusManager mStatusManager = null;
  private ViewDataSim mViewDataSim = null;
  private BitmapFetcher mBitmapFetcher = null;

  private int mStatusBarHeightPixels = -1;
  private DisplayMetrics mDisplayMetrics = null;

  public AppState() {
    super();
    Log.d(TAG, "AppState()");
  }

  public DB db() { return mDB; }
  public ActivityTable activityTable() { return mActivityTable; }
  public ContactManager contactManager() { return mContactManager; }
  public DayTable dayTable() { return mDayTable; }
  public EpisodeTable episodeTable() { return mEpisodeTable; }
  public NetworkManager networkManager() { return mNetworkManager; }
  public PhotoStorage photoStorage() { return mPhotoStorage; }
  public PhotoTable photoTable() { return mPhotoTable; }
  public ViewpointTable viewpointTable() { return mViewpointTable; }
  public StatusManager statusManager() { return mStatusManager; }
  public BitmapFetcher bitmapFetcher() { return mBitmapFetcher; }

  public String appVersion() { return mAppVersion; }
  public String getServerHost() { return mServerHost; }
  public int getServerPort() { return mServerPort; }
  public ViewData getViewData() { return mViewDataSim; }
  public boolean isDevBuild() { return mBuildTarget.equals("debug"); }

  public int getStatusBarHeightPixels() { return mStatusBarHeightPixels; }
  public int getDisplayWidthPixels() { return mDisplayMetrics.widthPixels; }
  public int getDisplayHeightPixels() { return mDisplayMetrics.heightPixels; }

  public void onCreate() {
    Log.d(TAG, "onCreate()");

    // The properties.xml file defines some run-time behavior, load it first.
    loadXMLProperties();
    // Determine the server host from the config.
    setupServerHost();

    // Get any dynamics display properties that will be used to generate views.
    initDisplayMetrics();
    // Copy ICU data from raw assets to local file. Must be done before LoadNative.
    initICUData();

    if (mUnlinkAtStartup) {
      unlinkDevice();
    }

    Log.i(TAG, "Preparing to load native app state");
    mNativeState = LoadNative(getFilesDir().toString(), mUnlinkAtStartup, getServerPort());

    mDB = new DB(GetDBHandle(mNativeState));
    mActivityTable = new ActivityTable(GetActivityTable(mNativeState));
    mContactManager = new ContactManager(this, GetContactManager(mNativeState));
    mDayTable = new DayTable(this, GetDayTable(mNativeState));
    mEpisodeTable = new EpisodeTable(GetEpisodeTable(mNativeState));
    mNetworkManager = new NetworkManager(
        this, GetNetworkManager(mNativeState), mUseProductionBackend,
        GetUserCookie(mNativeState), GetXsrfCookie(mNativeState));
    mPhotoStorage = new PhotoStorage(GetPhotoStorage(mNativeState));
    mPhotoTable = new PhotoTable(GetPhotoTable(mNativeState));
    mViewpointTable = new ViewpointTable(GetViewpointTable(mNativeState));

    RunMaintenance(mNativeState, mUnlinkAtStartup);

    Utils.dumpBuildInfo();

    initBitmapFetcher();

    mStatusManager = new StatusManager(this);


    getDeviceUUID();
    registerGCM();

    // TODO: Use lifecycle callbacks to notify native app state of app
    // becoming active as well as when it will resign active.
    // We could possibly use registerActivityLifecycleCallbacks, but it's API
    // level 14 and still deals with activities, so we'd need to interpret
    // these based on the activity stack.
    //
    // I found some other options on stackoverflow, but they don't
    // look very promising. As is, we're going to get the
    // app-did-become-active callback once upon creation and never
    // again. We'll never get the app-will-resign-active callback.

    // Fire up simulated data to drive UI.
    mViewDataSim = new ViewDataSim(this);
    mViewDataSim.Launch();

    super.onCreate();

    // Tell the native app state we are ready.
    AppDidBecomeActive(mNativeState);
  }

  private void setupServerHost() {
    String testHost = mTestHost == null ? TEST_HOST : mTestHost;
    mServerHost = mUseProductionBackend ? PROD_HOST : testHost;
    mServerPort = mUseProductionBackend ? PROD_PORT : TEST_PORT;
  }

  private void initDisplayMetrics() {
    int resourceId =  getResources().getIdentifier("status_bar_height", "dimen", "android");
    if (resourceId > 0) {
      mStatusBarHeightPixels = getResources().getDimensionPixelSize(resourceId);
    } else {
      mStatusBarHeightPixels = 25;  // This is correct for some devices, but definitely not all.
      Log.w(TAG, String.format("Unable to find resource for status_bar_height. Defaulting to %d pixels.",
                               mStatusBarHeightPixels));
    }
    mDisplayMetrics = new DisplayMetrics();
    ((WindowManager)getSystemService(Context.WINDOW_SERVICE)).getDefaultDisplay().getMetrics(mDisplayMetrics);
  }

  @Override
  public void onTerminate() {
    Log.d(TAG, "onTerminate");
    if (mNativeState != 0) {
      UnloadNative(mNativeState);
      mNativeState = 0;
    }
    mNetworkManager.onTerminate();
    super.onTerminate();
  }

  private void initBitmapFetcher() {
    ActivityManager am = (ActivityManager)getSystemService(Context.ACTIVITY_SERVICE);
    int memoryClassBytes = am.getMemoryClass() * 1024 * 1024;
    // Google/Android folks recommend using 1/8 of memoryClassBytes for image caching.
    // Because we're a photo heavy app, let's do 1/4 of memoryClassBytes.
    mBitmapFetcher = new BitmapFetcher(this, memoryClassBytes / 4);
  }

  private void initICUData() {
    InputStream raw = getResources().openRawResource(R.raw.icudt51l);
    String outPath = FilenameUtils.concat(getFilesDir().toString(), "icudt51l.dat");
    File outFile = new File(outPath);

    // TODO(marc): this will not detect changes in the file contents with the same name.
    if (outFile.exists() && outFile.length() > 0) {
      Log.d(TAG, "Found ICU data file: " + outPath);
      return;
    }

    Log.i(TAG, "Writing ICU data file from assets: " + outPath);
    try {
      FileOutputStream out = new FileOutputStream(outFile);
      IOUtils.copy(raw, out);
      out.close();
    } catch (IOException e) {
      Log.wtf(TAG, "Problem copying icudata from raw assets to " + outPath, e);
    }
  }

  private void loadXMLProperties() {
    String appVersion = null;
    String buildTarget = null;
    String useProduction = null;
    String unlinkAtStartup = null;
    String testHost = null;

    XmlResourceParser xpp = getResources().getXml(R.xml.properties);
    try {
      int eventType = xpp.getEventType();
      while (eventType != XmlResourceParser.END_DOCUMENT) {
        // Ignore tags: START_DOCUMENT, END_TAG, TEXT, we encode the data we care about as attributes.
        if (eventType == XmlResourceParser.START_TAG) {
          String name = xpp.getName();
          if (name.equals("app_version")) {
            appVersion = xpp.getAttributeValue(null, "value");
          } else if (name.equals("build_target")) {
            buildTarget = xpp.getAttributeValue(null, "value");
          } else if (name.equals("backend_production")) {
            useProduction = xpp.getAttributeValue(null, "value");
          } else if (name.equals("unlink_at_startup")) {
            unlinkAtStartup = xpp.getAttributeValue(null, "value");
          } else if (name.equals("test_host")) {
            testHost = xpp.getAttributeValue(null, "value");
            if ("".equals(testHost)) testHost = null;  // normalize empty string to null.
          }
        }
        eventType = xpp.next();
      }
    } catch (Exception e) {
      Log.wtf(TAG, "Error parsing properties.xml", e);
      Assert.fail();
    }
    xpp.close();

    Assert.assertFalse("Missing app_version from properties.xml", Utils.isEmptyOrNull(appVersion));
    Assert.assertFalse("Missing build_target from properties.xml", Utils.isEmptyOrNull(buildTarget));
    mAppVersion = appVersion;
    mBuildTarget = buildTarget;
    mUseProductionBackend = Boolean.parseBoolean(useProduction);
    // TODO(marc): make sure this can never show up in a real build.
    mUnlinkAtStartup = isDevBuild() && Boolean.parseBoolean(unlinkAtStartup);
    mTestHost = testHost;
    Log.d(TAG, "Property: App version: " + appVersion);
    Log.d(TAG, "Property: Build target: " + buildTarget);
    Log.d(TAG, "Property: Production backend: " + mUseProductionBackend);
    Log.d(TAG, "Property: Unlink at startup: " + mUnlinkAtStartup);
    Log.d(TAG, "Property: Viewfinder test host: " + mTestHost);
  }

  private void registerGCM() {
    // Registration will usually return the same id when called multiple times, so it's better to call it at
    // every startup to make sure we always have a working ID.
    final AppState appState = this;

    // GCM registration cannot be done on the main thread.
    new AsyncTask<Void, Void, String>() {
      @Override
      protected String doInBackground(Void... params) {
        try {
          return GoogleCloudMessaging.getInstance(appState).register(GCMBroadcastReceiver.SENDER_ID);
        } catch (IOException e) {
          if (Utils.isEmulator()) {
            Log.w(TAG, "Error registering GCM");
          } else {
            Log.wtf(TAG, "Error registering GCM", e);
          }
        }
        return null;
      }

      @Override
      protected void onPostExecute(String id) {
        // Back in the UI thread.
        if (!Utils.isEmptyOrNull(id)) {
          Log.d(TAG, "GCM ID: " + id);
          savePreference("gcm_id", id);
          // TODO(marc): if getting a new GCM id, send an update_device request.
        }
      }
    }.execute(null, null, null);
  }

  public String getDeviceUUID() {
    String deviceUUID = loadPreference(DEVICE_UUID_KEY);
    if (deviceUUID == null) {
      deviceUUID = UUID.randomUUID().toString();
      savePreference(DEVICE_UUID_KEY, deviceUUID);
      Log.d(TAG, "Initialized new device_uuid: " + deviceUUID);
    }
    return deviceUUID;
  }

  public long getUserId() {
    return GetUserID(mNativeState);
  }

  public long getNextLocalOperationId() {
    // Make sure we're in the UI thread for this.
    AppState.assertIsUIThread();

    long nextId = loadLongPreference(OPERATION_ID_KEY);
    if (nextId == -1) {
      Log.d(TAG, "Initializing local operation id");
      nextId = 1;
    } else {
      nextId++;
    }
    saveLongPreference(OPERATION_ID_KEY, nextId);
    return nextId;
  }

  private SharedPreferences getPreferences() {
    return getSharedPreferences(PREFS_NAME, 0);
  }

  public String loadPreference(String name)     { return getPreferences().getString(name, null); }
  public int    loadIntPreference(String name)  { return getPreferences().getInt(name, -1);      }
  public long   loadLongPreference(String name) { return getPreferences().getLong(name, -1);     }

  public void savePreference(String name, String value)   { getPreferences().edit().putString(name, value).commit(); }
  public void saveIntPreference(String name, int value)   { getPreferences().edit().putInt(name, value).commit();    }
  public void saveLongPreference(String name, long value) { getPreferences().edit().putLong(name, value).commit();   }


  public void unlinkDevice() {
    // Cleanup app data associated with user.
    Log.i(TAG, "Clearing all settings during unlinkDevice()");
    getPreferences().edit().clear().commit();
  }

  public static void assertIsUIThread() {
    Assert.assertEquals(Looper.getMainLooper().getThread(), Thread.currentThread());
  }

  public void popupShortMessage(String message) {
    Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
  }

  public void popupLongMessage(String message) {
    Toast.makeText(this, message, Toast.LENGTH_LONG).show();
  }

  public int convertDpsToPixels(int dps) {
    return (int) (dps * mDisplayMetrics.density + 0.5f);
  }

  public void setAuthCookies(byte[] userCookie, byte[] xsrfCookie) {
    SetAuthCookies(mNativeState, userCookie, xsrfCookie);
  }

  /**
   * Get the contact metadata for the current user, or null if it is not yet available.
   */
  public ContactMetadataPB.ContactMetadata getSelfContact() {
    long user_id = getUserId();
    if (user_id == 0) return null;
    return contactManager().lookupUser(user_id);
  }

  // Collator objects are not thread-safe.
  private static final ThreadLocal<java.text.Collator> mCollator =
      new ThreadLocal<java.text.Collator>() {
    @Override
    protected java.text.Collator initialValue() {
      java.text.Collator c = java.text.Collator.getInstance(
          java.util.Locale.getDefault());
      // The PRIMARY strength is case insensitive.
      c.setStrength(java.text.Collator.PRIMARY);
      return c;
    }
  };

  private static int localizedCaseInsensitiveCompare(String a, String b) {
    return mCollator.get().compare(a, b);
  }

  // NumberFormat objects are not thread-safe.
  private static final ThreadLocal<java.text.NumberFormat> mNumberFormat =
      new ThreadLocal<java.text.NumberFormat>() {
    @Override
    protected java.text.NumberFormat initialValue() {
      return java.text.NumberFormat.getIntegerInstance(
          java.util.Locale.getDefault());
    }
  };

  private static String localizedNumberFormat(int value) {
    return mNumberFormat.get().format(value);
  }

  private static String newUUID() {
    return UUID.randomUUID().toString();
  }

  private static String getLocaleCountry() {
    return java.util.Locale.getDefault().getCountry();
  }

  private static String getLocaleLanguage() {
    return java.util.Locale.getDefault().getLanguage();
  }

  private static long getTimeZoneOffset(long time) {
    // TimeZone.getOffset() returns milliseconds. We want seconds.
    return java.util.TimeZone.getDefault().getOffset(time) / 1000;
  }

  private static String getTimeZoneName() {
    return java.util.TimeZone.getDefault().getDisplayName(
        false, java.util.TimeZone.SHORT, java.util.Locale.getDefault());
  }

  private static long getFreeDiskSpace() {
    android.os.StatFs s = new android.os.StatFs(
        android.os.Environment.getDataDirectory().getAbsolutePath());
    return (long)s.getAvailableBlocks() * (long)s.getBlockSize();
  }

  private static long getTotalDiskSpace() {
    android.os.StatFs s = new android.os.StatFs(
        android.os.Environment.getDataDirectory().getAbsolutePath());
    return (long)s.getBlockCount() * (long)s.getBlockSize();
  }

  private String getPhoneNumberCountryCode() {
    try  {
      android.telephony.TelephonyManager tm = (android.telephony.TelephonyManager)
          getSystemService(Context.TELEPHONY_SERVICE);
      try {
        return tm.getNetworkCountryIso();
      } catch (Exception e) {
        return tm.getSimCountryIso();
      }
    } catch (Exception e) {
      return java.util.Locale.getDefault().getCountry();
    }
  }

  private void maintenanceProgress(String message) {
    Log.i(TAG, "maintenance progress: " + message);
  }

  private void maintenanceDone(boolean reset) {
    Log.i(TAG, "maintenance done: " + reset);
  }

  private void onDayTableUpdate() {
    Log.i(TAG, "onDayTableUpdate");
    mDayTable.notifyNewSnapshot();
  }

  // Internal life cycle management entry points in jni/NativeAppState.cc
  private native long LoadNative(String base_dir, boolean reset, int server_port);
  private static native void UnloadNative(long state);
  private static native void RunMaintenance(long state, boolean reset);

  private static native void AppDidBecomeActive(long state);
  private static native void AppWillResignActive(long state);
  private static native long GetActivityTable(long state);
  private static native long GetContactManager(long state);
  private static native long GetDayTable(long state);
  private static native long GetDBHandle(long state);
  private static native long GetEpisodeTable(long state);
  private static native long GetNetworkManager(long state);
  private static native long GetPhotoStorage(long state);
  private static native long GetPhotoTable(long state);
  private static native long GetViewpointTable(long state);
  private static native byte[] GetUserCookie(long state);
  private static native long GetUserID(long state);
  private static native byte[] GetXsrfCookie(long state);
  private static native void SetAuthCookies(long state, byte[] user_cookie, byte[] xsrf_cookie);
}
