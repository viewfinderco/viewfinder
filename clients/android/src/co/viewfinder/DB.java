package co.viewfinder;

import android.util.Log;
import com.google.protobuf.MessageLite;
import com.google.protobuf.Parser;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;

public class DB {
  private static final String TAG = "viewfinder.DB";

  private long mNativeDB;

  public DB(long nativeDB) {
    mNativeDB = nativeDB;
  }

  public void release() {
    if (mNativeDB != 0) {
      ReleaseHandle(mNativeDB);
      mNativeDB = 0;
    }
  }

  public void finalize() {
    // In case release() was not already called...
    release();
  }

  public long nativeHandle() {
    return mNativeDB;
  }

  public DB newHandle() {
    return new DB(NewHandle(mNativeDB));
  }

  public DB newSnapshot() {
    return new DB(NewSnapshot(mNativeDB));
  }

  public boolean put(String key, String value) {
    try {
      return putBytes(key, value.getBytes("UTF-8"));
    } catch (Exception e) {
      return false;
    }
  }

  public boolean putBytes(String key, byte[] value) {
    try {
      Put(mNativeDB, key, value);
      return true;
    } catch (Exception e) {
      return false;
    }
  }

  public boolean putProto(String key, MessageLite value) {
    return putBytes(key, value.toByteArray());
  }

  public String getString(String key) {
    try {
      byte[] bytes = getBytes(key);
      if (bytes == null) {
        return null;
      }
      return new String(bytes, "UTF-8");
    } catch (Exception e) {
      return null;
    }
  }

  public byte[] getBytes(String key) {
    try {
      return Get(mNativeDB, key);
    } catch (Exception e) {
      return null;
    }
  }

  public <T extends MessageLite> T getProto(String key, Parser<T> parser) {
    try {
      byte[] bytes = getBytes(key);
      if (bytes == null) {
        return null;
      }
      return parser.parseFrom(bytes);
    } catch (Exception e) {
      return null;
    }
  }

  public boolean hasKey(String key) {
    return Exists(mNativeDB, key);
  }

  // Native methods.
  private static native void Put(long db, String key, byte[] value);
  private static native byte[] Get(long db, String key);
  private static native boolean Exists(long db, String key);
  private static native long NewSnapshot(long db);
  private static native long NewHandle(long db);
  private static native void ReleaseHandle(long db_handle);
}
