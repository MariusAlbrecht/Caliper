set(CALIPER_SAMPLE_CALLBACK_SOURCES
    SampleCallback.cpp)

add_service_sources(${CALIPER_SAMPLE_CALLBACK_SOURCES})

add_caliper_service("sample_callback CALIPER_HAVE_LIBPFM")