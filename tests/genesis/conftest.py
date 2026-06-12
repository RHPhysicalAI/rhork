import pytest
import tempfile
import os


@pytest.fixture
def temp_world_file():
    """Fixture that creates a temporary .gen world file with a create_world function."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.gen', delete=False) as f:
        f.write('''
def create_world():
    """Create a test world."""
    return {
        "ground_plane": True,
        "objects": ["box1", "box2", "box3"],
        "cameras": [{"name": "overhead", "position": [0, 0, 5]}]
    }
''')
        temp_file = f.name

    yield temp_file

    # Cleanup
    if os.path.exists(temp_file):
        os.remove(temp_file)


@pytest.fixture
def streaming_config():
    """Fixture that provides streaming configuration."""
    return {
        "stream_prefix": "test-stream",
        "mediamtx_host": "localhost:8554",
        "world_file": None,
        "sim_step_freq": 100,
        "encoding_bitrate": "5000k",
        "encoding_fps": 30,
    }
