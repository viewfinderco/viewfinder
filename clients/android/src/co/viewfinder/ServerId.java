// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault
package co.viewfinder;

import android.util.Log;

class ServerId {
  // NOTE: these should be kept up to date with the id prefixes used by
  //       the server. These can be found in backend/db/id_prefix.py.
  private static final String ACTIVITY_PREFIX = "a";
  private static final String COMMENT_PREFIX = "c";
  private static final String EPISODE_PREFIX = "e";
  private static final String OPERATION_PREFIX = "o";
  private static final String PHOTO_PREFIX = "p";
  private static final String VIEWPOINT_PREFIX = "v";

  private static String encodeId(String prefix, long deviceId, long localId) {
    String preEnc = Utils.encodeVariableLength(deviceId) + Utils.encodeVariableLength(localId);
    return prefix + Utils.Base64HexEncode(preEnc, false);
  }

  public static String encodeOperationId(long deviceId, long opId) {
    return encodeId(OPERATION_PREFIX, deviceId, opId);
  }
}
