class ConfigPanel extends HTMLElement {
  set hass(hass) {}

  connectedCallback() {
    this.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100vh;
          width: 100vw;
          margin: 0;
          padding: 0;
          background-color: var(--lovelace-background, var(--primary-background-color));
          color: var(--primary-text-color);
          font-family: var(--paper-font-body1_-_font-family, "Arial", sans-serif);
          transition: background-color 0.3s, color 0.3s;
        }

        .back-arrow {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          margin: 16px;
          text-decoration: none;
          color: var(--primary-color);
          font-weight: 500;
        }

        .back-arrow:hover {
          color: var(--accent-color);
        }

        .container {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 20px;
          padding: 40px;
          box-sizing: border-box;
        }

        .tile {
          background-color: var(--card-background-color);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 24px;
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

        ha-icon {
          --mdc-icon-size: 36px;
          margin-bottom: 10px;
          color: var(--primary-color);
        }
      </style>

      <a class="back-arrow" href="javascript:history.back()">
        <ha-icon icon="mdi:arrow-left"></ha-icon>
        <span>Back</span>
      </a>

      <div class="container">     
        ${this._tile("/area-panel", "mdi:label-multiple", "Set Device Areas")}
        ${this._tile("/label-panel", "mdi:label", "Set Labels")}
        ${this._tile("http://oasira.local:8482", "mdi:hub", "Matterhub")}
        ${this._tile("/extended-profile", "mdi:cog", "Profile")}
      </div>
    `;
  }

  _tile(href, icon, label) {
    return `
      <a href="${href}" class="tile">
        <ha-icon icon="${icon}"></ha-icon>
        ${label}
      </a>
    `;
  }
}

customElements.define('config-panel', ConfigPanel);
