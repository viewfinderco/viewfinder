// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.os.Bundle;
import android.support.v4.app.FragmentTransaction;

/**
 * Handles display of web content.
 */
public class WebActivity extends BaseActivity {
  private static final String TAG_WEB = "co.viewfinder.WebFragment";

  private String mPageTitle;
  private String mPageUrl;

  public static final String EXTRA_WEB_VIEW_URL_RESOURCE_ID =
      "co.viewfinder.web_view_url";
  public static final String EXTRA_PAGE_TITLE_RESOURCE_ID =
      "co.viewfinder.page_title_resource_id";

  @Override
  public void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);

    setContentView(R.layout.statusbar_activity);

    mPageTitle = getString(getIntent().getIntExtra(EXTRA_PAGE_TITLE_RESOURCE_ID, 0));
    mPageUrl = getString(getIntent().getIntExtra(EXTRA_WEB_VIEW_URL_RESOURCE_ID, 0));

    FragmentTransaction ft = getSupportFragmentManager().beginTransaction();
    ft.add(R.id.statusbar_content, new WebFragment(), TAG_WEB);
    ft.commit();
  }

  public String getPageTitle() {
    return mPageTitle;
  }

  public String getPageUrl() {
    return mPageUrl;
  }
}
