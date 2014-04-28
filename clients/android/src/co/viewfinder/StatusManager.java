// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.os.Handler;
import android.util.Log;

import java.util.Observable;

/**
 * Update registered fragments with status that should be displayed.
 */
public class StatusManager extends Observable {
  private final static String TAG = "Viewfinder.StatusManager";

  private String mStatusText = null;
  private Handler mUIHandler;
  private Runnable mNotifyObserversRunnable;

  public StatusManager(AppState appState) {
    mUIHandler = new Handler(appState.getMainLooper());
    mNotifyObserversRunnable = new Runnable() {
      @Override
      public void run() {
        notifyObservers(getCurrentStatus());
      }
    };
  }

  public String getCurrentStatus() {
    return mStatusText;
  }

  public void setCurrentStatus(String statusText) {
    Log.d(TAG, "setCurrentStatus: " + statusText);
    mStatusText = statusText;
    notifyObserversOnUIThread();
  }

  public void clearCurrentStatus() {
    Log.d(TAG, "clearCurrentStatus()");
    mStatusText = null;
    notifyObserversOnUIThread();
  }

  private void notifyObserversOnUIThread() {
    setChanged();
    mUIHandler.post(mNotifyObserversRunnable);
  }
}
