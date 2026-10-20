# 阿里云机器翻译：可用备选方案

**状态（2026-10-20）：日译中 API 单次实测通过，可作为云端文本翻译方案。**
已通过 `--mt-backend aliyun` 接入 `livesub.py` 的手动测试入口，自动推流流程仍不启用字幕。
单次 API 验证及录像推流测试分开记录，持续直播的质量和稳定性尚未验收。

## 用途与接入参数

可在字幕流程中替代本地 Hy-MT2 翻译：

```text
直播音频 → ASR → 切句 → 阿里云机器翻译 → 字幕排期 → 编码推流
```

阿里云此接口接收文字，不处理音频，可移除本地翻译模型的常驻资源消耗。
短时录像推流的资源和字幕效果见 [2026-10-20 测试记录](livesub-aliyun-test-20261020.md)，
长时间运行稳定性尚未测量。原实验见 [实时字幕记录](livesub.md)。
字幕显示位置沿用该脚本的画面上方居中布局（距顶部 120 像素，日文在上、中文在下）。
画面缓冲延迟设为 **5 秒**，与 `livesub.py` 的 `--delay` 默认值一致；
短时测试结果见上述记录；单次 API 耗时不足以证明 5 秒内能完成整个字幕流程。

| 项目 | 本次验证值 |
|---|---|
| Endpoint | `https://mt.cn-hangzhou.aliyuncs.com/` |
| 调用方式 | HTTPS POST，RPC 签名，表单请求体 |
| Action / Version | `TranslateGeneral` / `2018-10-12` |
| Format / FormatType | `JSON` / `text` |
| SourceLanguage / TargetLanguage | `ja` / `zh` |
| Scene | `general` |
| 签名 | `HMAC-SHA1`，`SignatureVersion=1.0` |

用户最初提供的 [REST 调用文档](https://help.aliyun.com/zh/machine-translation/developer-reference/using-rest-api)
展示 `/api/translate/web/general` 路径；**本次实际验证的是上表中的 RPC 接口**，
参数以 [TranslateGeneral 文档](https://help.aliyun.com/zh/machine-translation/developer-reference/api-alimt-2018-10-12-translategeneral)
为准，两种请求格式不能混用。

## 凭据与复现

本机凭据已配置在 `~/.bashrc`，变量名为：

- `ALIBABA_CLOUD_ACCESS_KEY_ID`
- `ALIBABA_CLOUD_ACCESS_KEY_SECRET`

在交互式 Bash 中先执行 `source ~/.bashrc`，再运行以下代码。仅使用 Python 标准库，
不输出密钥或完整签名请求。每次执行会实际调用翻译服务；本次未验证账户额度或费用。
systemd 不会自动读取交互式 Shell 的 `~/.bashrc`；未来接入服务时需单独配置环境变量。

```bash
source ~/.bashrc
python3 - <<'PY'
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

key_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
if not key_id or not secret:
    raise SystemExit("未找到完整的阿里云凭据，请检查环境变量是否已 export")

params = {
    "Action": "TranslateGeneral", "Version": "2018-10-12",
    "Format": "JSON", "AccessKeyId": key_id,
    "SignatureMethod": "HMAC-SHA1", "SignatureVersion": "1.0",
    "SignatureNonce": str(uuid.uuid4()),
    "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "FormatType": "text", "SourceLanguage": "ja", "TargetLanguage": "zh",
    "SourceText": "皆さん、こんにちは。今日も配信を見に来てくれてありがとうございます。",
    "Scene": "general",
}
encode = lambda value: quote(str(value), safe="~")
canonical = "&".join(encode(k) + "=" + encode(v) for k, v in sorted(params.items()))
string_to_sign = "POST&%2F&" + encode(canonical)
params["Signature"] = base64.b64encode(hmac.new(
    (secret + "&").encode(), string_to_sign.encode(), hashlib.sha1
).digest()).decode()
request = Request(
    "https://mt.cn-hangzhou.aliyuncs.com/",
    data=urlencode(params).encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
)
started = time.monotonic()
try:
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
except HTTPError as error:
    # 只输出排障字段，不输出可能包含请求信息的完整错误正文。
    result = json.loads(error.read())
    print(json.dumps({"http_status": error.code, "Code": result.get("Code"),
                      "RequestId": result.get("RequestId")}, ensure_ascii=False))
    raise SystemExit(1)
except Exception as error:
    raise SystemExit("请求失败：" + type(error).__name__)
print(json.dumps({
    "Code": result.get("Code"), "RequestId": result.get("RequestId"),
    "Data": result.get("Data"),
    "elapsed_seconds": round(time.monotonic() - started, 3),
}, ensure_ascii=False, indent=2))
if str(result.get("Code")) != "200":
    raise SystemExit(1)
PY
```

## 实测结果

2026-10-20，本机加载上述环境变量后，发起一次日译中请求：

| 项目 | 结果 |
|---|---|
| 原文 | 皆さん、こんにちは。今日も配信を見に来てくれてありがとうございます。 |
| 译文 | 大家好，感谢大家今天也来看发布。 |
| 返回 Code | `200`（实际 JSON 中为字符串） |
| WordCount | `34` |
| 请求耗时 | `0.551` 秒（单次客户端请求耗时，含网络与服务端处理） |
| RequestId | `01A1581B-0947-5A53-BCA9-7BA6B7F89F00` |

接口调用成功，但「配信」被译成“发布”，在此场景应译为“直播”。单句结果只能证明接口
可调用，不能据此判断直播口语、人名和术语的整体质量，也不能将单次耗时视为稳定延迟。

## 接入实时字幕前待验证

- 用实际 ASR 输出评估口语、断句、人名和直播术语；云端翻译仍会受识别错误影响。
- 测量连续请求的延迟分布、吞吐和整机资源占用，再确定视频缓冲时间。
- 翻译请求在独立队列处理，设置超时、有限重试和过期字幕丢弃，避免阻塞取流与编码。
- 单独验证 `Context` 上下文参数的效果；本次请求未携带上下文。
- 确认账户计费、额度及接口限流，再安排持续直播测试。

这些工作完成前，仅在手动测试中使用，不接入自动字幕推流。
