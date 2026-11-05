/**
 * @name Proteus-Profile
 * @author lildmate
 * @description Shows the rank you picked in the Proteus window (and your party friends' picks) on profiles and lobby banners
 * @link https://github.com/lildmate/claude
 */
(function initProteusProfile() {
  // Only what this client shows is changed: the client's answers about ranks
  // (regalia: the banner and its border; ranked stats: the profile) are
  // rewritten as they arrive. Nothing is sent anywhere, so players without
  // Proteus keep seeing the real rank. Chat presence is left alone on purpose:
  // the client sends that one on to friends.
  const LOG_PREFIX = "[Proteus-Profile]";
  const RANK_URL = /\/lol-(regalia|ranked)\/v\d+\/(current-summoner|current-ranked-stats|summoners\/([^/?]+)|ranked-stats\/([^/?]+))/;
  const TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"];
  const APEX = ["MASTER", "GRANDMASTER", "CHALLENGER"];
  const SOLO_QUEUE = "RANKED_SOLO_5x5";

  // Whose rank to change: "self", summoner ids and puuids -> {tier, division}
  let ranks = new Map();
  let me = null; // {summonerId, puuid}
  const nativeFetch = window.fetch.bind(window);

  // What the client asked about ranks, for the log (Beállítások → Naplók)
  const seen = new Map(); // address without ids -> [count, changed]
  function note(url, changed) {
    if (!/regalia|ranked|lol-lobby\/v2\/lobby|hovercard|summoner-profile|profile/i.test(url)) return;
    const key = url.replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, "{puuid}").replace(/\/\d{5,}/g, "/{id}").split("?")[0];
    const entry = seen.get(key) || [0, false];
    entry[0] += 1;
    entry[1] = entry[1] || changed;
    seen.set(key, entry);
  }

  function rankFor(url) {
    const match = RANK_URL.exec(url);
    if (!match || !ranks.size) return null;
    const who = match[3] || match[4];
    if (!who) return ranks.get("self") || null; // current-summoner / current-ranked-stats
    return ranks.get(decodeURIComponent(who)) || null;
  }

  function isTier(value) {
    return typeof value === "string" && (value === "" || value === "NONE" || value === "UNRANKED" || TIERS.includes(value));
  }

  // Every rank field of the answer (solo queue entries and the "highest rank"
  // ones the banner uses) becomes the chosen rank; other queues stay.
  function rewrite(value, rank) {
    if (Array.isArray(value)) return value.map((v) => rewrite(v, rank));
    if (!value || typeof value !== "object") return value;
    if (typeof value.queueType === "string" && value.queueType && value.queueType !== SOLO_QUEUE) return value;
    const division = APEX.includes(rank.tier) ? "NA" : rank.division;
    const out = {};
    for (const [key, v] of Object.entries(value)) {
      if ((key === "tier" || /Tier$/.test(key) || key === "lastSeasonHighestRank") && (isTier(v) || v === null)) out[key] = rank.tier;
      else if ((key === "division" || /Division$/.test(key)) && (typeof v === "string" || v === null)) out[key] = division;
      // the border around the icon and the banner: the ranked ones (an unranked or
      // level-crest profile has none to show otherwise)
      else if (key === "crestType" || key === "preferredCrestType") out[key] = "ranked";
      else if (key === "bannerType" || key === "preferredBannerType") out[key] = "lastSeasonHighestRank";
      else if (/^highestRankedEntry/.test(key) && !v) out[key] = { queueType: SOLO_QUEUE, tier: rank.tier, division };
      else out[key] = rewrite(v, rank);
    }
    return out;
  }

  // A few answers that were changed, as the client sent them, for the log
  const samples = new Map();
  function sample(url, text) {
    const key = "SAMPLE " + url.replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, "{puuid}").replace(/\/\d{5,}/g, "/{id}").split("?")[0];
    if (samples.size < 12 && !samples.has(key) && typeof text === "string") samples.set(key, text.slice(0, 1500));
  }

  function rewriteText(url, text) {
    const rank = rankFor(url);
    note(url, Boolean(rank));
    if (rank) sample(url, text);
    if (!rank || typeof text !== "string" || !text) return text;
    try {
      return JSON.stringify(rewrite(JSON.parse(text), rank));
    } catch (e) {
      return text;
    }
  }

  // -- the client's requests ----------------------------------------------------
  window.fetch = async function (input, init) {
    const response = await nativeFetch(input, init);
    try {
      const url = typeof input === "string" ? input : input && input.url;
      if (url && !rankFor(url)) note(url, false);
      if (!url || !response.ok || !rankFor(url)) return response;
      const text = await response.clone().text();
      return new Response(rewriteText(url, text), { status: response.status, statusText: response.statusText, headers: response.headers });
    } catch (e) {
      return response;
    }
  };

  const proto = XMLHttpRequest.prototype;
  const nativeOpen = proto.open;
  const textGetter = Object.getOwnPropertyDescriptor(proto, "responseText").get;
  const responseGetter = Object.getOwnPropertyDescriptor(proto, "response").get;
  proto.open = function (method, url) {
    this.__proteusUrl = String(url || "");
    return nativeOpen.apply(this, arguments);
  };
  Object.defineProperty(proto, "responseText", {
    configurable: true,
    get() {
      const text = textGetter.call(this);
      return this.__proteusUrl && this.readyState === 4 ? rewriteText(this.__proteusUrl, text) : text;
    },
  });
  Object.defineProperty(proto, "response", {
    configurable: true,
    get() {
      const value = responseGetter.call(this);
      if (!this.__proteusUrl || this.readyState !== 4 || !rankFor(this.__proteusUrl)) return value;
      if (typeof value === "string") return rewriteText(this.__proteusUrl, value);
      if (value && typeof value === "object" && this.responseType === "json") return rewrite(value, rankFor(this.__proteusUrl));
      return value;
    },
  });

  // -- the client's live updates (OnJsonApiEvent over its websocket) ---------------
  function rewriteEvent(event) {
    if (typeof event.data !== "string" || !/regalia|ranked|lol-lobby/.test(event.data)) return event;
    try {
      const message = JSON.parse(event.data);
      const update = message && message[2];
      const rank = update && typeof update.uri === "string" && rankFor(update.uri);
      if (update && typeof update.uri === "string") note("ws " + update.uri, Boolean(rank));
      if (!rank || !update.data) return event;
      sample("ws " + update.uri, JSON.stringify(update.data));
      update.data = rewrite(update.data, rank);
      return new MessageEvent("message", { data: JSON.stringify(message), origin: event.origin });
    } catch (e) {
      return event;
    }
  }

  const nativeAdd = WebSocket.prototype.addEventListener;
  WebSocket.prototype.addEventListener = function (type, listener, options) {
    if (type !== "message" || typeof listener !== "function") return nativeAdd.call(this, type, listener, options);
    const wrapped = function (event) { return listener.call(this, rewriteEvent(event)); };
    return nativeAdd.call(this, type, wrapped, options);
  };
  const onmessage = Object.getOwnPropertyDescriptor(WebSocket.prototype, "onmessage");
  Object.defineProperty(WebSocket.prototype, "onmessage", {
    configurable: true,
    get() { return onmessage.get.call(this); },
    set(handler) {
      if (typeof handler !== "function") return onmessage.set.call(this, handler);
      onmessage.set.call(this, function (event) { return handler.call(this, rewriteEvent(event)); });
    },
  });

  // -- the ranks, from Proteus ----------------------------------------------------
  async function summoner(path) {
    try {
      const response = await nativeFetch(path);
      return response.ok ? await response.json() : null;
    } catch (e) {
      return null;
    }
  }

  async function applyRanks(data) {
    const next = new Map();
    if (!me) {
      const current = await summoner("/lol-summoner/v1/current-summoner");
      if (current) me = { summonerId: String(current.summonerId), puuid: current.puuid };
    }
    if (data.self) {
      next.set("self", data.self);
      if (me) {
        next.set(me.summonerId, data.self);
        if (me.puuid) next.set(me.puuid, data.self);
      }
    }
    for (const peer of data.peers || []) {
      const rank = { tier: peer.tier, division: peer.division };
      next.set(String(peer.summonerId), rank);
      const info = await summoner("/lol-summoner/v1/summoners/" + encodeURIComponent(peer.summonerId));
      if (info && info.puuid) next.set(info.puuid, rank);
    }
    ranks = next;
    console.log(`${LOG_PREFIX} Showing ${data.self ? data.self.tier + " " + data.self.division : "your real rank"}, ${(data.peers || []).length} friend(s)`);
  }

  function waitForBridge() {
    return new Promise((resolve, reject) => {
      let waited = 0;
      const check = () => {
        if (window.__proteusBridge) return resolve(window.__proteusBridge);
        waited += 100;
        if (waited >= 60000) return reject(new Error("Bridge not available"));
        setTimeout(check, 100);
      };
      check();
    });
  }

  waitForBridge()
    .then((bridge) => {
      bridge.subscribe("rank-display", (data) => applyRanks(data).catch((e) => console.warn(LOG_PREFIX, e)));
      bridge.onReady(() => bridge.send({ type: "rank-display-get" }));
      // every minute (when something new was seen): the rank addresses, into Proteus's log
      let reported = "";
      setInterval(() => {
        const report = [...seen.entries()].map(([url, [count, changed]]) => `${changed ? "CHANGED" : "seen"} x${count} ${url}`).sort()
          .concat([...samples.entries()].map(([url, text]) => `${url}: ${text}`));
        const text = report.join("\n");
        if (!report.length || text === reported) return;
        reported = text;
        bridge.send({ type: "rank-display-debug", ranks: [...ranks.keys()].length, lines: report.slice(0, 100) });
      }, 60000);
    })
    .catch((e) => console.warn(`${LOG_PREFIX} ${e.message}`));
})();
