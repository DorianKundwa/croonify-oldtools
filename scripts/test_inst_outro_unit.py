import os
import unittest
from unittest.mock import MagicMock, patch
import json
import uuid

# Mock config before importing app
import sys
from types import ModuleType

# Mock backend package
backend = ModuleType('backend')
backend.__path__ = [] # Mark it as a package
sys.modules['backend'] = backend

mock_config = ModuleType('backend.config')
mock_config.FFMPEG_PATH = 'ffmpeg'
mock_config.FFMPEG_ENCODER = 'libx264'
mock_config.FFMPEG_PRESET = 'ultrafast'
mock_config.FFMPEG_THREADS = 1
mock_config.FFMPEG_TUNE = None
mock_config.FFMPEG_CRF = 23
mock_config.UPLOAD_DIR = 'uploads'
mock_config.OUTPUT_DIR = 'outputs'
mock_config.ALIGN_DIR = 'alignments'
mock_config.FONTS_DIR = 'assets/fonts'
mock_config.OUTRO_ENABLED = True
mock_config.OUTRO_POSITION = 'center'
mock_config.OUTRO_BOX_COLOR = 'black'
mock_config.OUTRO_BOX_OPACITY = '0.5'
mock_config.OUTRO_FADE_IN_SEC = '0.5'
mock_config.OUTRO_FADE_OUT_SEC = '0.5'
mock_config.OUTRO_MESSAGE_TEXT = 'Thanks for watching'
mock_config.OUTRO_FONT_COLOR = 'white'

sys.modules['backend.config'] = mock_config
backend.config = mock_config

# Mock other backend modules
mock_audio = ModuleType('backend.audio_utils')
mock_audio.convert_to_wav = MagicMock()
mock_audio.normalize_audio = MagicMock()
mock_audio.get_duration = MagicMock()
mock_audio.detect_vocal_onset = MagicMock()
mock_audio.classify_vocal_segments = MagicMock()
mock_audio.detect_main_vocal_onset_from_alignment = MagicMock()
mock_audio.separate_stems = MagicMock()
mock_audio.align_offset_crosscorr = MagicMock()
mock_audio.shift_wav = MagicMock()
mock_audio.shift_alignment_times = MagicMock()
mock_audio.export_alignment_formats = MagicMock()
mock_audio.refine_word_alignment = MagicMock()
mock_audio.refine_syllable_alignment = MagicMock()
mock_audio.detect_vocal_segments_from_stem = MagicMock()
mock_audio.compute_separation_quality = MagicMock()
mock_audio.detect_breaks_and_pauses = MagicMock()
mock_audio.extract_audio_from_video = MagicMock()
sys.modules['backend.audio_utils'] = mock_audio
backend.audio_utils = mock_audio

mock_align = ModuleType('backend.alignment_hybrid')
mock_align.align = MagicMock()
sys.modules['backend.alignment_hybrid'] = mock_align
backend.alignment_hybrid = mock_align

mock_video = ModuleType('backend.video_builder')
mock_video.build_lyric_video = MagicMock()
mock_video.generate_thumbnail_image = MagicMock()
mock_video._find_font_path = MagicMock()
mock_video.extract_video_thumbnail = MagicMock()
mock_video.add_metadata = MagicMock()
sys.modules['backend.video_builder'] = mock_video
backend.video_builder = mock_video

# Now import app
# We'll use importlib to load it manually since it's in a subfolder but we mocked the package
import importlib.util
spec = importlib.util.spec_from_file_location("backend.app", "backend/app.py")
app = importlib.util.module_from_spec(spec)
sys.modules["backend.app"] = app
backend.app = app # Attach to backend module
spec.loader.exec_module(app)

class TestInstrumentalOutro(unittest.TestCase):
    def setUp(self):
        self.job_id = str(uuid.uuid4())
        app.jobs[self.job_id] = {
            "status": "processing",
            "total_tasks": 1,
            "completed_tasks": 0
        }
        self.session_dir = os.path.join('outputs', 'test_session')
        if not os.path.exists(self.session_dir):
            os.makedirs(self.session_dir, exist_ok=True)
        
        self.base_video = os.path.join(self.session_dir, "test_base.mp4")
        self.outro_path = "test_outro.mp3"
        self.files_to_keep = [self.base_video]
        
        # Create dummy files
        with open(self.base_video, "w") as f: f.write("dummy video")
        with open(self.outro_path, "w") as f: f.write("dummy outro")

    def tearDown(self):
        import shutil
        if os.path.exists(self.session_dir):
            shutil.rmtree(self.session_dir)
        if os.path.exists(self.outro_path):
            os.remove(self.outro_path)
        if os.path.exists('uploads'):
            shutil.rmtree('uploads')

    @patch('backend.app.convert_to_wav')
    @patch('backend.app.normalize_audio')
    @patch('backend.app.get_duration')
    @patch('backend.app.subprocess.run')
    @patch('backend.app.os.path.exists')
    def test_append_outro_instrumental_flow(self, mock_exists, mock_run, mock_duration, mock_norm, mock_conv):
        # Mock file existence checks
        mock_exists.side_effect = lambda p: True
        mock_duration.return_value = 5.0
        mock_run.return_value = MagicMock(returncode=0)
        
        # We need to simulate the file creation for the _final check
        final_path = self.base_video.replace(".mp4", "_final.mp4")
        
        # Mocking open for concat file
        with patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            app._append_outro_async(
                self.job_id,
                self.base_video,
                self.outro_path,
                is_instrumental=True,
                files_to_keep=self.files_to_keep
            )
            
        # Verify job was updated with instrumental keys
        self.assertIn("instrumental_video", app.jobs[self.job_id])
        self.assertIn("instrumental_video_url", app.jobs[self.job_id])
        self.assertEqual(app.jobs[self.job_id]["completed_tasks"], 1)
        
        # Verify cleanup attempt for intermediate
        # Note: In our test, the actual os.remove will fail because we mocked exists to True but didn't create all files
        # but we care about the logic flow.

    @patch('backend.app.build_lyric_video')
    @patch('backend.app.add_metadata')
    @patch('backend.app._append_outro_async')
    @patch('backend.app._mark_task_complete')
    @patch('backend.app.os.path.exists')
    def test_render_instrument_video_variant_async_with_outro(self, mock_exists, mock_mark, mock_append, mock_meta, mock_build):
        mock_exists.return_value = True
        mock_build.return_value = True
        mock_meta.side_effect = lambda p, out, title, artist: out
        
        # Simulate the final file existence check in _render_instrument_video_variant_async
        inst_output = os.path.join(self.session_dir, "inst.mp4")
        inst_final = inst_output.replace(".mp4", "_final.mp4")
        
        def exists_side_effect(p):
            if p == inst_final: return True
            return True
        mock_exists.side_effect = exists_side_effect

        app._render_instrument_video_variant_async(
            self.job_id,
            "vid.mp4",
            "inst.wav",
            "align.json",
            inst_output,
            "Arial",
            70,
            "Title",
            "Artist",
            outro_path="outro.mp3",
            files_to_keep=[]
        )
        
        # Verify _append_outro_async was called
        mock_append.assert_called_once()
        # Verify _mark_task_complete was NOT called directly (it's called inside _append_outro_async)
        mock_mark.assert_not_called()

    @patch('backend.app.build_lyric_video')
    @patch('backend.app.add_metadata')
    @patch('backend.app._mark_task_complete')
    @patch('backend.app.os.path.exists')
    def test_render_instrument_video_variant_async_no_outro(self, mock_exists, mock_mark, mock_meta, mock_build):
        mock_exists.side_effect = lambda p: p != "outro.mp3" # Outro doesn't exist
        mock_build.return_value = True
        mock_meta.side_effect = lambda p, out, title, artist: out
        
        inst_output = os.path.join(self.session_dir, "inst.mp4")
        
        app._render_instrument_video_variant_async(
            self.job_id,
            "vid.mp4",
            "inst.wav",
            "align.json",
            inst_output,
            "Arial",
            70,
            "Title",
            "Artist",
            outro_path="outro.mp3",
            files_to_keep=[]
        )
        
        # Verify _mark_task_complete was called because no outro was appended
        mock_mark.assert_called_once()
        # Verify job was updated
        self.assertIn("instrumental_video", app.jobs[self.job_id])

if __name__ == '__main__':
    unittest.main()
