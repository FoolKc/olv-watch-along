// OLV Watch-Along - background script.
// Forwards the state reported by the content script to the local bridge, and
// polls the bridge for playback commands (pause / play / next / previous / search)
// which it passes on to the YouTube tab.
// Requests sent from here carry an Origin of "moz-extension://...", which the bridge accepts.
const BRIDGE = "http://127.0.0.1:12450";
const POLL_MS = 2000;
const SEARCH_WAIT_MS = 20000;
let youtubeTab = null;      // the YouTube tab that reported most recently
let pendingSearch = null;   // { tabId, id, until }: open the first result once the search page loads

browser.runtime.onMessage.addListener((msg, sender) => {
  if (!msg) return;
  if (msg.type === "watch-along-hello" && sender.tab) {
    youtubeTab = sender.tab.id;
    const p = pendingSearch;
    if (p && p.tabId === sender.tab.id && Date.now() < p.until) {
      pendingSearch = null;
      browser.tabs.sendMessage(p.tabId, { type: "watch-along-playfirst" })
        .then((r) => report(p.id, r || "opened the search results"))
        .catch(() => report(p.id, "opened the search results but could not start a video"));
    }
    return;
  }
  if (msg.type !== "watch-along-update") return;
  if (sender.tab) youtubeTab = sender.tab.id;
  fetch(BRIDGE + "/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(msg.state),
  })
    .then((r) => console.log("[Watch-Along] sent:", r.status, msg.state.title))
    .catch((e) => console.log("[Watch-Along] bridge may be offline:", e.message));
});

function report(id, result) {
  fetch(BRIDGE + "/command/result", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: id, result: result }),
  }).catch(() => {});
}

async function startSearch(cmd) {
  const url = "https://www.youtube.com/results?search_query=" + encodeURIComponent(cmd.query || "");
  const until = Date.now() + SEARCH_WAIT_MS;
  if (youtubeTab !== null) {
    pendingSearch = { tabId: youtubeTab, id: cmd.id, until: until };
    try {
      await browser.tabs.update(youtubeTab, { url: url });
      return;
    } catch (e) {
      youtubeTab = null;   // the tab was closed
    }
  }
  try {
    const tab = await browser.tabs.create({ url: url });
    youtubeTab = tab.id;
    pendingSearch = { tabId: tab.id, id: cmd.id, until: until };
  } catch (e) {
    pendingSearch = null;
    report(cmd.id, "could not open YouTube search");
  }
}

async function poll() {
  let cmd = null;
  try {
    const r = await fetch(BRIDGE + "/command", { headers: { "X-Watch-Along": "1" } });
    cmd = (await r.json()).command;
  } catch (e) {
    return;                // bridge is not running
  }
  if (!cmd) return;
  console.log("[Watch-Along] command:", cmd.id, cmd.action, cmd.query || "");
  if (cmd.action === "search") {
    startSearch(cmd);
    return;
  }
  if (youtubeTab === null) {
    report(cmd.id, "no YouTube video tab found");
    return;
  }
  try {
    const result = await browser.tabs.sendMessage(youtubeTab, { type: "watch-along-command", action: cmd.action });
    report(cmd.id, result || "done");
  } catch (e) {
    youtubeTab = null;
    report(cmd.id, "the YouTube tab is closed or not ready");
  }
}

setInterval(poll, POLL_MS);
