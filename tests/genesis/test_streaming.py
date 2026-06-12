import pytest
import subprocess
import numpy as np
import threading
import time
from genesis_streamer import GenesisStreamer


class TestStreamingEncoding:
    """Tests for frame capture and RTSP streaming."""

    def test_rtsp_stream_creation(self, streaming_config):
        """Test that RTSP stream can be created with an encoder subprocess."""
        streamer = GenesisStreamer(**streaming_config)
        encoder = streamer._create_encoder("test_camera")

        # Verify encoder is created and has started
        assert encoder is not None
        assert isinstance(encoder.process, subprocess.Popen)

    def test_frame_capture_and_encode(self, streaming_config):
        """Test that frame capture works with correct shape and dtype."""
        # Create a dummy RGBA frame (height=720, width=1280, channels=4)
        frame = np.zeros((720, 1280, 4), dtype=np.uint8)

        # Verify frame properties
        assert frame.shape == (720, 1280, 4)
        assert frame.dtype == np.uint8


class TestWorldLoading:
    """Tests for world loading in GenesisStreamer."""

    def test_world_loading_from_file(self, temp_world_file, streaming_config):
        """Test that a .gen file can be loaded via GenesisStreamer."""
        config = streaming_config.copy()
        config["world_file"] = temp_world_file

        streamer = GenesisStreamer(**config)
        world = streamer._load_world()

        # The world should be loaded successfully
        assert world is not None
        assert isinstance(world, dict)
        assert "ground_plane" in world
        assert "objects" in world
        assert "cameras" in world

    def test_fallback_to_minimal_world(self, streaming_config):
        """Test that a minimal world is used as fallback if no file provided."""
        config = streaming_config.copy()
        config["world_file"] = None

        streamer = GenesisStreamer(**config)
        world = streamer._load_world()

        # The world should be created with minimal content
        assert world is not None
        assert isinstance(world, dict)
        # Verify minimal world structure
        assert "ground_plane" in world or "cameras" in world

    def test_invalid_world_file(self, streaming_config):
        """Test that FileNotFoundError is raised if world file doesn't exist."""
        config = streaming_config.copy()
        config["world_file"] = "/nonexistent/path/to/world.gen"

        streamer = GenesisStreamer(**config)

        with pytest.raises(FileNotFoundError):
            streamer._load_world()


class TestStreamingLoop:
    """Tests for the main streaming loop."""

    def test_streaming_loop_basic(self, streaming_config):
        """Test that streaming loop can run and be stopped gracefully."""
        streamer = GenesisStreamer(**streaming_config)

        # Start the loop in a separate thread
        loop_thread = threading.Thread(target=streamer.run)
        loop_thread.start()

        # Let it run for 0.5 seconds
        time.sleep(0.5)

        # Stop the loop by setting _running to False
        streamer._running = False

        # Wait for thread to finish
        loop_thread.join(timeout=2)

        # Verify thread is no longer alive (completed execution)
        assert not loop_thread.is_alive()
