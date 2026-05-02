/// \file sample_callback.h
/// \brief Public interface to register a snapshot-time user callback for the
///        Caliper \c sample_callback service.
///
/// The registered callback is invoked synchronously from the channel's
/// snapshot event and may append Caliper Attributes to the current snapshot.
///
/// By default, the service fires for every snapshot on its channel,
/// regardless of which other service triggered the snapshot. Set the
/// \c CALI_SAMPLE_CALLBACK_FILTER_ATTRIBUTE config variable to limit
/// invocations to snapshots whose trigger view contains a given attribute
/// (e.g. \c libpfm.event_sample_name to mirror libpfm-only behavior).
///
/// When paired with a sampling service such as \c libpfm, the callback runs
/// in signal context on the thread that received the sample. In that
/// configuration the callback MUST be async-signal-safe. Pre-create any
/// Caliper Attributes (via \c Caliper::create_attribute()) before sampling
/// starts; do NOT create attributes inside the callback.

#pragma once

namespace cali
{

class Caliper;
class SnapshotView;
class SnapshotBuilder;

namespace sample_callback
{

/// \brief Snapshot-time callback signature.
///
/// Receives:
///
/// - \a c       a Caliper instance (signal-safe when invoked from the
///              libpfm SIGIO sample handler).
/// - \a trigger the trigger info SnapshotView assembled by the service that
///              raised the snapshot. For libpfm samples, contains
///              \c libpfm.ip, \c libpfm.addr, \c libpfm.time, etc.
/// - \a rec     a writable SnapshotBuilder. Use \c rec.append(attr, val) to
///              attach extra Caliper Attributes to this snapshot.
/// - \a args    the opaque user pointer passed at registration time.
using callback_fn = void (*)(Caliper& c, SnapshotView trigger, SnapshotBuilder& rec, void* args);

/// \brief Register the snapshot-time callback.
///
/// Pass \c nullptr to clear. Call before any sampling channel is started
/// (e.g. before the first \c ConfigManager::start()). Only one callback
/// is registered at a time; later calls overwrite earlier ones.
void register_callback(callback_fn fn, void* args);

} // namespace sample_callback

} // namespace cali
