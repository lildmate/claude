"use strict";

(function () {
  // -- token, api ---------------------------------------------------------------
  const TOKEN_KEY = "proteus-token";
  const hashToken = /^#t=([A-Za-z0-9_-]+)/.exec(location.hash);
  if (hashToken) {
    try { sessionStorage.setItem(TOKEN_KEY, hashToken[1]); } catch (e) { /* private mode */ }
  }
  let token = hashToken ? hashToken[1] : "";
  if (!token) {
    try { token = sessionStorage.getItem(TOKEN_KEY) || ""; } catch (e) { token = ""; }
  }
  if (hashToken) history.replaceState(null, "", "#/home");

  let offline = false;

  async function api(path, body) {
    const options = { headers: { "X-Proteus-Token": token }, cache: "no-store" };
    if (body !== undefined) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(path, options);
    } catch (e) {
      setOffline(true);
      throw e;
    }
    setOffline(false);
    if (!response.ok) throw new Error(path + ": " + response.status);
    return response.json();
  }

  function img(src) {
    return src ? src + (src.indexOf("?") >= 0 ? "&" : "?") + "t=" + encodeURIComponent(token) : "";
  }

  // -- dom helpers ----------------------------------------------------------------
  function h(tag, attrs) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else if (key.startsWith("on")) el.addEventListener(key.slice(2).toLowerCase(), value);
      else el.setAttribute(key, value === true ? "" : value);
    }
    for (let i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }
  function append(el, child) {
    if (child === undefined || child === null || child === false) return;
    if (Array.isArray(child)) child.forEach((c) => append(el, c));
    else el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  function picture(src, cls, alt) {
    const el = h("img", { class: cls, alt: alt || "", loading: "lazy", decoding: "async" });
    if (src) el.src = img(src);
    el.addEventListener("error", () => { el.removeAttribute("src"); });
    return el;
  }
  const STAR_PATH = "M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z";
  function star(filled) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("fill", filled ? "currentColor" : "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.8");
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", STAR_PATH);
    svg.appendChild(path);
    return svg;
  }

  let toastTimer = null;
  function toast(text) {
    const el = document.getElementById("toast");
    el.textContent = text;
    el.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.add("hidden"), 2600);
  }

  // -- texts ------------------------------------------------------------------------
  const PHASES = {
    None: "Nincs játékban", Lobby: "Lobby", Matchmaking: "Sorban áll", CheckedIntoTournament: "Clash",
    ReadyCheck: "Meccs elfogadása", ChampSelect: "Champion select", GameStart: "Meccs indul",
    InProgress: "Meccsben", Reconnect: "Visszacsatlakozás", WaitingForStats: "Meccs vége",
    PreEndOfGame: "Meccs vége", EndOfGame: "Meccs vége",
  };
  function ago(ms) {
    if (!ms) return "";
    const minutes = Math.floor((Date.now() - ms) / 60000);
    if (minutes < 1) return "most";
    if (minutes < 60) return minutes + " perce";
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + " órája";
    const days = Math.floor(hours / 24);
    return days === 1 ? "tegnap" : days + " napja";
  }
  function minutes(seconds) { return Math.round((seconds || 0) / 60) + " perc"; }
  function rankText(r) {
    if (!r || !r.tier) return "Nincs rangja";
    return r.tier + (r.division ? " " + r.division : "") + " · " + r.lp + " LP";
  }

  // -- status (sidebar) -------------------------------------------------------------
  let lastStatus = null;
  async function refreshStatus() {
    try {
      const s = await api("/api/status");
      lastStatus = s;
      document.getElementById("version").textContent = "v" + s.version;
      const on = s.client.connected;
      document.getElementById("client-dot").classList.toggle("on", on);
      document.getElementById("client-text").textContent = on ? "League kliens kapcsolódva" : "A League kliens nem fut";
      document.getElementById("client-phase").textContent = on ? (PHASES[s.client.phase] || s.client.phase || "") : "";
    } catch (e) { /* offline banner shows it */ }
  }
  function setOffline(value) {
    if (offline === value) return;
    offline = value;
    if (offline) {
      document.getElementById("client-dot").classList.remove("on");
      document.getElementById("client-text").textContent = "A Proteus nem fut";
      document.getElementById("client-phase").textContent = "Indítsd el újra a Proteust";
    }
  }

  // -- router ------------------------------------------------------------------------
  const main = document.getElementById("main");
  let renderId = 0;

  function route() {
    const m = /^#\/([a-z]+)(?:\/(\d+))?(?:\/([A-Za-z]+))?/.exec(location.hash) || [null, "home"];
    return { page: m[1], id: m[2] ? parseInt(m[2], 10) : null, sub: m[3] || null };
  }
  async function render() {
    const id = ++renderId;
    const r = route();
    document.querySelectorAll(".nav").forEach((n) => {
      const active = n.dataset.route === (r.page === "build" ? "tier" : r.page);
      n.classList.toggle("active", active);
      if (active) n.setAttribute("aria-current", "page"); else n.removeAttribute("aria-current");
    });
    const pages = { home: renderHome, skins: renderSkins, mods: renderMods, tier: renderTier, build: renderBuild, patch: renderPatch, profile: renderProfile, settings: renderSettings };
    const fn = pages[r.page] || renderHome;
    let content;
    try {
      content = await fn(r);
    } catch (e) {
      content = page("Hiba", h("div", { class: "card empty", text: offline
        ? "A Proteus nem fut. Indítsd el újra, és frissítsd ezt az ablakot."
        : "Nem sikerült betölteni. Próbáld újra egy kicsit később." }));
    }
    if (id !== renderId) return; // a newer navigation won
    const samePage = main.dataset.page === location.hash;
    main.replaceChildren(content);
    main.dataset.page = location.hash;
    if (!samePage) window.scrollTo(0, 0);
  }
  function page(title, ...children) {
    return h("div", { class: "page" }, h("div", { class: "page-head" }, h("h1", { text: title })), children);
  }
  document.querySelectorAll(".nav").forEach((n) => n.addEventListener("click", () => { location.hash = "#/" + n.dataset.route; }));
  window.addEventListener("hashchange", render);

  // -- home --------------------------------------------------------------------------
  async function renderHome() {
    const [status, favorites, profile] = await Promise.all([
      api("/api/status"), api("/api/favorites"), api("/api/profile").catch(() => ({ connected: false })),
    ]);
    const name = profile.connected && profile.summoner ? profile.summoner.name : "";
    const client = status.client;
    const cards = h("div", { class: "cards" },
      h("div", { class: "card" }, h("div", { class: "stat-label", text: "Proteus" }),
        h("div", { class: "stat-value", text: "Fut" }), h("div", { class: "stat-sub", text: "v" + status.version })),
      h("div", { class: "card" }, h("div", { class: "stat-label", text: "League kliens" }),
        h("div", { class: "stat-value", text: client.connected ? (PHASES[client.phase] || "Kapcsolódva") : "Nem fut" }),
        h("div", { class: "stat-sub", text: client.connected ? "Kapcsolódva" : "Indítsd el a League-et" })),
      h("div", { class: "card" }, h("div", { class: "stat-label", text: "Ranked Solo/Duo" }),
        h("div", { class: "stat-value gold", text: profile.connected && profile.ranked ? rankText(profile.ranked.solo) : "–" }),
        h("div", { class: "stat-sub", text: profile.connected && profile.ranked && profile.ranked.solo && profile.ranked.solo.winrate !== null
          ? profile.ranked.solo.winrate + "% winrate" : "" })));

    const favCard = h("div", { class: "card" },
      h("div", { class: "section-head" }, h("h2", { text: "Kedvenc skinjeid" }),
        h("button", { class: "btn", text: "Skin könyvtár", onclick: () => { location.hash = "#/skins"; } })),
      favorites.skins.length
        ? h("div", { class: "fav-row" }, favorites.skins.map((s) => h("button", {
            class: "fav", onclick: () => { location.hash = "#/skins/" + s.championId; },
            "aria-label": s.name },
            picture(s.tile, "", ""), h("div", { text: s.name }))))
        : h("div", { class: "muted", text: "Még nincs kedvenc skined. A Skinek oldalon a csillaggal jelölheted meg őket." }));

    const recent = h("div", { class: "card" },
      h("div", { class: "section-head" }, h("h2", { text: "Legutóbbi meccsek" }),
        h("button", { class: "btn", text: "Profil", onclick: () => { location.hash = "#/profile"; } })),
      profile.connected
        ? matchTable(profile.matches.slice(0, 5))
        : h("div", { class: "muted", text: "Indítsd el a League klienst, és itt megjelennek a meccseid." }));

    return page(name ? "Szia, " + name + "!" : "Proteus", cards, favCard, recent);
  }

  // -- skins -------------------------------------------------------------------------
  let championsCache = null;
  let skinFilter = "all";
  let champQuery = "";

  async function renderSkins(r) {
    if (!championsCache) championsCache = (await api("/api/champions")).champions;
    const champions = championsCache;
    if (!champions.length) {
      return page("Skinek", h("div", { class: "card empty", text: "Nem sikerült betölteni a championöket. Ellenőrizd az internetkapcsolatot, vagy indítsd el a League klienst." }));
    }
    let champId = r.id;
    if (!champId) {
      try { champId = parseInt(sessionStorage.getItem("proteus-champ") || "", 10) || null; } catch (e) { champId = null; }
    }
    if (!champId || !champions.some((c) => c.id === champId)) champId = champions[0].id;
    try { sessionStorage.setItem("proteus-champ", String(champId)); } catch (e) { /* ignore */ }

    const list = h("div", { class: "champ-list", role: "list" });
    function fillList() {
      const q = champQuery.trim().toLowerCase();
      list.replaceChildren(...champions.filter((c) => !q || c.name.toLowerCase().includes(q) || c.alias.toLowerCase().includes(q))
        .map((c) => h("button", {
          class: "champ" + (c.id === champId ? " on" : ""), role: "listitem",
          "aria-current": c.id === champId ? "true" : null,
          onclick: () => { location.hash = "#/skins/" + c.id; } },
          picture(c.icon, "", ""), h("span", { text: c.name }))));
    }
    fillList();
    const search = h("input", { class: "search", id: "champ-search", type: "search", placeholder: "pl. Ahri", value: champQuery,
      autocomplete: "off", oninput: (e) => { champQuery = e.target.value; fillList(); } });
    const panel = h("div", { class: "card champ-panel" },
      h("label", { class: "muted small", for: "champ-search", text: "Champion keresése" }), search, list);

    const champ = await api("/api/champions/" + champId);
    const right = h("div", { class: "skins-main" });
    const grid = h("div", { class: "skin-grid" });

    function fillGrid() {
      const skins = champ.skins.filter((s) => skinFilter === "all"
        || (skinFilter === "owned" && s.owned) || (skinFilter === "unowned" && !s.owned) || (skinFilter === "fav" && s.favorite));
      if (!skins.length) {
        grid.replaceChildren(h("div", { class: "muted", text: skinFilter === "fav"
          ? "Ennél a championnél még nincs kedvenc skined." : "Nincs ilyen skin." }));
        return;
      }
      grid.replaceChildren(...skins.map(skinCard));
    }
    function skinCard(s) {
      const isNext = champ.nextSkinId === s.id || (s.isBase && !champ.nextSkinId);
      const tags = h("div", { class: "skin-tags" },
        s.rarity ? h("span", { class: "tag", text: s.rarity }) : null,
        s.legacy ? h("span", { class: "tag", text: "Legacy" }) : null,
        s.chromas ? h("span", { class: "tag", text: s.chromas + " chroma" }) : null,
        s.owned && !s.isBase ? h("span", { class: "tag owned", text: "Megvan" }) : null,
        isNext ? h("span", { class: "tag next", text: "Következő meccsen" }) : null);
      let action;
      if (s.owned && !s.isBase) {
        action = h("button", { class: "btn", disabled: true, text: "A kliensben válaszd ki" });
      } else if (isNext) {
        action = h("button", { class: "btn set", disabled: true, text: "Beállítva" });
      } else {
        action = h("button", { class: "btn primary", text: s.isBase ? "Alap skin legyen" : "Következő meccsre",
          onclick: async (e) => {
            e.currentTarget.disabled = true;
            try {
              const res = await api("/api/next-skin", { championId: champ.id, skinId: s.isBase ? null : s.id });
              champ.nextSkinId = res.nextSkinId;
              toast(s.isBase ? champ.name + ": alap skin" : champ.name + ": " + s.name + " a következő meccsen");
            } catch (err) { toast("Nem sikerült beállítani"); }
            fillGrid();
          } });
      }
      const favBtn = h("button", { class: "star", "aria-label": s.favorite ? s.name + " eltávolítása a kedvencek közül" : s.name + " hozzáadása a kedvencekhez",
        "aria-pressed": s.favorite ? "true" : "false",
        onclick: async () => {
          try {
            const res = await api("/api/favorite", { skinId: s.id, favorite: !s.favorite });
            s.favorite = res.favorite;
          } catch (err) { toast("Nem sikerült menteni"); }
          fillGrid();
        } }, star(s.favorite));
      return h("div", { class: "skin" + (isNext ? " next" : "") },
        picture(s.tile, "skin-img", ""),
        h("div", { class: "skin-body" }, h("div", { class: "skin-name", text: s.name }), tags),
        h("div", { class: "skin-actions" }, action),
        favBtn);
    }
    const chip = (key, label) => h("button", { class: "chip" + (skinFilter === key ? " on" : ""), "aria-pressed": skinFilter === key ? "true" : "false",
      text: label, onclick: () => { skinFilter = key; render(); } });
    right.append(
      h("div", { class: "champ-head" },
        h("div", {}, h("h2", { text: champ.name }), h("div", { class: "champ-title small", text: champ.title })),
        h("div", { class: "chips", role: "group", "aria-label": "Szűrő" },
          chip("all", "Mind"), chip("unowned", "Nincs meg"), chip("owned", "Megvan"), chip("fav", "Kedvencek"))),
      h("div", { class: "muted small", text: "Amit „Következő meccsre” állítasz, azt a Proteus magától felrakja, amikor ezzel a championnel zárolsz. Champion selectben még átválthatsz másikra." }),
      grid);
    fillGrid();

    const layout = h("div", { class: "skins-layout" }, panel, right);
    setTimeout(() => {
      const on = list.querySelector(".champ.on");
      if (on) on.scrollIntoView({ block: "nearest" });
    }, 0);
    return page("Skinek", layout);
  }

  // -- custom skins (mods) -----------------------------------------------------------
  const MOD_KINDS = [["skin", "Skin"], ["maps", "Pálya"], ["fonts", "Betűtípus"], ["announcers", "Bemondó"],
    ["ui", "Felület"], ["voiceover", "Hangok"], ["loading_screen", "Betöltőképernyő"], ["vfx", "Effektek"],
    ["sfx", "Hangeffektek"], ["others", "Egyéb"]];
  const MOD_SUFFIX = /\.(fantome|zip|modpkg)$/i;

  function guessChampion(fileName, champions) {
    const name = fileName.toLowerCase().replace(/[^a-z0-9]+/g, " ");
    let best = null;
    champions.forEach((c) => {
      [c.name, c.alias].forEach((n) => {
        const key = (n || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
        if (key && (" " + name + " ").includes(" " + key + " ") && (!best || key.length > best.key.length)) best = { key, id: c.id };
      });
    });
    return best ? best.id : null;
  }

  async function renderMods() {
    if (!championsCache) championsCache = (await api("/api/champions")).champions;
    const champions = championsCache;
    let file = null;
    let kind = "skin";
    let champ = null;
    let selected = new Set();

    const formBox = h("div", { class: "mod-form" });
    const listBox = h("div", {});
    const fileInput = h("input", { type: "file", accept: ".fantome,.zip,.modpkg", class: "hidden", id: "mod-file",
      onchange: (e) => { if (e.target.files[0]) pick(e.target.files[0]); } });
    const drop = h("div", { class: "drop", role: "button", tabindex: "0",
      "aria-label": "Mod fájl kiválasztása vagy behúzása",
      onclick: () => fileInput.click(),
      onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } } },
      h("div", { class: "drop-title", text: "Húzd ide a letöltött fájlt" }),
      h("div", { class: "muted small", text: ".fantome, .zip vagy .modpkg · vagy kattints a kiválasztáshoz" }));
    ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) pick(f); });

    function pick(f) {
      if (!MOD_SUFFIX.test(f.name)) { toast("Csak .fantome, .zip vagy .modpkg fájl tölthető fel"); return; }
      file = f;
      const guess = guessChampion(f.name, champions);
      if (guess) { kind = "skin"; selectChampion(guess); } else { champ = null; selected = new Set(); drawForm(); }
    }

    async function selectChampion(id) {
      champ = await api("/api/champions/" + id);
      selected = new Set([champ.skins[0].id]);
      drawForm();
      drawList();
    }

    async function drawList() {
      if (!champ) { listBox.replaceChildren(); return; }
      const data = await api("/api/mods?champion=" + champ.id);
      const names = Object.fromEntries(champ.skins.map((s) => [s.id, s.name]));
      listBox.replaceChildren(h("div", { class: "card" },
        h("h2", { text: champ.name + " saját skinjei" }),
        data.mods.length
          ? h("ul", { class: "mod-list" }, data.mods.map((m) => h("li", {},
              h("span", { class: "skin-name", text: m.name }),
              h("span", { class: "muted small", text: m.skinIds.map((id) => names[id] || id).join(", ") }))))
          : h("div", { class: "muted", text: "Ehhez a championhöz még nincs saját skined." })));
    }

    function drawForm() {
      if (!file) { formBox.replaceChildren(); return; }
      const kindSelect = h("select", { class: "search", id: "mod-kind", onchange: (e) => { kind = e.target.value; drawForm(); } },
        MOD_KINDS.map(([v, l]) => h("option", { value: v, text: l, selected: v === kind })));
      const parts = [
        h("div", { class: "mod-file" }, h("span", { class: "skin-name", text: file.name }),
          h("span", { class: "muted small", text: (file.size / 1048576).toFixed(1) + " MB" })),
        h("label", { for: "mod-kind", class: "muted small", text: "Mi ez?" }), kindSelect,
      ];
      if (kind === "skin") {
        const champSelect = h("select", { class: "search", id: "mod-champ",
          onchange: (e) => { if (e.target.value) selectChampion(parseInt(e.target.value, 10)); } },
          h("option", { value: "", text: "Válassz championt…" }),
          champions.map((c) => h("option", { value: c.id, text: c.name, selected: champ && c.id === champ.id })));
        parts.push(h("label", { for: "mod-champ", class: "muted small", text: "Melyik champion skinje?" }), champSelect);
        if (champ) {
          parts.push(h("div", { class: "muted small", text: "Melyik skin helyett jelenjen meg? (többet is választhatsz)" }),
            h("div", { class: "mod-skins" }, champ.skins.map((s) => h("button", {
              class: "mod-skin" + (selected.has(s.id) ? " on" : ""), "aria-pressed": selected.has(s.id) ? "true" : "false",
              onclick: () => { if (selected.has(s.id)) selected.delete(s.id); else selected.add(s.id); drawForm(); } },
              picture(s.tile, "", ""), h("span", { text: s.name })))));
        }
      }
      const ready = kind !== "skin" || (champ && selected.size);
      const progress = h("div", { class: "muted small", id: "mod-progress" });
      parts.push(h("div", { class: "row-actions" },
        h("button", { class: "btn primary", disabled: !ready, text: "Feltöltés", onclick: (e) => upload(e.currentTarget, progress) }),
        h("button", { class: "btn", text: "Mégse", onclick: () => { file = null; drawForm(); } })), progress);
      formBox.replaceChildren(h("div", { class: "card mod-card" }, parts));
    }

    function upload(button, progress) {
      button.disabled = true;
      const params = new URLSearchParams({ name: file.name, kind });
      if (kind === "skin") { params.set("champion", champ.id); params.set("skins", [...selected].join(",")); }
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/mods/upload?" + params.toString());
      xhr.setRequestHeader("X-Proteus-Token", token);
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) progress.textContent = "Feltöltés: " + Math.round(e.loaded / e.total * 100) + "%"; };
      xhr.onload = () => {
        let res = {};
        try { res = JSON.parse(xhr.responseText); } catch (e) { res = {}; }
        if (xhr.status === 200 && res.ok) {
          toast(res.name + " feltöltve");
          file = null;
          drawForm();
          drawList();
        } else {
          progress.textContent = res.error || "Nem sikerült feltölteni";
          button.disabled = false;
        }
      };
      xhr.onerror = () => { progress.textContent = "Nem sikerült feltölteni"; button.disabled = false; };
      progress.textContent = "Feltöltés…";
      xhr.send(file);
    }

    return page("Saját skinek",
      h("div", { class: "card" },
        h("h2", { text: "1. Keress egy skint" }),
        h("div", { class: "muted small", text: "Válassz egy egyedi skint, és töltsd le a fájlját." }),
        h("div", { class: "row-actions" },
          h("a", { class: "btn primary", href: "https://runeforge.io", target: "_blank", rel: "noopener", text: "Keresés itt: runeforge.io" }))),
      h("div", { class: "card" },
        h("h2", { text: "2. Töltsd fel" }),
        h("div", { class: "muted small", text: "A letöltött fájlt húzd ide, vagy kattints és válaszd ki." }),
        drop, fileInput),
      formBox,
      h("div", { class: "card" },
        h("h2", { text: "3. Válaszd ki champion selectben" }),
        h("div", { class: "muted small", text: "Champion selectben jobb alul a „Mods” gombbal tudod kiválasztani, hogy a skin helyett a saját skined legyen rajtad." })),
      listBox);
  }

  // -- tier list and builds ---------------------------------------------------------
  let tierPosition = "Middle";
  const SKILL_KEYS = { 1: "Q", 2: "W", 3: "E", 4: "R" };

  async function champSelectCard() {
    let cs;
    try { cs = await api("/api/champ-select"); } catch (e) { return null; }
    if (!cs.inChampSelect) return null;
    if (!championsCache) championsCache = (await api("/api/champions")).champions;
    const champ = championsCache.find((c) => c.id === cs.championId);
    return h("div", { class: "card cs-card" },
      picture(champ && champ.icon, "pn-icon big", ""),
      h("div", { class: "cs-text" }, h("div", { class: "stat-label", text: cs.locked ? "Lezárt championöd" : "Kiválasztott championöd" }),
        h("div", { class: "stat-value", text: champ ? champ.name : "#" + cs.championId })),
      h("a", { class: "btn primary", href: "#/build/" + cs.championId, text: "Build megnyitása" }));
  }

  async function renderTier() {
    const [data, cs] = await Promise.all([api("/api/tierlist"), champSelectCard()]);
    if (!data.available) return page("Tier list", h("div", { class: "card empty", text: "Most nem sikerült betölteni a tier listet." }));
    const position = data.positions.find((p) => p.key === tierPosition) || data.positions[0];
    const tabs = h("div", { class: "chips", role: "group", "aria-label": "Pozíció" }, data.positions.map((p) =>
      h("button", { class: "chip" + (p.key === position.key ? " on" : ""), "aria-pressed": p.key === position.key ? "true" : "false",
        text: p.name, onclick: () => { tierPosition = p.key; render(); } })));
    const table = h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ["#", "Champion", "Tier", "Winrate", "Pickrate", "Banrate"].map((t) => h("th", { scope: "col", text: t })))),
      h("tbody", {}, position.champions.map((c) => h("tr", {},
        h("td", { class: "muted", text: c.rank }),
        h("td", {}, h("a", { class: "match-champ pn-link", href: "#/build/" + c.championId + "/" + position.key },
          picture(c.icon, "", ""), c.name)),
        h("td", {}, h("span", { class: "tier-badge t" + c.tierNumber, text: c.tier })),
        h("td", { text: c.winRate + "%" }),
        h("td", { class: "muted", text: c.pickRate + "%" }),
        h("td", { class: "muted", text: c.banRate + "%" }))))));
    const old = data.version !== data.currentVersion
      ? h("div", { class: "banner", text: "A " + data.currentVersion + " patchhez még kevés az adat, ezért a " + data.version + " adatai látszanak." })
      : null;
    return page("Tier list", cs, old,
      h("div", { class: "card" },
        h("div", { class: "section-head" }, tabs,
          h("span", { class: "muted small", text: "Forrás: " + data.source + " · " + data.region + " " + data.rank + " · patch " + data.version })),
        table));
  }

  function iconRow(list, cls) {
    return h("div", { class: "build-row" }, list.map((x) => h("span", { class: "build-chip " + (cls || "") },
      picture(x.icon, "", ""), h("span", { text: x.name }))));
  }

  async function renderBuild(r) {
    const data = await api("/api/builds/" + r.id);
    if (!data.available || !data.lanes.length) {
      return page("Build", h("div", { class: "card empty", text: "Ehhez a championhöz most nincs build adat." }));
    }
    const lane = data.lanes.find((l) => l.key === r.sub) || data.lanes[0];
    let index = 0;
    const box = h("div", {});
    const onetricks = "https://www.onetricks.gg/champions/ranking/" + encodeURIComponent((data.championName || "").replace(/[^A-Za-z]/g, ""));
    function draw() {
      const b = lane.builds[index];
      const v = b.view;
      const status = h("div", { class: "muted small" });
      box.replaceChildren(h("div", { class: "card build-card" },
        lane.builds.length > 1 ? h("div", { class: "chips" }, lane.builds.map((_, i) => h("button", {
          class: "chip" + (i === index ? " on" : ""), text: (i + 1) + ". build", onclick: () => { index = i; draw(); } }))) : null,
        h("h2", { text: "Rúnák" }),
        h("div", { class: "rune-cols" },
          h("div", {}, iconRow([v.primaryStyle], "style"), iconRow(v.primary)),
          h("div", {}, iconRow([v.subStyle], "style"), iconRow(v.secondary), iconRow(v.shards, "shard"))),
        h("h2", { text: "Summoner spellek" }), iconRow(v.spells),
        h("h2", { text: "Kezdő tárgyak" }), iconRow(v.startItems),
        h("h2", { text: "Tárgyak sorrendben" }), iconRow(v.items),
        h("h2", { text: "Skill sorrend" }),
        h("div", { class: "build-row" }, h("span", { class: "skill-max", text: b.skills.map((k) => SKILL_KEYS[k] || k).join(" › ") }),
          h("span", { class: "muted small", text: b.skillOrder.map((k) => SKILL_KEYS[k] || k).join(" ") })),
        h("div", { class: "row-actions" },
          h("button", { class: "btn primary", text: "Rúnák és spellek beállítása", onclick: async (e) => {
            e.currentTarget.disabled = true;
            try {
              await api("/api/apply-build", { championId: data.championId, lane: lane.key, index });
              status.textContent = "Beállítva: a rúnaoldal „Proteus” néven került be.";
            } catch (err) { status.textContent = "Nem sikerült: indítsd el a League klienst, és légy champion selectben."; }
            e.currentTarget.disabled = false;
          } }),
          h("a", { class: "btn", href: onetricks, target: "_blank", rel: "noopener", text: "onetricks.gg ranking" })),
        status));
    }
    draw();
    const laneTabs = h("div", { class: "chips", role: "group", "aria-label": "Pozíció" }, data.lanes.map((l) =>
      h("a", { class: "chip chip-link" + (l.key === lane.key ? " on" : ""), href: "#/build/" + data.championId + "/" + l.key, text: l.name })));
    const oldBuild = data.version !== data.currentVersion
      ? h("div", { class: "banner", text: "A " + data.currentVersion + " patchhez még kevés az adat, ezért a " + data.version + " buildje látszik." })
      : null;
    return page((data.championName || "Build") + " build", oldBuild,
      h("div", { class: "card build-head" }, picture(data.championIcon, "pn-icon big", ""), laneTabs,
        h("span", { class: "muted small", text: "Forrás: " + data.source + " · patch " + data.version })),
      box);
  }

  // -- patch notes -------------------------------------------------------------------
  const VERDICT = { buff: ["Erősítés", "buff"], nerf: ["Gyengítés", "nerf"], adjust: ["Módosítás", "adjust"] };

  function changeText(c) {
    let text = (c.label ? c.label + ": " : "") + c.old + " → " + c.new;
    if (c.percent !== null && c.percent !== undefined && c.percent !== 0) text += " (" + (c.percent > 0 ? "+" : "") + c.percent + "%)";
    return text;
  }

  function summaryTable(title, hint, entries, withIcon) {
    return h("div", { class: "card" },
      h("div", { class: "section-head" }, h("h2", { text: title }), h("span", { class: "muted small", text: hint })),
      entries.length
        ? h("ul", { class: "pn-summary" }, entries.map((e) => h("li", {},
            h("a", { href: "#pn-" + e.anchor, class: "pn-link" },
              withIcon ? picture(e.icon, "pn-icon", "") : null,
              h("span", { text: e.name })),
            h("span", { class: "muted small", text: e.better + " jobb · " + e.worse + " rosszabb" }))))
        : h("div", { class: "muted", text: "Ebben a patchben nincs ilyen." }));
  }

  function entryCard(e, withIcon) {
    const [label, cls] = VERDICT[e.verdict] || VERDICT.adjust;
    let lastDetail = null;
    const lines = [];
    e.changes.forEach((c) => {
      if (c.detail && c.detail !== lastDetail) {
        lines.push(h("div", { class: "pn-detail", text: c.detail }));
        lastDetail = c.detail;
      }
      lines.push(h("div", { class: "pn-change" },
        h("span", { class: "tag " + (c.effect === "better" ? "buff" : c.effect === "worse" ? "nerf" : ""),
          text: c.effect === "better" ? "jobb" : c.effect === "worse" ? "rosszabb" : "változott" }),
        h("span", { text: changeText(c) })));
    });
    return h("div", { class: "card pn-entry", id: "pn-" + e.anchor },
      h("div", { class: "pn-head" },
        withIcon ? picture(e.icon, "pn-icon big", "") : null,
        h("h2", { text: e.name }),
        h("span", { class: "tag " + cls, text: label })),
      e.context ? h("p", { class: "pn-context", text: e.context }) : null,
      lines);
  }

  async function renderPatch() {
    const notes = await api("/api/patch-notes");
    if (!notes.available) {
      return page("Patch notes", h("div", { class: "card empty", text: "Most nem sikerült betölteni a patch notes-t. Ellenőrizd az internetkapcsolatot, és próbáld újra." }));
    }
    let n = 0;
    notes.champions.forEach((e) => { e.anchor = "c" + (n++); });
    notes.items.forEach((e) => { e.anchor = "i" + (n++); });
    const by = (list, v) => list.filter((e) => e.verdict === v);
    const head = h("div", { class: "card" },
      h("div", { class: "muted small", text: "A hivatalos patch notes alapján. Az „Erősítés” és a „Gyengítés” a számokból és a fejlesztők indoklásából jön." }),
      h("a", { href: notes.url, target: "_blank", rel: "noopener", class: "small", text: "Hivatalos oldal megnyitása" }));
    const content = h("div", { class: "pn-anchor-root" },
      h("div", { class: "pn-grid" },
        summaryTable("Erősített championök", "ezeket érdemes most játszani", by(notes.champions, "buff"), true),
        summaryTable("Gyengített championök", "ezek rosszabbak lettek", by(notes.champions, "nerf"), true),
        summaryTable("Erősített tárgyak", "ezeket érdemes most venni", by(notes.items, "buff"), false),
        summaryTable("Gyengített tárgyak", "ezek rosszabbak lettek", by(notes.items, "nerf"), false)),
      h("h2", { class: "pn-section", text: "Championök részletesen" }),
      notes.champions.map((e) => entryCard(e, true)),
      h("h2", { class: "pn-section", text: "Tárgyak részletesen" }),
      notes.items.map((e) => entryCard(e, false)));
    content.addEventListener("click", (ev) => {
      const link = ev.target.closest("a.pn-link");
      if (!link) return;
      ev.preventDefault();
      const target = document.getElementById(link.getAttribute("href").slice(1));
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return page("Patch " + notes.patch, head, content);
  }

  // -- profile -----------------------------------------------------------------------
  function matchTable(matches) {
    if (!matches.length) return h("div", { class: "muted", text: "Még nincs meccs a listában." });
    return h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Eredmény", "Champion", "KDA", "CS", "Mód", "Hossz", "Mikor"].map((t) => h("th", { scope: "col", text: t })))),
      h("tbody", {}, matches.map((m) => h("tr", {},
        h("td", {}, h("span", { class: "tag " + (m.win ? "win" : "loss"), text: m.win ? "Győzelem" : "Vereség" })),
        h("td", {}, h("span", { class: "match-champ" }, picture(m.championIcon, "", ""), m.championName)),
        h("td", { text: m.kills + " / " + m.deaths + " / " + m.assists }),
        h("td", { class: "muted", text: m.cs }),
        h("td", { class: "muted", text: m.queue }),
        h("td", { class: "muted", text: minutes(m.duration) }),
        h("td", { class: "muted", text: ago(m.createdAt) }))))));
  }

  async function renderProfile() {
    const p = await api("/api/profile");
    if (!p.connected) {
      return page("Profil", h("div", { class: "card empty", text: "Indítsd el a League klienst, és itt megjelenik a profilod és a meccstörténeted." }));
    }
    const s = p.summoner || {};
    const head = h("div", { class: "card profile-head" }, picture(s.icon, "", ""),
      h("div", {}, h("h2", { text: (s.name || "") + (s.tag ? " #" + s.tag : "") }),
        h("div", { class: "muted small", text: s.level ? "Szint " + s.level : "" })));
    const rankCard = (label, r) => h("div", { class: "card" }, h("div", { class: "stat-label", text: label }),
      h("div", { class: "stat-value gold", text: rankText(r) }),
      h("div", { class: "stat-sub", text: r && (r.wins + r.losses) ? r.wins + " győzelem · " + r.losses + " vereség · " + r.winrate + "%" : "Ebben a szezonban még nem játszottál" }));
    return page("Profil", head,
      h("div", { class: "cards" }, rankCard("Ranked Solo/Duo", (p.ranked || {}).solo), rankCard("Ranked Flex", (p.ranked || {}).flex)),
      h("div", { class: "card" }, h("div", { class: "section-head" }, h("h2", { text: "Meccstörténet" })), matchTable(p.matches || [])));
  }

  // -- settings ----------------------------------------------------------------------
  async function renderSettings() {
    const [settings, status] = await Promise.all([api("/api/settings"), api("/api/status")]);
    const toggle = h("button", { class: "toggle" + (settings.windowOnStart ? " on" : ""), "aria-pressed": settings.windowOnStart ? "true" : "false",
      "aria-label": "Ablak megnyitása induláskor",
      onclick: async () => {
        try {
          const next = await api("/api/settings", { windowOnStart: !settings.windowOnStart });
          settings.windowOnStart = next.windowOnStart;
          toggle.classList.toggle("on", settings.windowOnStart);
          toggle.setAttribute("aria-pressed", settings.windowOnStart ? "true" : "false");
        } catch (e) { toast("Nem sikerült menteni"); }
      } });
    const folder = (which, label) => h("button", { class: "btn", text: label, onclick: async () => {
      try { await api("/api/open-folder", { folder: which }); } catch (e) { toast("Nem sikerült megnyitni"); }
    } });
    return page("Beállítások",
      h("div", { class: "card" },
        h("div", { class: "setting" },
          h("div", {}, h("div", { text: "Ablak megnyitása induláskor" }),
            h("div", { class: "muted small", text: "Kikapcsolva a Proteus csak a tálcán indul, az ablakot a tálcaikonnal nyithatod meg." })),
          toggle),
        h("div", { class: "setting" },
          h("div", {}, h("div", { text: "Modok mappa" }), h("div", { class: "muted small", text: "Ide kerülnek a saját skinek, pályák, betűtípusok." })),
          folder("mods", "Megnyitás")),
        h("div", { class: "setting" },
          h("div", {}, h("div", { text: "Naplók" }), h("div", { class: "muted small", text: "Hiba esetén ezeket küldd el." })),
          folder("logs", "Megnyitás"))),
      h("div", { class: "card" },
        h("h2", { text: "Proteus v" + status.version }),
        h("div", { class: "muted small", text: "A frissítéseket a Proteus induláskor magától keresi. A League kliensben lévő beállításokat (injektálás, nyelv) a kliens Proteus menüjében találod." })));
  }

  // -- start --------------------------------------------------------------------------
  if (!token) {
    main.replaceChildren(page("Proteus", h("div", { class: "card empty",
      text: "Ezt az ablakot a Proteus tálcaikonjáról nyisd meg." })));
  } else {
    refreshStatus();
    setInterval(refreshStatus, 5000);
    if (!location.hash || location.hash.length < 3) history.replaceState(null, "", "#/home");
    render();
  }
})();
