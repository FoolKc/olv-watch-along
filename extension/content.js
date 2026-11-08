// OLV Watch-Along - YouTube content script.
// On /watch pages only, reads the title, channel, URL, paused state, description and
// the captions currently on screen. It does not read comments, your account or other tabs.
const CHECK_MS = 3000;       // check every 3 seconds
const CAPTION_MS = 1000;     // check captions every second
const HEARTBEAT_MS = 60000;  // "still watching" once a minute even without changes
const SUBS_EVERY_MS = 15000; // send new captions at most every 15 s
const SETTLE_MS = 10000;     // URL changed but title is old: wait up to 10 s
const DESC_MAX = 400;
const SUBS_MAX = 400;
const SUBS_LINES = 6;
const DESC_STALE_MS = 20000;  // on a new video, ignore the old description for up to 20 s

let lastSent = null;         // { url, title, paused, description, subtitle, time }
let urlChangedAt = 0;
let lastSeenUrl = "";
let captionLines = [];       // last caption lines seen on screen
let staleDesc = "";          // previous video's description (YouTube may update it late)

function clean(text, max) {
  return (text || "").replace(/\s+/g, " ").trim().slice(0, max);
}

function firstMatch(selectors) {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.textContent && el.textContent.trim()) return el;
  }
  return null;
}

// Drop auto-caption tags like "[Music]" or note symbols; keep the real words.
function cleanCaption(text) {
  let t = clean(text, 200).replace(/\[[^\]]*\]/g, " ").replace(/[\u266A\u266B\u266C]/g, " ");
  t = clean(t, 200);
  if (/^(music|foreign|applause|laughter)$/i.test(t)) return "";
  if (!/[\p{L}\p{N}]/u.test(t)) return "";
  return t;
}

function readCaptions() {
  if (location.pathname !== "/watch") return;
  const segs = document.querySelectorAll(".ytp-caption-segment");
  if (!segs.length) return;
  const line = cleanCaption(Array.from(segs).map((s) => s.textContent).join(" "));
  if (!line || captionLines[captionLines.length - 1] === line) return;
  captionLines.push(line);
  if (captionLines.length > SUBS_LINES) captionLines.shift();
}

function readState() {
  if (location.pathname !== "/watch") return null;
  const h1 = document.querySelector("ytd-watch-metadata h1 yt-formatted-string, ytd-watch-metadata h1");
  let title = h1 && h1.textContent ? h1.textContent.trim() : "";
  if (!title) title = document.title.replace(/^\(\d+\)\s*/, "").replace(/\s*-\s*YouTube$/, "").trim();
  if (!title || title === "YouTube") return null;
  const ch = document.querySelector("ytd-watch-metadata ytd-channel-name a, #owner ytd-channel-name a");
  const video = document.querySelector("video.html5-main-video, video");
  // Only the video's own description text (not view counts, suggestions or other boxes).
  // Order matters: a single comma-separated selector would return the outer container.
  const desc = firstMatch([
    "ytd-watch-metadata #description-inline-expander #expanded yt-attributed-string",
    "ytd-watch-metadata #description-inline-expander #attributed-snippet-text",
    "ytd-watch-metadata #description-inline-expander yt-attributed-string",
  ]);
  return {
    site: "YouTube",
    title: title,
    channel: ch && ch.textContent ? ch.textContent.trim() : "",
    url: location.href.split("&")[0],
    paused: video ? video.paused : null,
    description: desc ? clean(desc.textContent, DESC_MAX) : "",
    subtitle: clean(captionLines.join(" / "), SUBS_MAX),
  };
}

function check() {
  if (location.href !== lastSeenUrl) {
    lastSeenUrl = location.href;
    urlChangedAt = Date.now();
    captionLines = [];       // new video: forget old captions
    staleDesc = lastSent ? lastSent.description : "";
  }
  const s = readState();
  if (!s) return;
  const now = Date.now();

  // On a new video, a description identical to the previous one is not updated yet: don't send it.
  if (staleDesc && s.description === staleDesc) {
    if (now - urlChangedAt < DESC_STALE_MS) s.description = "";
    else staleDesc = "";     // still the same after 20 s: it really is the same
  } else if (staleDesc && s.description) {
    staleDesc = "";          // the new description arrived
  }

  // YouTube changes the URL before the title: new video but old title, so wait a bit.
  if (lastSent && s.url !== lastSent.url && s.title === lastSent.title && now - urlChangedAt < SETTLE_MS) {
    return;
  }

  const changed = !lastSent || s.url !== lastSent.url || s.title !== lastSent.title ||
    s.paused !== lastSent.paused || s.description !== lastSent.description;
  const subsChanged = lastSent && s.subtitle !== lastSent.subtitle && now - lastSent.time >= SUBS_EVERY_MS;
  const heartbeat = lastSent && now - lastSent.time >= HEARTBEAT_MS;
  if (!changed && !subsChanged && !heartbeat) return;

  // In a background tab, only real changes; no captions or "still watching".
  if (!changed && document.hidden) return;

  lastSent = { url: s.url, title: s.title, paused: s.paused, description: s.description, subtitle: s.subtitle, time: now };
  browser.runtime.sendMessage({ type: "watch-along-update", state: s }).catch(() => {});
}

setInterval(readCaptions, CAPTION_MS);
setInterval(check, CHECK_MS);
check();

// --- Playback control: carry out commands coming from the background script ---
function clickVisible(sel) {
  const el = document.querySelector(sel);
  if (!el || getComputedStyle(el).display === "none") return false;
  el.click();
  return true;
}

function goNext() {
  if (clickVisible("#movie_player .ytp-next-button")) return "skipped to the next video";
  const btn = document.querySelector("#movie_player .ytp-next-button");
  if (btn && btn.href && btn.href.includes("/watch")) {
    location.assign(btn.href);
    return "skipped to the next video";
  }
  const rec = document.querySelector("#secondary a[href^='/watch']");
  if (rec) {
    rec.click();
    return "skipped to the first recommended video";
  }
  return "there is no next video to skip to";
}

// On the search results page, open the first real video (not an ad or a Short).
function playFirst() {
  return new Promise((resolve) => {
    let tries = 0;
    const timer = setInterval(() => {
      tries++;
      const a = document.querySelector("ytd-search ytd-video-renderer a#video-title[href^='/watch']") ||
        document.querySelector("ytd-search a[href^='/watch?v=']");
      if (a) {
        clearInterval(timer);
        const title = clean(a.getAttribute("title") || a.textContent || a.getAttribute("aria-label"), 150);
        a.click();
        resolve(title ? "now playing \"" + title + "\"" : "opened the first search result");
      } else if (tries >= 20) {
        clearInterval(timer);
        resolve("searched YouTube but could not find a video to play");
      }
    }, 500);
  });
}


// Tell the background script this tab is on YouTube (also used to open the first result after a search).
browser.runtime.sendMessage({ type: "watch-along-hello" }).catch(() => {});
browser.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "watch-along-playfirst") return playFirst();
  if (!msg || msg.type !== "watch-along-command") return;
  const video = document.querySelector("video.html5-main-video, video");
  if (location.pathname !== "/watch" || !video) return Promise.resolve("no video is open in the YouTube tab");
  if (msg.action === "pause") {
    video.pause();
    return Promise.resolve("paused");
  }
  if (msg.action === "play") {
    return video.play().then(() => "playing", () => "could not start playback (the browser blocked it)");
  }
  if (msg.action === "next") {
    return Promise.resolve(goNext());
  }
  if (msg.action === "louder") {
    video.muted = false;
    video.volume = Math.min(1, video.volume + 0.2);
    return Promise.resolve("Volume is now " + Math.round(video.volume * 100) + "%");
  }
  if (msg.action === "quieter") {
    // If the video is muted, leave the volume alone and just report it.
    if (video.muted) {
      return Promise.resolve("the video is muted, so the volume was not changed");
    }
    video.volume = Math.max(0, video.volume - 0.2);
    return Promise.resolve("Volume is now " + Math.round(video.volume * 100) + "%");
  }
  if (msg.action === "previous") {
    // After a few seconds YouTube's previous button only restarts the video: rewind first, then press it.
    video.currentTime = 0;
    return new Promise((resolve) => setTimeout(() => {
      if (clickVisible("#movie_player .ytp-prev-button")) resolve("went to the previous video");
      else { history.back(); resolve("went back to the previous page"); }
    }, 400));
  }
  return Promise.resolve("unknown command");
});
