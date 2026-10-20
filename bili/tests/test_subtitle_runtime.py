"""字幕队列过载与输出停滞恢复，不加载模型。"""
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import subtitle_runtime as runtime
import subtitle_config


class SubtitleRuntimeTest(unittest.TestCase):
    def test_queue_keeps_recent_sentences_and_shutdown_marker(self):
        items = queue.Queue(maxsize=2)
        for item in ('old', 'recent', 'new'):
            runtime.offer_latest(items, item)
        self.assertEqual(items.get_nowait(), 'recent')
        runtime.offer_latest(items, 'last')
        runtime.offer_latest(items, None)
        self.assertEqual(items.get_nowait(), 'last')
        self.assertIsNone(items.get_nowait())

    def test_progress_reads_latest_timestamp_even_when_file_grows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'progress'
            path.write_text('padding\n' * 20000 + 'out_time_us=100\nout_time_us=200\n')
            self.assertEqual(runtime.output_time(path), 200)

    def test_stalled_output_stops_both_processes(self):
        puller, pusher, stop = mock.Mock(), mock.Mock(), mock.Mock()
        pusher.poll.return_value = None
        stop.wait.side_effect = [False, False]
        failed = threading.Event()
        with mock.patch.object(runtime, 'output_time', return_value=123), \
                mock.patch.object(runtime.time, 'monotonic', side_effect=[0, 1, 2, 62]):
            runtime.watch_pipeline(puller, pusher, Path('unused'), stop, failed, mock.Mock())
        self.assertTrue(failed.is_set())
        puller.terminate.assert_called_once()
        pusher.terminate.assert_called_once()

    def test_encoder_failure_unblocks_audio_reader(self):
        puller, pusher, stop = mock.Mock(), mock.Mock(), mock.Mock()
        pusher.poll.return_value = 1
        stop.wait.return_value = False
        failed = threading.Event()
        runtime.watch_pipeline(puller, pusher, Path('unused'), stop, failed, mock.Mock())
        self.assertTrue(failed.is_set())
        puller.terminate.assert_called_once()

    def test_natural_end_is_not_a_fault(self):
        puller, pusher, stop = mock.Mock(), mock.Mock(), mock.Mock()
        puller.poll.return_value = pusher.poll.return_value = 0
        stop.wait.return_value = False
        failed = threading.Event()
        runtime.watch_pipeline(puller, pusher, Path('unused'), stop, failed, mock.Mock())
        self.assertFalse(failed.is_set())
        puller.terminate.assert_not_called()

    def test_credential_reader_does_not_evaluate_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'aliyun.env'
            path.write_text('export ALIBABA_CLOUD_ACCESS_KEY_ID="test-key"\n'
                            "ALIBABA_CLOUD_ACCESS_KEY_SECRET='$(no-execution)`literal`'\n")
            self.assertEqual(subtitle_config.read_credentials(path), {
                'ALIBABA_CLOUD_ACCESS_KEY_ID': 'test-key',
                'ALIBABA_CLOUD_ACCESS_KEY_SECRET': '$(no-execution)`literal`',
            })


if __name__ == '__main__':
    unittest.main()
