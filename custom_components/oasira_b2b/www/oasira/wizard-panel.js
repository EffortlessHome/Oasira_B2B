class WizardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.shadowRoot.innerHTML = `
      <style>
        .wizard-container { padding: 20px; font-family: sans-serif; }
        .wizard-step { margin-bottom: 2em; }
        button { margin-top: 1em; }

        #map { width: 100%; height: 300px; margin-top: 1em; }

        .wizard-status {
          position: fixed;
          bottom: 20px;
          right: 20px;
          background: #f1f1f1;
          border: 1px solid #ccc;
          border-radius: 8px;
          padding: 12px 16px;
          font-size: 14px;
          box-shadow: 0 2px 6px rgba(0,0,0,0.15);
          max-width: 240px;
          z-index: 1000;
        }
        .wizard-status h4 {
          margin-top: 0;
          font-size: 15px;
          margin-bottom: 8px;
        }
        .status-item {
          margin: 4px 0;
        }
        .complete { color: green; }
        .active { font-weight: bold; }
        .pending { color: #aaa; }
      </style>
      <div class="wizard-container" id="wizard-container"></div>
      <div class="wizard-status" id="wizard-status"></div>
    `;
    this.wizard = new Wizard(
      this.shadowRoot.getElementById('wizard-container'),
      this.shadowRoot.getElementById('wizard-status')
    );
  }
}

customElements.define('wizard-panel', WizardPanel);

class Wizard {
  constructor(container, statusContainer) {
    this.container = container;
    this.statusContainer = statusContainer;
    this.step = 0;
    this.homeData = {};
    this.steps = [
      { label: "Welcome", render: this.introStep.bind(this), complete: false },
      { label: "Name Home", render: this.nameStep.bind(this), complete: false },
      { label: "Set Location", render: this.locationStep.bind(this), complete: false }
    ];
    this.renderCurrentStep();
  }

  async renderCurrentStep() {
    this.container.innerHTML = '';
    this.updateStatusDisplay();
    await this.steps[this.step].render();
  }

  nextStep() {
    this.steps[this.step].complete = true;
    if (this.step < this.steps.length - 1) {
      this.step++;
      this.renderCurrentStep();
    } else {
      this.completeWizard();
    }
  }

  updateStatusDisplay() {
    this.statusContainer.innerHTML = `
      <h4>Wizard Progress</h4>
      ${this.steps.map((step, i) => `
        <div class="status-item ${step.complete ? 'complete' : i === this.step ? 'active' : 'pending'}">
          ${step.label} ${step.complete ? '✓' : ''}
        </div>
      `).join('')}
    `;
  }

  introStep() {
    this.container.innerHTML = `
      <div class="wizard-step">
        <h2>Welcome</h2>
        <p>Let’s get started by setting up your smart home.</p>
        <button id="startBtn">Create My Home</button>
      </div>
    `;
    this.container.querySelector('#startBtn').onclick = () => this.nextStep();
  }

  nameStep() {
    this.container.innerHTML = `
      <div class="wizard-step">
        <h2>Name Your Home</h2>
        <input type="text" id="homeName" placeholder="e.g. Lake House, Main Home" />
        <button id="nameNext">Next</button>
      </div>
    `;
    this.container.querySelector('#nameNext').onclick = async () => {
      const name = this.container.querySelector('#homeName').value.trim();
      if (!name) return alert("Please enter a home name.");
      this.homeData.name = name;
      await this.postData('/api/home/name', { name });
      this.nextStep();
    };
  }

  locationStep() {
    this.container.innerHTML = `
      <div class="wizard-step">
        <h2>Set Your Home Location</h2>
        <input type="text" id="homeAddress" placeholder="Enter your home address" />
        <div id="map"></div>
        <button id="locationNext">Next</button>
      </div>
    `;

    const mapEl = this.container.querySelector("#map");
    const map = new google.maps.Map(mapEl, { center: { lat: 20, lng: 0 }, zoom: 2 });
    const geocoder = new google.maps.Geocoder();

    const input = this.container.querySelector('#homeAddress');
    input.onblur = () => {
      const address = input.value;
      geocoder.geocode({ address }, async (results, status) => {
        if (status === 'OK') {
          const loc = results[0].geometry.location;
          map.setCenter(loc);
          new google.maps.Marker({ map, position: loc });
          this.homeData.address = results[0].formatted_address;
          this.homeData.lat = loc.lat();
          this.homeData.lng = loc.lng();
          const inferred = await this.fetchInferredData(loc.lat(), loc.lng());
          Object.assign(this.homeData, inferred);
        }
      });
    };

    this.container.querySelector('#locationNext').onclick = async () => {
      if (!this.homeData.address) {
        return alert("Please enter and confirm your home address.");
      }
      await this.postData('/api/home/location', this.homeData);
      this.nextStep();
    };
  }

  async fetchInferredData(lat, lng) {
    const res = await fetch(`/api/location/infer?lat=${lat}&lng=${lng}`);
    return await res.json();
  }

  async postData(url, data) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return await res.json();
    } catch (err) {
      console.error("POST failed:", err);
    }
  }

  completeWizard() {
    this.steps[this.step].complete = true;
    this.updateStatusDisplay();
    this.container.innerHTML = `
      <div class="wizard-step">
        <h2>Setup Complete</h2>
        <p>Your home is now registered. Welcome!</p>
      </div>
    `;
  }
}