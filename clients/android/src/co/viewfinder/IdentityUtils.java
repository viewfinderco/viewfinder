// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball

package co.viewfinder;

import junit.framework.Assert;

/**
 * Utility methods to parse and format user identities of this form:
 *   Email:foo@emailscrubbed.com
 *   Phone:+14251234567
 *   FacebookGraph:1234
 */
public class IdentityUtils {
  public enum IdType {
    EMAIL,
    PHONE,
    FACEBOOK,
    VIEWFINDER,
  }

  /**
   * Parses the identity key and returns its type as an ID_TYPE enum value.
   */
  public static IdType getType(String identityKey) {
    if (identityKey.startsWith("Email:")) {
      return IdType.EMAIL;
    } else if (identityKey.startsWith("Phone:")) {
      return IdType.PHONE;
    } else if (identityKey.startsWith("FacebookGraph:")) {
      return IdType.FACEBOOK;
    }

    Assert.assertTrue(identityKey, identityKey.startsWith("VF:"));
    return IdType.VIEWFINDER;
  }

  /**
   * Returns the value of the identity key (part after the colon).
   */
  public static String getValue(String identityKey) {
    int colonPos = identityKey.indexOf(':');
    Assert.assertTrue(identityKey, colonPos != -1);

    return identityKey.substring(colonPos + 1);
  }

  /**
   * Returns a user-friendly formatted version of the identity key value.
   */
  public static String getFormattedValue(String identityKey) {
    // For now, this is same as getValue.
    return getValue(identityKey);
  }
}
