// App-Bound Encryption Native Module - IElevator COM Interface
// (c) Based on Alexander 'xaitax' Hagenah's Chrome ABE research
// Licensed under the MIT License

#pragma once

#ifdef _WIN32

#include "abe_common.hpp"
#include <stdexcept>
#include <sstream>

namespace AbeNative {
namespace Com {

// IElevator interface definitions for different browsers
// Chrome/Brave base IElevator (3 methods after IUnknown)
MIDL_INTERFACE("A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C")
IBaseElevator : public IUnknown {
public:
    virtual HRESULT STDMETHODCALLTYPE RunRecoveryCRXElevated(
        const WCHAR*, const WCHAR*, const WCHAR*, const WCHAR*, DWORD, ULONG_PTR*) = 0;
    virtual HRESULT STDMETHODCALLTYPE EncryptData(
        ProtectionLevel, const BSTR, BSTR*, DWORD*) = 0;
    virtual HRESULT STDMETHODCALLTYPE DecryptData(
        const BSTR, BSTR*, DWORD*) = 0;
};

// Avast IElevator (12 methods - includes browser-specific methods)
MIDL_INTERFACE("7737BB9F-BAC1-4C71-A696-7C82D7994B6F")
IAvastElevator : public IUnknown {
public:
    virtual HRESULT STDMETHODCALLTYPE RunRecoveryCRXElevated(
        const WCHAR*, const WCHAR*, const WCHAR*, const WCHAR*, DWORD, ULONG_PTR*) = 0;
    virtual HRESULT STDMETHODCALLTYPE UpdateSearchProviderElevated(const WCHAR*) = 0;
    virtual HRESULT STDMETHODCALLTYPE CleanupMigrateStateElevated(void) = 0;
    virtual HRESULT STDMETHODCALLTYPE UpdateInstallerLangElevated(const WCHAR*) = 0;
    virtual HRESULT STDMETHODCALLTYPE UpdateBrandValueElevated(const WCHAR*) = 0;
    virtual HRESULT STDMETHODCALLTYPE MigrateUninstallKeyElevated(const WCHAR*) = 0;
    virtual HRESULT STDMETHODCALLTYPE UpdateEndpointIdElevated(const char*) = 0;
    virtual HRESULT STDMETHODCALLTYPE UpdateFingerprintIdElevated(const char*) = 0;
    virtual HRESULT STDMETHODCALLTYPE RunMicroMVDifferentialUpdate(void) = 0;
    virtual HRESULT STDMETHODCALLTYPE EncryptData(ProtectionLevel, const BSTR, BSTR*, DWORD*) = 0;
    virtual HRESULT STDMETHODCALLTYPE DecryptData(const BSTR, BSTR*, DWORD*) = 0;
    virtual HRESULT STDMETHODCALLTYPE DecryptData2(const BSTR, BSTR*, DWORD*) = 0;
};

// Edge IElevator base placeholder (3 methods)
MIDL_INTERFACE("E12B779C-CDB8-4F19-95A0-9CA19B31A8F6")
IEdgeElevatorBase : public IUnknown {
public:
    virtual HRESULT STDMETHODCALLTYPE EdgeBaseMethod1(void) = 0;
    virtual HRESULT STDMETHODCALLTYPE EdgeBaseMethod2(void) = 0;
    virtual HRESULT STDMETHODCALLTYPE EdgeBaseMethod3(void) = 0;
};

// Edge intermediate IElevator (inherits from base)
MIDL_INTERFACE("A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C")
IEdgeIntermediateElevator : public IEdgeElevatorBase {
public:
    virtual HRESULT STDMETHODCALLTYPE RunRecoveryCRXElevated(
        const WCHAR*, const WCHAR*, const WCHAR*, const WCHAR*, DWORD, ULONG_PTR*) = 0;
    virtual HRESULT STDMETHODCALLTYPE EncryptData(ProtectionLevel, const BSTR, BSTR*, DWORD*) = 0;
    virtual HRESULT STDMETHODCALLTYPE DecryptData(const BSTR, BSTR*, DWORD*) = 0;
};

// Edge IElevator v1
MIDL_INTERFACE("C9C2B807-7731-4F34-81B7-44FF7779522B")
IEdgeElevator : public IEdgeIntermediateElevator {};

// Edge IElevator v2 (Chrome 144+)
MIDL_INTERFACE("8F7B6792-784D-4047-845D-1782EFBEF205")
IEdgeElevator2 : public IEdgeIntermediateElevator {
public:
    virtual HRESULT STDMETHODCALLTYPE RunIsolatedChrome(
        const WCHAR*, const WCHAR*, DWORD*, ULONG_PTR*) = 0;
    virtual HRESULT STDMETHODCALLTYPE AcceptInvitation(const WCHAR*) = 0;
};

// Known browser CLSIDs
namespace CLSID {
    // Chrome variants
    const CLSID Chrome = {0x708860E0, 0xF641, 0x4611, {0x88, 0x95, 0x7D, 0x86, 0x7D, 0xD3, 0x67, 0x5B}};
    const CLSID ChromeBeta = {0xDD2646BA, 0x3707, 0x4BF8, {0xB9, 0xA7, 0x03, 0x86, 0x91, 0xA6, 0x8F, 0xC2}};
    const CLSID ChromeDev = {0xDA7FDCA5, 0x2CAA, 0x4637, {0xAA, 0x17, 0x07, 0x49, 0xF6, 0x4F, 0x49, 0xD2}};
    const CLSID ChromeCanary = {0x3A84F9C2, 0x6164, 0x485C, {0xA7, 0xD9, 0x4B, 0x27, 0xF8, 0xAC, 0x3D, 0x58}};
    
    // Edge variants
    const CLSID Edge = {0x1EBBCAB8, 0xD9A8, 0x4FBA, {0x8B, 0xC2, 0x7B, 0x76, 0x87, 0xB3, 0x1B, 0x52}};
    const CLSID EdgeBeta = {0x0BF56C16, 0x8FF7, 0x4F59, {0xBC, 0xEB, 0x5F, 0xA2, 0xC4, 0x3A, 0x5E, 0x83}};
    const CLSID EdgeDev = {0x1F8A8A7F, 0x9E44, 0x46C3, {0x96, 0xAE, 0x85, 0xE7, 0x84, 0x0B, 0x14, 0xB6}};
    const CLSID EdgeCanary = {0xD1D80F3B, 0x4F3E, 0x4D7C, {0xBF, 0x56, 0xB2, 0xBF, 0xE8, 0xF7, 0x70, 0x71}};
    
    // Brave variants
    const CLSID Brave = {0x576B31AF, 0x6369, 0x4B6B, {0x85, 0x60, 0xE4, 0xB2, 0x03, 0xA9, 0x7A, 0x8B}};
    const CLSID BraveBeta = {0x68FFB1C9, 0xE60C, 0x4B22, {0xA4, 0x35, 0x45, 0x3E, 0x94, 0x3F, 0x29, 0xC0}};
    const CLSID BraveNightly = {0x93D8C03B, 0x6F72, 0x4F8D, {0x98, 0x4A, 0x3B, 0xE9, 0x89, 0x62, 0x83, 0x2D}};
    
    // Avast
    const CLSID Avast = {0x30D7F8EB, 0x1F8E, 0x4D77, {0xA1, 0x5E, 0xC9, 0x3C, 0x34, 0x2A, 0xE5, 0x4D}};
}

// IID definitions
namespace IID {
    const IID BaseElevator = {0xA949CB4E, 0xC4F9, 0x44C4, {0xB2, 0x13, 0x6B, 0xF8, 0xAA, 0x9A, 0xC6, 0x9C}};
    const IID EdgeElevator = {0xC9C2B807, 0x7731, 0x4F34, {0x81, 0xB7, 0x44, 0xFF, 0x77, 0x79, 0x52, 0x2B}};
    const IID EdgeElevator2 = {0x8F7B6792, 0x784D, 0x4047, {0x84, 0x5D, 0x17, 0x82, 0xEF, 0xBE, 0xF2, 0x05}};
    const IID AvastElevator = {0x7737BB9F, 0xBAC1, 0x4C71, {0xA6, 0x96, 0x7C, 0x82, 0xD7, 0x99, 0x4B, 0x6F}};
    
    // Chrome variants (same IID as base, but version-specific)
    const IID ChromeElevator = {0x463ABECF, 0x410D, 0x407F, {0x8A, 0xF5, 0x0D, 0xF3, 0x5A, 0x00, 0x5C, 0xC8}};
    const IID BraveElevator = {0xF396861E, 0x0C8E, 0x4C71, {0x82, 0x56, 0x2F, 0xAE, 0x6D, 0x75, 0x9C, 0xE9}};
    const IID BraveElevator2 = {0x1BF5208B, 0x295F, 0x4992, {0xB5, 0xF4, 0x3A, 0x9B, 0xB6, 0x49, 0x48, 0x38}};
}

// BSTR deleter for smart pointer
struct BstrDeleter {
    void operator()(BSTR b) { if (b) SysFreeString(b); }
};

class Elevator {
public:
    Elevator() : m_initialized(false) {
        HRESULT hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
        if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) {
            throw std::runtime_error("CoInitializeEx failed");
        }
        m_initialized = true;
    }

    ~Elevator() {
        if (m_initialized) {
            CoUninitialize();
        }
    }

    // Decrypt ABE key using IElevator COM interface
    DecryptResult DecryptKey(
        const std::vector<uint8_t>& encrypted_key,
        BrowserType browser_type
    ) {
        DecryptResult result;
        result.success = false;

        try {
            // Allocate BSTR from encrypted key
            BSTR bstrEnc = SysAllocStringByteLen(
                reinterpret_cast<const char*>(encrypted_key.data()),
                static_cast<UINT>(encrypted_key.size())
            );
            if (!bstrEnc) {
                result.error_message = "Failed to allocate BSTR for encrypted key";
                return result;
            }
            std::unique_ptr<OLECHAR[], BstrDeleter> encGuard(bstrEnc);

            BSTR bstrPlain = nullptr;
            DWORD comErr = 0;
            HRESULT hr = E_FAIL;

            // Try decryption based on browser type
            switch (browser_type) {
                case BrowserType::Edge:
                case BrowserType::EdgeBeta:
                case BrowserType::EdgeDev:
                case BrowserType::EdgeCanary:
                    hr = DecryptEdge(bstrEnc, &bstrPlain, &comErr, browser_type);
                    break;
                case BrowserType::Avast:
                    hr = DecryptAvast(bstrEnc, &bstrPlain, &comErr);
                    break;
                default:
                    hr = DecryptChromium(bstrEnc, &bstrPlain, &comErr, browser_type);
                    break;
            }

            if (FAILED(hr)) {
                std::ostringstream oss;
                oss << "DecryptData failed: 0x" << std::hex << hr;
                if (comErr != 0) {
                    oss << " (COM error: " << std::dec << comErr << ")";
                }
                result.error_message = oss.str();
                return result;
            }

            if (!bstrPlain) {
                result.error_message = "Decrypted key is null";
                return result;
            }

            std::unique_ptr<OLECHAR[], BstrDeleter> plainGuard(bstrPlain);
            UINT len = SysStringByteLen(bstrPlain);

            result.data.resize(len);
            memcpy(result.data.data(), bstrPlain, len);
            result.success = true;

        } catch (const std::exception& e) {
            result.error_message = e.what();
        }

        return result;
    }

    // Try all available browsers
    DecryptResult DecryptKeyAuto(const std::vector<uint8_t>& encrypted_key) {
        static const BrowserType browsers[] = {
            BrowserType::Chrome,
            BrowserType::Edge,
            BrowserType::Brave,
            BrowserType::ChromeBeta,
            BrowserType::ChromeDev,
            BrowserType::ChromeCanary,
            BrowserType::EdgeBeta,
            BrowserType::BraveBeta,
            BrowserType::Avast
        };

        for (auto browser : browsers) {
            auto result = DecryptKey(encrypted_key, browser);
            if (result.success) {
                return result;
            }
        }

        DecryptResult result;
        result.success = false;
        result.error_message = "All browser elevation services failed";
        return result;
    }

private:
    bool m_initialized;

    CLSID GetCLSID(BrowserType type) {
        switch (type) {
            case BrowserType::Chrome: return CLSID::Chrome;
            case BrowserType::ChromeBeta: return CLSID::ChromeBeta;
            case BrowserType::ChromeDev: return CLSID::ChromeDev;
            case BrowserType::ChromeCanary: return CLSID::ChromeCanary;
            case BrowserType::Edge: return CLSID::Edge;
            case BrowserType::EdgeBeta: return CLSID::EdgeBeta;
            case BrowserType::EdgeDev: return CLSID::EdgeDev;
            case BrowserType::EdgeCanary: return CLSID::EdgeCanary;
            case BrowserType::Brave: return CLSID::Brave;
            case BrowserType::BraveBeta: return CLSID::BraveBeta;
            case BrowserType::BraveNightly: return CLSID::BraveNightly;
            case BrowserType::Avast: return CLSID::Avast;
            default: return CLSID::Chrome;
        }
    }

    HRESULT DecryptChromium(BSTR bstrEnc, BSTR* bstrPlain, DWORD* comErr, BrowserType type) {
        CLSID clsid = GetCLSID(type);
        HRESULT hr = E_FAIL;

        // Try v2 interface first (Chrome 144+)
        Microsoft::WRL::ComPtr<IBaseElevator> elevator;
        
        // Try browser-specific IID
        if (type == BrowserType::Brave || type == BrowserType::BraveBeta || type == BrowserType::BraveNightly) {
            hr = CoCreateInstance(clsid, nullptr, CLSCTX_LOCAL_SERVER, IID::BraveElevator2, &elevator);
            if (FAILED(hr)) {
                hr = CoCreateInstance(clsid, nullptr, CLSCTX_LOCAL_SERVER, IID::BraveElevator, &elevator);
            }
        } else {
            hr = CoCreateInstance(clsid, nullptr, CLSCTX_LOCAL_SERVER, IID::ChromeElevator, &elevator);
        }

        // Fallback to base IID
        if (FAILED(hr)) {
            hr = CoCreateInstance(clsid, nullptr, CLSCTX_LOCAL_SERVER, IID::BaseElevator, &elevator);
        }

        if (SUCCEEDED(hr)) {
            CoSetProxyBlanket(
                elevator.Get(),
                RPC_C_AUTHN_DEFAULT,
                RPC_C_AUTHZ_DEFAULT,
                COLE_DEFAULT_PRINCIPAL,
                RPC_C_AUTHN_LEVEL_PKT_PRIVACY,
                RPC_C_IMP_LEVEL_IMPERSONATE,
                nullptr,
                EOAC_DYNAMIC_CLOAKING
            );
            hr = elevator->DecryptData(bstrEnc, bstrPlain, comErr);
        }

        return hr;
    }

    HRESULT DecryptEdge(BSTR bstrEnc, BSTR* bstrPlain, DWORD* comErr, BrowserType type) {
        CLSID clsid = GetCLSID(type);
        HRESULT hr = E_FAIL;

        // Try v2 interface first
        Microsoft::WRL::ComPtr<IEdgeElevator2> elevator2;
        hr = CoCreateInstance(clsid, nullptr, CLSCTX_LOCAL_SERVER, IID::EdgeElevator2, &elevator2);
        
        if (SUCCEEDED(hr)) {
            CoSetProxyBlanket(
                elevator2.Get(),
                RPC_C_AUTHN_DEFAULT,
                RPC_C_AUTHZ_DEFAULT,
                COLE_DEFAULT_PRINCIPAL,
                RPC_C_AUTHN_LEVEL_PKT_PRIVACY,
                RPC_C_IMP_LEVEL_IMPERSONATE,
                nullptr,
                EOAC_DYNAMIC_CLOAKING
            );
            return elevator2->DecryptData(bstrEnc, bstrPlain, comErr);
        }

        // Fallback to v1
        Microsoft::WRL::ComPtr<IEdgeElevator> elevator;
        hr = CoCreateInstance(clsid, nullptr, CLSCTX_LOCAL_SERVER, IID::EdgeElevator, &elevator);
        
        if (SUCCEEDED(hr)) {
            CoSetProxyBlanket(
                elevator.Get(),
                RPC_C_AUTHN_DEFAULT,
                RPC_C_AUTHZ_DEFAULT,
                COLE_DEFAULT_PRINCIPAL,
                RPC_C_AUTHN_LEVEL_PKT_PRIVACY,
                RPC_C_IMP_LEVEL_IMPERSONATE,
                nullptr,
                EOAC_DYNAMIC_CLOAKING
            );
            hr = elevator->DecryptData(bstrEnc, bstrPlain, comErr);
        }

        return hr;
    }

    HRESULT DecryptAvast(BSTR bstrEnc, BSTR* bstrPlain, DWORD* comErr) {
        Microsoft::WRL::ComPtr<IAvastElevator> elevator;
        HRESULT hr = CoCreateInstance(CLSID::Avast, nullptr, CLSCTX_LOCAL_SERVER,
                                      IID::AvastElevator, &elevator);
        
        if (SUCCEEDED(hr)) {
            CoSetProxyBlanket(
                elevator.Get(),
                RPC_C_AUTHN_DEFAULT,
                RPC_C_AUTHZ_DEFAULT,
                COLE_DEFAULT_PRINCIPAL,
                RPC_C_AUTHN_LEVEL_PKT_PRIVACY,
                RPC_C_IMP_LEVEL_IMPERSONATE,
                nullptr,
                EOAC_DYNAMIC_CLOAKING
            );
            hr = elevator->DecryptData(bstrEnc, bstrPlain, comErr);
        }

        return hr;
    }
};

} // namespace Com
} // namespace AbeNative

#endif // _WIN32
