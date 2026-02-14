cmake_minimum_required(VERSION 3.15)
project(abe_native VERSION 1.0.0 LANGUAGES CXX)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find Python and pybind11
find_package(Python3 REQUIRED COMPONENTS Interpreter Development)
find_package(pybind11 CONFIG REQUIRED)

# Source files
set(SOURCES
    src/abe_module.cpp
)

# Header files (for IDE support)
set(HEADERS
    src/abe_common.hpp
    src/aes_gcm.hpp
    src/elevator.hpp
)

# Create the Python module
pybind11_add_module(abe_native ${SOURCES} ${HEADERS})

# Set include directories
target_include_directories(abe_native PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# Windows-specific settings
if(WIN32)
    # Link Windows libraries
    target_link_libraries(abe_native PRIVATE
        bcrypt
        ole32
        oleaut32
    )
    
    # Set Windows-specific compile definitions
    target_compile_definitions(abe_native PRIVATE
        UNICODE
        _UNICODE
        WIN32_LEAN_AND_MEAN
        NOMINMAX
    )
    
    # Enable MSVC parallel build
    if(MSVC)
        target_compile_options(abe_native PRIVATE /MP /W4)
    endif()
endif()

# Install target
install(TARGETS abe_native
    LIBRARY DESTINATION .
    RUNTIME DESTINATION .
)
