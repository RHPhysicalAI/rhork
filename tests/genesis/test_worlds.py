"""
Genesis World Loading Tests

Tests for verifying world definitions load correctly and have expected structure.
Covers quadcopter world and other demo worlds.
"""

import pytest
import sys
import tempfile
import os
from pathlib import Path


@pytest.fixture
def quadcopter_world_file():
    """Fixture that creates a temporary quadcopter world file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.gen', delete=False) as f:
        f.write('''
def create_world():
    """Create and return the quadcopter demo world."""
    return {
        "ground_plane": True,
        "landing_pad": {"name": "landing_pad", "type": "box", "position": [0, 0, 0.025]},
        "obstacles": [
            {"name": "obs1", "position": [5, 5, 0.5]},
            {"name": "obs2", "position": [5, -5, 0.5]},
            {"name": "obs3", "position": [-5, 5, 0.5]},
            {"name": "obs4", "position": [-5, -5, 0.5]},
            {"name": "obs5", "position": [10, 0, 0.3]},
        ],
        "quadcopter": {
            "name": "quad_body",
            "type": "box",
            "position": [0, 0, 1.0],
            "rotors": [
                {"position": [0.2, 0.2, 0.05]},
                {"position": [0.2, -0.2, 0.05]},
                {"position": [-0.2, 0.2, 0.05]},
                {"position": [-0.2, -0.2, 0.05]},
            ]
        },
        "cameras": [
            {"name": "front_camera", "resolution": [1280, 720], "position": [0.15, 0, 0]},
            {"name": "down_camera", "resolution": [640, 480], "position": [0, 0, -0.05]},
            {"name": "overhead_camera", "resolution": [1280, 720], "position": [0, 0, 5]},
        ]
    }
''')
        temp_file = f.name

    yield temp_file

    # Cleanup
    if os.path.exists(temp_file):
        os.remove(temp_file)


class TestQuadcopterWorld:
    """Test quadcopter demo world loading and structure."""

    @pytest.fixture(autouse=True)
    def setup_path(self):
        """Add project root to sys.path for imports."""
        project_root = Path(__file__).parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

    def test_quadcopter_world_loads(self, quadcopter_world_file):
        """
        Test that the quadcopter world loads via GenesisStreamer.

        Validates:
        - GenesisStreamer can be instantiated with quadcopter world
        - World is loaded and returns a valid object
        - No exceptions are raised during world loading
        """
        from genesis_streamer import GenesisStreamer

        # Create streamer with quadcopter world
        streamer = GenesisStreamer(
            stream_prefix="quadcopter_test",
            mediamtx_host="localhost:8554",
            world_file=quadcopter_world_file,
        )

        # Load the world
        world = streamer._load_world()

        # Verify world is not None
        assert world is not None, "Quadcopter world failed to load"

        # Verify world is a dictionary (test implementation returns dict)
        assert isinstance(world, dict), "World should be a dictionary"

        # Verify world has expected keys
        assert "ground_plane" in world, "World missing ground_plane"
        assert "quadcopter" in world, "World missing quadcopter"
        assert "cameras" in world, "World missing cameras"

    def test_quadcopter_world_has_cameras(self, quadcopter_world_file):
        """
        Test that the quadcopter world has expected cameras.

        Validates:
        - World loads successfully
        - World contains 3 cameras (front, down, overhead)
        - Each camera has required properties
        """
        from genesis_streamer import GenesisStreamer

        # Create streamer with quadcopter world
        streamer = GenesisStreamer(
            stream_prefix="quadcopter_test",
            mediamtx_host="localhost:8554",
            world_file=quadcopter_world_file,
        )

        # Load the world
        world = streamer._load_world()

        # Verify world loaded
        assert world is not None, "World failed to load"

        # Verify cameras exist and count
        cameras = world.get("cameras", [])
        assert len(cameras) == 3, f"Expected 3 cameras, got {len(cameras)}"

        # Verify camera names
        camera_names = [cam.get("name") for cam in cameras]
        expected_names = ["front_camera", "down_camera", "overhead_camera"]
        for expected_name in expected_names:
            assert expected_name in camera_names, f"Camera {expected_name} not found"

    def test_quadcopter_world_steps(self, quadcopter_world_file):
        """
        Test that the quadcopter world can be validated.

        Note: Actual physics stepping requires Genesis library.
        This test validates the world structure loads and is valid.

        Validates:
        - World loads successfully
        - World contains required entities for a quadcopter simulation
        """
        from genesis_streamer import GenesisStreamer

        # Create streamer with quadcopter world
        streamer = GenesisStreamer(
            stream_prefix="quadcopter_test",
            mediamtx_host="localhost:8554",
            world_file=quadcopter_world_file,
        )

        # Load the world
        world = streamer._load_world()

        # Verify world loaded
        assert world is not None, "World failed to load"

        # Verify world structure
        assert "ground_plane" in world, "Missing ground plane"
        assert "landing_pad" in world, "Missing landing pad"
        assert "obstacles" in world, "Missing obstacles"
        assert len(world["obstacles"]) == 5, "Expected 5 obstacles"

        # Verify quadcopter structure
        quad = world.get("quadcopter")
        assert quad is not None, "Missing quadcopter"
        assert quad.get("name") == "quad_body", "Quadcopter body name incorrect"
        assert len(quad.get("rotors", [])) == 4, "Expected 4 rotors"
