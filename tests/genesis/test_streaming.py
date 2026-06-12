import pytest
from genesis_streamer import GenesisStreamer


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
