// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Intent;
import android.os.Bundle;
import android.support.v4.app.FragmentTransaction;
import android.util.Log;

/**
 * Activity to manage application settings.
 */
public class SettingsActivity extends BaseActivity implements SettingsFragment.OnSettingsListener {
  private static final String TAG = "viewfinder.SettingsActivity";
  private static final String TAG_SETTINGS = "co.viewfinder.SettingsFragment";

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);

    setContentView(R.layout.statusbar_activity);

    FragmentTransaction ft = getSupportFragmentManager().beginTransaction();
    ft.add(R.id.statusbar_content, new SettingsFragment(), TAG_SETTINGS);
    ft.commit();
  }

  @Override
  public void onFAQ() {
    Intent i = new Intent(SettingsActivity.this, WebActivity.class);
    i.putExtra(WebActivity.EXTRA_WEB_VIEW_URL_RESOURCE_ID, R.string.url_faq);
    i.putExtra(WebActivity.EXTRA_PAGE_TITLE_RESOURCE_ID, R.string.settings_faq);
    startActivity(i);
    overridePendingTransition(R.anim.slide_in_right, R.anim.hold);
  }

  @Override
  public void onTermsOfService() {
    Intent i = new Intent(SettingsActivity.this, WebActivity.class);
    i.putExtra(WebActivity.EXTRA_WEB_VIEW_URL_RESOURCE_ID, R.string.url_termsOfService);
    i.putExtra(WebActivity.EXTRA_PAGE_TITLE_RESOURCE_ID, R.string.settings_terms);
    startActivity(i);
    overridePendingTransition(R.anim.slide_in_right, R.anim.hold);
  }

  @Override
  public void onPrivacyPolicy() {
    Intent i = new Intent(SettingsActivity.this, WebActivity.class);
    i.putExtra(WebActivity.EXTRA_WEB_VIEW_URL_RESOURCE_ID, R.string.url_privacyPolicy);
    i.putExtra(WebActivity.EXTRA_PAGE_TITLE_RESOURCE_ID, R.string.settings_privacy);
    startActivity(i);
    overridePendingTransition(R.anim.slide_in_right, R.anim.hold);
  }

  @Override
  public void onSendFeedback() {
    String subject = getString(R.string.settings_versionInfo,
                               getAppState().appVersion(),
                               Utils.osAndroidRelease());

    Intent emailIntent = new Intent(android.content.Intent.ACTION_SEND);
    emailIntent.setType("plain/text");
    emailIntent.putExtra(android.content.Intent.EXTRA_EMAIL, new String[]{getString(R.string.emailAddress_support)});
    emailIntent.putExtra(android.content.Intent.EXTRA_SUBJECT, subject);

    // Use chooser in case the user has more than one email client configured.
    startActivity(Intent.createChooser(emailIntent, "Send mail..."));
    overridePendingTransition(R.anim.slide_in_right, R.anim.hold);
  }

  @Override
  public void onDebugLogs(boolean doDebugLogging) {
    Log.d(TAG, "onDebugLogs(" + doDebugLogging + "): currently no-op.");
  }

  @Override
  public void onUnlinkDevice() {
    getAppState().unlinkDevice();
    finish();
    moveTaskToBack(true);
  }

  @Override
  public void onCrash() {
    Log.d(TAG, "onCrash(): dereference null object to cause crash.");
    Intent i = null;
    i.addFlags(0);
  }
}
