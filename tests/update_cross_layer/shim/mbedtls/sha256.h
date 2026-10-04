#pragma once
#include <openssl/sha.h>
struct mbedtls_sha256_context { SHA256_CTX context; };
inline void mbedtls_sha256_init(mbedtls_sha256_context*){}
inline int mbedtls_sha256_starts_ret(mbedtls_sha256_context* c,int){return SHA256_Init(&c->context)==1?0:-1;}
inline int mbedtls_sha256_update_ret(mbedtls_sha256_context* c,const unsigned char* p,size_t n){return SHA256_Update(&c->context,p,n)==1?0:-1;}
inline int mbedtls_sha256_finish_ret(mbedtls_sha256_context* c,unsigned char* out){return SHA256_Final(out,&c->context)==1?0:-1;}
