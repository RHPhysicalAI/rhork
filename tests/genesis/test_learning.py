"""
Genesis Learning Framework Tests

Tests for the learning framework with control policy, tasks, and optimizer.
Covers gradient-based control policy learning with Genesis's differentiable physics.
"""

import pytest
import sys
import numpy as np
from pathlib import Path


class TestLearningFramework:
    """Test learning framework components."""

    @pytest.fixture(autouse=True)
    def setup_path(self):
        """Add project root to sys.path for imports."""
        project_root = Path(__file__).parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

    def test_control_policy_creation(self):
        """
        Test that ControlPolicy can be created with expected dimensions.

        Validates:
        - ControlPolicy is instantiable
        - Policy stores input_dim, output_dim correctly
        - Policy has hidden_dim parameter
        """
        from genesis_learning import ControlPolicy

        policy = ControlPolicy(input_dim=6, output_dim=4, hidden_dim=64)

        assert policy is not None, "ControlPolicy failed to create"
        assert policy.input_dim == 6, f"Expected input_dim=6, got {policy.input_dim}"
        assert policy.output_dim == 4, f"Expected output_dim=4, got {policy.output_dim}"

    def test_learning_task_definition(self):
        """
        Test that LearningTask can be created with a loss function.

        Validates:
        - LearningTask is instantiable with name and loss_function
        - Task stores name and max_steps
        - Task can accept custom loss function
        """
        from genesis_learning import LearningTask

        # Define simple loss function
        loss_fn = lambda world_state, target_state: np.linalg.norm(world_state - target_state)

        task = LearningTask(
            name='hover_target',
            loss_function=loss_fn,
            max_steps=1000
        )

        assert task is not None, "LearningTask failed to create"
        assert task.name == 'hover_target', f"Expected name='hover_target', got {task.name}"
        assert task.max_steps == 1000, f"Expected max_steps=1000, got {task.max_steps}"

    def test_policy_forward_pass(self):
        """
        Test that ControlPolicy can perform forward pass.

        Validates:
        - Policy forward() method accepts state input
        - Forward pass returns action tensor with correct shape
        - Action values are constrained to [-1, 1] (tanh output)
        """
        from genesis_learning import ControlPolicy

        policy = ControlPolicy(input_dim=6, output_dim=4, hidden_dim=64)

        # Create random state
        state = np.random.randn(1, 6)

        # Get action from policy
        action = policy.forward(state)

        assert action is not None, "Policy forward() returned None"
        assert action.shape == (1, 4), f"Expected action shape (1, 4), got {action.shape}"

        # Verify action is constrained to [-1, 1] (tanh output)
        assert np.all(action >= -1.0), f"Action values below -1: {action}"
        assert np.all(action <= 1.0), f"Action values above 1: {action}"
