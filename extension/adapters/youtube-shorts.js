// Adapter for YouTube Shorts (/shorts/...).
// Shorts pages have no watch-page title/channel boxes: the title comes from the tab title.
// There are several videos on the page, so pickBestVideo (common.js) picks the right one.
ADAPTERS.push({
  name: "youtube-shorts",
  site: "YouTube Shorts",

  matches() {
    return location.pathname.startsWith("/shorts/");
  },

  pickVideo() {
    return pickBestVideo();
  },

  readState() {
    const title = document.title.replace(/^\(\d+\)\s*/, "").replace(/\s*-\s*YouTube$/, "").trim();
    if (!title || title === "YouTube" || title === "Shorts") return null;

    // Channel name: best-effort selectors. If nothing is found it stays empty.
    const ch = firstMatch([
      "ytd-reel-video-renderer[is-active] ytd-channel-name a",
      "ytd-reel-video-renderer[is-active] #channel-name a",
    ]);

    return {
      title: title,
      channel: ch ? ch.textContent.trim() : "",
      description: "",
    };
  },
});
