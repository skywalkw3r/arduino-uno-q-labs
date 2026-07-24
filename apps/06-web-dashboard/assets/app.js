// Browser side of the dashboard.
//
// WebUI comes from libs/arduino.js, which is a thin wrapper over socket.io.
// Run scripts/fetch-webui-libs.sh once to download both into assets/libs/.

const HISTORY = 200; // samples kept in the rolling chart

const statusEl = document.querySelector('#status');
const voltsEl = document.querySelector('#volts');
const rawEl = document.querySelector('#raw');
const samplesEl = document.querySelector('#samples');
const ledButton = document.querySelector('#led-button');
const ledStateEl = document.querySelector('#led-state');
const canvas = document.querySelector('#chart');
const ctx = canvas.getContext('2d');

const history = [];
let vref = 3.3;

const ui = new WebUI();

ui.on_connect(() => {
  statusEl.textContent = 'connected';
  statusEl.classList.replace('status--down', 'status--up');
});

ui.on_disconnect(() => {
  statusEl.textContent = 'disconnected';
  statusEl.classList.replace('status--up', 'status--down');
});

ui.on_message('telemetry', (data) => {
  voltsEl.textContent = data.volts.toFixed(3);
  rawEl.textContent = data.raw;
  samplesEl.textContent = data.samples;
  setLedState(data.led);

  history.push(data.percent);
  if (history.length > HISTORY) history.shift();
  draw();
});

ui.on_message('led_state', (data) => setLedState(data.on));

ledButton.addEventListener('click', () => ui.send_message('toggle_led'));

function setLedState(on) {
  ledStateEl.textContent = on ? 'LED on' : 'LED off';
  ledStateEl.classList.toggle('led-state--on', Boolean(on));
}

// Plain canvas rather than a charting library — no external CDN, nothing to
// vendor, and it keeps the whole page under a few KB.
function draw() {
  const { width, height } = canvas;
  const style = getComputedStyle(document.documentElement);
  const line = style.getPropertyValue('--accent').trim() || '#00979d';
  const grid = style.getPropertyValue('--grid').trim() || '#d6dde0';
  // Labels need more contrast than the gridlines themselves, or they vanish
  // against the panel background in dark mode.
  const label = style.getPropertyValue('--muted').trim() || '#5c6b73';

  ctx.clearRect(0, 0, width, height);

  ctx.font = '12px system-ui, sans-serif';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = (height / 4) * i;

    ctx.strokeStyle = grid;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();

    ctx.fillStyle = label;
    // Nudge the top label down so it isn't clipped by the canvas edge.
    ctx.fillText(`${((4 - i) * (vref / 4)).toFixed(2)} V`, 6, i === 0 ? y + 14 : y - 5);
  }

  if (history.length < 2) return;

  ctx.strokeStyle = line;
  ctx.lineWidth = 2;
  ctx.beginPath();
  history.forEach((percent, i) => {
    const x = (i / (HISTORY - 1)) * width;
    const y = height - (percent / 100) * height;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

draw();
