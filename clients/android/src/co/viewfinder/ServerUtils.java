// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault
package co.viewfinder;

import co.viewfinder.proto.*;

import com.google.protobuf.Descriptors;
import com.google.protobuf.GeneratedMessage;

import android.util.Log;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import junit.framework.Assert;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.json.JSONTokener;

/**
 * JSON/Protobuf utilities.
 *
 */
public class ServerUtils {
  private static final String TAG = "viewfinder.ServerUtils";

  private static void maybePut(JSONObject obj, String key, String value) throws JSONException {
    if (!Utils.isEmptyOrNull(value)) {
      obj.put(key, value);
    }
  }

  private static void maybePut(JSONObject obj, String key, long value) throws JSONException {
    if (value != -1) {
      obj.put(key, value);
    }
  }


  private static void setProtoObject(GeneratedMessage.Builder builder, String fieldName, Object fieldValue) {
    Descriptors.Descriptor desc = builder.getDescriptorForType();
    Descriptors.FieldDescriptor fieldDesc = desc.findFieldByName(fieldName);
    Assert.assertNotNull("Missing field: name=" + fieldName + " value=" + fieldValue, fieldDesc);

    builder.setField(fieldDesc, fieldValue);
  }

  public static void maybeSetString(GeneratedMessage.Builder builder, String fieldName, String fieldValue) {
    if (Utils.isEmptyOrNull(fieldValue)) {
      return;
    }
    setProtoObject(builder, fieldName, fieldValue);
  }

  public static void maybeSetInt(GeneratedMessage.Builder builder, String fieldName, int fieldValue) {
    if (fieldValue == -1) {
      return;
    }
    setProtoObject(builder, fieldName, fieldValue);
  }

  public static void maybeSetLong(GeneratedMessage.Builder builder, String fieldName, long fieldValue) {
    if (fieldValue == -1) {
      return;
    }
    setProtoObject(builder, fieldName, fieldValue);
  }

  public static void maybeSetDouble(GeneratedMessage.Builder builder, String fieldName, double fieldValue) {
    if (fieldValue == -1) {
      return;
    }
    setProtoObject(builder, fieldName, fieldValue);
  }
}
