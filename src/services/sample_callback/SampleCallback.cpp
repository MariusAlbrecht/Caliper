// Snapshot-time user callback dispatch service. Connects to the channel's
// snapshot event and invokes a user-registered function pointer that may
// append Caliper Attributes to the snapshot.
//
// By default the callback fires for every snapshot on the channel. The
// CALI_SAMPLE_CALLBACK_FILTER_ATTRIBUTE option restricts dispatch to
// snapshots whose trigger view contains the named attribute (e.g.
// "libpfm.event_sample_name" to fire only on libpfm samples).

#include "../Services.h"

#include "caliper/Caliper.h"
#include "caliper/SnapshotRecord.h"
#include "caliper/sample_callback.h"

#include "caliper/common/Attribute.h"
#include "caliper/common/Log.h"

#include <atomic>

using namespace cali;

namespace
{

// Single global callback slot. Read from signal context via a relaxed atomic
// load; written from application code via register_callback().
std::atomic<sample_callback::callback_fn> g_user_fn { nullptr };
std::atomic<void*>                        g_user_args { nullptr };

class SampleCallbackService
{
    std::string m_filter_attr_name;       // empty => no filter
    Attribute   m_filter_attr;            // resolved post-init
    bool        m_filter_pending = false; // filter requested but attr not yet present

    void snapshot_cb(Caliper* c, SnapshotView trigger_info, SnapshotBuilder& rec)
    {
        auto fn = g_user_fn.load(std::memory_order_relaxed);
        if (!fn)
            return;
        // Hot path. When no filter is configured (the default), m_filter_attr
        // is empty and the second branch short-circuits. With a configured
        // filter, get() does a small linear scan of trigger_info.
        if (m_filter_attr && trigger_info.get(m_filter_attr).empty())
            return;

        fn(*c, trigger_info, rec, g_user_args.load(std::memory_order_relaxed));
    }

    void post_init_cb(Caliper* c, Channel* channel)
    {
        if (m_filter_attr_name.empty())
            return;
        m_filter_attr = c->get_attribute(m_filter_attr_name);
        if (!m_filter_attr) {
            m_filter_pending = true;
            Log(1).stream() << channel->name()
                            << ": sample_callback: filter attribute \""
                            << m_filter_attr_name
                            << "\" not yet present at post_init; will resolve on first matching snapshot."
                            << std::endl;
        }
    }

    // Late binding: if the filter attribute wasn't created at post_init time
    // (the typical case for libpfm.* attributes, which the libpfm service
    // creates lazily on its first sample), resolve it on the create_attr
    // event so subsequent snapshots get filtered correctly.
    void create_attr_cb(Caliper* /*c*/, const Attribute& attr)
    {
        if (m_filter_pending && attr.name() == m_filter_attr_name) {
            m_filter_attr = attr;
            m_filter_pending = false;
        }
    }

public:

    static const char* s_spec;

    static void register_sample_callback_service(Caliper* /*c*/, Channel* channel)
    {
        ConfigSet cfg = services::init_config_from_spec(channel->config(), s_spec);

        SampleCallbackService* instance = new SampleCallbackService;
        instance->m_filter_attr_name = cfg.get("filter_attribute").to_string();

        channel->events().post_init_evt.connect([instance](Caliper* c, Channel* chn) {
            instance->post_init_cb(c, chn);
        });
        if (!instance->m_filter_attr_name.empty()) {
            channel->events().create_attr_evt.connect(
                [instance](Caliper* c, const Attribute& attr) {
                    instance->create_attr_cb(c, attr);
                }
            );
        }
        channel->events().snapshot.connect(
            [instance](Caliper* c, SnapshotView trigger_info, SnapshotBuilder& rec) {
                instance->snapshot_cb(c, trigger_info, rec);
            }
        );
        channel->events().finish_evt.connect([instance](Caliper* /*c*/, Channel* /*chn*/) {
            delete instance;
        });

        Log(1).stream() << channel->name() << ": Registered sample_callback service" << std::endl;
    }
};

const char* SampleCallbackService::s_spec = R"json(
{   "name"        : "sample_callback",
    "description" : "Dispatch a user-registered function-pointer callback at snapshot time. The callback may append Caliper Attributes to the snapshot. When paired with a sampling service such as libpfm, the callback runs in signal context and must be async-signal-safe.",
    "config"      :
    [
     {
      "name": "filter_attribute",
      "description": "If non-empty, only invoke the user callback for snapshots whose trigger view contains an entry with this attribute name (e.g. libpfm.event_sample_name). Empty (default) disables filtering.",
      "type": "string",
      "value": ""
     }
    ]
}
)json";

} // namespace

namespace cali
{

namespace sample_callback
{

void register_callback(callback_fn fn, void* args)
{
    g_user_args.store(args, std::memory_order_relaxed);
    g_user_fn.store(fn, std::memory_order_relaxed);
}

} // namespace sample_callback

CaliperService sample_callback_service = { ::SampleCallbackService::s_spec,
                                           ::SampleCallbackService::register_sample_callback_service };

} // namespace cali
