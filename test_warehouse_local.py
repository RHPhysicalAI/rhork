#!/usr/bin/env python3
"""Test warehouse world in Genesis container."""

import sys
from pathlib import Path

print("="*70)
print("WAREHOUSE WORLD TEST - Genesis Container")
print("="*70)

world_path = Path("/app/worlds/warehouse.gen").resolve()
print(f"\nLoading world from: {world_path}")

try:
    import genesis as gs
    print("✓ Genesis imported successfully")
    print(f"  Genesis version: {gs.__version__}")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Initialize Genesis
print("\nInitializing Genesis...")
try:
    gs.init()
    print("✓ Genesis initialized")
except Exception as e:
    print(f"✗ Failed to initialize: {e}")
    sys.exit(1)

# Load and create the world
print("\nLoading world module...")
with open(world_path, 'r') as f:
    source_code = f.read()

module_dict = {"gs": gs}
try:
    exec(compile(source_code, str(world_path), 'exec'), module_dict)
    print("✓ World module loaded")
except Exception as e:
    print(f"✗ Failed to load module: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nCreating world...")
try:
    world = module_dict["create_world"]()
    print("✓ Warehouse world created successfully")
except Exception as e:
    print(f"✗ Failed to create world: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Verify structure
print("\nVerifying world structure...")
try:
    print(f"✓ World object created: {type(world)}")

    # Try to step the world
    print("\nRunning physics simulation (10 steps)...")
    for step_num in range(10):
        world.step()
        if (step_num + 1) % 5 == 0:
            print(f"  Step {step_num + 1}/10 ✓")
    print("✓ Physics simulation completed")

except Exception as e:
    print(f"✗ Simulation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*70)
print("✓ WAREHOUSE WORLD TEST COMPLETED SUCCESSFULLY!")
print("="*70)
print("\nSummary:")
print(f"  World created:       True")
print(f"  Simulation steps:    10")
print(f"  World type:          {type(world).__name__}")
print("\n✓ All components working correctly!")
print("="*70 + "\n")
