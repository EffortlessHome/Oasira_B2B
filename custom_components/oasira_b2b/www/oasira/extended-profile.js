class ExtendedProfile extends HTMLElement {
  set hass(hass) {}

  async connectedCallback() {
    this.innerHTML = `
      <style>
        :host {
          display: flex;
          justify-content: center;
          align-items: center;
          height: 100vh;
          background-color: var(--lovelace-background, var(--primary-background-color));
          color: var(--primary-text-color);
          font-family: var(--primary-font-family, Roboto, sans-serif);
        }

        .container {
          background: var(--card-background-color);
          width: 800px;
          padding: 24px;
          border-radius: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.2));
          display: flex;
          flex-wrap: wrap;
          gap: 24px;
          position: relative;
        }

        .back-btn {
          position: absolute;
          top: 16px;
          left: 16px;
          font-size: 22px;
          cursor: pointer;
          background: none;
          border: none;
          color: var(--primary-color);
          transition: color 0.3s;
        }

        .back-btn:hover {
          color: var(--accent-color);
        }

        .left-column, .right-column {
          flex: 1;
          min-width: 320px;
        }

        .profile {
          text-align: center;
        }

        .profile img {
          width: 90px;
          height: 90px;
          border-radius: 50%;
          margin-bottom: 10px;
          border: 2px solid var(--divider-color);
          background: var(--card-background-color);
        }

        .profile h2 {
          margin: 5px 0;
          color: var(--primary-text-color);
        }

        .profile p {
          color: var(--secondary-text-color);
          font-size: 0.9em;
        }

        .profile button {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          border: none;
          padding: 10px 16px;
          border-radius: 8px;
          cursor: pointer;
          margin-top: 10px;
          transition: background 0.3s, transform 0.1s;
        }

        .profile button:hover {
          background: var(--accent-color);
          transform: scale(1.02);
        }

        .section {
          background: var(--secondary-background-color, var(--card-background-color));
          padding: 16px;
          border-radius: 12px;
          margin-top: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 1px 4px rgba(0,0,0,0.1));
        }

        .section h3 {
          margin-top: 0;
          color: var(--primary-text-color);
          border-bottom: 1px solid var(--divider-color);
          padding-bottom: 6px;
          font-weight: 500;
        }

        .user-list div {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px;
          background: var(--card-background-color);
          margin-top: 6px;
          border-radius: 8px;
          box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,0.1));
          color: var(--primary-text-color);
        }

        .user-list div:hover {
          background: var(--ha-card-background-hover, var(--secondary-background-color));
        }

        .user-list img {
          width: 30px;
          height: 30px;
          border-radius: 50%;
          margin-right: 10px;
        }

        .security-box, .subscription-box {
          background: var(--card-background-color);
          padding: 12px;
          border-radius: 8px;
          margin-top: 10px;
          color: var(--primary-text-color);
        }

        a {
          color: var(--link-text-color, var(--primary-color));
          text-decoration: none;
          transition: color 0.3s;
        }

        a:hover {
          color: var(--accent-color);
        }

        p {
          color: var(--secondary-text-color);
        }
      </style>

      <div class="container">
        <button class="back-btn" id="back-btn">←</button>

        <div class="profile left-column">
          <div id="current-user"></div>

          <button id="custom-logout-btn" class="logout-btn">Logout</button>
          <button id="custom-restart-btn" class="restart-btn">Restart</button>
          <p><a href="https://oasira.ai/account/my-oasira/" target="_blank">My Account</a></p>
        </div>
    
        <div class="section left-column">
          <h3>System Users</h3>
          <div class="user-list" id="user-list"></div>
          <p><a href="https://oasira.ai/account/my-oasira/" target="_blank">Manage Users</a></p>
        </div>

        <div class="right-column">
          <div class="section">
            <h3>Privacy and Security</h3>
            <div class="security-box">
              <strong>Two-Factor Authentication</strong>
              <p>Double the security, double the peace of mind. Two-factor authentication keeps your smart space safer.</p>
              <a href="/profile/security">Two-Factor Settings</a>
            </div>
          </div>

          <div class="section">
            <h3>Subscription</h3>
            <div class="subscription-box" id="subscriptions">
              <a href="https://oasira.ai/account/my-oasira/manage-subscription/" target="_blank">Manage Subscription</a>
            </div>
          </div>
        </div>
      </div>
    `;

    this.querySelector("#back-btn")?.addEventListener("click", () => history.back());
    this.querySelector("#custom-logout-btn")?.addEventListener("click", this.handleLogout.bind(this));
    this.querySelector("#custom-restart-btn")?.addEventListener("click", this.handleRestart.bind(this));
    this.querySelector("#enable-mfa-btn")?.addEventListener("click", this.handleTwoFactor.bind(this));

    const hass = document.querySelector("home-assistant")?.hass;
    if (hass && !hass.user.is_admin) {
      this.querySelector("#custom-restart-btn").style.visibility = "hidden";
    }

    await this.populateUsers();
    await this.populateCurrentUser();
  }

  async handleLogout(event) {
    event.preventDefault();
    try {
      const hass = document.querySelector("home-assistant")?.hass;
      if (!hass) return;
      await hass.auth.revoke();
      hass.connection.close();
      if (window.localStorage) window.localStorage.clear();
      document.location.href = "/";
    } catch (err) {
      console.error(err);
      alert("Log out failed");
    }
  }

  async handleRestart() {
    const hass = document.querySelector("home-assistant")?.hass;
    if (!hass) return alert("Instance not found.");
    try {
      await hass.callService("homeassistant", "restart");
    } catch (err) {
      console.error("Failed to restart:", err);
      alert("Restart failed.");
    }
  }

  async handleTwoFactor() {
    const homeAssistant = document.querySelector("home-assistant");
    const hass = homeAssistant?.hass;
    if (!hass) return alert("Instance not found.");

    const haRoot = document.querySelector("home-assistant");
    const event = new CustomEvent("show-dialog");
    haRoot.dispatchEvent(event);

    showMfaModuleSetupFlowDialog(haRoot, {
      mfaModuleId: "totp",
      dialogClosedCallback: ({ flowFinished }) => {
        alert(flowFinished ? "MFA setup complete." : "MFA setup cancelled.");
      },
    });
  }

  async populateCurrentUser() {
    const hass = document.querySelector("home-assistant")?.hass;
    if (!hass) return;

    const userElement = this.querySelector("#current-user");
    userElement.innerHTML = `
      <img src="https://oasira.ai/wp-content/uploads/2025/10/user.png" alt="Profile Picture">
      <h2>${hass.user.name}</h2> 
      <p>${hass.states["sensor.ha_url"]?.state || ""}</p>
    `;
  }

  async populateUsers() {
    const userListElement = this.querySelector("#user-list");
    const hass = document.querySelector("home-assistant")?.hass;
    if (!hass) return alert("Oasira instance not found.");

    const systemId = hass.states["sensor.systemid"]?.state;
    const customerId = hass.states["sensor.customerid"]?.state;
    const customertoken = hass.states["sensor.customertoken"]?.state;

    try {
      const response = await fetch("https://cust.effortlesshome.co/getsystemusersbysystemid/0", {
        method: "GET",
        headers: {
          "eh_system_id": systemId,
          "eh_customer_id": customerId,
          "Accept": "*/*",
        },
      });

      if (!response.ok) throw new Error(`Failed to fetch users: ${response.statusText}`);
      const data = await response.json();
      if (!data.success || !data.results) throw new Error("Unexpected response structure");

      userListElement.innerHTML = data.results
        .map((user) => `<div><span>${user.User_Email} (${user.user_type})</span></div>`)
        .join("");
    } catch (error) {
      console.error("Error fetching users:", error);
      userListElement.innerHTML = `<p>Failed to load users. Please try again later.</p>`;
    }
  }
}

customElements.define("extended-profile", ExtendedProfile);
