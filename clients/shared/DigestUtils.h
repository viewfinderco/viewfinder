// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_DIGEST_UTILS_H
#define VIEWFINDER_DIGEST_UTILS_H

#import "Utils.h"

#if defined(OS_IOS)

#import <CommonCrypto/CommonDigest.h>

#define MD5_DIGEST_LENGTH CC_MD5_DIGEST_LENGTH
#define SHA256_DIGEST_LENGTH CC_SHA256_DIGEST_LENGTH

// On IOS, the MD5*/SHA256* routines are simple wrappers around the
// CommonCrypto library.
typedef CC_MD5_CTX MD5_CTX;
inline void MD5_Init(MD5_CTX* ctx) {
  CC_MD5_Init(ctx);
}
inline void MD5_Update(MD5_CTX* ctx, const void* data, size_t len) {
  CC_MD5_Update(ctx, data, len);
}
inline void MD5_Final(MD5_CTX* ctx, uint8_t* digest) {
  CC_MD5_Final(digest, ctx);
}

typedef CC_SHA256_CTX SHA256_CTX;
inline void SHA256_Init(SHA256_CTX* ctx) {
  CC_SHA256_Init(ctx);
}
inline void SHA256_Update(SHA256_CTX* ctx, const void* data, size_t len) {
  CC_SHA256_Update(ctx, data, len);
}
inline void SHA256_Final(SHA256_CTX* ctx, uint8_t* digest) {
  CC_SHA256_Final(digest, ctx);
}

#elif defined(OS_ANDROID)


#define SHA256_DIGEST_LENGTH 32
#define MD5_DIGEST_LENGTH 16

// On Android, we use our own MD5/SHA256 implementations (provided by the
// internets).
struct MD5_CTX {
  uint8_t data[64];
  uint32_t datalen;
  uint64_t bitlen;
  uint32_t state[4];
};

struct SHA256_CTX {
  uint8_t data[64];
  uint32_t datalen;
  uint64_t bitlen;
  uint32_t state[8];
};

void MD5_Init(MD5_CTX* ctx);
void MD5_Update(MD5_CTX* ctx, const void* data, size_t len);
void MD5_Final(MD5_CTX* ctx, uint8_t* digest);

void SHA256_Init(SHA256_CTX* ctx);
void SHA256_Update(SHA256_CTX* ctx, const void* data, size_t len);
void SHA256_Final(SHA256_CTX* ctx, uint8_t* digest);

#endif  // defined(OS_ANDROID)

string MD5(const Slice& str);
string MD5HexToBase64(const Slice& str);

#endif  // VIEWFINDER_DIGEST_UTILS_H
