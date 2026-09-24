#!/usr/bin/env bash
# 运行仓库全部 Python 单元测试（标准库 unittest，无需安装额外依赖）。
#
#   bash test.sh
#
# 覆盖：tests/（录制引擎 + 录制 WebUI）、bili/tests/（Bilibili 推流 + 推流 WebUI）。
set -euo pipefail
cd "$(dirname "$0")"

echo "== tests/（录制引擎 + 录制 WebUI）=="
python3 -m unittest discover -s tests

echo "== bili/tests/（Bilibili 推流 + 推流 WebUI）=="
python3 -m unittest discover -s bili/tests

echo "全部测试通过。"
