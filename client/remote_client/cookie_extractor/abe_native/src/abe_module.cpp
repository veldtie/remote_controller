// App-Bound Encryption Native Module - pybind11 bindings
// (c) Based on Alexander 'xaitax' Hagenah's Chrome ABE research
// Licensed under the MIT License

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

#ifdef _WIN32
#include "abe_common.hpp"
#include "aes_gcm.hpp"
#include "elevator.hpp"

using namespace AbeNative;
#endif

// Module version
const char* MODULE_VERSION = "1.0.0";

// Platform check
bool is_windows() {
#ifdef _WIN32
    return true;
#else
    return false;
#endif
}

#ifdef _WIN32

// Wrapper for AES-GCM decryption
py::object decrypt_aes_gcm(const py::bytes& key, const py::bytes& encrypted_data) {
    std::string key_str = key;
    std::string data_str = encrypted_data;
    
    std::vector<uint8_t> key_vec(key_str.begin(), key_str.end());
    std::vector<uint8_t> data_vec(data_str.begin(), data_str.end());
    
    auto result = Crypto::AesGcm::Decrypt(key_vec, data_vec);
    
    if (result) {
        return py::bytes(reinterpret_cast<const char*>(result->data()), result->size());
    }
    return py::none();
}

// Wrapper for raw AES-GCM decryption
py::object decrypt_aes_gcm_raw(const py::bytes& key, const py::bytes& iv, 
                               const py::bytes& ciphertext, const py::bytes& tag) {
    std::string key_str = key;
    std::string iv_str = iv;
    std::string ct_str = ciphertext;
    std::string tag_str = tag;
    
    std::vector<uint8_t> key_vec(key_str.begin(), key_str.end());
    std::vector<uint8_t> iv_vec(iv_str.begin(), iv_str.end());
    std::vector<uint8_t> ct_vec(ct_str.begin(), ct_str.end());
    std::vector<uint8_t> tag_vec(tag_str.begin(), tag_str.end());
    
    auto result = Crypto::AesGcm::DecryptRaw(key_vec, iv_vec, ct_vec, tag_vec);
    
    if (result) {
        return py::bytes(reinterpret_cast<const char*>(result->data()), result->size());
    }
    return py::none();
}

// Check if data is ABE encrypted key
bool check_abe_encrypted_key(const py::bytes& data) {
    std::string data_str = data;
    std::vector<uint8_t> data_vec(data_str.begin(), data_str.end());
    return is_abe_encrypted_key(data_vec);
}

// Check if data is ABE encrypted value (v20)
bool check_abe_encrypted_value(const py::bytes& data) {
    std::string data_str = data;
    std::vector<uint8_t> data_vec(data_str.begin(), data_str.end());
    return is_abe_encrypted_value(data_vec);
}

// Wrapper class for Elevator
class PyElevator {
public:
    PyElevator() : elevator_() {}
    
    py::dict decrypt_key(const py::bytes& encrypted_key, const std::string& browser_type) {
        std::string key_str = encrypted_key;
        std::vector<uint8_t> key_vec(key_str.begin(), key_str.end());
        
        BrowserType bt = parse_browser_type(browser_type);
        auto result = elevator_.DecryptKey(key_vec, bt);
        
        py::dict ret;
        ret["success"] = result.success;
        if (result.success) {
            ret["data"] = py::bytes(reinterpret_cast<const char*>(result.data.data()), 
                                    result.data.size());
        } else {
            ret["data"] = py::none();
        }
        ret["error"] = result.error_message;
        return ret;
    }
    
    py::dict decrypt_key_auto(const py::bytes& encrypted_key) {
        std::string key_str = encrypted_key;
        std::vector<uint8_t> key_vec(key_str.begin(), key_str.end());
        
        auto result = elevator_.DecryptKeyAuto(key_vec);
        
        py::dict ret;
        ret["success"] = result.success;
        if (result.success) {
            ret["data"] = py::bytes(reinterpret_cast<const char*>(result.data.data()), 
                                    result.data.size());
        } else {
            ret["data"] = py::none();
        }
        ret["error"] = result.error_message;
        return ret;
    }
    
private:
    Com::Elevator elevator_;
    
    BrowserType parse_browser_type(const std::string& type) {
        if (type == "chrome") return BrowserType::Chrome;
        if (type == "chrome_beta") return BrowserType::ChromeBeta;
        if (type == "chrome_dev") return BrowserType::ChromeDev;
        if (type == "chrome_canary") return BrowserType::ChromeCanary;
        if (type == "edge") return BrowserType::Edge;
        if (type == "edge_beta") return BrowserType::EdgeBeta;
        if (type == "edge_dev") return BrowserType::EdgeDev;
        if (type == "edge_canary") return BrowserType::EdgeCanary;
        if (type == "brave") return BrowserType::Brave;
        if (type == "brave_beta") return BrowserType::BraveBeta;
        if (type == "brave_nightly") return BrowserType::BraveNightly;
        if (type == "avast") return BrowserType::Avast;
        if (type == "opera") return BrowserType::Opera;
        if (type == "vivaldi") return BrowserType::Vivaldi;
        return BrowserType::Unknown;
    }
};

#endif // _WIN32

// Python module definition
PYBIND11_MODULE(abe_native, m) {
    m.doc() = R"pbdoc(
        App-Bound Encryption Native Module
        ----------------------------------
        
        Native C++ implementation for Chrome 127+ App-Bound Encryption decryption.
        Uses Windows COM interfaces (IElevator) and BCrypt for AES-GCM decryption.
        
        Based on Alexander 'xaitax' Hagenah's Chrome ABE research.
    )pbdoc";

    m.attr("__version__") = MODULE_VERSION;
    m.def("is_windows", &is_windows, "Check if running on Windows");
    
#ifdef _WIN32
    // AES-GCM functions
    m.def("decrypt_aes_gcm", &decrypt_aes_gcm, 
          py::arg("key"), py::arg("encrypted_data"),
          R"pbdoc(
              Decrypt v20 (ABE) encrypted data using AES-GCM.
              
              Args:
                  key: 32-byte AES key
                  encrypted_data: Data with v20 prefix + IV + ciphertext + tag
                  
              Returns:
                  Decrypted bytes or None on failure
          )pbdoc");
    
    m.def("decrypt_aes_gcm_raw", &decrypt_aes_gcm_raw,
          py::arg("key"), py::arg("iv"), py::arg("ciphertext"), py::arg("tag"),
          R"pbdoc(
              Decrypt raw AES-GCM data.
              
              Args:
                  key: 32-byte AES key
                  iv: 12-byte initialization vector
                  ciphertext: Encrypted data
                  tag: 16-byte authentication tag
                  
              Returns:
                  Decrypted bytes or None on failure
          )pbdoc");
    
    // Helper functions
    m.def("is_abe_encrypted_key", &check_abe_encrypted_key,
          py::arg("data"),
          "Check if data has APPB prefix (App-Bound Encryption key)");
    
    m.def("is_abe_encrypted_value", &check_abe_encrypted_value,
          py::arg("data"),
          "Check if data has v20 prefix (ABE encrypted value)");
    
    // Elevator class for IElevator COM decryption
    py::class_<PyElevator>(m, "Elevator", 
        R"pbdoc(
            IElevator COM interface wrapper for ABE key decryption.
            
            Supports Chrome, Edge, Brave, and Avast elevation services.
        )pbdoc")
        .def(py::init<>())
        .def("decrypt_key", &PyElevator::decrypt_key,
             py::arg("encrypted_key"), py::arg("browser_type"),
             R"pbdoc(
                 Decrypt ABE key using specified browser's elevation service.
                 
                 Args:
                     encrypted_key: APPB-prefixed encrypted key from Local State
                     browser_type: Browser type string (chrome, edge, brave, avast, etc.)
                     
                 Returns:
                     Dict with 'success', 'data' (bytes), and 'error' (string)
             )pbdoc")
        .def("decrypt_key_auto", &PyElevator::decrypt_key_auto,
             py::arg("encrypted_key"),
             R"pbdoc(
                 Automatically try all available elevation services to decrypt key.
                 
                 Args:
                     encrypted_key: APPB-prefixed encrypted key from Local State
                     
                 Returns:
                     Dict with 'success', 'data' (bytes), and 'error' (string)
             )pbdoc");
    
    // Browser type constants
    py::module_ browsers = m.def_submodule("browsers", "Browser type constants");
    browsers.attr("CHROME") = "chrome";
    browsers.attr("CHROME_BETA") = "chrome_beta";
    browsers.attr("CHROME_DEV") = "chrome_dev";
    browsers.attr("CHROME_CANARY") = "chrome_canary";
    browsers.attr("EDGE") = "edge";
    browsers.attr("EDGE_BETA") = "edge_beta";
    browsers.attr("EDGE_DEV") = "edge_dev";
    browsers.attr("EDGE_CANARY") = "edge_canary";
    browsers.attr("BRAVE") = "brave";
    browsers.attr("BRAVE_BETA") = "brave_beta";
    browsers.attr("BRAVE_NIGHTLY") = "brave_nightly";
    browsers.attr("AVAST") = "avast";
    browsers.attr("OPERA") = "opera";
    browsers.attr("VIVALDI") = "vivaldi";

#else
    // Stub implementations for non-Windows
    m.def("decrypt_aes_gcm", [](const py::bytes&, const py::bytes&) -> py::object {
        throw std::runtime_error("ABE native module requires Windows");
    }, py::arg("key"), py::arg("encrypted_data"));
    
    m.def("decrypt_aes_gcm_raw", [](const py::bytes&, const py::bytes&, 
                                    const py::bytes&, const py::bytes&) -> py::object {
        throw std::runtime_error("ABE native module requires Windows");
    }, py::arg("key"), py::arg("iv"), py::arg("ciphertext"), py::arg("tag"));
    
    m.def("is_abe_encrypted_key", [](const py::bytes&) -> bool {
        throw std::runtime_error("ABE native module requires Windows");
    }, py::arg("data"));
    
    m.def("is_abe_encrypted_value", [](const py::bytes&) -> bool {
        throw std::runtime_error("ABE native module requires Windows");
    }, py::arg("data"));
    
    // Stub Elevator class
    py::class_<py::object>(m, "Elevator")
        .def(py::init([]() -> py::object {
            throw std::runtime_error("ABE native module requires Windows");
        }));
#endif
}
