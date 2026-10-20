"""push.sh 开启字幕时实际执行的命令，隔离 HOME、服务和网络。"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class SubtitleLauncherTest(unittest.TestCase):
    def test_enabled_routes_to_cloud_subtitle_pipeline(self):
        script = Path(__file__).resolve().parents[1] / 'push.sh'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'bin'
            binary.mkdir()
            config = root / '.config/bili'
            config.mkdir(parents=True)
            (config / 'subtitle.env').write_text('SUBTITLES=1\n')
            for name in ('yt-dlp', 'ffmpeg', 'python3'):
                path = binary / name
                path.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE"\n')
                path.chmod(0o755)
            capture = root / 'args'
            env = dict(os.environ, HOME=str(root), PATH=str(binary) + ':' + os.environ['PATH'],
                       BILI_FFMPEG=str(binary / 'ffmpeg'), BILIBILI_PUSH_URL='rtmp://example/',
                       BILIBILI_PUSH_CODE='test-code', CAPTURE=str(capture))
            result = subprocess.run(['bash', str(script), 'test_streamer'], cwd=root,
                                    env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = capture.read_text().splitlines()
            self.assertEqual(Path(args[0]).name, 'livesub.py')
            self.assertEqual(args[1:], ['test_streamer', '--out', 'rtmp', '--delay', '5',
                                       '--mt-backend', 'aliyun', '--workdir', './logs/livesub'])


if __name__ == '__main__':
    unittest.main()
