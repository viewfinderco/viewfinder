// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault
package co.viewfinder;

import co.viewfinder.proto.*;
import co.viewfinder.proto.CookieMetadataPB.CookieMetadata;

import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import com.google.protobuf.Message;
import com.loopj.android.http.*;
import java.io.InputStream;
import java.io.IOException;
import java.io.UnsupportedEncodingException;
import java.net.URL;
import java.net.MalformedURLException;
import java.security.KeyStore;
import java.util.ArrayList;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.Date;
import java.util.List;
import junit.framework.Assert;
import org.apache.http.HttpResponse;
import org.apache.http.Header;
import org.apache.http.HttpEntity;
import org.apache.http.client.CookieStore;
import org.apache.http.client.methods.HttpGet;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.client.methods.HttpPut;
import org.apache.http.client.methods.HttpRequestBase;
import org.apache.http.client.params.ClientPNames;
import org.apache.http.client.params.CookiePolicy;
import org.apache.http.conn.ClientConnectionManager;
import org.apache.http.conn.scheme.PlainSocketFactory;
import org.apache.http.conn.scheme.Scheme;
import org.apache.http.conn.scheme.SchemeRegistry;
import org.apache.http.conn.ssl.SSLSocketFactory;
import org.apache.http.cookie.Cookie;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.DefaultHttpClient;
import org.apache.http.impl.conn.tsccm.ThreadSafeClientConnManager;
import org.apache.http.impl.cookie.BasicClientCookie;
import org.apache.http.params.BasicHttpParams;
import org.apache.http.params.HttpConnectionParams;
import org.apache.http.params.HttpParams;
import org.apache.http.util.EntityUtils;

/**
 * Manage network interactions.
 */
public class NetworkManager {
  private static final String TAG = "viewfinder.NetworkManager";

  // Timeouts and period settings.
  private static final int HTTP_TIMEOUT_SECS = 60;

  // Threadpool settings.
  // TODO(marc): are those correct? If needed, we could use Runtime.getRuntime().availableProcessors();
  // Threadpool always keeps at least THREADPOOL_CORE_SIZE threads. If needed, it creates up to THREADPOOL_MAX_SIZE.
  // Extra idle threads get destroyed after THREADPOOL_KEEP_ALIVE_TIME (in THREADPOOL_KEEP_ALIVE_UNITS).
  private static final int THREADPOOL_CORE_SIZE = 2;
  private static final int THREADPOOL_MAX_SIZE = 4;
  private static final long THREADPOOL_KEEP_ALIVE_TIME = 10;
  private static final TimeUnit THREADPOOL_KEEP_ALIVE_UNIT = TimeUnit.SECONDS;

  private static AppState mAppState = null;

  // Pointer to the native NetworkManager.
  private final long mNativeNetworkManager;

  // Threadpool.
  private static ThreadPoolExecutor mExecutor;

  // Handler to schedule runnables on the UI thread.
  private static Handler mUIHandler;

  // Thread-safe http client.
  private static DefaultHttpClient mHttpClient;

  public NetworkManager(AppState appState, long nativePointer, boolean isProduction,
                        byte[] userCookie, byte[] xsrfCookie) {
    mAppState = appState;
    mNativeNetworkManager = nativePointer;
    mExecutor = new ThreadPoolExecutor(THREADPOOL_CORE_SIZE, THREADPOOL_MAX_SIZE,
                                       THREADPOOL_KEEP_ALIVE_TIME, THREADPOOL_KEEP_ALIVE_UNIT,
                                       new LinkedBlockingQueue<Runnable>());
    mUIHandler = new Handler(Looper.getMainLooper());
    initHttpClient(isProduction, userCookie, xsrfCookie);
  }

  public void onTerminate() {
    Log.d(TAG, "onDestroy");
  }

  private static void maybeUpdateCookies() {
    VFCookieStore store = (VFCookieStore) NetworkManager.getHttpClient().getCookieStore();
    if (!store.checkAndClearNewCookies()) {
      return;
    }

    byte[] userCookie = store.getRawUserCookie();
    byte[] xsrfCookie = store.getRawXsrfCookie();

    mAppState.setAuthCookies(userCookie, xsrfCookie);
  }

  /**
   * Custom cookie store that only keeps viewfinder cookies around.
   * TODO(marc): make this thread-safe.
   */
  public static class VFCookieStore implements CookieStore {
    private Cookie mUserCookie = null;
    private Cookie mXsrfCookie = null;
    private boolean mNewCookies = false;

    public VFCookieStore() { }

    public Cookie getUserCookie() { return mUserCookie; }
    public Cookie getXsrfCookie() { return mXsrfCookie; }

    public byte[] getRawUserCookie() {
      if (mUserCookie == null) {
        return null;
      }
      return serializeCookie(mUserCookie);
    }

    public byte[] getRawXsrfCookie() {
      if (mXsrfCookie == null) {
        return null;
      }
      return serializeCookie(mXsrfCookie);
    }

    public boolean checkAndClearNewCookies() {
      if (mNewCookies) {
        mNewCookies = false;
        return true;
      }
      return false;
    }

    private byte[] serializeCookie(Cookie cookie) {
      CookieMetadata.Builder builder = CookieMetadata.newBuilder();
      ServerUtils.maybeSetString(builder, "name", cookie.getName());
      ServerUtils.maybeSetString(builder, "value", cookie.getValue());
      ServerUtils.maybeSetString(builder, "comment", cookie.getComment());
      ServerUtils.maybeSetString(builder, "domain", cookie.getDomain());
      ServerUtils.maybeSetLong(builder, "expiry_date", cookie.getExpiryDate().getTime());
      ServerUtils.maybeSetString(builder, "path", cookie.getPath());
      ServerUtils.maybeSetInt(builder, "version", cookie.getVersion());
      builder.setIsSecure(cookie.isSecure());
      return builder.build().toByteArray();
    }

    private Cookie parseCookie(byte[] raw) {
      if (raw == null || raw.length == 0) {
        return null;
      }
      CookieMetadata cm;
      try {
        cm = CookieMetadata.parseFrom(raw);
      } catch (Exception e) {
        return null;
      }

      BasicClientCookie cookie = new BasicClientCookie(cm.getName(), cm.getValue());
      if (cm.hasComment())     cookie.setComment(cm.getComment());
      if (cm.hasDomain())      cookie.setDomain(cm.getDomain());
      if (cm.hasExpiryDate())  cookie.setExpiryDate(new Date(cm.getExpiryDate()));
      if (cm.hasPath())        cookie.setPath(cm.getPath());
      if (cm.hasVersion())     cookie.setVersion(cm.getVersion());
      if (cm.hasIsSecure())    cookie.setSecure(cm.getIsSecure());
      return cookie;
    }

    public void addRawCookie(byte[] raw) {
      Cookie c = parseCookie(raw);
      if (c != null) {
        addCookie(c);
      }
    }

    @Override
    public void addCookie(Cookie cookie) {
      String name = cookie.getName();
      if (name.equals("user")) {
        Log.i(TAG, "Got new user cookie");
        mUserCookie = cookie;
        mNewCookies = true;
      } else if (name.equals("_xsrf")) {
        Log.i(TAG, "Got new xsrf cookie");
        mXsrfCookie = cookie;
        mNewCookies = true;
      } else {
        Log.w(TAG, "Unknown cookie name: " + name);
      }
    }

    @Override
    public void clear() {
      mUserCookie = null;
      mXsrfCookie = null;
    }

    @Override
    public boolean clearExpired(Date date) {
      boolean ret = false;
      if (mUserCookie != null && mUserCookie.isExpired(date)) {
        mUserCookie = null;
        ret = true;
      }
      if (mXsrfCookie != null && mXsrfCookie.isExpired(date)) {
        mXsrfCookie = null;
      }
      return ret;
    }

    @Override
    public List<Cookie> getCookies() {
      ArrayList<Cookie> list = new ArrayList<Cookie>();
      if (mUserCookie != null) {
        list.add(mUserCookie);
      }
      if (mXsrfCookie != null) {
        list.add(mXsrfCookie);
      }
      return list;
    }
  }

  private static void initHttpClient(boolean isProduction, byte[] userCookie, byte[] xsrfCookie) {
    HttpParams params = new BasicHttpParams();

    SchemeRegistry registry = new SchemeRegistry();
    registry.register(new Scheme("http", PlainSocketFactory.getSocketFactory(), 80));
    if (isProduction) {
      registry.register(new Scheme("https", SSLSocketFactory.getSocketFactory(), 443));
    } else {
      // Use a custom SSL factory when working on local backend.
      registry.register(new Scheme("https", newSslSocketFactory(), 443));
    }

    ClientConnectionManager connectionManager = new ThreadSafeClientConnManager(params, registry);
    mHttpClient = new DefaultHttpClient(connectionManager, params);
    HttpConnectionParams.setSoTimeout(mHttpClient.getParams(), HTTP_TIMEOUT_SECS * 1000);
    HttpConnectionParams.setConnectionTimeout(mHttpClient.getParams(), HTTP_TIMEOUT_SECS * 1000);
    // Don't handle redirects automatically.
    mHttpClient.getParams().setParameter(ClientPNames.HANDLE_REDIRECTS, false);
    // Set the cookie policy. It still rejects cookies when hostnames don't match.
    mHttpClient.getParams().setParameter(ClientPNames.COOKIE_POLICY, CookiePolicy.BROWSER_COMPATIBILITY);

    // Initialize our custom cookie store and add the user and xsrf cookies if non-null.
    VFCookieStore store = new VFCookieStore();
    store.addRawCookie(userCookie);
    store.addRawCookie(xsrfCookie);
    // New cookies come from the AppState, no need to set them again.
    store.checkAndClearNewCookies();
    mHttpClient.setCookieStore(store);
  }

  private static SSLSocketFactory newSslSocketFactory() {
    try {
      // Get an instance of the Bouncy Castle KeyStore format
      KeyStore trusted = KeyStore.getInstance("BKS");
      // Get the raw resource, which contains the keystore with
      // your trusted certificates (root and any intermediate certs)
      InputStream in = mAppState.getApplicationContext().getResources().openRawResource(R.raw.emulator_keystore);
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
      // Don't be too careful about SSL. For testing against local backends only.
      // sf.setHostnameVerifier(SSLSocketFactory.STRICT_HOSTNAME_VERIFIER);
      sf.setHostnameVerifier(SSLSocketFactory.ALLOW_ALL_HOSTNAME_VERIFIER);
      return sf;
    } catch (Exception e) {
      throw new AssertionError(e);
    }
  }

  public static DefaultHttpClient getHttpClient() {
    return mHttpClient;
  }

  // Add the runnable to the network threadpool.
  private static void dispatchNetwork(Runnable task) {
    mExecutor.execute(task);
  }

  // Run on the UI thread.
  private static void dispatchUI(Runnable task) {
    mUIHandler.post(task);
  }

  public static void sendRequest(long requestPointer, String url, String method, String body,
                                 String contentType, String contentMD5, String ifNoneMatch) {
    Log.i(TAG, "sendRequest: url=" + url + " method=" + method + " body=" + body);
    if (getHttpClient() == null) {
      // TODO(marc): figure out why the native network manager runs before our explicit dispatch.
      throw new java.lang.AssertionError("Java HTTP Client not yet initialized.");
    }

    AsyncHttpHandler mHandler = new AsyncHttpHandler(requestPointer, method, url, body,
                                                     contentType, contentMD5, ifNoneMatch);
    mHandler.execute();
  }

  public static class AsyncHttpHandler implements Runnable {
    private long mRequestPointer;
    private String mMethod;
    private String mUrl;
    private String mBody;
    private String mContentType;
    private String mContentMD5;
    private String mIfNoneMatch;
    private HttpHandler mHandler;

    public AsyncHttpHandler(long requestPointer, String method, String url, String body,
                            String contentType, String contentMD5, String ifNoneMatch) {
      mRequestPointer = requestPointer;
      mMethod = method;
      mUrl = url;
      mBody = body;
      mContentType = contentType;
      mContentMD5 = contentMD5;
      mIfNoneMatch = ifNoneMatch;
      mHandler = new HttpHandler(method, url, body, contentType, contentMD5, ifNoneMatch);
    }

    public void execute() {
      NetworkManager.dispatchNetwork(this);
    }

    @Override
    public void run() {
      mHandler.execute();

      Log.i(TAG, "got response: " + mHandler.responseCode());
      if (mHandler.responseCode() == -1) {
        // An exception was thrown. Call HandleError.
        HandleError(mRequestPointer, mHandler.exception().toString());
      } else if (mHandler.responseCode() == 301) {
        // Permanent redirect. Check that it's staging.
        Header redirectHeader = mHandler.response().getLastHeader("X-Vf-Staging-Redirect");
        if (redirectHeader == null) {
          Log.wtf(TAG, "Got redirect from backend but no X-Vf-Staging-Redirect redirect");
        }
        String redirectHost = redirectHeader.getValue();
        Log.d(TAG, "Got redirect: " + redirectHost);

        // Tell native code about the change.
        HandleRedirect(mRequestPointer, redirectHost);

        // Replace protocol://host:port from url.
        try {
          URL prevUrl = new URL(mUrl);
          URL newUrl = new URL(prevUrl.getProtocol(), redirectHost, prevUrl.getPort(), prevUrl.getFile());
          mUrl = newUrl.toString();
        } catch (MalformedURLException e) {
          Log.wtf(TAG, "Failed to parse previous URL even though we got a redirect from it: " + mUrl);
        }

        // Create new HttpHandler and execute.
        Log.d(TAG, "Reissuing request with redirect url=" + mUrl);
        mHandler = new HttpHandler(mMethod, mUrl, mBody, mContentType, mContentMD5, mIfNoneMatch);
        execute();
      } else {
        // We get the data all at once, so combine HandleData and HandleDone into a single call.
        HandleDone(mRequestPointer, mHandler.result(), mHandler.responseCode());
      }
    }
  }

  public static class HttpHandler {
    private DefaultHttpClient mClient;
    private HttpRequestBase mRequest;

    private int mResponseCode = -1;
    private String mResult = null;
    private HttpResponse mResponse = null;
    private Exception mException = null;

    // Typical for a GET request.
    public HttpHandler(String method, String url) {
      init(method, url, "", "", "", "");
    }

    // Typical for a POST request.
    public HttpHandler(String method, String url, String body, String contentType) {
      init(method, url, body, contentType, "", "");
    }

    // Typical for a PUT request.
    public HttpHandler(String method, String url, String body,
                       String contentType, String contentMD5, String ifNoneMatch) {
      init(method, url, body, contentType, contentMD5, ifNoneMatch);
    }

    private void init(String method, String url, String body,
                      String contentType, String contentMD5, String ifNoneMatch) {
      if (method.equals("GET")) {
        mRequest = new HttpGet(url);
        // GET does not have a body, or a setEntity method.
      } else if (method.equals("POST")) {
        HttpPost post = new HttpPost(url);
        try {
          if (!Utils.isEmptyOrNull(body))           post.setEntity(new StringEntity(body));
        } catch (UnsupportedEncodingException e) {
          Log.wtf(NetworkManager.TAG, "Unsupposed encoding for HttpPost.setEntity: " + body, e);
        }
        mRequest = post;
      } else if (method.equals("PUT")) {
        HttpPut put = new HttpPut(url);
        try {
          if (!Utils.isEmptyOrNull(body))           put.setEntity(new StringEntity(body));
        } catch (UnsupportedEncodingException e) {
          Log.wtf(NetworkManager.TAG, "Unsupposed encoding for HttpPut.setEntity: " + body, e);
        }
        mRequest = put;
      } else {
        Log.wtf(NetworkManager.TAG, "Unsupported HTTP method: " + method);
      }

      mClient = NetworkManager.getHttpClient();

      // Find the xsrf cookie.
      // TODO(marc): we should really do manual cookie handling and re-login when expired.
      String xsrfValue = getCookieValue(mClient.getCookieStore(), "_xsrf");
      if (!Utils.isEmptyOrNull(xsrfValue))      mRequest.setHeader("X-Xsrftoken", xsrfValue);

      // Set extra headers.
      if (!Utils.isEmptyOrNull(contentType))    mRequest.setHeader("Content-Type", contentType);
      if (!Utils.isEmptyOrNull(contentMD5))     mRequest.setHeader("Content-MD5", contentMD5);
      if (!Utils.isEmptyOrNull(ifNoneMatch))    mRequest.setHeader("If-None-Match", ifNoneMatch);
    }

    public String result() {
      return mResult;
    }

    public int responseCode() {
      return mResponseCode;
    }

    public HttpResponse response() {
      return mResponse;
    }

    public Exception exception() {
      return mException;
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

    public void execute() {
      Assert.assertNull(mResult);
      Assert.assertNull(mResponse);
      Assert.assertNull(mException);
      try {
        // Issue request.
        mResponse = mClient.execute(mRequest);

        // Extract status code and data.
        // TODO(marc): do we care about the rest of the StatusLine? (protocol version and reason phrase).
        mResponseCode = mResponse.getStatusLine().getStatusCode();
        HttpEntity entity = mResponse.getEntity();
        if (entity != null) {
          mResult = EntityUtils.toString(entity);
        }

        // Check if cookies have changed and push them down to native.
        maybeUpdateCookies();
      } catch (IOException e) {
        Log.e(NetworkManager.TAG, "Problem issuing request", e);
        mException = e;
      }
    }
  }

  /**
   * Callback for the Auth requests. Run on the UI thread.
   * Implement run() in instances.
   */
  public static class AuthResponseCallback implements Runnable {
    protected int mStatusCode;
    protected int mErrorId;
    protected String mErrorMsg;

    public AuthResponseCallback() { }

    public void done(int statusCode, int errorId, String errorMsg) {
      mStatusCode = statusCode;
      mErrorId = errorId;
      mErrorMsg = errorMsg;
    }

    @Override
    public void run() { }
  }

  // Singleton gatekeeper for auth requests. TODO: should this be in UI code?
  private static boolean mHasInflightAuthRequest = false;

  private void startAuthRequest() {
    if (mHasInflightAuthRequest) {
      Log.wtf(TAG, "We already have an in-flight auth request.");
    }
    mHasInflightAuthRequest = true;
  }

  public void sendAuthLogin(String identity, String password, AuthResponseCallback callback) {
    startAuthRequest();

    // TODO(marc): maybe pass NULL instead of empty string here and fix native side to check for it.
    // TODO(marc): proper identity management instead of AddIdentityPrefix.
    // TODO(marc): name formatting.
    AuthViewfinder(mNativeNetworkManager, "login", Utils.AddIdentityPrefix(identity),
                   password, "", "", "", true, callback);
  }

  public void sendAuthRegister(String identity, String first, String last, String password,
                               AuthResponseCallback callback) {
    startAuthRequest();

    String name = ContactManager.ConstructFullName(first, last);
    AuthViewfinder(mNativeNetworkManager, "register", Utils.AddIdentityPrefix(identity),
                   password, first, last, name, true, callback);
  }

  public void sendAuthReset(String identity, AuthResponseCallback callback) {
    startAuthRequest();

    AuthViewfinder(mNativeNetworkManager, "login_reset", Utils.AddIdentityPrefix(identity),
                   "", "", "", "", true, callback);
  }

  public void sendAuthVerify(String identity, String accessToken, AuthResponseCallback callback) {
    startAuthRequest();

    VerifyViewfinder(mNativeNetworkManager, Utils.AddIdentityPrefix(identity),
                     accessToken, true, callback);
  }

  public void sendChangePassword(String oldPassword, String newPassword, AuthResponseCallback callback) {
    startAuthRequest();

    ChangePassword(mNativeNetworkManager, oldPassword, newPassword, callback);
  }

  public static void authDone(Object callback, int statusCode, int errorId, String errorMsg) {
    if (!mHasInflightAuthRequest) {
      Log.wtf(TAG, "authDone() called but no in-flight auth requests.");
    }
    AuthResponseCallback cb = (AuthResponseCallback) callback;
    // Set variables for callback object.
    cb.done(statusCode, errorId, errorMsg);
    // Run on the UI thread.
    NetworkManager.dispatchUI(cb);
    mHasInflightAuthRequest = false;
  }

  // NetworkRequest native methods.
  private static native void AuthViewfinder(long net_mgr, String endpoint, String identity, String password,
                                            String first, String last, String name, boolean error_if_linked,
                                            Object callback);
  private static native void ChangePassword(long net_mgr, String oldPassword, String newPassword, Object callback);
  private static native void VerifyViewfinder(long net_mgr, String identity, String access_token, boolean manual_entry,
                                              Object callback);
  private static native void HandleError(long request, String e);
  // TODO(marc): use byte[] data once java no longer calls the network manager.
  private static native void HandleDone(long request, String data, int code);
  private static native void HandleRedirect(long request, String redirectHost);
}
