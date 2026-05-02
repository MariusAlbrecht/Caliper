// Demonstrates the sample_callback service paired with libpfm. The user
// callback runs in signal context from the libpfm SIGIO sample handler and
// attaches a CLOCK_MONOTONIC timestamp to each libpfm sample snapshot.
//
// CALI_SAMPLE_CALLBACK_FILTER_ATTRIBUTE is set so that the callback only
// fires for libpfm samples; without it, the callback would also fire on
// region begin/end snapshots emitted by the event service.
//
// Run with:
//
//   CALI_SERVICES_ENABLE=event,trace,recorder,libpfm,sample_callback \
//   CALI_SAMPLE_CALLBACK_FILTER_ATTRIBUTE=libpfm.event_sample_name \
//   CALI_LIBPFM_EVENTS=MEM_TRANS_RETIRED:LATENCY_ABOVE_THRESHOLD \
//   CALI_LIBPFM_SAMPLE_PERIOD=1000 \
//   CALI_LIBPFM_PRECISE_IP=2 \
//   CALI_LIBPFM_SAMPLE_ATTRIBUTES=ip,id,time,tid,period,cpu,addr,weight,data_src \
//   CALI_RECORDER_FILENAME=sample_cb_example.cali \
//       ./sample_callback_example
//
// Then inspect the trace:
//
//   cali-query -t sample_cb_example.cali | head

#include <caliper/cali.h>
#include <caliper/Caliper.h>
#include <caliper/SnapshotRecord.h>
#include <caliper/sample_callback.h>

#include <caliper/common/Attribute.h>
#include <caliper/common/Variant.h>

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <iostream>
#include <vector>

namespace
{

// Pre-created at startup; used inside the signal-context callback.
cali::Attribute g_ts_attr;

// Async-signal-safe: clock_gettime is on POSIX's signal-safe list, and
// SnapshotBuilder::append is just an array write.
void sample_cb(cali::Caliper&        /*c*/,
               cali::SnapshotView    /*trigger*/,
               cali::SnapshotBuilder& rec,
               void*                  /*args*/)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t ns = static_cast<uint64_t>(ts.tv_sec) * 1000000000ULL
                + static_cast<uint64_t>(ts.tv_nsec);
    rec.append(g_ts_attr, cali::Variant(cali_make_variant_from_uint(ns)));
}

// Memory-bound workload to generate libpfm samples.
void workload()
{
    CALI_CXX_MARK_FUNCTION;

    constexpr std::size_t N = 1u << 22; // 4 Mi entries
    std::vector<std::uint64_t> a(N), b(N);
    for (std::size_t i = 0; i < N; ++i) {
        a[i] = i;
        b[i] = N - i;
    }

    std::uint64_t acc = 0;
    for (int rep = 0; rep < 8; ++rep)
        for (std::size_t i = 0; i < N; ++i)
            acc += a[i] * b[(i * 1664525u + 1013904223u) % N];

    if (acc == 42)
        std::cout << "(unreachable)\n";
}

} // namespace

int main()
{
    g_ts_attr = cali::Caliper::instance().create_attribute(
        "user.sample_timestamp_ns",
        CALI_TYPE_UINT,
        CALI_ATTR_ASVALUE | CALI_ATTR_SKIP_EVENTS
    );

    cali::sample_callback::register_callback(&sample_cb, nullptr);

    workload();

    return 0;
}
