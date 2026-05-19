// Renderer process — all UI logic

// ── State ──────────────────────────────────────────────────────────────────

type Page = "onboarding-choice" | "onboarding-server" | "onboarding-join" | "main" | "game-config";

interface AppState {
  page: Page;
  port: number;
  token: string;
  editSlug: string | null;
  serverOnline: boolean;
}

const state: AppState = {
  page: "onboarding-choice",
  port: 8765,
  token: "",
  editSlug: null,
  serverOnline: false,
};

// ── API helpers ────────────────────────────────────────────────────────────

async function api(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  return fetch(`http://localhost:${state.port}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

async function apiJSON<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await api(method, path, body);
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`);
  return r.json() as Promise<T>;
}

// ── Polling ────────────────────────────────────────────────────────────────

function startHealthPoll(): void {
  setInterval(async () => {
    try {
      const r = await fetch(`http://localhost:${state.port}/health`);
      const online = r.ok;
      if (online !== state.serverOnline) {
        state.serverOnline = online;
        updateStatusBar();
      }
    } catch {
      if (state.serverOnline) {
        state.serverOnline = false;
        updateStatusBar();
      }
    }
  }, 5000);
}

function updateStatusBar(): void {
  const bar = document.getElementById("status-bar");
  if (!bar) return;
  bar.innerHTML = state.serverOnline
    ? `<span class="dot dot-green"></span> Server running`
    : `<span class="dot dot-grey"></span> Server offline — is your gaming PC on?`;
}

// ── Router ─────────────────────────────────────────────────────────────────

function navigate(page: Page, params?: { editSlug?: string }): void {
  state.page = page;
  if (params?.editSlug !== undefined) state.editSlug = params.editSlug;
  render();
}

function render(): void {
  const app = document.getElementById("app")!;
  app.innerHTML = "";

  switch (state.page) {
    case "onboarding-choice": app.appendChild(renderOnboardingChoice()); break;
    case "onboarding-server": app.appendChild(renderOnboardingServer()); break;
    case "onboarding-join":   app.appendChild(renderOnboardingJoin());   break;
    case "main":              app.appendChild(renderMain());              break;
    case "game-config":       app.appendChild(renderGameConfig());        break;
  }
}

// ── Onboarding: choice ─────────────────────────────────────────────────────

function renderOnboardingChoice(): HTMLElement {
  const el = div("onboarding");
  el.innerHTML = `
    <h1>Welcome to EmuSync</h1>
    <p>Keep your save files in sync across devices on your home network — no cloud, no accounts.</p>
    <div class="card">
      <h2>Is this your first device?</h2>
      <p style="color:var(--muted);font-size:13px;margin-bottom:8px">
        The "server" machine is your gaming PC. The Steam Deck (or second device) joins it.
      </p>
      <button class="btn-primary" id="btn-yes">Yes — set up as server</button>
      <button class="btn-secondary" id="btn-no" style="margin-top:8px">No — join an existing server</button>
    </div>
  `;
  el.querySelector("#btn-yes")!.addEventListener("click", () => navigate("onboarding-server"));
  el.querySelector("#btn-no")!.addEventListener("click", () => navigate("onboarding-join"));
  return el;
}

// ── Onboarding: server setup ───────────────────────────────────────────────

function renderOnboardingServer(): HTMLElement {
  const el = div("onboarding");
  el.innerHTML = `
    <h1>Server Setup</h1>
    <div class="card" id="server-card">
      <h2>Starting server...</h2>
      <div class="spinner" style="margin:16px auto"></div>
    </div>
  `;

  (async () => {
    try {
      const r = await api("POST", "/setup/init-server");
      const data = await r.json() as { master_token: string };
      const card = el.querySelector("#server-card")!;
      card.innerHTML = `
        <h2>Server is running</h2>
        <p style="color:var(--muted);font-size:13px">Show this token to the other device when pairing:</p>
        <div class="token-box">${data.master_token}</div>
        <p style="color:var(--muted);font-size:12px;margin-top:4px">This token is valid until the server restarts.</p>
        <button class="btn-primary" id="btn-continue" style="margin-top:8px">Continue</button>
      `;

      // Self-pair the server machine
      const setupState = await apiJSON<{ device_id: string; device_name: string }>("GET", "/setup-state");
      const pairRes = await apiJSON<{ token: string }>("POST", "/pair", {
        master_token: data.master_token,
        device_id: setupState.device_id,
        device_name: setupState.device_name,
      });
      state.token = pairRes.token;

      card.querySelector("#btn-continue")!.addEventListener("click", () => {
        startHealthPoll();
        navigate("main");
      });
    } catch (e) {
      el.querySelector("#server-card")!.innerHTML = `
        <h2>Error</h2>
        <p style="color:var(--red)">${e}</p>
        <button class="btn-secondary" id="btn-back">Back</button>
      `;
      el.querySelector("#btn-back")!.addEventListener("click", () => navigate("onboarding-choice"));
    }
  })();

  return el;
}

// ── Onboarding: join server ────────────────────────────────────────────────

function renderOnboardingJoin(): HTMLElement {
  const el = div("onboarding");
  el.innerHTML = `
    <h1>Join a Server</h1>
    <div class="card" id="join-card">
      <h2>Scanning LAN...</h2>
      <div class="spinner" style="margin:16px auto"></div>
    </div>
  `;

  (async () => {
    const card = el.querySelector("#join-card")!;
    try {
      const servers = await apiJSON<Array<{ name: string; host: string; port: number }>>("GET", "/setup/discover");
      if (servers.length === 0) {
        card.innerHTML = `
          <h2>No servers found</h2>
          <p>Make sure EmuSync is running on your gaming PC.</p>
          <button class="btn-secondary" id="btn-retry">Scan again</button>
          <button class="btn-ghost" id="btn-back" style="margin-top:8px">Back</button>
        `;
        card.querySelector("#btn-retry")!.addEventListener("click", () => navigate("onboarding-join"));
        card.querySelector("#btn-back")!.addEventListener("click", () => navigate("onboarding-choice"));
        return;
      }

      card.innerHTML = `
        <h2>Found ${servers.length} server${servers.length > 1 ? "s" : ""}</h2>
        <div class="server-list" id="server-list"></div>
        <div class="field" style="margin-top:16px">
          <label>Pairing token (shown on the server)</label>
          <input type="text" id="pair-token" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
          <div class="error-text" id="pair-error"></div>
        </div>
        <button class="btn-ghost" id="btn-back">Back</button>
      `;

      let selectedServer = servers[0];
      const listEl = card.querySelector("#server-list")!;

      function renderServers(): void {
        listEl.innerHTML = "";
        servers.forEach((s) => {
          const item = div("server-item");
          item.innerHTML = `
            <span>${s.name} <span style="color:var(--muted);font-size:12px">${s.host}:${s.port}</span></span>
            <button class="${s === selectedServer ? "btn-primary" : "btn-secondary"}" style="font-size:12px;padding:4px 12px">
              ${s === selectedServer ? "Selected" : "Select"}
            </button>
          `;
          item.querySelector("button")!.addEventListener("click", () => {
            selectedServer = s;
            renderServers();
          });
          listEl.appendChild(item);
        });

        // Add pair button after server list is populated
        const existing = card.querySelector("#btn-pair");
        if (!existing) {
          const pairBtn = document.createElement("button");
          pairBtn.id = "btn-pair";
          pairBtn.className = "btn-primary";
          pairBtn.style.marginTop = "8px";
          pairBtn.textContent = "Pair";
          card.querySelector(".field")!.insertAdjacentElement("afterend", pairBtn);
          pairBtn.addEventListener("click", async () => {
            const tokenInput = card.querySelector<HTMLInputElement>("#pair-token")!;
            const errEl = card.querySelector("#pair-error")!;
            const masterToken = tokenInput.value.trim();
            if (!masterToken) { errEl.textContent = "Enter the pairing token."; return; }
            errEl.textContent = "";
            pairBtn.textContent = "Pairing...";
            pairBtn.setAttribute("disabled", "true");
            try {
              const setupState = await apiJSON<{ device_id: string; device_name: string }>(
                "GET", "/setup-state"
              );
              const res = await fetch(`http://${selectedServer.host}:${selectedServer.port}/pair`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  master_token: masterToken,
                  device_id: setupState.device_id,
                  device_name: setupState.device_name,
                }),
              });
              if (!res.ok) throw new Error(await res.text());
              const { token } = await res.json() as { token: string };
              state.token = token;
              state.port = selectedServer.port;
              startHealthPoll();
              navigate("main");
            } catch (e) {
              errEl.textContent = `Pairing failed: ${e}`;
              pairBtn.textContent = "Pair";
              pairBtn.removeAttribute("disabled");
            }
          });
        }
      }

      renderServers();
      card.querySelector("#btn-back")!.addEventListener("click", () => navigate("onboarding-choice"));
    } catch (e) {
      card.innerHTML = `
        <h2>Scan failed</h2>
        <p style="color:var(--red)">${e}</p>
        <button class="btn-secondary" id="btn-back">Back</button>
      `;
      card.querySelector("#btn-back")!.addEventListener("click", () => navigate("onboarding-choice"));
    }
  })();

  return el;
}

// ── Main view ──────────────────────────────────────────────────────────────

function renderMain(): HTMLElement {
  const el = div("main-layout");

  // Status bar
  const bar = div("status-bar");
  bar.id = "status-bar";
  bar.innerHTML = `<span class="dot dot-grey"></span> Checking server...`;
  el.appendChild(bar);

  // Toolbar
  const toolbar = div("toolbar");
  toolbar.innerHTML = `
    <h1>EmuSync</h1>
    <button class="btn-primary" id="btn-add">+ Add game</button>
  `;
  toolbar.querySelector("#btn-add")!.addEventListener("click", () => {
    state.editSlug = null;
    navigate("game-config");
  });
  el.appendChild(toolbar);

  // Game list container
  const listWrap = div("game-list");
  listWrap.id = "game-list";
  listWrap.innerHTML = `<div class="spinner" style="margin:40px auto"></div>`;
  el.appendChild(listWrap);

  // Load games
  (async () => {
    try {
      // Check server health and update token from backend config if needed
      const setupRes = await apiJSON<{ configured: boolean; token?: string }>("GET", "/setup-state");
      if (!state.token && setupRes.configured) {
        // Token may already be in the backend config — load via health check
      }

      const healthR = await fetch(`http://localhost:${state.port}/health`);
      state.serverOnline = healthR.ok;
      updateStatusBar();

      const games = await apiJSON<Array<{ slug: string; name: string; created_at: number }>>("GET", "/games");
      renderGameList(listWrap, games);
    } catch (e) {
      listWrap.innerHTML = `
        <div class="empty-state">
          <p>Could not load games: ${e}</p>
        </div>
      `;
    }
  })();

  startHealthPoll();
  return el;
}

interface Game {
  slug: string;
  name: string;
  created_at: number;
}

function renderGameList(container: HTMLElement, games: Game[]): void {
  container.innerHTML = "";
  if (games.length === 0) {
    const empty = div("empty-state");
    empty.innerHTML = `<p>No games yet. Click <strong>+ Add game</strong> to get started.</p>`;
    container.appendChild(empty);
    return;
  }
  games.forEach((g) => {
    const row = div("game-row");
    row.innerHTML = `
      <div>
        <div class="game-name">${g.name}</div>
        <div class="game-meta">Slug: ${g.slug}</div>
      </div>
      <div class="game-actions">
        <button class="btn-icon" title="Play" data-action="play">&#9654;</button>
        <button class="btn-icon" title="Settings" data-action="edit">&#9881;</button>
        <button class="btn-danger" title="Remove" data-action="remove">&#128465;</button>
      </div>
    `;
    row.querySelector<HTMLElement>('[data-action="play"]')!.addEventListener("click", () =>
      showPlayModal(g)
    );
    row.querySelector<HTMLElement>('[data-action="edit"]')!.addEventListener("click", () =>
      navigate("game-config", { editSlug: g.slug })
    );
    row.querySelector<HTMLElement>('[data-action="remove"]')!.addEventListener("click", () =>
      confirmRemove(g)
    );
    container.appendChild(row);
  });
}

function showPlayModal(g: Game): void {
  const overlay = div("modal-overlay");
  overlay.innerHTML = `
    <div class="modal">
      <h3>Play ${g.name}</h3>
      <p>Use the CLI to launch with sync:<br><code style="font-family:monospace;font-size:12px;color:var(--green)">emusync run --game ${g.slug} -- &lt;emulator command&gt;</code></p>
      <p>Add that to your Steam launch options to sync automatically.</p>
      <div class="modal-actions">
        <button class="btn-primary" id="btn-close">Got it</button>
      </div>
    </div>
  `;
  overlay.querySelector("#btn-close")!.addEventListener("click", () => overlay.remove());
  document.body.appendChild(overlay);
}

function confirmRemove(g: Game): void {
  const overlay = div("modal-overlay");
  overlay.innerHTML = `
    <div class="modal">
      <h3>Remove game</h3>
      <p>Remove <strong>${g.name}</strong> from EmuSync? The save file on your device will <strong>not</strong> be deleted.</p>
      <div class="modal-actions">
        <button class="btn-ghost" id="btn-cancel">Cancel</button>
        <button class="btn-danger" id="btn-confirm" style="background:var(--red);color:#fff;padding:8px 16px">Remove</button>
      </div>
    </div>
  `;
  overlay.querySelector("#btn-cancel")!.addEventListener("click", () => overlay.remove());
  overlay.querySelector("#btn-confirm")!.addEventListener("click", async () => {
    overlay.remove();
    await api("DELETE", `/games/${g.slug}`);
    navigate("main");
  });
  document.body.appendChild(overlay);
}

// ── Game config page ───────────────────────────────────────────────────────

function renderGameConfig(): HTMLElement {
  const isEdit = state.editSlug !== null;
  const el = div("");
  el.style.cssText = "flex:1;display:flex;flex-direction:column;overflow:hidden;";

  // Status bar passthrough
  const bar = div("status-bar");
  bar.id = "status-bar";
  updateStatusBar();
  el.appendChild(bar);

  const page = div("config-page");
  page.innerHTML = `
    <div class="page-header">
      <button class="btn-ghost" id="btn-back">&#8592; Back</button>
      ${isEdit ? `<button class="btn-primary" id="btn-play-top">&#9654; Play</button>` : ""}
    </div>
    <h2>${isEdit ? "Edit Game" : "Add Game"}</h2>
    <br/>

    <div class="field">
      <label>Game Name *</label>
      <input type="text" id="f-name" placeholder="The Legend of Zelda: BOTW" />
      <div class="error-text" id="err-name"></div>
    </div>

    <div class="field">
      <label>ROM file</label>
      <div class="input-row">
        <input type="text" id="f-rom" placeholder="/path/to/game.rom" />
        <button class="btn-ghost" id="btn-pick-rom" style="white-space:nowrap">Browse</button>
      </div>
    </div>

    <div class="field">
      <label>Save file location *</label>
      <div class="input-row">
        <input type="text" id="f-save" placeholder="/path/to/save.sav" />
        <button class="btn-ghost" id="btn-pick-save" style="white-space:nowrap">Browse</button>
      </div>
      <div class="error-text" id="err-save"></div>
    </div>

    <div class="field">
      <label>Launch command (optional)</label>
      <input type="text" id="f-cmd" placeholder="retroarch -L snes.so %ROM%" />
    </div>

    <div class="error-text" id="err-global" style="margin-bottom:12px"></div>
    <button class="btn-primary" id="btn-save">Save</button>
  `;

  page.querySelector("#btn-back")!.addEventListener("click", () => navigate("main"));

  if (isEdit) {
    page.querySelector("#btn-play-top")?.addEventListener("click", async () => {
      const g = await apiJSON<{ name: string }>("GET", `/games/${state.editSlug}`);
      showPlayModal({ slug: state.editSlug!, name: g.name, created_at: 0 });
    });
  }

  page.querySelector("#btn-pick-rom")!.addEventListener("click", async () => {
    const f = await window.emusync.openFileDialog();
    if (f) (page.querySelector<HTMLInputElement>("#f-rom")!).value = f;
  });

  page.querySelector("#btn-pick-save")!.addEventListener("click", async () => {
    const f = await window.emusync.openFileDialog();
    if (f) (page.querySelector<HTMLInputElement>("#f-save")!).value = f;
  });

  // Load existing data when editing
  if (isEdit) {
    (async () => {
      try {
        const g = await apiJSON<{ name: string }>("GET", `/games/${state.editSlug}`);
        (page.querySelector<HTMLInputElement>("#f-name")!).value = g.name;
        const gd = await apiJSON<{ rom_path: string; save_path: string; launch_command: string }>(
          "GET", `/games/${state.editSlug}/device`
        ).catch(() => null);
        if (gd) {
          (page.querySelector<HTMLInputElement>("#f-rom")!).value = gd.rom_path;
          (page.querySelector<HTMLInputElement>("#f-save")!).value = gd.save_path;
          (page.querySelector<HTMLInputElement>("#f-cmd")!).value = gd.launch_command;
        }
      } catch { /* ignore */ }
    })();
  }

  page.querySelector("#btn-save")!.addEventListener("click", async () => {
    const name = (page.querySelector<HTMLInputElement>("#f-name")!).value.trim();
    const rom  = (page.querySelector<HTMLInputElement>("#f-rom")!).value.trim();
    const savePath = (page.querySelector<HTMLInputElement>("#f-save")!).value.trim();
    const cmd  = (page.querySelector<HTMLInputElement>("#f-cmd")!).value.trim();

    page.querySelector("#err-name")!.textContent = "";
    page.querySelector("#err-save")!.textContent = "";
    page.querySelector("#err-global")!.textContent = "";

    let valid = true;
    if (!name) { page.querySelector("#err-name")!.textContent = "Game name is required."; valid = false; }
    if (!savePath) { page.querySelector("#err-save")!.textContent = "Save file path is required."; valid = false; }
    if (!valid) return;

    const saveBtn = page.querySelector<HTMLButtonElement>("#btn-save")!;
    saveBtn.textContent = "Saving...";
    saveBtn.setAttribute("disabled", "true");

    try {
      if (isEdit) {
        await api("PUT", `/games/${state.editSlug}`, { name });
        await api("PUT", `/games/${state.editSlug}/device`, {
          rom_path: rom, save_path: savePath, launch_command: cmd,
        });
      } else {
        const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
        await api("POST", "/games", { slug, name });
        await api("PUT", `/games/${slug}/device`, {
          rom_path: rom, save_path: savePath, launch_command: cmd,
        });
      }
      navigate("main");
    } catch (e) {
      page.querySelector("#err-global")!.textContent = `Save failed: ${e}`;
      saveBtn.textContent = "Save";
      saveBtn.removeAttribute("disabled");
    }
  });

  el.appendChild(page);
  return el;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function div(className: string): HTMLDivElement {
  const el = document.createElement("div");
  if (className) el.className = className;
  return el;
}

// ── Boot ───────────────────────────────────────────────────────────────────

async function boot(): Promise<void> {
  state.port = await window.emusync.getBackendPort();

  // Wait briefly for backend to be ready
  for (let i = 0; i < 10; i++) {
    try {
      await fetch(`http://localhost:${state.port}/health`);
      break;
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
  }

  const { configExists } = await window.emusync.checkConfig();

  if (configExists) {
    // Try to read token from setup-state; in a real build the backend
    // would expose the stored token — for now we ask user to re-pair on
    // first GUI open if token unknown
    try {
      const s = await apiJSON<{ configured: boolean }>("GET", "/setup-state");
      if (s.configured) {
        // Token is managed by the backend; we need it surfaced via an endpoint
        // For the server machine, self-pair to get a GUI token
        const setup = await apiJSON<{
          is_server: boolean; device_id: string; device_name: string; configured: boolean
        }>("GET", "/setup-state");

        if (setup.is_server && !state.token) {
          // Request a fresh token by re-initing (idempotent on server side)
          const initRes = await api("POST", "/setup/init-server");
          const { master_token } = await initRes.json() as { master_token: string };
          const pairRes = await apiJSON<{ token: string }>("POST", "/pair", {
            master_token,
            device_id: setup.device_id,
            device_name: setup.device_name,
          });
          state.token = pairRes.token;
        }

        startHealthPoll();
        navigate("main");
        return;
      }
    } catch { /* fall through to onboarding */ }
  }

  navigate("onboarding-choice");
}

boot();
