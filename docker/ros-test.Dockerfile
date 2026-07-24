# ROS 2 image for the OWE integration check (docs/ros2-testing.md).
FROM ros:jazzy-ros-base
RUN apt-get update -qq \
 && apt-get install -y -qq python3-pip >/dev/null \
 && python3 -m pip install --break-system-packages -q pydantic \
 && rm -rf /var/lib/apt/lists/*
