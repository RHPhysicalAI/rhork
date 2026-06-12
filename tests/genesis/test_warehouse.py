"""Tests for the Genesis warehouse world."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_warehouse_world_loads():
    """Verify warehouse.gen world loads successfully."""
    import importlib.util
    from pathlib import Path

    world_path = Path("worlds/warehouse.gen").resolve()
    with open(world_path, 'r') as f:
        source_code = f.read()

    module_dict = {}
    exec(compile(source_code, str(world_path), 'exec'), module_dict)
    create_world = module_dict["create_world"]
    world = create_world()

    assert world is not None
    cameras = list(world.cameras())
    assert len(cameras) == 3


def test_warehouse_cameras():
    """Verify all three cameras are present with correct names."""
    from pathlib import Path

    world_path = Path("worlds/warehouse.gen").resolve()
    with open(world_path, 'r') as f:
        source_code = f.read()

    module_dict = {}
    exec(compile(source_code, str(world_path), 'exec'), module_dict)
    world = module_dict["create_world"]()

    camera_names = {cam.name for cam in world.cameras()}
    assert "overhead_cam" in camera_names
    assert "aisle_cam" in camera_names
    assert "entrance_cam" in camera_names


def test_warehouse_physics_step():
    """Verify world steps without errors for 10 simulation steps."""
    from pathlib import Path

    world_path = Path("worlds/warehouse.gen").resolve()
    with open(world_path, 'r') as f:
        source_code = f.read()

    module_dict = {}
    exec(compile(source_code, str(world_path), 'exec'), module_dict)
    world = module_dict["create_world"]()

    for _ in range(10):
        world.step()
    assert True


def test_warehouse_camera_frames():
    """Verify frames can be captured from all cameras."""
    from pathlib import Path

    world_path = Path("worlds/warehouse.gen").resolve()
    with open(world_path, 'r') as f:
        source_code = f.read()

    module_dict = {}
    exec(compile(source_code, str(world_path), 'exec'), module_dict)
    world = module_dict["create_world"]()

    world.step()
    for camera in world.cameras():
        frame = camera.rgb()
        assert frame is not None
        assert frame.shape == (720, 1280, 4)  # RGBA


def test_warehouse_geometry():
    """Verify warehouse has expected structure (ground, walls, shelves)."""
    from pathlib import Path

    world_path = Path("worlds/warehouse.gen").resolve()
    with open(world_path, 'r') as f:
        source_code = f.read()

    module_dict = {}
    exec(compile(source_code, str(world_path), 'exec'), module_dict)
    world = module_dict["create_world"]()

    entities = list(world.entities())
    assert len(entities) >= 25, f"Expected at least 25 entities, got {len(entities)}"
