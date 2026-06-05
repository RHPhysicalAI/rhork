# gz-camera-stream

A world-level system plugin for Gazebo Sim that streams H.264 video from camera sensors to a media server via WHIP or RTSP. Frames are captured in the PostRender callback, converted from RGB/RGBA to YUV420P, encoded with libx264 (ultrafast/zerolatency), and pushed to the configured endpoint. The plugin is idle by default and activates on demand through a gz-transport control topic.

## How it works

```
Gazebo (OGRE2 render) -> PostRender callback -> RGB->YUV420P (swscale) -> H.264 (libx264) -> WHIP or RTSP -> Media Server
```

The plugin registers a `PostRender` event handler that fires after each render pass. For each active stream, it copies the camera image, queues it into a lock-free SPSC ring buffer, and a dedicated encoder thread picks it up, scales it, encodes it, and writes the packet to the output. One encoder thread per stream - they sleep on a condition variable when idle and never block the render thread.

### Output protocols

The plugin auto-detects the output protocol from the URL scheme:

| URL scheme | Protocol | FFmpeg muxer | Notes |
|-----------|----------|-------------|-------|
| `http://` / `https://` | WHIP | `whip` | WebRTC HTTP Ingest Protocol. Requires FFmpeg 7+ with the WHIP muxer compiled in. Lowest latency path to WebRTC viewers. |
| `rtsp://` | RTSP | `rtsp` | Real Time Streaming Protocol. Available in all FFmpeg builds. Uses TCP transport in container environments for reliability. MediaMTX converts to WebRTC/HLS automatically. |

If the WHIP muxer isn't available in the FFmpeg build (common with distro packages), the plugin logs a clear error and suggests using an `rtsp://` URL instead. Both protocols deliver H.264 to MediaMTX, which handles conversion to WebRTC (WHEP), HLS, or RTMP for downstream consumers.

## Plugin architecture

```
src/
  CameraStream.hh/.cc     World-level system plugin (ISystemConfigure + ISystemPostUpdate)
  StreamContext.hh/.cc     Per-stream FFmpeg encoder + network output
  FrameQueue.hh            Lock-free SPSC ring buffer (render thread -> encoder thread)
```

### CameraStream (world plugin)

Implements `ISystemConfigure` and `ISystemPostUpdate`. On `Configure()`, it reads SDF parameters and subscribes to the control topic (both as a topic subscriber and a service, so it works from CLI and WebSocket). On `PostRender()`, it iterates active streams, lazy-initializes camera pointers by matching sensor names (supports short names, scoped names, and suffix matching against the rendering scene), copies frames, and pushes them into each stream's ring buffer. Failed streams are reaped automatically after 30 consecutive write failures.

### StreamContext (per-stream encoder)

Each `StreamContext` owns a dedicated encoder thread and the full FFmpeg pipeline: `AVCodecContext` (libx264, ultrafast/zerolatency), `SwsContext` (RGB/RGBA to YUV420P), and `AVFormatContext` (WHIP or RTSP output). The sws context is created lazily on the first frame to detect the actual pixel format (3-channel RGB vs 4-channel RGBA) from the rendering backend. WHIP connections retry up to 3 times with 2-second delays to handle DTLS port reuse after a prior session.

### FrameQueue (render-to-encoder bridge)

A 3-slot SPSC ring buffer. The render thread calls `TryPush()` which never blocks - if the encoder is behind, the oldest frame is overwritten (frame dropping over blocking). The encoder thread calls `WaitAndPop()` which blocks on a condition variable until a frame is available or a timeout expires. This keeps encoder threads at near-zero CPU when no frames are being produced.

## SDF configuration

Add the plugin to any Gazebo world:

```xml
<plugin filename="gz-sim-camera-stream-system"
        name="gz::sim::systems::CameraStream">
  <topic>/stream/control</topic>
  <default_bitrate>4000000</default_bitrate>
  <default_fps>30</default_fps>
  <stream_prefix>my_robot</stream_prefix>
  <mediamtx_base>rtsp://mediamtx:8554</mediamtx_base>
</plugin>
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `topic` | `/stream/control` | gz-transport topic and service for stream start/stop commands |
| `default_bitrate` | `4000000` | H.264 encoding bitrate in bps |
| `default_fps` | `30` | Encoding framerate |
| `stream_prefix` | *(none)* | Path prefix prepended to all stream URLs (e.g., `my_robot` produces `rtsp://host/my_robot/cam1`). Also reads from `STREAM_PREFIX` env var. |
| `mediamtx_base` | *(none)* | Base URL for the media server. When set, the plugin constructs output URLs internally instead of requiring them in the start command. Also reads from `MEDIAMTX_WHIP_BASE` env var. |

When `mediamtx_base` is set, the plugin constructs the full output URL from `<mediamtx_base>/<stream_prefix>/<camera_name>`. The URL in the start command is ignored. When `mediamtx_base` is not set, the start command must include the full output URL (the original behavior for local development).

## Stream control

Start and stop streams by publishing `gz.msgs.StringMsg_V` to the control topic:

```bash
# Start streaming via WHIP (requires FFmpeg 7+ with WHIP muxer)
gz topic -t /stream/control -m gz.msgs.StringMsg_V \
  -p 'data: "start" data: "camera_name" data: "http://localhost:8889/cam1/whip"'

# Start streaming via RTSP
gz topic -t /stream/control -m gz.msgs.StringMsg_V \
  -p 'data: "start" data: "camera_name" data: "rtsp://localhost:8554/cam1"'

# Start with custom bitrate (2 Mbps) and fps (15)
gz topic -t /stream/control -m gz.msgs.StringMsg_V \
  -p 'data: "start" data: "cam1" data: "rtsp://localhost:8554/cam1" data: "2000000" data: "15"'

# Stop
gz topic -t /stream/control -m gz.msgs.StringMsg_V \
  -p 'data: "stop" data: "camera_name"'
```

The control topic also works as a gz-transport service, which means it can be called from the WebSocket server interface (used by `viewer.html`).

### Message format

**Start:** `data=["start", "<camera_name>", "<url>", "<bitrate>", "<fps>"]`

- `camera_name` - sensor name to match. Can be a short name (`cam1`), a topic-style name (`X3/front_camera`), or a fully scoped rendering name (`sensor_pod::pod_link::front_camera`). The plugin tries exact match first, then suffix match against all sensors in the scene.
- `url` - WHIP (`http://...`) or RTSP (`rtsp://...`) endpoint. Optional when `mediamtx_base` is set.
- `bitrate` / `fps` - optional overrides for this stream.

**Stop:** `data=["stop", "<camera_name>"]`

## Camera name matching

When a stream start request arrives, the plugin needs to find the corresponding camera in the rendering scene. Rendering sensor names are fully scoped (e.g., `sensor_pod::pod_link::front_camera`) while the request might use a short name (`front_camera`) or a topic-style name (`X3/front_camera`). The plugin resolves this in order:

1. Exact match against `Scene::SensorByName()`
2. Extract the short name (last segment after `/`) and try exact match
3. Suffix match - scan all sensors looking for one whose name ends with `::<short_name>`

This means you can refer to cameras by whatever name is most convenient. The matching is logged at the `msg` level so you can see which rendering sensor was resolved.

## Viewer

`viewer.html` is a single-file web UI that connects to both the Gazebo WebSocket server (port 9002, for topic discovery and telemetry) and a MediaMTX instance (for WebRTC video playback). It provides:

- Camera stream player with WebRTC (WHEP) playback
- Topic tree with type-based filtering and icons
- Live telemetry cards for subscribed topics (Pose, Odometry with attitude indicator and altitude sparkline, Clock, WorldStatistics, CameraInfo, Twist, and generic key-value fallback)
- Stream control through the sidebar (click a camera to start/stop streaming)
- Demand-based encoding: streams start when a viewer requests them and stop when all viewers disconnect

The viewer works locally (hardcoded localhost defaults) and in container deployments (endpoint URLs injected at startup via sed substitution of `__MEDIAMTX_BASE__`, `__MEDIAMTX_API__`, and `__WS_URL__` placeholders).

## Local development

### Requirements

- [Gazebo Sim](https://gazebosim.org/) (Ionic or newer)
- [MediaMTX](https://github.com/bluenviron/mediamtx) v1.18+
- FFmpeg with libx264 (WHIP muxer optional, requires FFmpeg 7+)
- cmake, pkg-config, C++17 compiler

### Build

```bash
cmake -B build -DCMAKE_PREFIX_PATH=/opt/homebrew  # macOS
cmake -B build                                     # Linux
cmake --build build
```

### Run

```bash
# Start MediaMTX
mediamtx mediamtx-gazebo.yml

# Launch headless simulation
GZ_SIM_SYSTEM_PLUGIN_PATH=$(pwd)/build \
  gz sim -s -r --headless-rendering quadcopter_demo.sdf -v 4

# Serve the viewer
python3 -m http.server 8080
open http://localhost:8080/viewer.html
```

The included `mediamtx-gazebo.yml` configures demand-based streaming: when a browser requests a camera path, MediaMTX tells Gazebo to start encoding. When all viewers leave, encoding stops.

## Demo worlds

### quadcopter_demo.sdf

X3 UAV quadcopter from [Gazebo Fuel](https://fuel.gazebosim.org/) with velocity control, three cameras (front-facing 1280x720, downward 640x480, tower overview 1280x720), ground objects (gas station, vehicles, warehouse, water tower), and a landing pad. Use `fly_patrol.sh` for an autonomous rectangular patrol pattern.

### headless_camera.sdf

Minimal test scene with a spinning arm, falling shapes, and a single static camera. Useful for verifying the encoding pipeline works without the overhead of a full world.

## Container deployment

This repo includes Containerfiles and Helm charts for deploying the full pipeline on Kubernetes/OpenShift. See the `charts/` directory for the four Helm charts (coturn, mediamtx, viewer, gz-sim) and `docs/architecture-diagram.html` for the deployment topology.

## License

Apache License 2.0
