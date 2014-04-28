package co.viewfinder;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Handler;
import android.os.HandlerThread;
import android.support.v4.util.LruCache;
import android.util.Log;
import junit.framework.Assert;

import java.io.IOException;
import java.io.InputStream;

/**
 * Fetches bitmap for ImageView.
 * If the bitmap is in the cache, it is simply set on the PhotoImageView.
 * If the bitmap is not in cache, we'll kick a request off to a separate thread to read the bitmap in.
 * Inform the PhotoImageView that an async fetch is in progress.  This include registering a requestId with
 *   the PhotoImageView.
 * Once the bitmap fetching is complete, dispatch to UI thread for update of ImageView with new bitmap and
 *   inform the PhotoImageView that the fetch is complete.  At several steps, the BitmapFetcher will ask
 *   the PhotoImageView if it's still interested in the bitmap (and still has a matching requestId).  If
 *   at any point BitmapFetcher determines that the bitmap is no longer needed by the PhotoImageView, it
 *   will abandon the request.
 * Once the bitmap has been loaded, it will be added to the cache.
 * TODO(mike): Consider a different design for this which allows for more than one thread to be loading bitmaps.
 *             In particular, consider using Java Executor to do thread pooling.
 */
public class BitmapFetcher extends HandlerThread {
  private static final String TAG = "viewfinder.BitmapFetcher";

  private BitmapCache mBitmapCache;
  private AppState mAppState;
  private Handler mUIHandler;
  private Handler mBitmapLoadHandler;

  // Note: mLastRequestId is only incremented in UIThread.
  private long mLastRequestId = 0;

  public static final int DIMENSIONS_AT_MOST = 1;
  public static final int DIMENSIONS_AT_LEAST = 2;

  public BitmapFetcher(AppState appState, int maxCacheSizeBytes) {
    super("BitmapFetcher", NORM_PRIORITY);
    mAppState = appState;
    mBitmapCache = new BitmapCache(maxCacheSizeBytes);
    mUIHandler = new Handler(appState.getMainLooper());
    start();  // Start the handler thread.
    mBitmapLoadHandler = new Handler(getLooper());
  }

  /**
   * This is useful when we want to make our memory footprint smaller to avoid getting killed by Android
   * when not active.  When Android is looking to reclaim memory, it will go after the largest memory consumers first.
   */
  public void evictAllFromCache() {
    mBitmapCache.evictAll();
  }

  /**
   * Synchronously get a bitmap.
   */
  public Bitmap fetch(int width,
                      int height,
                      int dimensionRequestType,
                      ViewData.PhotoViewData.PhotoItemViewData photoItem) {
    AppState.assertIsUIThread();
    int adjustedWidth = getAdjustedWidth(width, height, dimensionRequestType, photoItem.getAspectRatio());
    int adjustedHeight = getAdjustedHeight(width, height, dimensionRequestType, photoItem.getAspectRatio());
    return loadBitmapThroughCache(adjustedWidth, adjustedHeight, photoItem);
  }

  /**
   * Request for a bitmap of the given dimensions.
   * Use the dimensionRequestType param to hint at how to deal with images that don't fit the aspect ratio
   *   of the requested dimensions.
   */
  public void fetchAsync(int width,
                         int height,
                         int dimensionRequestType,
                         ViewData.PhotoViewData.PhotoItemViewData photoItem,
                         PhotoImageView photoImageView) {
    AppState.assertIsUIThread();
    photoImageView.assertNoPendingFetch();
    int adjustedWidth = getAdjustedWidth(width, height, dimensionRequestType, photoItem.getAspectRatio());
    int adjustedHeight = getAdjustedHeight(width, height, dimensionRequestType, photoItem.getAspectRatio());

    Bitmap bitmap = mBitmapCache.get(getCachePath(photoItem, adjustedWidth, adjustedHeight),
                                     adjustedWidth,
                                     adjustedHeight);
    if (null != bitmap) {
      // Got it, so just set it on the ImageView.
      photoImageView.setImageBitmap(bitmap);
    } else {
      // Take the scenic route.
      fetchAsyncInternal(adjustedWidth, adjustedHeight, photoItem, photoImageView);
    }
  }

  /**
   * Increase or decrease width with respect to height to match aspect ratio (depending on dimensionRequestType).
   */
  int getAdjustedWidth(int width, int height, int dimensionRequestType, float aspectRatio) {
    if (((DIMENSIONS_AT_LEAST == dimensionRequestType) && (width < Math.round(aspectRatio * height))) ||
        ((DIMENSIONS_AT_MOST == dimensionRequestType) && (width > Math.round(aspectRatio * height)))) {
      // Based on the dimension request type, the width needs to be adjusted.
      width = Math.round(aspectRatio * height);
    }
    return width;
  }

  /**
   * Increase or decrease height with respect to width to match aspect ratio (depending on dimensionRequestType).
   */
  int getAdjustedHeight(int width, int height, int dimensionRequestType, float aspectRatio) {
    if (((DIMENSIONS_AT_LEAST == dimensionRequestType) && (width > Math.round(aspectRatio * height))) ||
        ((DIMENSIONS_AT_MOST == dimensionRequestType) && (width < Math.round(aspectRatio * height)))) {
      // Based on the dimension request type, the height needs to be adjusted.
      height = Math.round(width / aspectRatio);
    }
    return height;
  }

  /**
   * Called when there's a cache miss to initiate the process of loading a bitmap.
   */
  private void fetchAsyncInternal(final int width,
                                  final int height,
                                  final ViewData.PhotoViewData.PhotoItemViewData photoItem,
                                  final PhotoImageView photoImageView) {
    final long requestId = getNextRequestId();

    // Establish a request id with the PhotoImageView.  This will be checked against
    //   the request id in the PhotoImageView at the point we want to set the new bitmap on it to ensure
    //   we're not setting the bitmap on a PhotoImageView that has been recycled and is being used to show
    //   a different image.
    photoImageView.onStartFetch(this, requestId);
    mBitmapLoadHandler.post(new Runnable() {
      @Override
      public void run() {
        // Only proceed if the current request id is still associated with the PhotoImageView.
        if (photoImageView.isCurrentFetcherRequest(requestId))
        {
          final Bitmap bitmap = loadBitmapThroughCache(width, height, photoItem);

          // Dispatch update of PhotoImageView to UIThread.
          mUIHandler.post(new Runnable() {
            @Override
            public void run() {
              photoImageView.setFetchedBitmap(requestId, bitmap);
            }
          });
        }
      }
    });
  }

  private long getNextRequestId() {
    AppState.assertIsUIThread();
    return ++mLastRequestId;
  }

  /**
   * Get bitmap from cache, if available.  Otherwise, load from disk and add to cache.
   */
  private Bitmap loadBitmapThroughCache(int width,
                                        int height,
                                        ViewData.PhotoViewData.PhotoItemViewData photoItem) {
    Bitmap bitmap = mBitmapCache.get(getCachePath(photoItem, width, height), width, height);
    if (null == bitmap) {
      bitmap = getBitmapFromPath(photoItem.getPathToImage(width, height), width, height);
      mBitmapCache.put(getCachePath(photoItem, width, height), width, height, bitmap);
    }
    return bitmap;
  }

  /**
   * Get a bitmap from the given file path which meets the width and/or the height target.
   * The returned bitmap must have dimensions equal to or greater than both dimensions.
   * At least one of the dimensions should be equal to its target.
   * One of the dimensions may be unconstrained and can be 0.
   */
  private Bitmap getBitmapFromPath(String path, int width, int height) {
    Bitmap bitmap = null;
    InputStream file = null;

    try {
      file = mAppState.getAssets().open(path);

      // First, determine the natural dimensions of the image file.
      BitmapFactory.Options options = new BitmapFactory.Options();
      options.inJustDecodeBounds = true;
      BitmapFactory.decodeStream(file, null, options);
      options.inJustDecodeBounds = false;
      if (options.outWidth < 0) {
        // TODO(mike): Consider doing something different for this error.
        throw new Exception("Error reading image file");
      }

      // Should we scale to width or height to meet the target minimums.
      if ((float)width / (float)options.outWidth > (float)height / (float)options.outHeight) {
        // Is width is the constraining dimension?
        if (options.outWidth != width) {
          options.inDensity = options.outWidth;
          options.inTargetDensity = width;
          options.inScaled = true;
        }
      } else {
        if (options.outHeight != height) {
          options.inDensity = options.outHeight;
          options.inTargetDensity = height;
          options.inScaled = true;
        }
      }

      // For now, use RBG_565 so that we're only using 2 bytes per pixel.  If image quality is not high enough,
      //   we'll reconsider default, RGB_8888.
      options.inPreferredConfig = Bitmap.Config.RGB_565;
      options.inDither = true;

      // Read in scaled image.
      bitmap = BitmapFactory.decodeStream(file, null, options);

    } catch (OutOfMemoryError e) {
      e.printStackTrace();
      mBitmapCache.dumpStats();
      throw e;
    } catch (IOException e) {
      e.printStackTrace();
    } catch (Exception e) {
      e.printStackTrace();
    } finally {
      if (null != file) {
        try {
          file.close();
        } catch(IOException e) {
          e.printStackTrace();
        }
      }
    }

    if (null != bitmap) {
      Assert.assertTrue(bitmap.getWidth() >= width && bitmap.getHeight() >= height);
    }

    return bitmap;
  }

  private String getCachePath(ViewData.PhotoViewData.PhotoItemViewData photoItem, int width, int height) {
    // For this simulation, there are only a handful of photo_ids and so to simulate caching of lots more,
    //   we add the item id of the photo to the cache key.
    return String.format("%s_%d", photoItem.getPathToImage(width, height), photoItem.getId());
  }

  /**
   * Cache bitmaps.
   */
  class BitmapCache {
    private static final boolean LOG_CACHE_ACTIVITY = false;
    private BitmapLruCache mCache;

    public BitmapCache(int maxSizeBytes) {
      Log.i(TAG, String.format("Initializing BitmapCache to %d bytes", maxSizeBytes));
      mCache = new BitmapLruCache(maxSizeBytes);
    }

    public Bitmap get(String path, int width, int height) {
      Bitmap bitmap = mCache.get(genKey(path, width, height));
      if (LOG_CACHE_ACTIVITY) {
        Log.d(TAG, String.format("BitmapCache.get(%s) -> %s (%d bytes)",
                                 genKey(path, width, height),
                                 bitmap,
                                 null == bitmap ? 0 : getBitmapByteCount(bitmap)));
      }
      return bitmap;
    }

    public void put(String path, int width, int height, Bitmap value) {
      if (LOG_CACHE_ACTIVITY) {
        Log.d(TAG, String.format("BitmapCache.put(%s, %s (%d bytes))",
                                 genKey(path, width, height),
                                 value,
                                 getBitmapByteCount(value)));
      }
      mCache.put(genKey(path, width, height), value);
    }

    public void dumpStats() {
      Log.d(TAG, String.format("BitmapCache stats: itemCount(%d), hit(%d), miss(%d), eviction(%d), put(%d), " +
                                   "size(%d), avg_item_size(%d)",
                               mCache.putCount() - mCache.evictionCount(),
                               mCache.hitCount(),
                               mCache.missCount(),
                               mCache.evictionCount(),
                               mCache.putCount(),
                               mCache.size(),
                               (mCache.putCount() - mCache.evictionCount()) == 0 ?
                                   0 : mCache.size() /  (mCache.putCount() - mCache.evictionCount())));
    }

    /**
     * Unless we use Android 4.0 or later, we don't have much information about when
     * we need to decrease our memory footprint.
     * For now, we can just evict everything when an activity is paused.
     * We may consider using it just when running on 4.0 or later.
     */
    public void evictAll() {
      dumpStats();
      mCache.evictAll();
    }

    private String genKey(String path, int width, int height) {
      return String.format("%s_%d_%d", path, width, height);
    }

    private int getBitmapByteCount(Bitmap bitmap) {
      // Ideally, we'd use Bitmap.getByteCount(), but that's only supported back to API level 11.
      return bitmap.getRowBytes() * bitmap.getHeight();
    }

    /**
     * Subclass LruCache in order to override sizeOf().
     */
    class BitmapLruCache extends LruCache<String, Bitmap> {
      public BitmapLruCache(int maxSize) {
        super(maxSize);
      }

      @Override
      protected int sizeOf(String key, Bitmap value) {
        return getBitmapByteCount(value);
      }
    }
  }
}
