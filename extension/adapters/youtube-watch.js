// Adapter for YouTube watch pages (/watch).
// Reads the title, channel and description; content.js adds the URL, paused state and captions.
ADAPTERS.push({
  name: "youtube-watch",
  site: "YouTube",

  matches() {
    return location.pathname === "/watch";
  },

  pickVideo() {
    return document.querySelector("video.html5-main-video, video");
  },

  readState() {
    const h1 = document.querySelector("ytd-watch-metadata h1 yt-formatted-string, ytd-watch-metadata h1");
    let title = h1 && h1.textContent ? h1.textContent.trim() : "";
    if (!title) title = document.title.replace(/^\(\d+\)\s*/, "").replace(/\s*-\s*YouTube$/, "").trim();
    if (!title || title === "YouTube") return null;

    const ch = document.querySelector("ytd-watch-metadata ytd-channel-name a, #owner ytd-channel-name a");
    // Only the video's own description text (not view counts, suggestions or other boxes).
    // Order matters: a single comma-separated selector would return the outer container.
    const desc = firstMatch([
      "ytd-watch-metadata #description-inline-expander #expanded yt-attributed-string",
      "ytd-watch-metadata #description-inline-expander #attributed-snippet-text",
      "ytd-watch-metadata #description-inline-expander yt-attributed-string",
    ]);

    return {
      title: title,
      channel: ch && ch.textContent ? ch.textContent.trim() : "",
      description: desc ? desc.textContent : "",
    };
  },
});
