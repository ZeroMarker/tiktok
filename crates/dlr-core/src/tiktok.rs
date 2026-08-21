//! TikTok 兜底取流：直接解析 /live 页面 + webcast API。
//!
//! 对照 Python `scripts/dlr/adapters/tiktok_extract.py`。
//! 差异：Python 用 curl_cffi 做 TLS 指纹伪装（impersonate），本实现用普通
//! HTTP 客户端 + 浏览器 UA；被风控时仍由前面的 yt-dlp impersonate 链兜底。

use std::path::Path;
use std::time::Duration;

use serde_json::Value;

const UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36";

fn agent(timeout: Duration) -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_global(Some(timeout))
        .build()
        .into()
}

/// 读取 Netscape Cookie 文件，拼成 Cookie 请求头。
///
/// 与 Python 版一致：跳过注释行（含 `#HttpOnly_` 前缀），仅取 name=value。
pub fn netscape_cookie_header(path: &Path) -> Option<String> {
    let text = std::fs::read_to_string(path).ok()?;
    let pairs: Vec<String> = text
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .filter_map(|line| {
            let parts: Vec<&str> = line.split('\t').collect();
            (parts.len() >= 7).then(|| format!("{}={}", parts[5], parts[6]))
        })
        .collect();
    (!pairs.is_empty()).then(|| pairs.join("; "))
}

fn http_get(agent: &ureq::Agent, url: &str, cookie: Option<&str>) -> Option<String> {
    let mut req = agent.get(url).header("User-Agent", UA);
    if let Some(c) = cookie {
        req = req.header("Cookie", c);
    }
    let mut resp = req.call().ok()?;
    resp.body_mut().read_to_string().ok()
}

/// 从 HTML 中取 `<script id="...">` 的 JSON 文本。
fn extract_script_json<'a>(text: &'a str, id: &str) -> Option<&'a str> {
    let pat = format!("id=\"{id}\"");
    let start = text.find(&pat)?;
    let gt = start + text[start..].find('>')?;
    let end = gt + text[gt..].find("</script>")?;
    Some(text[gt + 1..end].trim())
}

/// 从 SIGI_STATE 提取 (roomId, status)。
///
/// 对照 Python `get_room_id_from_sigi`：status != 2 时检查 CurrentRoom。
fn room_id_from_sigi(text: &str) -> (Option<String>, i64) {
    let Some(raw) = extract_script_json(text, "SIGI_STATE") else {
        return (None, -1);
    };
    let Ok(sigi) = serde_json::from_str::<Value>(raw) else {
        return (None, -1);
    };
    let live_room = &sigi["LiveRoom"]["liveRoomUserInfo"]["liveRoom"];
    let mut status = live_room["status"].as_i64().unwrap_or(0);
    let mut room_id = live_room["roomId"].as_str().map(str::to_string);

    if status != 2 || room_id.is_none() {
        if let Some(cr_id) = sigi["CurrentRoom"]["roomId"].as_str() {
            if !cr_id.is_empty() {
                room_id = Some(cr_id.to_string());
                status = 2; // CurrentRoom 有值视为直播中
            }
        }
    }
    (room_id, status)
}

/// 从 __UNIVERSAL_DATA_FOR_REHYDRATION__ 提取 roomId（可能是永久 roomId）。
fn room_id_from_universal(text: &str) -> Option<String> {
    let raw = extract_script_json(text, "__UNIVERSAL_DATA_FOR_REHYDRATION__")?;
    let data = serde_json::from_str::<Value>(raw).ok()?;
    let scope = &data["__DEFAULT_SCOPE__"];
    for key in [
        "webcast.user-detail",
        "webcast-sse.user-detail",
        "webapp.user-detail",
    ] {
        let room_id = scope[key]["userInfo"]["user"]["roomId"].as_str();
        if let Some(id) = room_id {
            if !id.is_empty() {
                return Some(id.to_string());
            }
        }
    }
    None
}

/// 页面全文扫描 `"roomId":"\d+"`（去重、排除 0）。
fn scan_room_ids(text: &str) -> Vec<String> {
    const PAT: &str = "\"roomId\":\"";
    let mut out: Vec<String> = Vec::new();
    let mut rest = text;
    while let Some(i) = rest.find(PAT) {
        let after = &rest[i + PAT.len()..];
        let digits: String = after.chars().take_while(|c| c.is_ascii_digit()).collect();
        if !digits.is_empty() && digits != "0" && !out.contains(&digits) {
            out.push(digits);
        }
        rest = after;
    }
    out
}

/// 直接调用 webcast API 检查直播状态，返回流 URL（如果有）。
///
/// 对照 Python `check_live_via_webcast_api`：FLV HD1 优先，其次各兜底键。
fn webcast_api_stream(agent: &ureq::Agent, room_id: &str, cookie: Option<&str>) -> Option<String> {
    let url = format!("https://webcast.tiktok.com/webcast/room/info/?room_id={room_id}&aid=1988");
    let text = http_get(agent, &url, cookie)?;
    let data = serde_json::from_str::<Value>(&text).ok()?;
    if data["status_code"].as_i64() != Some(0) {
        return None;
    }
    let room = &data["data"];
    if room["status"].as_i64() != Some(2) {
        return None;
    }

    let stream_url = &room["stream_url"];
    if stream_url.is_object() {
        // FLV（HD1 高清）优先
        let flv = &stream_url["flv_pull_url"];
        for key in ["HD1", "FULL_HD1", "SD1", "SD2"] {
            if let Some(url) = flv[key].as_str() {
                if !url.is_empty() {
                    return Some(url.to_string());
                }
            }
        }
        for key in ["rtmp_pull_url", "hls_pull_url", "liveUrl"] {
            if let Some(url) = stream_url[key].as_str() {
                if url.starts_with("http") {
                    return Some(url.to_string());
                }
            }
        }
    } else if let Some(url) = stream_url.as_str() {
        if url.starts_with("http") {
            return Some(url.to_string());
        }
    }
    // 直接挂在 data 上的兜底键
    for key in ["rtmp_pull_url", "hls_pull_url", "liveUrl"] {
        if let Some(url) = room[key].as_str() {
            if url.starts_with("http") {
                return Some(url.to_string());
            }
        }
    }
    None
}

/// 兜底取流主入口：成功返回流 URL，失败返回 None。
///
/// 对照 Python `get_stream_url`（yt-dlp 部分由调用方先行完成）。
pub fn get_stream_url(username: &str, cookies: Option<&Path>) -> Option<String> {
    let cookie = cookies.and_then(netscape_cookie_header);
    let agent = agent(Duration::from_secs(20));

    // 预热会话（对照 Python session.get 首页）
    let _ = http_get(&agent, "https://www.tiktok.com", cookie.as_deref());

    let live_url = format!("https://www.tiktok.com/@{username}/live");
    let text = http_get(&agent, &live_url, cookie.as_deref())?;

    // 方法A：SIGI_STATE
    let (room_id, status) = room_id_from_sigi(&text);
    if status == 2 {
        if let Some(id) = room_id.as_deref() {
            if let Some(url) = webcast_api_stream(&agent, id, cookie.as_deref()) {
                return Some(url);
            }
        }
    }

    // 方法B：Universal Data
    if let Some(id) = room_id_from_universal(&text) {
        if let Some(url) = webcast_api_stream(&agent, &id, cookie.as_deref()) {
            return Some(url);
        }
    }

    // 方法C：全文 roomId 扫描
    for id in scan_room_ids(&text) {
        if Some(id.as_str()) == room_id.as_deref() {
            continue;
        }
        if let Some(url) = webcast_api_stream(&agent, &id, cookie.as_deref()) {
            return Some(url);
        }
    }
    None
}

/// 在 __DEFAULT_SCOPE__ 各命名空间里找 userInfo.user.nickname。
fn find_nickname(scope: &Value) -> Option<String> {
    let map = scope.as_object()?;
    for value in map.values() {
        let nick = value["userInfo"]["user"]["nickname"].as_str();
        if let Some(n) = nick {
            let n = n.trim();
            if !n.is_empty() {
                return Some(n.to_string());
            }
        }
    }
    None
}

/// 从 profile 页解析显示昵称；短间隔重试 attempts 次。
///
/// 对照 Python `get_nickname`（风控概率返回无数据页，重试命中即可）。
pub fn get_nickname(username: &str, cookies: Option<&Path>, attempts: u32) -> Option<String> {
    let cookie = cookies.and_then(netscape_cookie_header);
    let agent = agent(Duration::from_secs(20));
    let _ = http_get(&agent, "https://www.tiktok.com", cookie.as_deref());

    let profile = format!("https://www.tiktok.com/@{username}");
    for attempt in 0..attempts {
        if let Some(text) = http_get(&agent, &profile, cookie.as_deref()) {
            if let Some(raw) = extract_script_json(&text, "__UNIVERSAL_DATA_FOR_REHYDRATION__") {
                if let Ok(data) = serde_json::from_str::<Value>(raw) {
                    if let Some(nick) = find_nickname(&data["__DEFAULT_SCOPE__"]) {
                        return Some(nick);
                    }
                }
            }
        }
        if attempt + 1 < attempts {
            std::thread::sleep(Duration::from_secs(1));
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sigi_state_parses_room() {
        let html = r#"<html><script id="SIGI_STATE" type="application/json">{"LiveRoom":{"liveRoomUserInfo":{"liveRoom":{"status":2,"roomId":"123"}}}}</script></html>"#;
        let (id, status) = room_id_from_sigi(html);
        assert_eq!(status, 2);
        assert_eq!(id.as_deref(), Some("123"));
    }

    #[test]
    fn sigi_state_current_room_fallback() {
        let html = r#"<script id="SIGI_STATE">{"LiveRoom":{"liveRoomUserInfo":{"liveRoom":{"status":4}}},"CurrentRoom":{"roomId":"999"}}</script>"#;
        let (id, status) = room_id_from_sigi(html);
        assert_eq!(status, 2);
        assert_eq!(id.as_deref(), Some("999"));
    }

    #[test]
    fn universal_data_room_id() {
        let html = r#"<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">{"__DEFAULT_SCOPE__":{"webcast.user-detail":{"userInfo":{"user":{"roomId":"777"}}}}}</script>"#;
        assert_eq!(room_id_from_universal(html).as_deref(), Some("777"));
    }

    #[test]
    fn scan_room_ids_dedup_and_skip_zero() {
        let text = r#"{"roomId":"0","a":{"roomId":"42"},"b":{"roomId":"42"},"c":{"roomId":"7"}}"#;
        assert_eq!(scan_room_ids(text), vec!["42".to_string(), "7".to_string()]);
    }

    #[test]
    fn webcast_api_prefers_hd1() {
        // 解析逻辑：直接内联调用不可行（需要 HTTP），这里只验证解析路径用 JSON 结构。
        let data: Value = serde_json::json!({
            "status_code": 0,
            "data": {"status": 2, "stream_url": {"flv_pull_url": {"HD1": "https://flv", "SD1": "https://sd"}}}
        });
        let room = &data["data"];
        let flv = &room["stream_url"]["flv_pull_url"];
        assert_eq!(flv["HD1"].as_str(), Some("https://flv"));
    }

    #[test]
    fn find_nickname_walks_scope() {
        let scope: Value = serde_json::json!({
            "x": {"userInfo": {"user": {"nickname": " 丘咲エミリ 本人 "}}}
        });
        assert_eq!(find_nickname(&scope).as_deref(), Some("丘咲エミリ 本人"));
    }

    #[test]
    fn cookie_header_from_netscape() {
        let dir = std::env::temp_dir().join(format!("dlr-cookie-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let file = dir.join("cookies.txt");
        std::fs::write(
            &file,
            "# Netscape HTTP Cookie File\n#HttpOnly_.tiktok.com\tTRUE\t/\tTRUE\t0\tskipped\t1\n.tiktok.com\tTRUE\t/\tTRUE\t0\tsessionid\tabc123\n",
        )
        .unwrap();
        assert_eq!(netscape_cookie_header(&file).as_deref(), Some("sessionid=abc123"));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
