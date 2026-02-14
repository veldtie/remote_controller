// App-Bound Encryption Native Module - AES-GCM Decryption
// (c) Based on Alexander 'xaitax' Hagenah's Chrome ABE research
// Licensed under the MIT License

#pragma once

#ifdef _WIN32

#include "abe_common.hpp"
#include <memory>

#ifndef NT_SUCCESS
#define NT_SUCCESS(Status) (((NTSTATUS)(Status)) >= 0)
#endif

namespace AbeNative {
namespace Crypto {

class AesGcm {
public:
    // Decrypt AES-GCM encrypted data (v20 format)
    // Format: "v20" (3 bytes) + IV (12 bytes) + Ciphertext + Tag (16 bytes)
    static std::optional<std::vector<uint8_t>> Decrypt(
        const std::vector<uint8_t>& key,
        const std::vector<uint8_t>& encrypted_data
    ) {
        constexpr size_t PREFIX_LEN = 3;  // "v20"
        constexpr size_t IV_LEN = 12;
        constexpr size_t TAG_LEN = 16;
        constexpr size_t OVERHEAD = PREFIX_LEN + IV_LEN + TAG_LEN;

        if (encrypted_data.size() < OVERHEAD) {
            return std::nullopt;
        }

        // Check v20 prefix
        if (memcmp(encrypted_data.data(), "v20", PREFIX_LEN) != 0) {
            return std::nullopt;
        }

        BCRYPT_ALG_HANDLE hAlg = nullptr;
        if (!NT_SUCCESS(BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_AES_ALGORITHM, nullptr, 0))) {
            return std::nullopt;
        }

        auto algCloser = [](BCRYPT_ALG_HANDLE h) { if (h) BCryptCloseAlgorithmProvider(h, 0); };
        std::unique_ptr<void, decltype(algCloser)> algGuard(hAlg, algCloser);

        if (!NT_SUCCESS(BCryptSetProperty(hAlg, BCRYPT_CHAINING_MODE,
                                          (PUCHAR)BCRYPT_CHAIN_MODE_GCM,
                                          sizeof(BCRYPT_CHAIN_MODE_GCM), 0))) {
            return std::nullopt;
        }

        BCRYPT_KEY_HANDLE hKey = nullptr;
        if (!NT_SUCCESS(BCryptGenerateSymmetricKey(hAlg, &hKey, nullptr, 0,
                                                   (PUCHAR)key.data(), (ULONG)key.size(), 0))) {
            return std::nullopt;
        }

        auto keyCloser = [](BCRYPT_KEY_HANDLE h) { if (h) BCryptDestroyKey(h); };
        std::unique_ptr<void, decltype(keyCloser)> keyGuard(hKey, keyCloser);

        const uint8_t* iv = encrypted_data.data() + PREFIX_LEN;
        const uint8_t* tag = encrypted_data.data() + (encrypted_data.size() - TAG_LEN);
        const uint8_t* ct = iv + IV_LEN;
        ULONG ctLen = static_cast<ULONG>(encrypted_data.size() - OVERHEAD);

        BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO authInfo;
        BCRYPT_INIT_AUTH_MODE_INFO(authInfo);
        authInfo.pbNonce = (PUCHAR)iv;
        authInfo.cbNonce = IV_LEN;
        authInfo.pbTag = (PUCHAR)tag;
        authInfo.cbTag = TAG_LEN;

        std::vector<uint8_t> plain(ctLen > 0 ? ctLen : 1);
        ULONG outLen = 0;

        if (!NT_SUCCESS(BCryptDecrypt(hKey, (PUCHAR)ct, ctLen, &authInfo,
                                      nullptr, 0, plain.data(), (ULONG)plain.size(), &outLen, 0))) {
            return std::nullopt;
        }

        plain.resize(outLen);
        return plain;
    }

    // Decrypt without v20 prefix (raw AES-GCM)
    static std::optional<std::vector<uint8_t>> DecryptRaw(
        const std::vector<uint8_t>& key,
        const std::vector<uint8_t>& iv,
        const std::vector<uint8_t>& ciphertext,
        const std::vector<uint8_t>& tag
    ) {
        if (iv.size() != AES_GCM_NONCE_LENGTH || tag.size() != AES_GCM_TAG_LENGTH) {
            return std::nullopt;
        }

        BCRYPT_ALG_HANDLE hAlg = nullptr;
        if (!NT_SUCCESS(BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_AES_ALGORITHM, nullptr, 0))) {
            return std::nullopt;
        }

        auto algCloser = [](BCRYPT_ALG_HANDLE h) { if (h) BCryptCloseAlgorithmProvider(h, 0); };
        std::unique_ptr<void, decltype(algCloser)> algGuard(hAlg, algCloser);

        if (!NT_SUCCESS(BCryptSetProperty(hAlg, BCRYPT_CHAINING_MODE,
                                          (PUCHAR)BCRYPT_CHAIN_MODE_GCM,
                                          sizeof(BCRYPT_CHAIN_MODE_GCM), 0))) {
            return std::nullopt;
        }

        BCRYPT_KEY_HANDLE hKey = nullptr;
        if (!NT_SUCCESS(BCryptGenerateSymmetricKey(hAlg, &hKey, nullptr, 0,
                                                   (PUCHAR)key.data(), (ULONG)key.size(), 0))) {
            return std::nullopt;
        }

        auto keyCloser = [](BCRYPT_KEY_HANDLE h) { if (h) BCryptDestroyKey(h); };
        std::unique_ptr<void, decltype(keyCloser)> keyGuard(hKey, keyCloser);

        BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO authInfo;
        BCRYPT_INIT_AUTH_MODE_INFO(authInfo);
        authInfo.pbNonce = (PUCHAR)iv.data();
        authInfo.cbNonce = (ULONG)iv.size();
        authInfo.pbTag = (PUCHAR)tag.data();
        authInfo.cbTag = (ULONG)tag.size();

        std::vector<uint8_t> plain(ciphertext.size() > 0 ? ciphertext.size() : 1);
        ULONG outLen = 0;

        if (!NT_SUCCESS(BCryptDecrypt(hKey, (PUCHAR)ciphertext.data(), (ULONG)ciphertext.size(),
                                      &authInfo, nullptr, 0, plain.data(), (ULONG)plain.size(), &outLen, 0))) {
            return std::nullopt;
        }

        plain.resize(outLen);
        return plain;
    }
};

} // namespace Crypto
} // namespace AbeNative

#endif // _WIN32
