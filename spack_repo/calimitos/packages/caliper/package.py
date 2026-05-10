# Copyright Spack Project Developers. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import re
import socket
import sys

from spack_repo.builtin.build_systems.cached_cmake import (
    CachedCMakePackage,
    cmake_cache_option,
    cmake_cache_path,
    cmake_cache_string,
)
from spack_repo.builtin.build_systems.cuda import CudaPackage
from spack_repo.builtin.build_systems.rocm import ROCmPackage

from spack.package import *


class Caliper(CachedCMakePackage, CudaPackage, ROCmPackage):
    """Caliper fork (MariusAlbrecht/Caliper) with the sample_callback service.

    sample_callback dispatches a user-registered function pointer at
    snapshot time, allowing applications to append Caliper attributes
    to snapshots from signal context. It is built whenever the libpfm
    service is enabled, so this package defaults to +libpfm.
    """

    homepage = "https://github.com/MariusAlbrecht/Caliper"
    git = "https://github.com/MariusAlbrecht/Caliper.git"

    maintainers("MariusAlbrecht")

    license("BSD-3-Clause")

    # Fork branch built on top of LLNL/Caliper releases/v2.14.0.
    # The sample_callback work is pushed directly onto releases/v2.14.0
    # on the fork, not a separate feature branch.
    version(
        "2.14.0-sample-callback",
        branch="releases/v2.14.0",
        preferred=True,
    )

    is_linux = sys.platform.startswith("linux")
    variant("shared", default=True, description="Build shared libraries")
    variant("adiak", default=True, description="Enable Adiak support")
    variant("mpi", default=True, description="Enable MPI support")
    variant(
        "libunwind", default=sys.platform != "darwin", description="Enable stack unwind support"
    )
    variant("libdw", default=is_linux, description="Enable DWARF symbol lookup")
    variant("papi", default=sys.platform != "darwin", description="Enable PAPI service")
    # Default +libpfm so the sample_callback service is built out of the box.
    variant("libpfm", default=is_linux, description="Enable libpfm (perf_events) service")
    variant("gotcha", default=is_linux, description="Enable GOTCHA support")
    variant("sampler", default=is_linux, description="Enable sampling support on Linux")
    variant("fortran", default=False, description="Enable Fortran support")
    variant("variorum", default=False, description="Enable Variorum support")
    variant("vtune", default=False, description="Enable Intel Vtune support")
    variant("kokkos", default=True, description="Enable Kokkos profiling support")
    variant("tests", default=False, description="Enable tests")
    variant("tools", default=True, description="Enable tools")
    variant("python", default=False, description="Build Python bindings")

    depends_on("c", type="build")
    depends_on("cxx", type="build")
    depends_on("fortran", when="+fortran", type="build")

    depends_on("rocprofiler-sdk", when="+rocm")
    depends_on("llvm-amdgpu@6.2.4:", when="+rocm")

    depends_on("adiak@0.4:0", when="+adiak")
    depends_on("papi@5.3:", when="+papi")
    depends_on("libpfm4@4.8:4", when="+libpfm")
    depends_on("mpi", when="+mpi")
    depends_on("unwind@1.2:1", when="+libunwind")
    depends_on("elfutils", when="+libdw")
    depends_on("variorum", when="+variorum")
    depends_on("intel-oneapi-vtune", when="+vtune")

    depends_on("cmake", type="build")
    depends_on("python", type="build")

    depends_on("python@3", when="+python", type=("build", "link", "run"))
    depends_on("py-pybind11", when="+python", type=("build", "link", "run"))

    conflicts("+rocm+cuda")

    def _get_sys_type(self, spec):
        sys_type = spec.architecture
        if "SYS_TYPE" in os.environ:
            sys_type = os.environ["SYS_TYPE"]
        return sys_type

    @property
    def cache_name(self):
        hostname = socket.gethostname()
        if "SYS_TYPE" in os.environ:
            hostname = hostname.rstrip("1234567890")
        return "{0}-{1}-{2}@{3}-{4}.cmake".format(
            hostname,
            self._get_sys_type(self.spec),
            self.spec.compiler.name,
            self.spec.compiler.version,
            self.spec.dag_hash(8),
        )

    def initconfig_compiler_entries(self):
        spec = self.spec
        entries = super().initconfig_compiler_entries()

        if spec.satisfies("+rocm"):
            entries.insert(0, cmake_cache_path("CMAKE_CXX_COMPILER", spec["hip"].hipcc))

        entries.append(cmake_cache_option("WITH_FORTRAN", spec.satisfies("+fortran")))

        entries.append(cmake_cache_option("BUILD_SHARED_LIBS", spec.satisfies("+shared")))
        entries.append(cmake_cache_option("BUILD_TESTING", spec.satisfies("+tests")))
        entries.append(cmake_cache_option("WITH_TOOLS", spec.satisfies("+tools")))
        entries.append(cmake_cache_option("BUILD_DOCS", False))
        entries.append(cmake_cache_path("PYTHON_EXECUTABLE", spec["python"].command.path))

        return entries

    def initconfig_hardware_entries(self):
        spec = self.spec
        entries = super().initconfig_hardware_entries()

        if spec.satisfies("+cuda"):
            entries.append(cmake_cache_option("WITH_CUPTI", True))
            entries.append(cmake_cache_option("WITH_NVTX", True))
            entries.append(cmake_cache_path("CUDA_TOOLKIT_ROOT_DIR", spec["cuda"].prefix))
            entries.append(cmake_cache_path("CUPTI_PREFIX", spec["cuda"].prefix))

            cuda_flags = []
            if not spec.satisfies("cuda_arch=none"):
                cuda_archs = ";".join(spec.variants["cuda_arch"].value)
                entries.append(cmake_cache_string("CMAKE_CUDA_ARCHITECTURES", cuda_archs))

            gcc_toolchain_regex = re.compile(".*gcc-toolchain.*")
            using_toolchain = list(
                filter(gcc_toolchain_regex.match, spec.compiler_flags["cxxflags"])
            )
            if using_toolchain:
                cuda_flags.append("-Xcompiler {}".format(using_toolchain[0]))

            if cuda_flags:
                entries.append(cmake_cache_string("CMAKE_CUDA_FLAGS", " ".join(cuda_flags)))
        else:
            entries.append(cmake_cache_option("WITH_CUPTI", False))
            entries.append(cmake_cache_option("WITH_NVTX", False))

        if spec.satisfies("+rocm"):
            rocm_root = spec["llvm-amdgpu"].prefix
            gcc_toolchain_regex = re.compile(".*gcc-toolchain.*")
            using_toolchain = list(
                filter(gcc_toolchain_regex.match, spec.compiler_flags["cxxflags"])
            )
            hip_link_flags = ""

            if using_toolchain:
                gcc_prefix = using_toolchain[0]
                entries.append(
                    cmake_cache_string("HIP_CLANG_FLAGS", "--gcc-toolchain={0}".format(gcc_prefix))
                )
                entries.append(
                    cmake_cache_string(
                        "CMAKE_EXE_LINKER_FLAGS",
                        hip_link_flags + " -Wl,-rpath={0}/lib64".format(gcc_prefix),
                    )
                )
            else:
                entries.append(
                    cmake_cache_string(
                        "CMAKE_EXE_LINKER_FLAGS", "-Wl,-rpath={0}/llvm/lib/".format(rocm_root)
                    )
                )

            entries.append(cmake_cache_option("WITH_ROCPROFILER", True))
            entries.append(cmake_cache_option("WITH_ROCTRACER", False))
            entries.append(cmake_cache_option("WITH_ROCTX", False))
        else:
            entries.append(cmake_cache_option("WITH_ROCPROFILER", False))
            entries.append(cmake_cache_option("WITH_ROCTRACER", False))
            entries.append(cmake_cache_option("WITH_ROCTX", False))

        return entries

    def initconfig_mpi_entries(self):
        spec = self.spec
        entries = super().initconfig_mpi_entries()

        entries.append(cmake_cache_option("WITH_MPI", spec.satisfies("+mpi")))

        return entries

    def initconfig_package_entries(self):
        spec = self.spec
        entries = []

        entries.append("#------------------{0}".format("-" * 60))
        entries.append("# TPLs")
        entries.append("#------------------{0}\n".format("-" * 60))

        if spec.satisfies("+adiak"):
            entries.append(cmake_cache_path("adiak_DIR", spec["adiak"].prefix))
        if spec.satisfies("+papi"):
            entries.append(cmake_cache_path("PAPI_PREFIX", spec["papi"].prefix))
        if spec.satisfies("+libdw"):
            entries.append(cmake_cache_path("LIBDW_PREFIX", spec["elfutils"].prefix))
        if spec.satisfies("+libpfm"):
            entries.append(cmake_cache_path("LIBPFM_INSTALL", spec["libpfm4"].prefix))
        if spec.satisfies("+variorum"):
            entries.append(cmake_cache_path("VARIORUM_PREFIX", spec["variorum"].prefix))
        if spec.satisfies("+vtune"):
            itt_dir = join_path(spec["intel-oneapi-vtune"].prefix, "vtune", "latest")
            entries.append(cmake_cache_path("ITT_PREFIX", itt_dir))
        if spec.satisfies("+libunwind"):
            entries.append(cmake_cache_path("LIBUNWIND_PREFIX", spec["unwind"].prefix))

        entries.append("#------------------{0}".format("-" * 60))
        entries.append("# Build Options")
        entries.append("#------------------{0}\n".format("-" * 60))

        entries.append(cmake_cache_option("WITH_ADIAK", spec.satisfies("+adiak")))
        entries.append(cmake_cache_option("WITH_GOTCHA", spec.satisfies("+gotcha")))
        entries.append(cmake_cache_option("WITH_SAMPLER", spec.satisfies("+sampler")))
        entries.append(cmake_cache_option("WITH_PAPI", spec.satisfies("+papi")))
        entries.append(cmake_cache_option("WITH_LIBDW", spec.satisfies("+libdw")))
        entries.append(cmake_cache_option("WITH_LIBPFM", spec.satisfies("+libpfm")))
        entries.append(cmake_cache_option("WITH_KOKKOS", spec.satisfies("+kokkos")))
        entries.append(cmake_cache_option("WITH_VARIORUM", spec.satisfies("+variorum")))
        entries.append(cmake_cache_option("WITH_VTUNE", spec.satisfies("+vtune")))
        entries.append(cmake_cache_option("WITH_PYTHON_BINDINGS", spec.satisfies("+python")))
        entries.append(cmake_cache_option("WITH_LIBUNWIND", spec.satisfies("+libunwind")))

        return entries

    def cmake_args(self):
        return []

    def setup_run_environment(self, env: EnvironmentModifications) -> None:
        if self.spec.satisfies("+python"):
            py_pkg = self.spec["python"].package
            env.prepend_path("PYTHONPATH", self.spec.prefix.join(py_pkg.platlib))
            env.prepend_path("PYTHONPATH", self.spec.prefix.join(py_pkg.purelib))
