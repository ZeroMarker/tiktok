// Fetch a live HLS URL from the signed-in browser-desktop Chromium via CDP.
// stdout is reserved for the stream URL; diagnostics go to stderr.

const [rawUrl, rawHeight = "0"] = process.argv.slice(2);
const height = Number(rawHeight);
const cdp = process.env.YOUTUBE_BROWSER_CDP || "http://127.0.0.1:9222";

function fail(message) {
  throw new Error(message);
}

async function evaluate(ws, expression, id) {
  return await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("CDP evaluation timed out")), 5000);
    const onMessage = (event) => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message.id !== id) return;
      clearTimeout(timer);
      ws.removeEventListener("message", onMessage);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result?.result?.value);
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({
      id,
      method: "Runtime.evaluate",
      params: { expression, returnByValue: true },
    }));
  });
}

async function main() {
  if (!rawUrl || !Number.isFinite(height) || height < 0) fail("invalid arguments");
  const url = new URL(rawUrl);
  if (!["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"].includes(url.hostname)) {
    fail("target is not a YouTube URL");
  }

  let id;
  let ws;
  try {
    const response = await fetch(`${cdp}/json/new?${encodeURIComponent(url.href)}`, { method: "PUT" });
    if (!response.ok) fail(`browser CDP returned HTTP ${response.status}`);
    const tab = await response.json();
    id = tab.id;
    ws = new WebSocket(tab.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("browser connection timed out")), 5000);
      ws.addEventListener("open", () => { clearTimeout(timer); resolve(); }, { once: true });
      ws.addEventListener("error", () => { clearTimeout(timer); reject(new Error("browser connection failed")); }, { once: true });
    });

    const deadline = Date.now() + 20000;
    let source;
    let status;
    let title;
    for (let attempt = 1; Date.now() < deadline; attempt++) {
      const result = await evaluate(ws, `JSON.stringify((() => {
        const player = window.ytInitialPlayerResponse || {};
        return { status: player.playabilityStatus?.status || "", title: player.videoDetails?.title || "",
          hls: player.streamingData?.hlsManifestUrl || "" };
      })())`, attempt);
      ({ status, title, hls: source } = JSON.parse(result || "{}"));
      if (source) break;
      if (status && status !== "OK" && status !== "LIVE_STREAM_OFFLINE") break;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!source) fail(`browser has no live HLS source (${status || "page not ready"}${title ? `: ${title}` : ""})`);

    const manifest = await fetch(source);
    if (!manifest.ok) fail(`HLS manifest returned HTTP ${manifest.status}`);
    const lines = (await manifest.text()).split(/\r?\n/);
    const variants = [];
    for (let i = 0; i < lines.length - 1; i++) {
      if (!lines[i].startsWith("#EXT-X-STREAM-INF:")) continue;
      const match = lines[i].match(/RESOLUTION=\d+x(\d+)/);
      if (match && lines[i + 1] && !lines[i + 1].startsWith("#")) {
        variants.push({ height: Number(match[1]), url: new URL(lines[i + 1], source).href });
      }
    }
    // yt-dlp's height cap is applied to the second RESOLUTION dimension.
    // ffmpeg receives the master playlist for best, but validate one variant
    // first: YouTube sometimes serves a valid manifest whose segments are 403.
    variants.sort((a, b) => a.height - b.height);
    const selected = variants.length
      ? (height ? [...variants].reverse().find((item) => item.height <= height) || variants[0] : variants.at(-1))
      : null;
    const mediaUrl = selected?.url || source;
    const mediaResponse = selected ? await fetch(mediaUrl) : null;
    if (mediaResponse && !mediaResponse.ok) fail(`HLS variant returned HTTP ${mediaResponse.status}`);
    const mediaLines = mediaResponse ? (await mediaResponse.text()).split(/\r?\n/) : lines;
    const firstSegment = mediaLines.find((line) => line && !line.startsWith("#"));
    if (!firstSegment) fail("HLS variant has no segments yet");
    const probe = await fetch(new URL(firstSegment, mediaUrl), { headers: { Range: "bytes=0-1" } });
    await probe.body?.cancel();
    if (!probe.ok) fail(`HLS media segment returned HTTP ${probe.status}`);
    if (height && selected) source = mediaUrl;
    process.stdout.write(source + "\n");
  } finally {
    if (ws) ws.close();
    if (id) await fetch(`${cdp}/json/close/${encodeURIComponent(id)}`).catch(() => {});
  }
}

try { await main(); }
catch (error) { process.stderr.write(`YouTube browser fallback: ${error.message}\n`); process.exitCode = 1; }
