// OLV Watch-Along - shared code for all site adapters.
// ADAPTERS: each site file (youtube-watch.js, youtube-shorts.js, ...) adds itself to this list.
// The helper functions below do not depend on any site; adapters and content.js use them.
const ADAPTERS = [];

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
