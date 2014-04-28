// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "KeychainUtils.h"
#import "Logging.h"
#import "ValueUtils.h"

namespace {

NSString* const kAccount = @"OAuth";

Dict KeychainQuery(const string& service) {
  return Dict(kSecClass, kSecClassGenericPassword,
              kSecAttrAccount, kAccount,
              kSecAttrService, service);
}

NSData* EncodeToData(NSDictionary* d) {
  NSMutableData* data = [NSMutableData new];
  NSKeyedArchiver* archiver =
      [[NSKeyedArchiver alloc] initForWritingWithMutableData:data];
  [d encodeWithCoder:archiver];
  [archiver finishEncoding];
  return data;
}

NSDictionary* DecodeFromData(NSData* d) {
  NSKeyedUnarchiver* unarchiver =
      [[NSKeyedUnarchiver alloc] initForReadingWithData:d];
  return [[NSDictionary alloc] initWithCoder:unarchiver];
}

}  // namespace

bool SetKeychainItem(const string& service, NSDictionary* d) {
  Dict query(KeychainQuery(service));
  OSStatus status = SecItemDelete(query);
  if (status != errSecSuccess && status != errSecItemNotFound) {
    LOG("delete keychain item (%s) failed: %d", service, status);
  }
  query.insert(kSecValueData, EncodeToData(d));
  return SecItemAdd(query, NULL) == noErr;
}

NSDictionary* GetKeychainItem(const string& service) {
  Dict query(KeychainQuery(service));
  query.insert(kSecReturnData, kCFBooleanTrue);
  query.insert(kSecMatchLimit, kSecMatchLimitOne);
  CFDataRef result = NULL;
  OSStatus status = SecItemCopyMatching(query, (CFTypeRef*)&result);
  NSDictionary* d = NULL;
  if (status == noErr) {
    d = DecodeFromData((__bridge NSData*)result);
  }
  if (result) {
    CFRelease(result);
  }
  return d;
}

void DeleteKeychainItem(const string& service) {
  Dict query(KeychainQuery(service));
  OSStatus status = SecItemDelete(query);
  if (status != errSecSuccess && status != errSecItemNotFound) {
    LOG("delete keychain item (%s) failed: %d", service, status);
  }
}

void ListKeychain() {
  Dict query(kSecClass, kSecClassGenericPassword,
             kSecAttrAccount, kAccount,
             kSecReturnAttributes, kCFBooleanTrue,
             kSecMatchLimit, kSecMatchLimitAll);
  CFArrayRef result = NULL;
  OSStatus status = SecItemCopyMatching(query, (CFTypeRef*)&result);
  if (status == errSecSuccess) {
    LOG("keychain: %s", (__bridge id)result);
  }
  if (result) {
    CFRelease(result);
  }
}

void ClearKeychain() {
  Dict query(kSecClass, kSecClassGenericPassword,
             kSecAttrAccount, kAccount);
  OSStatus status = SecItemDelete(query);
  if (status != errSecSuccess) {
    LOG("clearing keychain failed: %d", status);
  }
}

// local variables:
// mode: c++
// end:
