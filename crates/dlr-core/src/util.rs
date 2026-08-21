//! 通用工具：路径清洗与频道标识提取。
//!
//! 与 Python 版 scripts/dlr 行为保持一致。

/// 清洗路径片段：保留可打印字符（含中文/日文/emoji 昵称），
/// 去控制字符、空白转下划线、替换文件名非法字符、限长 120。
pub fn sanitize_path_part(value: &str) -> String {
    // Python str.isprintable()：丢弃控制字符（\t \n \r 等），保留空格与可见字符。
    let cleaned: String = value.chars().filter(|c| !c.is_control()).collect();
    let cleaned = cleaned.trim();

    let mut out = String::with_capacity(cleaned.len());
    let mut prev_ws = false; // \s+ 折叠为一个 _
    for c in cleaned.chars() {
        if matches!(c, '/' | '\\' | ':' | '*' | '?' | '"' | '<' | '>' | '|') {
            out.push('_');
            prev_ws = false;
        } else if c.is_whitespace() {
            if !prev_ws {
                out.push('_');
            }
            prev_ws = true;
        } else {
            out.push(c);
            prev_ws = false;
        }
    }
    // 等价于 .strip(" .")：两端去掉空格与点
    let out = out.trim_matches(|c| c == ' ' || c == '.');
    out.chars().take(120).collect()
}

/// 从 URL 或标识中提取频道段：去查询串、去斜杠、去 @。
///
/// 优先识别 @handle 形式（TikTok/YouTube），其次去掉常见动作后缀再取末段。
pub fn extract_last_segment(raw: &str) -> String {
    let trimmed = raw.trim();
    let end = trimmed.find(['?', '#']).unwrap_or(trimmed.len());
    let cleaned = trimmed[..end].trim_end_matches('/');

    // 等价于 re.search(r"@([^/?#]+)", cleaned)：扫描每个 @，取首个有效捕获。
    let mut search = cleaned;
    while let Some(at) = search.find('@') {
        let rest = &search[at + 1..];
        let seg_end = rest.find(['/', '?', '#']).unwrap_or(rest.len());
        let seg = &rest[..seg_end];
        if !seg.is_empty() {
            return seg.trim_start_matches('@').to_string();
        }
        search = rest;
    }

    // 去掉结尾的 /live|/streams|/videos|/about
    let mut stripped = cleaned;
    for suffix in ["/live", "/streams", "/videos", "/about"] {
        if let Some(head) = stripped.strip_suffix(suffix) {
            stripped = head;
            break;
        }
    }
    stripped
        .rsplit('/')
        .next()
        .unwrap_or(stripped)
        .trim_start_matches('@')
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitize_keeps_cjk_and_emoji() {
        assert_eq!(sanitize_path_part("丘咲エミリ 本人🍣"), "丘咲エミリ_本人🍣");
    }

    #[test]
    fn sanitize_replaces_illegal_chars() {
        assert_eq!(sanitize_path_part("a/b\\c:d*e?f\"g<h>i|j"), "a_b_c_d_e_f_g_h_i_j");
    }

    #[test]
    fn sanitize_drops_control_and_trims_dots() {
        // \t 与 \n 是控制字符（isprintable=False），直接丢弃而非转下划线。
        assert_eq!(sanitize_path_part("  .\ta\nb.  "), "ab");
    }

    #[test]
    fn sanitize_limits_to_120_chars() {
        let long = "x".repeat(200);
        assert_eq!(sanitize_path_part(&long).chars().count(), 120);
    }

    #[test]
    fn extract_from_plain_handle() {
        assert_eq!(extract_last_segment("kobiritukii"), "kobiritukii");
        assert_eq!(extract_last_segment("@kobiritukii"), "kobiritukii");
    }

    #[test]
    fn extract_from_tiktok_url() {
        assert_eq!(
            extract_last_segment("https://www.tiktok.com/@emiri.okazaki/live"),
            "emiri.okazaki"
        );
    }

    #[test]
    fn extract_from_url_with_query() {
        assert_eq!(
            extract_last_segment("https://www.youtube.com/@foo/live?si=abc#frag"),
            "foo"
        );
    }

    #[test]
    fn extract_from_kick_and_chzzk() {
        assert_eq!(extract_last_segment("https://kick.com/playerid"), "playerid");
        assert_eq!(
            extract_last_segment("https://chzzk.naver.com/live/abcdef"),
            "abcdef"
        );
    }

    #[test]
    fn extract_from_youtube_channel_url() {
        assert_eq!(
            extract_last_segment("https://www.youtube.com/channel/UCxxxx/videos"),
            "UCxxxx"
        );
    }
}
