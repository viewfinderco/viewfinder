// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_KEYCHAIN_UTILS_H
#define VIEWFINDER_KEYCHAIN_UTILS_H

#import <Foundation/NSDictionary.h>
#import "Utils.h"

// Sets the keychain item for the specified service, returning true on success
// and false on failure. This function overwrites any previously specified item
// for the service.
bool SetKeychainItem(const string& service, NSDictionary* d);

// Retrieves the keychain item for the specified service, returning NULL if no
// item can be found.
NSDictionary* GetKeychainItem(const string& service);

// Deletes the keychain item for the specified service.
void DeleteKeychainItem(const string& service);

// Lists all (OAuth) keychain items.
void ListKeychain();

// Deletes all (OAuth) keychain items.
void ClearKeychain();

#endif  // VIEWFINDER_KEYCHAIN_UTILS_H
