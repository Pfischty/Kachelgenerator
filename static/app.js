const state = {
  colors: [],
  layouts: [],
  icons: [],
  selectedIcon: null,
  selectedColor: "#6870ef",
  text: "Alarm",
  iconPosition: { x: 300, y: 170 },
  iconScale: 0.45,
  textPosition: { x: 60, y: 360 },
  textSize: 48,
  dragging: null,
};

const canvas = document.getElementById("preview");
const ctx = canvas.getContext("2d");

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const message = await response.json().catch(() => ({}));
    throw new Error(message.error || "Request failed");
  }
  return response.json();
}

function drawRoundedRect(x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

async function loadColors() {
  state.colors = await fetchJSON("/api/colors");
  const select = document.getElementById("color-select");
  select.innerHTML = "";
  state.colors.forEach((color) => {
    const option = document.createElement("option");
    option.value = color.hex;
    option.textContent = `${color.name} (${color.hex})`;
    if (color.hex.toLowerCase() === state.selectedColor.toLowerCase()) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

async function loadLayouts() {
  state.layouts = await fetchJSON("/api/layout-presets");
  const select = document.getElementById("layout-select");
  select.innerHTML = "";
  state.layouts.forEach((layout) => {
    const option = document.createElement("option");
    option.value = layout.id;
    option.textContent = layout.name;
    select.appendChild(option);
  });
  if (state.layouts.length) {
    select.value = state.layouts[0].id;
    applyLayout(state.layouts[0]);
  }
}

function applyLayout(layout) {
  const params = layout.params;
  state.iconPosition = { ...params.icon };
  state.iconScale = params.icon.scale;
  state.textPosition = { x: params.text.x, y: params.text.y };
  state.textSize = params.text.font_size;
  document.getElementById("icon-scale").value = state.iconScale;
  document.getElementById("text-size").value = state.textSize;
  renderPreview();
}

async function loadIcons() {
  state.icons = await fetchJSON("/api/icons");
  const grid = document.getElementById("icon-grid");
  grid.innerHTML = "";
  state.icons.forEach((icon) => {
    const item = document.createElement("div");
    item.className = "icon-item";
    if (state.selectedIcon && state.selectedIcon.id === icon.id) {
      item.classList.add("selected");
    }
    const img = document.createElement("img");
    img.src = icon.preview_url;
    img.alt = icon.name;
    const label = document.createElement("div");
    label.textContent = icon.name;
    item.appendChild(img);
    item.appendChild(label);
    item.addEventListener("click", () => {
      state.selectedIcon = icon;
      refreshIcons();
      renderPreview();
    });
    grid.appendChild(item);
  });
}

function refreshIcons() {
  const items = document.querySelectorAll(".icon-item");
  items.forEach((item, index) => {
    if (state.selectedIcon && state.icons[index].id === state.selectedIcon.id) {
      item.classList.add("selected");
    } else {
      item.classList.remove("selected");
    }
  });
}

async function renderPreview() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  drawRoundedRect(0, 0, 450, 450, 30);
  ctx.clip();
  ctx.fillStyle = state.selectedColor;
  ctx.fillRect(0, 0, 450, 450);
  ctx.restore();

  if (state.selectedIcon) {
    const img = new Image();
    img.src = state.selectedIcon.preview_url;
    await img.decode();
    const size = 450 * state.iconScale;
    ctx.drawImage(
      img,
      state.iconPosition.x - size / 2,
      state.iconPosition.y - size / 2,
      size,
      size
    );
  }

  ctx.fillStyle = "white";
  ctx.font = `600 ${state.textSize}px Inter, Arial, sans-serif`;
  ctx.textBaseline = "top";
  const text = state.text;
  ctx.fillText(text, state.textPosition.x, state.textPosition.y);
}

function attachControls() {
  document.getElementById("text-input").addEventListener("input", (event) => {
    state.text = event.target.value;
    renderPreview();
  });

  document.getElementById("color-select").addEventListener("change", (event) => {
    state.selectedColor = event.target.value;
    document.getElementById("color-custom").value = state.selectedColor;
    renderPreview();
  });

  document.getElementById("color-custom").addEventListener("input", (event) => {
    state.selectedColor = event.target.value;
    renderPreview();
  });

  document.getElementById("icon-scale").addEventListener("input", (event) => {
    state.iconScale = parseFloat(event.target.value);
    renderPreview();
  });

  document.getElementById("text-size").addEventListener("input", (event) => {
    state.textSize = parseInt(event.target.value, 10);
    renderPreview();
  });

  document.getElementById("icon-upload").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const name = file.name.replace(/\.[^/.]+$/, "");
    const form = new FormData();
    form.append("file", file);
    form.append("name", name);
    try {
      await fetchJSON("/api/icons", { method: "POST", body: form });
      await loadIcons();
    } catch (error) {
      alert(error.message);
    }
  });

  document.getElementById("layout-select").addEventListener("change", (event) => {
    const selected = state.layouts.find((layout) => layout.id === event.target.value);
    if (!selected) return;
    applyLayout(selected);
  });

  document.getElementById("save-layout").addEventListener("click", async () => {
    const name = prompt("Name für Layout-Preset?");
    if (!name) return;
    const params = currentLayoutParams();
    await fetchJSON("/api/layout-presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, params }),
    });
    await loadLayouts();
  });

  document.getElementById("render-btn").addEventListener("click", async () => {
    try {
      const payload = {
        name: state.text || "kachel",
        icon_id: state.selectedIcon ? state.selectedIcon.id : null,
        color_hex: state.selectedColor,
        text: state.text,
        layout_params: currentLayoutParams(),
      };
      const response = await fetchJSON("/api/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await loadHistory();
      window.open(`${response.download_url}?download=1`, "_blank");
    } catch (error) {
      alert(error.message);
    }
  });

  canvas.addEventListener("mousedown", (event) => {
    const { offsetX, offsetY } = event;
    const iconSize = 450 * state.iconScale;
    if (
      state.selectedIcon &&
      offsetX >= state.iconPosition.x - iconSize / 2 &&
      offsetX <= state.iconPosition.x + iconSize / 2 &&
      offsetY >= state.iconPosition.y - iconSize / 2 &&
      offsetY <= state.iconPosition.y + iconSize / 2
    ) {
      state.dragging = "icon";
      return;
    }
    ctx.font = `600 ${state.textSize}px Inter, Arial, sans-serif`;
    const textWidth = ctx.measureText(state.text).width;
    if (
      offsetX >= state.textPosition.x &&
      offsetX <= state.textPosition.x + textWidth &&
      offsetY >= state.textPosition.y &&
      offsetY <= state.textPosition.y + state.textSize
    ) {
      state.dragging = "text";
    }
  });

  canvas.addEventListener("mousemove", (event) => {
    if (!state.dragging) return;
    if (state.dragging === "icon") {
      state.iconPosition = { x: event.offsetX, y: event.offsetY };
    }
    if (state.dragging === "text") {
      state.textPosition = { x: event.offsetX, y: event.offsetY };
    }
    renderPreview();
  });

  canvas.addEventListener("mouseup", () => {
    state.dragging = null;
  });

  canvas.addEventListener("mouseleave", () => {
    state.dragging = null;
  });
}

function currentLayoutParams() {
  return {
    name: "Custom",
    corner_radius_px: 30,
    icon: { x: state.iconPosition.x, y: state.iconPosition.y, scale: state.iconScale },
    text: {
      x: state.textPosition.x,
      y: state.textPosition.y,
      font_size: state.textSize,
      font_weight: "semibold",
      align: "left",
    },
  };
}

async function loadHistory() {
  const data = await fetchJSON("/api/renders");
  const grid = document.getElementById("history");
  grid.innerHTML = "";
  data.forEach((render) => {
    const card = document.createElement("div");
    card.className = "history-card";
    const img = document.createElement("img");
    img.src = render.download_url;
    img.alt = render.name;
    const label = document.createElement("div");
    label.textContent = render.name;
    const link = document.createElement("a");
    link.href = `${render.download_url}?download=1`;
    link.textContent = "Download";
    card.appendChild(img);
    card.appendChild(label);
    card.appendChild(link);
    grid.appendChild(card);
  });
}

async function init() {
  attachControls();
  await loadColors();
  await loadLayouts();
  await loadIcons();
  await loadHistory();
  renderPreview();
}

init();
