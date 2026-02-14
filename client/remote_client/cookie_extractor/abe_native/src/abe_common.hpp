// App-Bound Encryption Native Module - Common Definitions
// (c) Based on Alexander 'xaitax' Hagenah's Chrome ABE research
// Licensed under the MIT License

#pragma once

#ifdef _WIN32

#include <Windows.h>
#include <wrl/client.h>
#include <bcrypt.h>
#include <string>
#include <vector>
#include <optional>
#include <cstdint>

#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")

namespace AbeNative {

// Protection levels for ABE encryption
enum class ProtectionLevel {
    None = 0,
    PathValidationOld = 1,
    PathValidation = 2,
    Max = 3
};

// Browser types supported
enum class BrowserType {
    Chrome,
    ChromeBeta,
    ChromeDev,
    ChromeCanary,
    Edge,
    EdgeBeta,
    EdgeDev,
    EdgeCanary,
    Brave,
    BraveBeta,
    BraveNightly,
    Avast,
    Opera,
    Vivaldi,
    Unknown
};

// Browser configuration with CLSIDs and IIDs
struct BrowserConfig {
    BrowserType type;
    std::wstring name;
    CLSID clsid;
    IID iid_v1;
    std::optional<IID> iid_v2;
    bool is_edge;
    bool is_avast;
};

// Result structure for decryption operations
struct DecryptResult {
    bool success;
    std::vector<uint8_t> data;
    std::string error_message;
};

// Constants
constexpr size_t AES_GCM_NONCE_LENGTH = 12;
constexpr size_t AES_GCM_TAG_LENGTH = 16;
constexpr size_t V20_PREFIX_LENGTH = 3;  // "v20"
constexpr size_t APPB_PREFIX_LENGTH = 4; // "APPB"

// Check if data has App-Bound prefix
inline bool is_abe_encrypted_key(const std::vector<uint8_t>& data) {
    return data.size() >= APPB_PREFIX_LENGTH &&
           data[0] == 'A' && data[1] == 'P' && data[2] == 'P' && data[3] == 'B';
}

// Check if data has v20 prefix (ABE encrypted value)
inline bool is_abe_encrypted_value(const std::vector<uint8_t>& data) {
    return data.size() >= V20_PREFIX_LENGTH &&
           data[0] == 'v' && data[1] == '2' && data[2] == '0';
}

} // namespace AbeNative

#endif // _WIN32
