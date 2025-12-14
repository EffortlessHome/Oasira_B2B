class VideoConfPanel extends HTMLElement {
  connectedCallback() {
    // Clear panel and add a launch button
    this.innerHTML = `
      <style>
        .launch-btn {
          display: inline-block;
          padding: 12px 20px;
          font-size: 16px;
          font-weight: bold;
          background: #1a73e8;
          color: white;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          margin: 20px;
        }
        .launch-btn:hover {
          background: #1669c1;
        }
      </style>
      <div style="display:flex;justify-content:center;align-items:center;height:100%;">
        <button class="launch-btn" id="launch-jitsi">Launch Video Conference</button>
      </div>
    `;

    this.querySelector("#launch-jitsi").addEventListener("click", () => {
      const domain = "https://meet.jit.si";
      const roomName = "Oasira Senior Living Room Demo 1"; // Customize your room name
      const url = `${domain}/${roomName}#userInfo.displayName="Oasira Demo User 1"`;

      // Open popup window
      const width = 1000;
      const height = 800;
      const left = (screen.width / 2) - (width / 2);
      const top = (screen.height / 2) - (height / 2);

      window.open(
        url,
        "JitsiConference",
        `width=${width},height=${height},top=${top},left=${left},resizable=yes,scrollbars=yes,status=yes`
      );
    });
  }
}

customElements.define("videoconf-panel", VideoConfPanel);