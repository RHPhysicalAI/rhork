"""
Genesis Streaming Script

Main streaming script for Genesis World simulation with world loading and signal handling.
Provides a framework for streaming Genesis simulations via MediaMTX.
"""

import argparse
import importlib.util
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional, Dict, Any


# Configure logging at module level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class GenesisStreamer:
    """
    Main streaming class for Genesis World simulations.

    Handles world loading, signal management, and streaming orchestration.
    """

    def __init__(
        self,
        stream_prefix: str,
        mediamtx_host: str,
        world_file: Optional[str] = None,
        sim_step_freq: int = 100,
        encoding_bitrate: str = "5000k",
        encoding_fps: int = 30,
    ):
        """
        Initialize GenesisStreamer.

        Args:
            stream_prefix: Prefix for stream names (e.g., "genesis-stream")
            mediamtx_host: MediaMTX server address (e.g., "localhost:8554")
            world_file: Path to .gen world file (optional, uses minimal world if not provided)
            sim_step_freq: Simulation step frequency in Hz (default: 100)
            encoding_bitrate: Encoding bitrate (default: "5000k")
            encoding_fps: Encoding frames per second (default: 30)
        """
        self.stream_prefix = stream_prefix
        self.mediamtx_host = mediamtx_host
        self.world_file = world_file
        self.sim_step_freq = sim_step_freq
        self.encoding_bitrate = encoding_bitrate
        self.encoding_fps = encoding_fps

        self._running = True
        self._world = None

        # Register signal handlers
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        logger.info(
            f"GenesisStreamer initialized: prefix={stream_prefix}, "
            f"mediamtx={mediamtx_host}, world_file={world_file}"
        )

    def handle_signal(self, signum, frame):
        """
        Handle SIGTERM and SIGINT signals for graceful shutdown.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self._running = False

    def _load_world(self) -> Dict[str, Any]:
        """
        Load world from file or create minimal fallback.

        Returns:
            Dictionary representing the world configuration

        Raises:
            FileNotFoundError: If world_file is specified but doesn't exist
        """
        if self.world_file:
            if not os.path.exists(self.world_file):
                raise FileNotFoundError(f"World file not found: {self.world_file}")

            logger.info(f"Loading world from file: {self.world_file}")
            return self._load_world_from_file(self.world_file)
        else:
            logger.info("No world file specified, creating minimal world")
            return self._create_minimal_world()

    def _load_world_from_file(self, world_file: str) -> Dict[str, Any]:
        """
        Load a world from a .gen file using importlib.

        The .gen file must contain a create_world() function that returns
        a world configuration dictionary.

        Args:
            world_file: Path to the .gen file

        Returns:
            World configuration dictionary
        """
        world_path = Path(world_file).resolve()
        module_name = world_path.stem

        # Read the .gen file and compile it
        with open(world_path, 'r') as f:
            source_code = f.read()

        # Create a module namespace and execute the code
        module_dict = {}
        exec(compile(source_code, str(world_path), 'exec'), module_dict)

        # Call create_world() function from the executed module
        if "create_world" not in module_dict:
            raise AttributeError(
                f"World file {world_file} must contain a create_world() function"
            )

        create_world_fn = module_dict["create_world"]
        world = create_world_fn()

        logger.info(f"Successfully loaded world from {world_file}")
        return world

    def _create_minimal_world(self) -> Dict[str, Any]:
        """
        Create a minimal Genesis world with ground plane, falling objects, and camera.

        Returns:
            Minimal world configuration dictionary
        """
        world = {
            "ground_plane": True,
            "objects": [
                {"name": "box1", "type": "box", "position": [0, 0, 2]},
                {"name": "box2", "type": "box", "position": [1, 0, 3]},
                {"name": "box3", "type": "box", "position": [-1, 0, 4]},
            ],
            "cameras": [
                {
                    "name": "overhead",
                    "type": "camera",
                    "position": [0, 0, 5],
                    "lookat": [0, 0, 0],
                }
            ],
        }

        logger.info("Created minimal world with ground plane, 3 falling boxes, and overhead camera")
        return world

    def _discover_cameras(self) -> list:
        """
        Discover available cameras in the world.

        Placeholder for camera discovery logic.

        Returns:
            List of available cameras
        """
        if self._world is None:
            return []

        cameras = self._world.get("cameras", [])
        logger.info(f"Discovered {len(cameras)} cameras in world")
        return cameras

    def run(self) -> None:
        """
        Run the main simulation loop.

        This is a stub implementation that sets up signal handling and
        loads the world. Full streaming logic will be implemented in Task 3.
        """
        logger.info("Starting GenesisStreamer main loop")
        self._world = self._load_world()
        self._discover_cameras()

        logger.info("Simulation loop running (stub implementation)")

        # Main loop placeholder
        while self._running:
            # Simulation and streaming logic will be implemented here in Task 3
            pass

        logger.info("Simulation loop terminated")

    def run_viewer(self) -> None:
        """
        Run a viewer-only mode without simulation.

        This is a stub implementation for viewer-only operation.
        """
        logger.info("Starting GenesisStreamer in viewer mode (stub implementation)")

        while self._running:
            # Viewer logic will be implemented here
            pass

        logger.info("Viewer mode terminated")


def main():
    """
    Main entry point with argument parsing.
    """
    parser = argparse.ArgumentParser(
        description="Genesis World Streaming Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stream a world from file
  python genesis_streamer.py --stream-prefix my-stream --world-file world.gen

  # Stream with custom bitrate and fps
  python genesis_streamer.py --encoding-bitrate 8000k --encoding-fps 60

  # Stream in viewer mode
  python genesis_streamer.py --viewer
        """,
    )

    parser.add_argument(
        "--stream-prefix",
        default="genesis-stream",
        help="Prefix for stream names (default: genesis-stream)",
    )

    parser.add_argument(
        "--mediamtx-host",
        default="localhost:8554",
        help="MediaMTX server address (default: localhost:8554)",
    )

    parser.add_argument(
        "--world-file",
        default=None,
        help="Path to .gen world file (optional, uses minimal world if not provided)",
    )

    parser.add_argument(
        "--sim-step-freq",
        type=int,
        default=100,
        help="Simulation step frequency in Hz (default: 100)",
    )

    parser.add_argument(
        "--encoding-bitrate",
        default="5000k",
        help="Encoding bitrate (default: 5000k)",
    )

    parser.add_argument(
        "--encoding-fps",
        type=int,
        default=30,
        help="Encoding frames per second (default: 30)",
    )

    parser.add_argument(
        "--viewer",
        action="store_true",
        help="Run in viewer-only mode without simulation",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    # Create streamer instance
    streamer = GenesisStreamer(
        stream_prefix=args.stream_prefix,
        mediamtx_host=args.mediamtx_host,
        world_file=args.world_file,
        sim_step_freq=args.sim_step_freq,
        encoding_bitrate=args.encoding_bitrate,
        encoding_fps=args.encoding_fps,
    )

    # Run in appropriate mode
    try:
        if args.viewer:
            streamer.run_viewer()
        else:
            streamer.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
