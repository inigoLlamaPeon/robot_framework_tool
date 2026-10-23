const connectionStatus = document.querySelector("#connection-status");
const connectionLabel = document.querySelector("#connection-label");
const websocketMessage = document.querySelector("#websocket-message");

function setConnectionState(state, label) {
  connectionStatus.classList.toggle("is-connected", state === "connected");
  connectionStatus.classList.toggle("is-connecting", state === "connecting");
  connectionStatus.classList.toggle("is-disconnected", state === "disconnected");
  connectionLabel.textContent = label;
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
  setConnectionState("connecting", "Connecting");

  socket.addEventListener("open", () => {
    setConnectionState("connected", "Connected");
  });

  socket.addEventListener("message", (event) => {
    if (websocketMessage) websocketMessage.textContent = event.data;
  });

  socket.addEventListener("close", () => {
    setConnectionState("disconnected", "Reconnecting");
    if (websocketMessage) websocketMessage.textContent = "Connection interrupted";
    window.setTimeout(connectWebSocket, 2000);
  });

  socket.addEventListener("error", () => {
    socket.close();
  });
}

connectWebSocket();
