package com.hello;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.AsyncTask;
import android.util.Log;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.IOException;
import java.io.Reader;
import java.io.Serializable;
import java.security.KeyStore;
import java.util.List;

import com.loopj.android.http.*;

import org.apache.http.HttpResponse;
import org.apache.http.NameValuePair;
import org.apache.http.client.CookieStore;
import org.apache.http.client.HttpClient;
import org.apache.http.client.entity.UrlEncodedFormEntity;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.conn.ClientConnectionManager;
import org.apache.http.conn.scheme.PlainSocketFactory;
import org.apache.http.conn.scheme.Scheme;
import org.apache.http.conn.scheme.SchemeRegistry;
import org.apache.http.conn.ssl.SSLSocketFactory;
import org.apache.http.cookie.Cookie;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.DefaultHttpClient;
import org.apache.http.impl.conn.SingleClientConnManager;
import org.apache.http.impl.cookie.BasicClientCookie;
import org.apache.http.message.BasicNameValuePair;
import org.apache.http.StatusLine;
import org.json.JSONObject;


interface DownloadCaller {
  void downloadFinished(Download download_task);
}

public class Download extends AsyncTask<Void, Void, String> {
  // Given a URL, establishes an HttpUrlConnection and retrieves
  // the web page content as a InputStream, which it returns as
  // a string.
  private Context context;
  private int id;
  private String url;
  private JSONObject post_json;
  private int response_code;
  private String result;
  private DownloadCaller caller;

  public Download(Context app_context, int download_id, String download_url,
                  JSONObject json, DownloadCaller caller_class) {
    context = app_context;
    id = download_id;
    url = download_url;
    post_json = json;
    caller = caller_class;
  }

  public int id() {
    return id;
  }

  public String result() {
    return result;
  }

  public int responseCode() {
    return response_code;
  }

  @Override
  protected void onPreExecute() {
    // On UI thread.  
  }

  @Override
  protected String doInBackground(Void... params) {
    try {
      return postJson();
    } catch (IOException e) {
      return null;
    }
  }

  @Override
  protected void onPostExecute(String op_result) {
    // On UI thread.
    result = op_result;
    Log.i(HelloActivity.TAG, "Response code: " + response_code);
    Log.i(HelloActivity.TAG, "Got: " + result);
    if (caller != null) {
      caller.downloadFinished(this);
    }
  }

  private void listCookies(CookieStore store) {
    List<Cookie> cookies = store.getCookies();
    for (int i = 0; i < cookies.size(); ++i) {
      Cookie cookie = cookies.get(i);
      Log.i(HelloActivity.TAG, "Got cookie " + cookie.getName() + " for domain: " + cookie.getDomain() +
            " value=" + cookie.getValue());
    }
  }

  private String getCookieValue(CookieStore store, String name) {
    List<Cookie> cookies = store.getCookies();
    for (int i = 0; i < cookies.size(); ++i) {
      Cookie cookie = cookies.get(i);
      if (cookie.getName().equals(name)) {
        return cookie.getValue();
      }
    }
    return null;
  }

  private String postJson() throws IOException {
    // On background thread.
    // <uses-permission android:name="android.permission.INTERNET" />
    // http://blog.antoine.li/2010/10/22/android-trusting-ssl-certificates/
    // TODO(marc): detect debug build and only use on those. Otherwise, use DefaultHttpClient.
    // DefaultHttpClient client = new DefaultHttpClient();
    DefaultHttpClient client = new MyHttpClient(context);

    // Use a persistent cookie store (backed to SharedPreferences). From android-async-http library.
    PersistentCookieStore myCookieStore = new PersistentCookieStore(context);
    client.setCookieStore(myCookieStore);
    listCookies(myCookieStore);

    HttpPost post = new HttpPost(url);
    // Find the xsrf cookie.
    String xsrfValue = getCookieValue(myCookieStore, "_xsrf");
    if (xsrfValue != null) {
      Log.i(HelloActivity.TAG, "Setting xsrf header: " + xsrfValue);
      post.setHeader("X-Xsrftoken", xsrfValue);
    }

    post.setHeader("Content-Type", "application/json");
    post.setEntity(new StringEntity(post_json.toString()));

    try {
      // Issue request.
      HttpResponse response = client.execute(post);
      // Extract response code.
      response_code = response.getStatusLine().getStatusCode();
      // Extract and list cookies.
      listCookies(client.getCookieStore());
      // Extract data.
      BufferedReader rd = new BufferedReader(new InputStreamReader(response.getEntity().getContent()));
      String contents = "";
      String line = "";
      while ((line = rd.readLine()) != null) {
        contents += line;
      }
      return contents;
    } catch(IOException e) {
      Log.w(HelloActivity.TAG, "Got exception: " + e.getMessage());
      return null;
    }
  }

  protected class MyHttpClient extends DefaultHttpClient {
    final Context context;

    public MyHttpClient(Context context) {
      this.context = context;
    }

    @Override
      protected ClientConnectionManager createClientConnectionManager() {
        SchemeRegistry registry = new SchemeRegistry();
        registry.register(new Scheme("http", PlainSocketFactory.getSocketFactory(), 80));
        // Register for port 443 our SSLSocketFactory with our keystore
        // to the ConnectionManager
        registry.register(new Scheme("https", newSslSocketFactory(), 443));
        return new SingleClientConnManager(getParams(), registry);
      }

    private SSLSocketFactory newSslSocketFactory() {
      try {
        // Get an instance of the Bouncy Castle KeyStore format
        KeyStore trusted = KeyStore.getInstance("BKS");
        // Get the raw resource, which contains the keystore with
        // your trusted certificates (root and any intermediate certs)
        InputStream in = context.getResources().openRawResource(R.raw.my_keystore);
        try {
          // Initialize the keystore with the provided trusted certificates
          // Also provide the password of the keystore
          trusted.load(in, "local_pwd".toCharArray());
        } finally {
          in.close();
        }
        // Pass the keystore to the SSLSocketFactory. The factory is responsible
        // for the verification of the server certificate.
        SSLSocketFactory sf = new SSLSocketFactory(trusted);
        // Hostname verification from certificate
        // http://hc.apache.org/httpcomponents-client-ga/tutorial/html/connmgmt.html#d4e506
        sf.setHostnameVerifier(SSLSocketFactory.STRICT_HOSTNAME_VERIFIER);
        return sf;
      } catch (Exception e) {
        throw new AssertionError(e);
      }
    }
  }
}
