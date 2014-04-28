// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Context;
import android.graphics.Bitmap;
import android.util.AttributeSet;
import android.widget.ImageView;
import junit.framework.Assert;

/**
 * Wraps ImageView in order to inject some added functionality.
 */
public class PhotoImageView extends ImageView {
  private final static String TAG = "Viewfinder.PhotoImageView";

  private BitmapFetcher mBitmapFetcher = null;
  private long mFetcherRequestId;

  public PhotoImageView(Context context) {
    super(context);
  }

  public PhotoImageView(Context context, AttributeSet attrs) {
    super(context, attrs);
  }

  public PhotoImageView(Context context, AttributeSet attrs, int defStyle) {
    super(context, attrs, defStyle);
  }

  /**
   * Fetch bitmap with requested dimensions.
   */
  public void fetchBitmap(int width,
                          int height,
                          int dimensionRequestType,
                          ViewData.PhotoViewData.PhotoItemViewData photoItem,
                          AppState appState) {
    appState.bitmapFetcher().fetchAsync(width, height, dimensionRequestType, photoItem, this);
  }

  /**
   * Get reference to bitmap fetcher and establish current requestId for pending fetch.
   */
  public void onStartFetch(BitmapFetcher bitmapFetcher, long requestId) {
    AppState.assertIsUIThread();
    assertNoPendingFetch();
    mBitmapFetcher = bitmapFetcher;
    mFetcherRequestId = requestId;
    super.setImageBitmap(null);
  }

  /**
   * Called by BitmapFetcher once bitmap has been loaded.
   */
  public void setFetchedBitmap(long expectedFetcherRequestId, Bitmap bitmap) {
    AppState.assertIsUIThread();
    if (isCurrentFetcherRequest(expectedFetcherRequestId)) {
      cancelFetchRequest();
      setImageBitmap(bitmap);
    }
  }

  /**
   * Called whenever the view has been recycled or will otherwise not be drawn.
   * BitmapFetcher can then check this (using isCurrentFetcherRequest()) as it processes an
   *   async load to determine if it should abandon its attempt to load the bitmap.
   */
  public void cancelFetchRequest() {
    AppState.assertIsUIThread();
    mFetcherRequestId = 0;
    mBitmapFetcher = null;
  }

  /**
   * Allows BitmapFetcher to determine if this PhotoImageView is still waiting
   *   for the image associated with the request id to be loaded.
   */
  public boolean isCurrentFetcherRequest(long fetcherRequestId) {
    return (null != mBitmapFetcher) && (fetcherRequestId == mFetcherRequestId);
  }

  public void assertNoPendingFetch() {
    Assert.assertNull(mBitmapFetcher);
  }

  @Override
  public void setImageBitmap(Bitmap bm) {
    // This should be OK to call for sync fetch (cache hit), but
    //   we'll ensure that the caller doesn't use this for async fetch scenario.
    assertNoPendingFetch();
    super.setImageBitmap(bm);
  }

  @Override
  protected void onDetachedFromWindow() {
    cancelFetchRequest();
    super.onDetachedFromWindow();
  }
}
