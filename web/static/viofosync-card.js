/*
 * Viofosync Lovelace card.
 *
 * Install: Settings > Dashboards > Resources > Add resource
 *   URL:  http://<viofosync-host>:8080/static/viofosync-card.js   Type: JavaScript module
 * (The add-on runs on the host network, so the app serves this file directly.
 *  If Home Assistant is on https, copy the file to /config/www and use
 *  /local/viofosync-card.js instead, to avoid mixed content.)
 *
 * Card config:
 *   type: custom:viofosync-card
 *   prefix: ""        # optional, if your entity ids are e.g. sensor.viofosync_sync_status
 *   title: Dashcam    # optional
 */
const SLUGS = {
  status: ["sensor", "sync_status"],
  dashcam: ["binary_sensor", "dashcam"],
  pending: ["sensor", "queue_pending"],
  failed: ["sensor", "queue_failed"],
  remaining: ["sensor", "queue_remaining"],
  file: ["sensor", "current_download"],
  progress: ["sensor", "current_progress"],
  speed: ["sensor", "download_speed"],
  eta: ["sensor", "download_eta"],
  disk: ["sensor", "disk_used"],
  journey: ["sensor", "last_journey_distance"],
  sync: ["switch", "sync"],
  skip: ["button", "skip_current_download"],
};

class ViofosyncCard extends HTMLElement {
  setConfig(config) {
    this._config = { prefix: "", title: "Viofosync", ...config };
    this._ids = Object.fromEntries(
      Object.entries(SLUGS).map(([k, [domain, slug]]) =>
        [k, `${domain}.${this._config.prefix}${slug}`]),
    );
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 4; }

  static getStubConfig() { return { title: "Viofosync" }; }

  _s(key) {
    const st = this._hass.states[this._ids[key]];
    return st && st.state !== "unavailable" && st.state !== "unknown" ? st : null;
  }

  _val(key, unit = "") {
    const st = this._s(key);
    return st ? `${st.state}${unit}` : "—";
  }

  _onClick(e) {
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "sync" && this._s("sync")) {
      this._hass.callService("switch", "toggle", { entity_id: this._ids.sync });
    } else if (act === "skip" && this._s("skip")) {
      this._hass.callService("button", "press", { entity_id: this._ids.skip });
    }
  }

  _render() {
    if (!this._hass || !this._config) return;
    const status = this._s("status");
    const online = this._s("dashcam")?.state === "on";
    const progress = Number(this._s("progress")?.state);
    const file = this._s("file")?.state;
    const syncOn = this._s("sync")?.state === "on";
    const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        .row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        h2 { margin: 0; font-size: 18px; font-weight: 500; }
        .chip { padding: 2px 10px; border-radius: 999px; font-size: 12px;
                background: var(--secondary-background-color); }
        .chip.on { color: var(--success-color, #43a047); }
        .chip.off { color: var(--error-color, #db4437); }
        .bar { height: 6px; background: var(--divider-color); border-radius: 3px; margin: 10px 0 4px; overflow: hidden; }
        .bar > div { height: 100%; background: var(--primary-color); transition: width .4s linear; }
        .file { font-size: 12px; color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 14px; text-align: center; }
        .stats b { display: block; font-size: 18px; }
        .stats span { font-size: 11px; color: var(--secondary-text-color); }
        .actions { display: flex; gap: 8px; margin-top: 14px; }
        button { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid var(--divider-color);
                 background: var(--secondary-background-color); color: var(--primary-text-color); cursor: pointer; }
        button[disabled] { opacity: .5; cursor: default; }
      </style>
      <ha-card>
        <div class="row">
          <h2>${esc(this._config.title)}</h2>
          <span class="chip ${online ? "on" : "off"}">${online ? "online" : "offline"} · ${esc(status ? status.state : "unknown")}</span>
        </div>
        ${Number.isFinite(progress) && file ? `
          <div class="bar"><div style="width:${progress}%"></div></div>
          <div class="file">${esc(file)} · ${progress}%</div>` : ""}
        <div class="stats">
          <div><b>${esc(this._val("pending"))}</b><span>pending</span></div>
          <div><b>${esc(this._val("failed"))}</b><span>failed</span></div>
          <div><b>${esc(this._val("speed"))}</b><span>MB/s</span></div>
          <div><b>${esc(this._val("eta"))}</b><span>min left</span></div>
          <div><b>${esc(this._val("remaining"))}</b><span>GB to go</span></div>
          <div><b>${esc(this._val("disk", "%"))}</b><span>disk</span></div>
          <div><b>${esc(this._val("journey"))}</b><span>last km</span></div>
        </div>
        <div class="actions">
          <button data-act="sync" ${this._s("sync") ? "" : "disabled"}>${syncOn ? "Pause sync" : "Start sync"}</button>
          <button data-act="skip" ${this._s("skip") ? "" : "disabled"}>Skip current</button>
        </div>
      </ha-card>`;
  }
}

customElements.define("viofosync-card", ViofosyncCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "viofosync-card",
  name: "Viofosync",
  description: "Sync status, queue, progress and controls for Viofosync.",
});
