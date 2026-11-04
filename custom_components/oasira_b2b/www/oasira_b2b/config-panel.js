class ConfigPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (this.parentNode) {
      this.populateCurrentUser();
    }
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          background-color: var(--lovelace-background, var(--primary-background-color));
          color: var(--primary-text-color);
          font-family: var(--paper-font-body1_-_font-family, "Arial", sans-serif);
          transition: background-color 0.3s, color 0.3s;
          padding: 20px;
        }

        .dashboard-container {
          max-width: 1000px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        .brand-logo {
          position: absolute;
          top: 0;
          right: 0;
        }

        .brand-logo img {
          max-width: 40px;
          height: auto;
          transition: opacity 0.2s;
        }

        .brand-logo img:hover {
          opacity: 0.8;
        }

        .header-section {
          display: flex;
          flex-wrap: wrap;
          gap: 24px;
          background: var(--card-background-color);
          padding: 24px;
          border-radius: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.1));
        }

        .profile-info {
          flex: 1;
          min-width: 250px;
          text-align: center;
          border-right: 1px solid var(--divider-color);
          padding-right: 24px;
        }

        @media (max-width: 600px) {
          .profile-info {
            border-right: none;
            border-bottom: 1px solid var(--divider-color);
            padding-right: 0;
            padding-bottom: 24px;
          }
        }

        .profile-info img {
          width: 80px;
          height: 80px;
          border-radius: 50%;
          margin-bottom: 12px;
          border: 2px solid var(--primary-color);
          background: var(--secondary-background-color);
        }

        .profile-info h2 {
          margin: 8px 0;
          font-size: 1.5rem;
        }

        .profile-info p {
          color: var(--secondary-text-color);
          font-size: 0.9rem;
          margin-bottom: 16px;
        }

        .controls {
          display: flex;
          justify-content: center;
          gap: 12px;
          margin-bottom: 16px;
        }

        .btn {
          padding: 8px 16px;
          border-radius: 8px;
          border: none;
          cursor: pointer;
          font-weight: 500;
          transition: opacity 0.2s, transform 0.1s;
        }

        .btn:active { transform: scale(0.98); }

        .btn-primary { background: var(--primary-color); color: white; }
        .btn-outline { background: transparent; border: 1px solid var(--primary-color); color: var(--primary-color); }

        .system-status {
          flex: 2;
          min-width: 300px;
          display: flex;
          flex-direction: column;
          gap: 16px;
          position: relative;
        }

        .status-grid {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .status-item {
          padding: 12px 0;
          border-bottom: 1px solid var(--divider-color);
        }

        .status-item:last-child {
          border-bottom: none;
        }

        .status-item h4 { margin: 0 0 4px 0; color: var(--secondary-text-color); font-size: 0.8rem; text-transform: uppercase; }

        .status-item a {
          color: var(--primary-color);
          text-decoration: none;
          font-weight: 500;
          transition: color 0.2s;
        }

        .status-item a:hover {
          color: var(--accent-color);
          text-decoration: underline;
        }

        .nav-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 20px;
        }

        .tile {
          background-color: var(--card-background-color);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 32px;
          text-align: center;
          font-weight: bold;
          text-decoration: none;
          color: var(--primary-text-color);
          box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1));
          transition: background-color 0.3s, box-shadow 0.3s, transform 0.2s;
        }

        .tile:hover {
          background-color: var(--secondary-background-color);
          box-shadow: var(--ha-card-box-shadow-hover, 0 4px 8px rgba(0,0,0,0.15));
          transform: translateY(-2px);
        }

        .tile ha-icon {
          --mdc-icon-size: 40px;
          margin-bottom: 12px;
          color: var(--orange);
        }

        .footer-links {
          text-align: center;
          padding: 20px;
          color: var(--secondary-text-color);
        }

        .footer-links a {
          color: var(--primary-color);
          text-decoration: none;
          margin: 0 12px;
        }

        /* Matter Section Styles */
        .matter-section {
          background: var(--card-background-color);
          padding: 24px;
          border-radius: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.1));
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .matter-section h2 {
          margin: 0 0 8px 0;
          font-size: 1.25rem;
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .matter-section h2 ha-icon {
          color: var(--primary-color);
        }

        .bridge-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 20px;
        }

        .bridge-card {
          background: var(--secondary-background-color);
          padding: 20px;
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          border: 1px solid var(--divider-color);
        }

        .bridge-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .bridge-header h3 { margin: 0; font-size: 1.1rem; }

        .status-badge {
          padding: 4px 8px;
          border-radius: 12px;
          font-size: 0.75rem;
          font-weight: bold;
          text-transform: uppercase;
        }

        .status-running { background: var(--success-color, #4caf50); color: white; }
        .status-stopped { background: var(--error-color, #f44336); color: white; }

        .pairing-info {
          background: var(--card-background-color);
          padding: 12px;
          border-radius: 8px;
          font-family: monospace;
          font-size: 0.9rem;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .pairing-info span { color: var(--secondary-text-color); font-size: 0.75rem; }
        .pairing-code { font-weight: bold; letter-spacing: 1px; color: var(--primary-color); }
      </style>

      <div class="dashboard-container">
        <div class="header-section">
          <div class="profile-info">
            <div>
              <img src="/local/oasira_b2b/user.png" alt="Profile">
              <h2 id="user-name">Loading...</h2>
              <p id="ha-url">Connecting...</p>
            </div>
            <div class="controls">
              <button id="logout-btn" class="btn btn-outline">Logout</button>
              <button id="restart-btn" class="btn btn-primary">Restart</button>
            </div>
          </div>

          <div class="system-status">
             <div class="brand-logo">
               <a href="https://www.oasira.ai" target="_blank">
                 <img src="/local/oasira_b2b/ehlogo.jpg" alt="EH Logo">
               </a>
             </div>
             <div class="status-grid">
                <div class="status-item">
                  <h4>Security</h4>
                  <a href="/profile/security">Two-Factor Authentication</a>
                </div>
                <div class="status-item">
                  <h4>Account</h4>
                  <a href="https://my.oasira.ai" target="_blank">Manage Subscription</a>
                </div>
             </div>
          </div>
        </div>

        <div class="nav-grid">
          ${this._tile("/oasira-area-panel", "mdi:label-multiple", "Set Device Areas")}
          ${this._tile("/oasira-label-panel", "mdi:label", "Set Labels")}
        </div>

        <div class="matter-section">
          <h2><ha-icon icon="mdi:hub"></ha-icon> Matter Bridges</h2>
          <div id="bridge-list" class="bridge-grid">
             <p>Loading Matter bridges...</p>
          </div>
        </div>

        <div class="footer-links">
           <a href="https://www.oasira.ai" target="_blank">oasira.ai</a> |
           <a href="https://www.oasira.ai/support" target="_blank">Support</a>
        </div>
      </div>
    `;

    this.querySelector("#logout-btn")?.addEventListener("click", () => this.handleLogout());
    this.querySelector("#restart-btn")?.addEventListener("click", () => this.handleRestart());

    this.populateCurrentUser();
    this.fetchMatterBridges();
  }

  async handleLogout() {
    if (!this.hass) return;
    try {
      await this.hass.auth.revoke();
      if (window.localStorage) window.localStorage.clear();
      document.location.href = "/";
    } catch (err) {
      console.error(err);
      alert("Logout failed");
    }
  }

  async handleRestart() {
    if (!this.hass) return;
    if (!confirm("Are you sure you want to restart Home Assistant?")) return;
    try {
      await this.hass.callService("homeassistant", "restart");
      alert("Restarting System...");
    } catch (err) {
      console.error(err);
      alert("Restart failed.");
    }
  }

  populateCurrentUser() {
    if (!this.hass) return;
    const nameEl = this.querySelector("#user-name");
    const urlEl = this.querySelector("#ha-url");
    if (nameEl) nameEl.textContent = this.hass.user.name;
    if (urlEl) urlEl.textContent = this.hass.states["sensor.ha_url"]?.state || "Connected";

    if (!this.hass.user.is_admin) {
      const restartBtn = this.querySelector("#restart-btn");
      if (restartBtn) restartBtn.style.display = "none";
    }
  }

  _tile(href, icon, label) {
    return `
      <a href="${href}" class="tile">
        <ha-icon icon="${icon}"></ha-icon>
        ${label}
      </a>
    `;
  }

  async fetchMatterBridges() {
    const hostname = window.location.hostname;
    const url = `http://${hostname}:8482/api/matter/bridges`;
    const list = this.querySelector("#bridge-list");

    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error("Matter Hub unreachable");
      const bridges = await response.json();

      if (bridges && bridges.length > 0) {
        if (list) {
          const cards = document.createDocumentFragment();
          for (const bridge of bridges) {
            cards.append(this._renderBridgeCard(bridge));
          }
          list.replaceChildren(cards);
        }
      } else {
        if (list) {
          const message = document.createElement("p");
          message.textContent = "No Matter bridges found.";
          list.replaceChildren(message);
        }
      }
    } catch (err) {
      console.error("Failed to fetch Matter bridges:", err);
      if (list) {
        const message = document.createElement("p");
        message.style.color = "var(--error-color, #f44336)";
        message.textContent = "Matter Hub unreachable or API failed.";
        list.replaceChildren(message);
      }
    }
  }

  _renderBridgeCard(bridge) {
    const comm = bridge.commissioning || {};
    const info = bridge.basicInformation || {};
    const createElement = (tagName, className, text) => {
      const element = document.createElement(tagName);
      if (className) element.className = className;
      if (text !== undefined) element.textContent = text;
      return element;
    };

    const card = createElement("div", "bridge-card");
    const header = createElement("div", "bridge-header");
    header.append(
      createElement("h3", "", bridge.name || "Matter Bridge"),
      createElement(
        "span",
        `status-badge status-${bridge.status === "running" ? "running" : "stopped"}`,
        String(bridge.status)
      )
    );
    card.append(header);

    const pairingInfo = createElement("div", "pairing-info");
    pairingInfo.append(
      createElement("span", "", "Manual Pairing Code"),
      createElement("div", "pairing-code", comm.manualPairingCode || "N/A")
    );

    const pairingDetails = createElement("div");
    pairingDetails.style.marginTop = "8px";
    const passcode = createElement("span", "", "Passcode: ");
    passcode.append(createElement("strong", "", comm.passcode || "N/A"));
    const discriminator = createElement("span", "", "Discriminator: ");
    discriminator.style.marginLeft = "12px";
    discriminator.append(createElement("strong", "", comm.discriminator || "N/A"));
    pairingDetails.append(passcode, discriminator);
    pairingInfo.append(pairingDetails);
    card.append(pairingInfo);

    const details = createElement("div");
    details.style.fontSize = "0.85rem";
    details.style.color = "var(--secondary-text-color)";
    const deviceCount = createElement("strong", "", bridge.deviceCount || 0);
    details.append("Devices: ", deviceCount, document.createElement("br"));
    details.append(
      "Vendor: ",
      info.vendorName || "Unknown",
      " | Version: ",
      info.softwareVersion || "N/A"
    );
    card.append(details);

    const resetButton = createElement("button", "btn btn-outline", "Factory Reset");
    resetButton.style.marginTop = "10px";
    resetButton.style.alignSelf = "flex-start";
    resetButton.addEventListener("click", async () => {
      if (!confirm("Factory reset this bridge? This cannot be undone.")) return;
      resetButton.disabled = true;
      resetButton.textContent = "Resetting...";
      try {
        const hostname = window.location.hostname;
        const bridgeId = encodeURIComponent(String(bridge.id));
        const url = `http://${hostname}:8482/api/matter/bridges/${bridgeId}/actions/factory-reset`;
        const resp = await fetch(url, { method: "GET" });
        if (!resp.ok) throw new Error("Factory reset failed");
        alert("Bridge factory reset successfully.");
      } catch (err) {
        alert("Factory reset failed: " + (err.message || err));
      } finally {
        resetButton.disabled = false;
        resetButton.textContent = "Factory Reset";
      }
    });
    card.append(resetButton);

    return card;
  }
}

customElements.define("oasira-config-panel", ConfigPanel);
