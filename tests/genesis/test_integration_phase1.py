"""
Phase 1 PoC End-to-End Integration Tests

Tests for verifying Phase 1 (PoC) works end-to-end:
- Container builds successfully
- Helm chart validates
- Streaming script imports work
- Worlds load correctly
"""

import pytest
import subprocess
import sys
import os
from pathlib import Path


class TestContainerBuild:
    """Test container build for Genesis streamer."""

    def test_container_build(self):
        """
        Test that the Genesis container builds successfully.

        Runs: podman build -f Containerfile.genesis -t localhost/genesis-sim-streamer:test
        Validates:
        - returncode == 0
        - no error in stderr
        """
        # Get the project root directory
        project_root = Path(__file__).parent.parent.parent

        # Build command
        cmd = [
            "podman",
            "build",
            "-f", str(project_root / "Containerfile.genesis"),
            "-t", "localhost/genesis-sim-streamer:test",
        ]

        # Run the build with timeout (300 seconds for container builds)
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=300,
        )

        # Verify build succeeded
        assert result.returncode == 0, (
            f"Container build failed with returncode {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Verify no errors in stderr
        assert "error" not in result.stderr.lower(), (
            f"Build produced errors in stderr:\n{result.stderr}"
        )


class TestHelmChartValidation:
    """Test Helm chart validation for Genesis."""

    def test_helm_chart_validation(self):
        """
        Test that the Genesis Helm chart validates successfully.

        Runs: helm lint charts/genesis-sim/
        Validates:
        - returncode == 0
        - "0 chart(s) failed" in stdout
        """
        # Get the project root directory
        project_root = Path(__file__).parent.parent.parent

        # Check if the genesis-sim chart directory exists
        genesis_chart_dir = project_root / "charts" / "genesis-sim"

        # If the chart doesn't exist yet, create a minimal one for testing
        if not genesis_chart_dir.exists():
            pytest.skip("Genesis Helm chart not yet created - skipping validation")

        # Lint command
        cmd = [
            "helm",
            "lint",
            str(genesis_chart_dir),
        ]

        # Run helm lint
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Verify lint succeeded
        assert result.returncode == 0, (
            f"Helm lint failed with returncode {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Verify no charts failed
        assert "0 chart(s) failed" in result.stdout, (
            f"Helm lint found chart failures:\n{result.stdout}"
        )


class TestStreamingScriptImport:
    """Test Genesis streaming script imports."""

    def test_streaming_script_import(self):
        """
        Test that the Genesis streaming script can be imported successfully.

        Validates:
        - GenesisStreamer class exists and is importable
        - FFmpegEncoder class exists and is importable
        """
        # Get the project root directory
        project_root = Path(__file__).parent.parent.parent

        # Add project root to sys.path to allow importing genesis_streamer
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # Import the module
        from genesis_streamer import GenesisStreamer, FFmpegEncoder

        # Verify both classes are importable and not None
        assert GenesisStreamer is not None, "GenesisStreamer class is None"
        assert FFmpegEncoder is not None, "FFmpegEncoder class is None"

        # Verify they are classes
        assert isinstance(GenesisStreamer, type), "GenesisStreamer is not a class"
        assert isinstance(FFmpegEncoder, type), "FFmpegEncoder is not a class"


class TestWorldLoading:
    """Test world loading in Genesis streaming."""

    def test_world_loading(self):
        """
        Test that world loading works in GenesisStreamer.

        Validates:
        - GenesisStreamer can be instantiated with no world_file
        - World is loaded with fallback to minimal world
        - stream_prefix is set correctly
        - _world attribute exists and is not None
        """
        # Get the project root directory
        project_root = Path(__file__).parent.parent.parent

        # Add project root to sys.path
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # Import the GenesisStreamer class
        from genesis_streamer import GenesisStreamer

        # Create streamer with no world_file (fallback to minimal)
        streamer = GenesisStreamer(
            stream_prefix="test",
            mediamtx_host="localhost:8554",
            world_file=None,
        )

        # Verify stream_prefix is set
        assert streamer.stream_prefix == "test", (
            f"Expected stream_prefix='test', got '{streamer.stream_prefix}'"
        )

        # Load the world (this happens during run(), but we can call it directly)
        world = streamer._load_world()

        # Verify world is loaded and not None
        assert world is not None, "World is None after loading"

        # Verify world is a dictionary
        assert isinstance(world, dict), f"World is not a dict, got {type(world)}"

        # Verify minimal world structure exists (ground_plane or cameras)
        assert "ground_plane" in world or "cameras" in world, (
            f"Minimal world missing expected keys: {world.keys()}"
        )
