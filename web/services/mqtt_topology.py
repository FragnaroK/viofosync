"""Entity catalog + discovery payload builders for MQTT.

The TOPOLOGY list (populated in later tasks) is the single source of
truth for every entity viofosync publishes. Each entry knows:

* its HA component (sensor/binary_sensor/button),
* its discovery payload shape,
* how to extract its state from the running app (state_fn),
* which Hub event types should trigger a re-publish,
* whether it accepts commands (command_handler).

Builders in this module are pure functions over EntityDef + a config
dict, so they're trivial to test without a broker.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from . import mqtt_state as _st
from . import queue as _q
from . import scanner as _scanner

log = logging.getLogger("viofosync.mqtt")


@dataclass
class EntityDef:
    object_id: str
    component: str            # "sensor" | "binary_sensor" | "button"
    name: str
    icon: Optional[str]
    device_class: Optional[str]
    state_class: Optional[str]
    unit_of_measurement: Optional[str]
    enabled_by_default: bool
    min_publish_interval_s: float
    state_fn: Optional[Callable]     # signature pinned in Task 6
    command_handler: Optional[Callable[[bytes], Awaitable[None]]]
    affected_by_hub_events: tuple[str, ...] = field(default_factory=tuple)
    attrs_fn: Optional[Callable] = None
    # None → use the global MQTT_QOS setting. Override on disposable
    # high-rate entities (e.g. current_progress) to QoS=0 so PUBACK
    # latency from the broker can't stall the publisher.
    qos: Optional[int] = None
    # Merged into the discovery payload (e.g. switch payloads, event_types).
    discovery_extra: dict = field(default_factory=dict)
    # Re-published every 60 s by the service tick (poll-sourced entities).
    poll: bool = False

def build_state_topic(object_id: str, cfg: dict) -> str:
    return f"{cfg['node_id']}/{object_id}/state"


def build_command_topic(object_id: str, cfg: dict) -> str:
    return f"{cfg['node_id']}/{object_id}/cmd"


def build_attrs_topic(object_id: str, cfg: dict) -> str:
    return f"{cfg['node_id']}/{object_id}/attr"


def build_discovery_topic(component: str, object_id: str, cfg: dict) -> str:
    return (
        f"{cfg['discovery_prefix']}/{component}/"
        f"{cfg['node_id']}/{object_id}/config"
    )


def build_availability_topic(cfg: dict) -> str:
    return f"{cfg['node_id']}/availability"


def build_unique_id(object_id: str, cfg: dict) -> str:
    return f"viofosync_{cfg['node_id']}_{object_id}"


def _device_manifest(cfg: dict) -> dict:
    m = {
        "identifiers": [f"viofosync_{cfg['node_id']}"],
        "name": "Viofosync",
        "model": "viofosync",
        "manufacturer": "viofosync",
        "sw_version": cfg.get("version", "0.0.0"),
    }
    # HA rejects the whole discovery message if configuration_url
    # is present but not a valid URL — omit when empty.
    url = cfg.get("configuration_url", "")
    if url:
        m["configuration_url"] = url
    return m


def build_discovery_payload(entity: EntityDef, cfg: dict) -> dict:
    """Render the HA discovery `config` payload for one entity."""
    payload: dict = {
        "name": entity.name,
        "unique_id": build_unique_id(entity.object_id, cfg),
        "availability_topic": build_availability_topic(cfg),
        "payload_available": "online",
        "payload_not_available": "offline",
        "enabled_by_default": entity.enabled_by_default,
        "device": _device_manifest(cfg),
    }
    if entity.component in ("sensor", "binary_sensor", "switch", "event"):
        payload["state_topic"] = build_state_topic(entity.object_id, cfg)
    if entity.component in ("sensor", "binary_sensor") and entity.attrs_fn is not None:
        payload["json_attributes_topic"] = build_attrs_topic(entity.object_id, cfg)
    if entity.component in ("button", "switch"):
        payload["command_topic"] = build_command_topic(entity.object_id, cfg)
    if entity.icon:
        payload["icon"] = entity.icon
    if entity.device_class:
        payload["device_class"] = entity.device_class
    if entity.state_class:
        payload["state_class"] = entity.state_class
    if entity.unit_of_measurement:
        payload["unit_of_measurement"] = entity.unit_of_measurement
    payload.update(entity.discovery_extra)
    return payload


# Populated in Tasks 4–7.
TOPOLOGY: list[EntityDef] = [
    # --- Binary sensors ---
    EntityDef(
        object_id="dashcam",
        component="binary_sensor",
        name="Dashcam",
        icon="mdi:cctv",
        device_class="connectivity",
        state_class=None,
        unit_of_measurement=None,
        enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=_st.state_dashcam,
        command_handler=None,
        affected_by_hub_events=("dashcam_online", "dashcam_offline",
                                "dashcam_reachability_changed"),
    ),
    EntityDef(
        object_id="dashcam_connection",
        component="sensor",
        name="Dashcam connection",
        icon="mdi:transit-connection-variant",
        device_class=None,
        state_class=None,
        unit_of_measurement=None,
        enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=_st.state_dashcam_connection,
        command_handler=None,
        affected_by_hub_events=("dashcam_online", "dashcam_offline"),
        attrs_fn=_st.attrs_dashcam_connection,
    ),
    EntityDef(
        object_id="sync_status",
        component="sensor",
        name="Sync status",
        icon="mdi:sync",
        device_class=None,
        state_class=None,
        unit_of_measurement=None,
        enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=_st.state_sync_status,
        command_handler=None,
        affected_by_hub_events=(
            "sync_state", "item_started", "item_finished",
            "queue_changed",
            "dashcam_online", "dashcam_offline",
            "disk_pct", "sync_error",
            "triage_progress",
        ),
        attrs_fn=_st.attrs_sync_status,
    ),

    # --- Queue ---
    EntityDef(
        object_id="queue_pending",
        component="sensor",
        name="Queue pending",
        icon="mdi:download",
        device_class=None,
        state_class="measurement",
        unit_of_measurement=None,
        enabled_by_default=True,
        min_publish_interval_s=1.0,
        state_fn=_st.state_queue_pending,
        command_handler=None,
        affected_by_hub_events=("queue_changed", "item_started",
                                "item_finished", "dashcam_online",
                                "dashcam_offline"),
    ),
    EntityDef(
        object_id="queue_failed",
        component="sensor",
        name="Queue failed",
        icon="mdi:alert-circle",
        device_class=None,
        state_class="measurement",
        unit_of_measurement=None,
        enabled_by_default=False,
        min_publish_interval_s=1.0,
        state_fn=_st.state_queue_failed,
        command_handler=None,
        affected_by_hub_events=("queue_changed",),
    ),
    EntityDef(
        object_id="queue_downloading",
        component="sensor",
        name="Queue downloading",
        icon="mdi:download-circle",
        device_class=None,
        state_class="measurement",
        unit_of_measurement=None,
        enabled_by_default=False,
        min_publish_interval_s=1.0,
        state_fn=_st.state_queue_downloading,
        command_handler=None,
        affected_by_hub_events=("queue_changed", "item_started",
                                "item_finished"),
    ),

    # --- Archive ---
    EntityDef(
        object_id="last_downloaded_clip",
        component="sensor",
        name="Last downloaded clip",
        icon="mdi:clock",
        device_class="timestamp",
        state_class=None,
        unit_of_measurement=None,
        enabled_by_default=True,
        min_publish_interval_s=5.0,
        state_fn=_st.state_last_downloaded_clip,
        command_handler=None,
        affected_by_hub_events=("clip_indexed",),
    ),
    EntityDef(
        object_id="total_clips",
        component="sensor",
        name="Total clips",
        icon="mdi:counter",
        device_class=None,
        state_class="measurement",
        unit_of_measurement=None,
        enabled_by_default=False,
        min_publish_interval_s=5.0,
        state_fn=_st.state_total_clips,
        command_handler=None,
        affected_by_hub_events=("clip_indexed",),
    ),

    # --- Current download ---
    EntityDef(
        object_id="current_filename",
        component="sensor",
        name="Current download",
        icon="mdi:file-download",
        device_class=None,
        state_class=None,
        unit_of_measurement=None,
        enabled_by_default=False,
        min_publish_interval_s=2.0,
        state_fn=_st.state_current_filename,
        command_handler=None,
        affected_by_hub_events=("item_started", "item_finished"),
    ),
    EntityDef(
        object_id="current_progress",
        component="sensor",
        name="Current progress",
        icon="mdi:progress-download",
        device_class=None,
        state_class="measurement",
        unit_of_measurement="%",
        enabled_by_default=False,
        min_publish_interval_s=2.0,
        state_fn=_st.state_current_progress,
        command_handler=None,
        affected_by_hub_events=("item_progress", "item_started",
                                "item_finished"),
        qos=0,
    ),
    EntityDef(
        object_id="download_speed",
        component="sensor",
        name="Download speed",
        icon="mdi:speedometer",
        device_class="data_rate",
        state_class="measurement",
        unit_of_measurement="MB/s",
        enabled_by_default=True,
        min_publish_interval_s=60.0,
        state_fn=_st.state_download_speed,
        command_handler=None,
        affected_by_hub_events=("item_progress", "item_started",
                                "item_finished", "sync_done", "sync_state",
                                "dashcam_offline"),
        qos=0,
    ),

    # --- Disk / sync history ---
    EntityDef(
        object_id="disk_used",
        component="sensor",
        name="Disk used",
        icon="mdi:harddisk",
        device_class=None,
        state_class="measurement",
        unit_of_measurement="%",
        enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=_st.state_disk_used,
        command_handler=None,
        affected_by_hub_events=(),  # poll-only, no hub events
    ),
]


# Buttons in TOPOLOGY use sentinel `_pending_command` for `command_handler`.
# The real handler is bound at startup via build_command_handlers(app).
async def _pending_command(_payload: bytes) -> None:
    raise RuntimeError(
        "command handler not bound — call build_command_handlers(app) first"
    )


TOPOLOGY.extend([
    EntityDef(
        object_id="start_sync", component="button", name="Start sync",
        icon="mdi:play", device_class=None, state_class=None,
        unit_of_measurement=None, enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=None, command_handler=_pending_command,
        affected_by_hub_events=(),
    ),
    EntityDef(
        object_id="pause_sync", component="button", name="Pause sync",
        icon="mdi:pause", device_class=None, state_class=None,
        unit_of_measurement=None, enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=None, command_handler=_pending_command,
        affected_by_hub_events=(),
    ),
    EntityDef(
        object_id="skip_current", component="button", name="Skip current download",
        icon="mdi:skip-next", device_class=None, state_class=None,
        unit_of_measurement=None, enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=None, command_handler=_pending_command,
        affected_by_hub_events=(),
    ),
    EntityDef(
        object_id="refresh_queue", component="button", name="Refresh queue",
        icon="mdi:refresh", device_class=None, state_class=None,
        unit_of_measurement=None, enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=None, command_handler=_pending_command,
        affected_by_hub_events=(),
    ),
    EntityDef(
        object_id="retry_failed", component="button", name="Retry failed",
        icon="mdi:reload-alert", device_class=None, state_class=None,
        unit_of_measurement=None, enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=None, command_handler=_pending_command,
        affected_by_hub_events=(),
    ),
    EntityDef(
        object_id="rescan_archive", component="button", name="Rescan archive",
        icon="mdi:folder-refresh", device_class=None, state_class=None,
        unit_of_measurement=None, enabled_by_default=True,
        min_publish_interval_s=0.0,
        state_fn=None, command_handler=_pending_command,
        affected_by_hub_events=(),
    ),
])


def _e(object_id, component, name, icon, state_fn, *, events=(), interval=1.0,
       device_class=None, state_class=None, unit=None, enabled=True,
       handler=None, attrs_fn=None, poll=False, extra=None) -> EntityDef:
    return EntityDef(
        object_id=object_id, component=component, name=name, icon=icon,
        device_class=device_class, state_class=state_class,
        unit_of_measurement=unit, enabled_by_default=enabled,
        min_publish_interval_s=interval, state_fn=state_fn,
        command_handler=handler, affected_by_hub_events=tuple(events),
        attrs_fn=attrs_fn, poll=poll, discovery_extra=extra or {},
    )


TOPOLOGY.extend([
    _e("sync_enabled", "switch", "Sync", "mdi:sync", _st.state_sync_switch,
       events=("sync_state",), interval=0.0, handler=_pending_command,
       extra={"payload_on": "ON", "payload_off": "OFF",
              "state_on": "ON", "state_off": "OFF"}),
    _e("resume_sync", "button", "Resume sync", "mdi:play-pause", None,
       interval=0.0, handler=_pending_command),

    _e("queue_gone", "sensor", "Queue gone", "mdi:cloud-off-outline",
       _st.state_queue_gone, events=("queue_changed",),
       state_class="measurement", enabled=False),
    _e("queue_skipped", "sensor", "Queue skipped", "mdi:skip-next-circle-outline",
       _st.state_queue_skipped, events=("queue_changed",),
       state_class="measurement", enabled=False),
    _e("queue_remaining", "sensor", "Queue remaining", "mdi:database-arrow-down",
       _st.state_queue_remaining, events=("queue_changed", "item_finished"),
       interval=30.0, device_class="data_size", state_class="measurement",
       unit="GB"),
    _e("download_eta", "sensor", "Download ETA", "mdi:timer-sand",
       _st.state_download_eta, events=("item_progress", "item_finished", "sync_done"),
       interval=60.0, device_class="duration", state_class="measurement",
       unit="min"),
    _e("session_downloaded", "sensor", "Session downloaded",
       "mdi:download-multiple", _st.state_session_downloaded,
       events=("item_progress", "item_finished", "sync_done"), interval=60.0,
       device_class="data_size", state_class="measurement", unit="MB",
       enabled=False),

    _e("camera_recording", "binary_sensor", "Camera recording",
       "mdi:record-rec", _st.state_camera_recording,
       events=("dashcam_online", "dashcam_offline"),
       device_class="running", poll=True),
    _e("camera_sd_free", "sensor", "Camera SD free", "mdi:sd",
       _st.state_camera_sd_free, events=("dashcam_online",), interval=60.0,
       device_class="data_size", state_class="measurement", unit="GB",
       poll=True),
    _e("camera_sd_status", "sensor", "Camera SD status", "mdi:sd",
       _st.state_camera_sd_status, events=("dashcam_online",), poll=True,
       enabled=False),
    _e("camera_firmware", "sensor", "Camera firmware", "mdi:chip",
       _st.state_camera_firmware, events=("dashcam_online",), poll=True,
       enabled=False, extra={"entity_category": "diagnostic"}),

    _e("last_journey", "sensor", "Last journey", "mdi:map-marker-path",
       _st.state_last_journey, events=("sync_done",), interval=30.0,
       device_class="timestamp", attrs_fn=_st.attrs_last_journey, poll=True),
    _e("last_journey_distance", "sensor", "Last journey distance",
       "mdi:map-marker-distance", _st.state_last_journey_distance,
       events=("sync_done",), interval=30.0, device_class="distance",
       state_class="measurement", unit="km", poll=True),
    _e("last_journey_duration", "sensor", "Last journey duration",
       "mdi:timer-outline", _st.state_last_journey_duration,
       events=("sync_done",), interval=30.0, device_class="duration",
       state_class="measurement", unit="min", poll=True),

    # No state_fn: published per hub event by MqttService, never retained.
    _e("activity", "event", "Activity", "mdi:bell-ring", None, interval=0.0,
       extra={"event_types": ["clip_downloaded", "download_failed",
                              "sync_error", "disk_full"]}),
])


def build_command_handlers(app: Any) -> dict[str, Any]:
    """Return a dict of object_id (and 'prioritize_recent') to async
    handlers bound to the running app's services."""

    async def _start_sync(_p: bytes) -> None:
        sw = app.state.sync_worker
        sw.resume()
        sw.start()
        sw.kick()

    async def _pause_sync(_p: bytes) -> None:
        app.state.sync_worker.pause()

    async def _sync_switch(p: bytes) -> None:
        if p.strip().upper() == b"ON":
            await _start_sync(p)
        else:
            await _pause_sync(p)

    async def _skip_current(_p: bytes) -> None:
        app.state.sync_worker.skip_current()

    async def _refresh_queue(_p: bytes) -> None:
        app.state.sync_worker.kick()

    async def _retry_failed(_p: bytes) -> None:
        _q.retry_failed(app.state.db)
        _q.emit_queue_changed(app.state.db, app.state.hub)
        app.state.sync_worker.kick()

    async def _rescan_archive(_p: bytes) -> None:
        snap = app.state.settings_provider.get()
        await asyncio.to_thread(
            _scanner.scan, app.state.db, snap.recordings, snap.grouping,
            app.state.hub, asyncio.get_running_loop(),
        )

    async def _prioritize_recent(payload: bytes) -> None:
        try:
            body = json.loads(payload)
            hours = float(body["hours"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            log.warning("mqtt: prioritize_recent: bad payload %r", payload[:80])
            return
        if not (0 < hours <= 168):
            log.warning("mqtt: prioritize_recent: hours out of range: %s", hours)
            return
        _q.prioritize_recent_hours(app.state.db, hours)
        _q.emit_queue_changed(app.state.db, app.state.hub)
        app.state.sync_worker.kick()

    return {
        "start_sync": _start_sync,
        "pause_sync": _pause_sync,
        "skip_current": _skip_current,
        "refresh_queue": _refresh_queue,
        "retry_failed": _retry_failed,
        "rescan_archive": _rescan_archive,
        "prioritize_recent": _prioritize_recent,
        "resume_sync": _start_sync,
        "sync_enabled": _sync_switch,
    }
