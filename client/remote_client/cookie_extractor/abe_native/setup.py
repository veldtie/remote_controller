"""
Setup script for ABE Native Module.

This module provides native C++ implementations for Chrome 127+ 
App-Bound Encryption (ABE) decryption using pybind11.

Build requirements:
- Windows: Visual Studio 2019+ with C++ workload
- pybind11 >= 2.11.0
- CMake >= 3.15

Install:
    pip install .
    
Build wheel:
    pip wheel . --no-deps
"""

import os
import sys
import subprocess
from pathlib import Path

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext


class CMakeExtension(Extension):
    """CMake extension wrapper."""
    
    def __init__(self, name: str, sourcedir: str = ""):
        super().__init__(name, sources=[])
        self.sourcedir = os.fspath(Path(sourcedir).resolve())


class CMakeBuild(build_ext):
    """CMake build command."""
    
    def build_extension(self, ext: CMakeExtension) -> None:
        # Ensure build directory exists
        ext_fullpath = Path.cwd() / self.get_ext_fullpath(ext.name)
        extdir = ext_fullpath.parent.resolve()
        
        # CMake configuration arguments
        cmake_args = [
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}{os.sep}",
            f"-DPYTHON_EXECUTABLE={sys.executable}",
            f"-DCMAKE_BUILD_TYPE={'Debug' if self.debug else 'Release'}",
        ]
        
        # Build arguments
        build_args = ["--config", "Debug" if self.debug else "Release"]
        
        # Platform-specific settings
        if sys.platform == "win32":
            # Use Visual Studio generator
            cmake_args += [
                "-A", "x64" if sys.maxsize > 2**32 else "Win32",
            ]
            build_args += ["--", "/m"]
        else:
            # Use default generator (Makefiles/Ninja)
            build_args += ["--", "-j2"]
        
        # Set environment
        env = os.environ.copy()
        env["CXXFLAGS"] = f'{env.get("CXXFLAGS", "")} -DVERSION_INFO=\\"{self.distribution.get_version()}\\"'
        
        # Create build directory
        build_temp = Path(self.build_temp) / ext.name
        build_temp.mkdir(parents=True, exist_ok=True)
        
        # Run CMake configure
        subprocess.run(
            ["cmake", ext.sourcedir, *cmake_args],
            cwd=build_temp,
            check=True,
            env=env,
        )
        
        # Run CMake build
        subprocess.run(
            ["cmake", "--build", ".", *build_args],
            cwd=build_temp,
            check=True,
        )


# Only build on Windows
if sys.platform == "win32":
    ext_modules = [CMakeExtension("abe_native")]
    cmdclass = {"build_ext": CMakeBuild}
else:
    ext_modules = []
    cmdclass = {}

setup(
    name="abe-native",
    version="1.0.0",
    author="Based on xaitax's research",
    description="Native ABE decryption module for Chrome 127+",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    ext_modules=ext_modules,
    cmdclass=cmdclass,
    zip_safe=False,
    python_requires=">=3.8",
    install_requires=[
        "pybind11>=2.11.0",
    ],
    extras_require={
        "dev": [
            "cmake>=3.15",
            "wheel",
        ],
    },
)
