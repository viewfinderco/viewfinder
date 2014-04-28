// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;

/**
 *  UI for web page viewing.
 */
public class WebFragment extends BaseFragment {
  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.web_fragment, container, false);

    String pageTitle = ((WebActivity)getActivity()).getPageTitle();
    ((TextView)view.findViewById(R.id.titlebar_title)).setText(pageTitle);

    WebView webView = (WebView)view.findViewById(R.id.titlebar_content);
    webView.setWebViewClient(new WrappedWebViewClient());
    webView.getSettings().setJavaScriptEnabled(true);

    String pageUrl = ((WebActivity)getActivity()).getPageUrl();
    webView.loadUrl(pageUrl);

    return view;
  }

  public class WrappedWebViewClient extends WebViewClient {
    @Override
    public boolean shouldOverrideUrlLoading(WebView view, String url) {
      view.loadUrl(url);
      return true;
    }
  }
}
