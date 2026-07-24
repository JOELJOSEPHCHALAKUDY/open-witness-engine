"""owe_ros_bridge — non-blocking capture of robot decisions into OWE.

This package is the seam between a robot's ROS 2 graph (Open-RMF task lifecycle,
Nav2 behavior trees) and the OWE provenance core. It is observation-only and
fail-open: capture must never block, stall, or crash a robot process.

The ROS-specific I/O (subscriptions, message types) is intentionally left as thin
adapter seams so the transport, translation, and mapping logic stay pure and
testable without a running ROS stack.
"""
