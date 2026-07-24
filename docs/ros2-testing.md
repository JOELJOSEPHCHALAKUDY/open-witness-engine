# Running the ROS 2 integration check

The unit/property/volume suite runs without ROS. This check exercises the *live*
path — a real `rclpy` executor, real DDS transport, real timers — through OWE's
production capture code, in a container. No robot or simulator required.

It was validated on **ROS 2 Jazzy**: two task-summary messages published over real
DDS were captured by OWE's `capture_rmf_task`, drained into the store, and answered
correctly by `explain_decision` (robot-3/succeeded, robot-7/failed).

## Run it

```bash
docker build -t owe-ros:jazzy -f docker/ros-test.Dockerfile docker
docker run --rm -v "$PWD/src:/owe_src:ro" -v "$PWD/examples:/ex:ro" owe-ros:jazzy \
  bash -lc 'source /opt/ros/jazzy/setup.bash && \
    PYTHONPATH=/owe_src:$PYTHONPATH python3 /ex/ros2_integration.py'
```

Exit code `0` and `RESULT: PASS` means the live path works.

## Scope and the remaining seam

This drives OWE's real capture path over a real ROS graph, but uses
`std_msgs/String` (carrying JSON) as a stand-in for `rmf_task_msgs/TaskSummary`,
which is not in a base ROS image. Two things are still required for production on a
real fleet:

1. Confirm the message-field mapping in `bridge/ros_node.py` against your distro's
   actual `rmf_task_msgs` / Nav2 message definitions.
2. Run against a real Open-RMF / Nav2 stack (Gazebo sim or hardware), which needs a
   full simulation environment beyond this container.
