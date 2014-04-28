// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault
package co.viewfinder;

import android.os.Build;
import android.util.Log;
import android.view.View;
import android.view.ViewTreeObserver;
import com.google.protobuf.InvalidProtocolBufferException;
import com.google.protobuf.MessageLite;
import com.google.protobuf.Parser;
import java.util.ArrayList;
import java.util.List;

public class Utils {
  private static final String TAG = "viewfinder.Utils";

  public static boolean isEmptyOrNull(String val) {
    return (val == null || "".equals(val));
  }

  public static boolean isEmptyOrNull(byte[] val) {
    return (val == null || val.length == 0);
  }

  /**
   * Produce single string with comma separated elements from input String array.
   * Optionally skip last element so that caller may insert a conjunction and/or special formatting.
   */
  public static String enumeratedStringFromStrings(String[] strings, boolean skipLast) {
    StringBuilder sb = new StringBuilder("");
    int count = strings.length - (skipLast ? 1 : 0);

    for (int i = 0; i < count; i++) {
      if (i != 0) {
        sb.append(", ");
      }
      sb.append(strings[i]);
    }
    return sb.toString();
  }

  public static <T extends MessageLite> T parseProto(byte[] bytes, Parser<T> parser) {
    if (isEmptyOrNull(bytes)) {
      return null;
    }
    try {
      return parser.parseFrom(bytes);
    } catch (InvalidProtocolBufferException e) {
      return null;
    }
  }

  public static String AddIdentityPrefix(String identity) {
    if (identity.indexOf("@") != -1) {
      return "Email:" + identity;
    } else {
      return "Phone:" + identity;
    }
  }

  public static void dumpBuildInfo() {
    Log.d(TAG, "BUILD Dump: ");
    Log.d(TAG, "VERSION.CODENAME: " + Build.VERSION.CODENAME);
    Log.d(TAG, "VERSION.INCREMENTAL: " + Build.VERSION.INCREMENTAL);
    Log.d(TAG, "VERSION.RELEASE: " + Build.VERSION.RELEASE);
    Log.d(TAG, "VERSION.SDK_INT: " + Build.VERSION.SDK_INT);
    Log.d(TAG, "BOARD: " +        Build.BOARD);
    Log.d(TAG, "BOOTLOADER: " +   Build.BOOTLOADER);
    Log.d(TAG, "BRAND: " +        Build.BRAND);
    Log.d(TAG, "CPU_ABI: " +      Build.CPU_ABI);
    Log.d(TAG, "CPU_ABI2: " +     Build.CPU_ABI2);
    Log.d(TAG, "DEVICE: " +       Build.DEVICE);
    Log.d(TAG, "DISPLAY: " +      Build.DISPLAY);
    Log.d(TAG, "FINGERPRINT: " +  Build.FINGERPRINT);
    Log.d(TAG, "HARDWARE: " +     Build.HARDWARE);
    Log.d(TAG, "HOST: " +         Build.HOST);
    Log.d(TAG, "ID: " +           Build.ID);
    Log.d(TAG, "MANUFACTURER: " + Build.MANUFACTURER);
    Log.d(TAG, "MODEL: " +        Build.MODEL);
    Log.d(TAG, "PRODUCT: " +      Build.PRODUCT);
    Log.d(TAG, "RADIO: " +        Build.RADIO);
    if (isGingerbreadCapableDevice()) {
      Log.d(TAG, "SERIAL: " +       Build.SERIAL);
    }
    Log.d(TAG, "TAGS: " +         Build.TAGS);
    Log.d(TAG, "TIME: " +         Build.TIME);
    Log.d(TAG, "TYPE: " +         Build.TYPE);
    Log.d(TAG, "USER: " +         Build.USER);
  }

  public static boolean isEmulator() {
    return Build.HARDWARE.contains("goldfish");
  }

  public static String osAndroidRelease() {
    return "Android " + osRelease();
  }

  public static String osRelease() {
    return Build.VERSION.RELEASE;
  }

  public static String deviceMakeModel() {
    return Build.MANUFACTURER + " " + Build.MODEL;
  }

  public static String deviceHost() {
    return Build.HOST;
  }

  public static String encodeVariableLength(long value) {
    StringBuilder builder = new StringBuilder();
    while (value >= 128) {
      // It's important to cast to char, or StringBuilder will append the string representation of the number.
      builder.append((char)((value & 127) | 128));
      value = value >> 7;
    }
    builder.append((char)(value & 127));
    return builder.toString();
  }

  public static boolean isHoneycombCapableDevice() {
    return Build.VERSION.SDK_INT >= Build.VERSION_CODES.HONEYCOMB;
  }

  public static boolean isGingerbreadCapableDevice() {
    return Build.VERSION.SDK_INT >= Build.VERSION_CODES.GINGERBREAD;
  }

  public static boolean isJellyBeanCapableDevice() {
    return Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN;
  }

  @SuppressWarnings("deprecation")
  public static void removeOnGlobalLayoutListener(View v, ViewTreeObserver.OnGlobalLayoutListener listener){
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.JELLY_BEAN) {
      v.getViewTreeObserver().removeGlobalOnLayoutListener(listener);
    } else {
      v.getViewTreeObserver().removeOnGlobalLayoutListener(listener);
    }
  }

  // TODO(marc): the entire Base64 encoding is translated from the iOS client.

  private static char[] stringToCharArray(String str) {
    char[] arr = new char[str.length()];
    for (int i = 0; i < str.length(); ++i) {
      arr[i] = str.charAt(i);
    }
    return arr;
  }

  private static final String BASE64_HEX_CHARSET = "-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz";
  private static final char[] BASE64_HEX_ENCODING_TABLE = stringToCharArray(BASE64_HEX_CHARSET);

  public static String Base64HexEncode(String str, boolean padding) {
    return Base64EncodeInternal(str, BASE64_HEX_ENCODING_TABLE, padding);
  }

  private static String Base64EncodeInternal(String str, char[] encoding_table, boolean padding) {
    if (isEmptyOrNull(str)) {
      return "";
    }

    int len = str.length();
    char[] src = str.toCharArray();
    StringBuilder result = new StringBuilder();
    int i = 0;

    // Keep going until we have less than 3 octets
    int index = 0;
    while (len > 2) {
      result.append(encoding_table[src[index] >> 2]);
      result.append(encoding_table[((src[index] & 0x03) << 4) + (src[index + 1] >> 4)]);
      result.append(encoding_table[((src[index + 1] & 0x0f) << 2) + (src[index + 2] >> 6)]);
      result.append(encoding_table[src[index + 2] & 0x3f]);

      // We just handled 3 octets of data
      index += 3;
      len -= 3;
    }

    // Now deal with the tail end of things
    if (len != 0) {
      result.append(encoding_table[src[index] >> 2]);
      if (len > 1) {
        result.append(encoding_table[((src[index] & 0x03) << 4) + (src[index + 1] >> 4)]);
        result.append(encoding_table[(src[index + 1] & 0x0f) << 2]);
        if (padding) {
          result.append('=');
        }
      } else {
        result.append(encoding_table[(src[index] & 0x03) << 4]);
        if (padding) {
          result.append('=');
          result.append('=');
        }
      }
    }

    return result.toString();
  }

  public static List<Long> longArrayToList(long[] array) {
    if (array == null) {
      return null;
    }
    ArrayList<Long> a = new ArrayList<Long>(array.length);
    for (long elem : array) {
      a.add(elem);
    }
    return a;
  }
}
