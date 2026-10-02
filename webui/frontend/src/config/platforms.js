export const PLATFORM_ZH = {
  tiktok: "TikTok",
  soop: "SOOP",
  kick: "Kick",
  youtube: "YouTube",
  chzzk: "CHZZK",
  twitch: "Twitch",
};

export const LOGO_COLORS = {
  tiktok: "#fb7185",
  soop: "#60a5fa",
  kick: "#4ade80",
  youtube: "#f87171",
  chzzk: "#2dd4bf",
  twitch: "#c4a7ff",
};

export const QUALITY_ZH = { best: "原画", "1080p": "1080p", "720p": "720p", "480p": "480p" };
export const QUALITIES = ["best", "1080p", "720p", "480p"];

export const PLATFORM_HINTS = {
  tiktok: ["TikTok 用户名，如 akane.no.1", "输入 TikTok 用户名或完整直播地址。"],
  soop: ["SOOP 用户名或直播 URL", "输入主播用户名或 play.sooplive.co.kr 地址。"],
  kick: ["Kick 用户名或直播 URL", "输入 Kick 频道名或完整地址。"],
  youtube: ["YouTube @handle 或直播 URL", "支持频道直播页和具体直播链接。"],
  chzzk: ["CHZZK 频道 ID 或直播 URL", "输入频道 ID 或 chzzk.naver.com/live 地址。"],
  twitch: ["Twitch 用户名，如 shroud", "输入 Twitch 用户名或 twitch.tv 频道地址；不支持点播或剪辑地址。"],
};

export const PLATFORM_KEYS = Object.keys(PLATFORM_ZH);
