# gz-camera-stream OpenShift 4.21 Deployment Design

A reusable development platform that deploys the Gazebo camera streaming pipeline on OpenShift 4.21. Engineers spin up isolated simulation instances, push H.264 video streams to a shared MediaMTX server, and view them in a browser via WebRTC with coturn relaying UDP through the cluster boundary.

## Architecture Overview

```
                              ┌──────────────────────────────────┐
                              │        OpenShift Cluster          │
                              │        Namespace: gz-sim          │
                              │                                   │
  Engineer's Browser          │   ┌────────┐    WHIP (HTTP)       │
  -- WHEP signaling (HTTPS) ─────>│MediaMTX│<──────────────────── Gazebo (chris)
  -- API (HTTPS) ────────────────>│  :8889 │<──────────────────── Gazebo (dave)
                              │   │  :9997 │                      │
                              │   └────────┘                      │
                              │        │ ICE candidates            │
                              │        v point to coturn           │
                              │   ┌────────┐                      │
  -- UDP media (TURN) ───────────>│ coturn │                      │
  -- TURN/TCP fallback ──────────>│ :3478  │ hostNetwork          │
                              │   │ :49152-│                      │
                              │   │  49252 │                      │
                              │   └────────┘                      │
                              │                                   │
  -- viewer.html (HTTPS) ───────> nginx :8080                     │
  -- WebSocket (WSS) ───────────> Gazebo :9002 (per-engineer)     │
                              │                                   │
                              └──────────────────────────────────┘
```

## Components

| Component | Type | Count | Image |
|-----------|------|-------|-------|
| coturn | Deployment (hostNetwork) | 1 | coturn/coturn:latest |
| MediaMTX | Deployment + Service + Route | 1 | bluenviron/mediamtx:latest |
| Viewer | Deployment + Service + Route | 1 | gz-viewer (custom) |
| Gazebo Sim | Helm release + Service + Route + PVC | per-engineer | gz-sim-streamer (custom) |

## Container Images

### gz-sim-streamer

The Gazebo simulation server with the CameraStream plugin baked in.

```dockerfile
# ---- Build stage ----
FROM registry.access.redhat.com/ubi10/ubi:latest AS builder

RUN dnf install -y \
    cmake gcc-c++ make pkg-config \
    gz-sim gz-sim-devel \
    gz-rendering-devel gz-transport-devel \
    gz-msgs-devel gz-common-devel gz-plugin-devel \
    ffmpeg-free-devel libx264-devel \
    && dnf clean all

COPY src/ /build/src/
COPY CMakeLists.txt /build/
RUN cmake -B /build/out /build && cmake --build /build/out

# ---- Runtime stage ----
FROM registry.access.redhat.com/ubi10/ubi-minimal:latest

RUN microdnf install -y \
    gz-sim gz-tools \
    ffmpeg-free libx264 \
    mesa-dri-drivers mesa-libEGL mesa-libGL mesa-vulkan-drivers \
    libgbm libxkbcommon \
    && microdnf clean all

COPY --from=builder /build/out/libgz-sim-camera-stream-system.so /usr/local/lib/
COPY quadcopter_demo.sdf headless_camera.sdf /worlds/
COPY fly_patrol.sh /usr/local/bin/fly_patrol.sh

ENV GZ_SIM_SYSTEM_PLUGIN_PATH=/usr/local/lib
ENV GZ_FUEL_CACHE_PATH=/fuel-cache

EXPOSE 9002

ENTRYPOINT ["gz", "sim", "-s", "-r", "--headless-rendering"]
CMD ["/worlds/quadcopter_demo.sdf", "-v", "4"]
```

All images use RHEL UBI 10.x as the base. Mesa packages cover all three GPU modes (NVIDIA, AMD, CPU-only) in a single image. GPU selection happens at the pod level, not in the image.

Note: Gazebo and FFmpeg packages may require enabling additional repositories (EPEL, RPM Fusion, or Gazebo's official RPM repo at packages.osrfoundation.org) in the build stage. The exact repo configuration will be determined during implementation based on what's available for RHEL 10.

### gz-viewer

Static web server for the viewer UI.

```dockerfile
FROM registry.access.redhat.com/ubi10/ubi-minimal:latest

RUN microdnf install -y nginx gettext && microdnf clean all

RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/gz-viewer.conf
COPY viewer.html /usr/share/nginx/html/viewer.html.template

COPY <<'EOF' /docker-entrypoint.sh
#!/bin/sh
envsubst '$MEDIAMTX_BASE $MEDIAMTX_API $TURN_HOST $TURN_PORT' \
  < /usr/share/nginx/html/viewer.html.template \
  > /usr/share/nginx/html/index.html
exec nginx -g 'daemon off;'
EOF
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
```

nginx.conf:

```nginx
server {
    listen 8080;
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ =404;
    }
}
```

### coturn

No custom image. Uses `coturn/coturn:latest` with a ConfigMap for `turnserver.conf` and an init container to discover the node's external IP via the Kubernetes downward API.

## Shared Services

### coturn

Deployed with `hostNetwork: true` so it binds directly to the node's network stack. This avoids the NodePort range-mapping problem for the media relay ports.

turnserver.conf:

```ini
listening-port=3478
min-port=49152
max-port=49252
realm=gz-sim.local
user=gzsim:gzsimpass
lt-cred-mech
no-tls
no-dtls
external-ip=__NODE_EXTERNAL_IP__
```

The `external-ip` is resolved at startup by an init container:

```yaml
initContainers:
- name: discover-ip
  image: registry.access.redhat.com/ubi10/ubi-micro:latest
  command: ["sh", "-c"]
  args:
  - |
    sed "s/__NODE_EXTERNAL_IP__/$NODE_IP/" \
      /config-template/turnserver.conf > /config/turnserver.conf
  env:
  - name: NODE_IP
    valueFrom:
      fieldRef:
        fieldPath: status.hostIP
  volumeMounts:
  - name: config-template
    mountPath: /config-template
  - name: config-rendered
    mountPath: /config
```

Resources: 128Mi-512Mi RAM, 250m-1 CPU.

### MediaMTX

Single shared deployment. All Gazebo instances push streams here via WHIP. Browsers connect via WHEP for WebRTC playback.

Cluster-adapted config changes from the local `mediamtx-gazebo.yml`:

- Remove IPv4 loopback restriction (`webrtcLocalUDPAddress` cleared, binds all interfaces)
- Path pattern widened to `~^(.+/.+)$` for namespaced paths like `chris/front_camera`
- `runOnDemand` disabled (Gazebo pods push streams directly via WHIP)
- ICE servers configured to point at coturn

```yaml
webrtcICEServers2:
  - url: turn:<node-ip>:3478
    username: gzsim
    password: gzsimpass

webrtcLocalUDPAddress: ""
webrtcIPsFromInterfaces: no
webrtcAdditionalHosts: []
```

Ports: 8889 (WebRTC/WHIP/WHEP), 8554 (RTSP), 9997 (API).
Resources: 256Mi-512Mi RAM, 250m-500m CPU.

### Viewer

Nginx serving `viewer.html` with runtime-injected endpoint URLs via `envsubst`.

Viewer modifications for cluster mode:

1. Replace hardcoded `localhost` URLs with `__MEDIAMTX_BASE__`, `__MEDIAMTX_API__` placeholders
2. WebRTC PeerConnection reads ICE server config from WHEP response `Link` headers (MediaMTX passes TURN config automatically)
3. Add a simulation selector dropdown for connecting to a specific engineer's Gazebo WebSocket for telemetry (`?sim=chris` -> `wss://gz-chris.apps.<cluster>`)
4. Stream discovery via MediaMTX API shows namespaced paths (`chris/front_camera`, `dave/cam_down`)

Resources: 64Mi-128Mi RAM, 50m-100m CPU.

## Routes

| Route | Target | Protocol | Purpose |
|-------|--------|----------|---------|
| `mediamtx.apps.<cluster>` | mediamtx-webrtc:8889 | edge TLS | WHEP signaling, HLS fallback |
| `mediamtx-api.apps.<cluster>` | mediamtx-api:9997 | edge TLS | Stream listing API |
| `viewer.apps.<cluster>` | gz-viewer:8080 | edge TLS | Web UI |
| `gz-<engineer>.apps.<cluster>` | `<engineer>-sim-ws:9002` | edge TLS (WebSocket) | Gazebo telemetry |
| (no Route) | coturn hostNetwork | UDP direct to node | TURN media relay |

WebSocket Routes need the timeout annotation:

```yaml
metadata:
  annotations:
    haproxy.router.openshift.io/timeout: 300s
```

## Per-Engineer Gazebo Helm Chart

### Chart Structure

```
charts/gz-sim/
  Chart.yaml
  values.yaml
  templates/
    deployment.yaml
    service.yaml
    route.yaml
    configmap.yaml
    pvc.yaml
    _helpers.tpl
```

### values.yaml

```yaml
engineer: ""              # Required - naming, stream paths, labels

world: quadcopter_demo    # SDF file from /worlds/
customWorldConfigMap: ""  # Optional ConfigMap with custom SDF

image:
  repository: quay.io/<org>/gz-sim-streamer
  tag: latest
  pullPolicy: IfNotPresent

gpu:
  vendor: none            # none | nvidia | amd

resources:
  requests:
    cpu: "1"
    memory: 2Gi
  limits:
    cpu: "4"
    memory: 4Gi

mediamtx:
  host: mediamtx-webrtc.gz-sim.svc.cluster.local
  port: 8889

gazebo:
  bitrate: 4000000
  fps: 30
  verbosity: 4

persistence:
  enabled: true
  keep: true              # Survive helm uninstall
  size: 5Gi
  storageClass: ""
```

### Usage

```bash
# CPU-only sim
helm install chris-sim ./charts/gz-sim \
  --set engineer=chris

# NVIDIA GPU
helm install dave-sim ./charts/gz-sim \
  --set engineer=dave \
  --set gpu.vendor=nvidia

# Custom world
oc create configmap chris-world --from-file=my_world.sdf
helm install chris-sim ./charts/gz-sim \
  --set engineer=chris \
  --set customWorldConfigMap=chris-world \
  --set world=my_world

# Teardown
helm uninstall chris-sim
```

### GPU Configuration

**CPU-only (gpu.vendor=none)**:

```yaml
env:
- name: LIBGL_ALWAYS_SOFTWARE
  value: "1"
- name: MESA_GL_VERSION_OVERRIDE
  value: "3.3"
- name: GALLIUM_DRIVER
  value: llvmpipe
```

**NVIDIA (gpu.vendor=nvidia)**:

```yaml
runtimeClassName: nvidia
resources:
  limits:
    nvidia.com/gpu: 1
nodeSelector:
  nvidia.com/gpu.present: "true"
```

Requires NVIDIA GPU Operator on the cluster.

**AMD (gpu.vendor=amd)**:

```yaml
resources:
  limits:
    amd.com/gpu: 1
securityContext:
  supplementalGroups: [44]
nodeSelector:
  amd.com/gpu.present: "true"
```

Requires AMD GPU device plugin on the cluster.

## Storage

### Fuel Model Cache (per-engineer PVC)

```yaml
PVC: <engineer>-fuel-cache
  Size: 5Gi
  Access: ReadWriteOnce
  Mount: /fuel-cache
  Env: GZ_FUEL_CACHE_PATH=/fuel-cache
```

Survives `helm uninstall` when `persistence.keep=true` (Helm resource policy annotation). Avoids re-downloading Gazebo Fuel models on pod restart.

### Custom World Files

Two methods:

1. **ConfigMap mount**: `oc create configmap <name> --from-file=world.sdf`, reference via `customWorldConfigMap` Helm value
2. **Direct copy**: `oc cp my_world.sdf <pod>:/worlds/` for quick iteration

## Plugin Code Change

The CameraStream plugin needs a small change to support stream path namespacing.

**CameraStream.cc** (~10 lines): Read `<stream_prefix>` from SDF config in `Configure()`, falling back to the `STREAM_PREFIX` environment variable.

**StreamContext.cc** (~5 lines): When building the WHIP URL, if a prefix is set, insert it into the path: `http://mediamtx:8889/<prefix>/<camera>/whip`.

This ensures each engineer's streams are namespaced (e.g., `chris/front_camera`) and don't collide in the shared MediaMTX instance.

## Deployment Runbook

### Prerequisites

- OpenShift 4.21 cluster with `oc` CLI authenticated
- Helm v3 installed
- Container registry accessible from the cluster
- For GPU: NVIDIA GPU Operator or AMD device plugin installed on relevant nodes

### Step 1: Build and Push Images

```bash
podman build -t quay.io/<org>/gz-sim-streamer:latest -f Containerfile.gazebo .
podman push quay.io/<org>/gz-sim-streamer:latest

podman build -t quay.io/<org>/gz-viewer:latest -f Containerfile.viewer .
podman push quay.io/<org>/gz-viewer:latest
```

### Step 2: Deploy Shared Services

```bash
oc new-project gz-sim

helm install coturn ./charts/coturn \
  --set nodePort.turn=30478

helm install mediamtx ./charts/mediamtx \
  --set coturn.host=<node-ip> \
  --set coturn.port=30478

helm install viewer ./charts/viewer \
  --set mediamtx.route=mediamtx-gz-sim.apps.<cluster> \
  --set mediamtxApi.route=mediamtx-api-gz-sim.apps.<cluster>
```

### Step 3: Spin Up a Simulation

```bash
helm install chris-sim ./charts/gz-sim \
  --set engineer=chris \
  --set world=quadcopter_demo
```

### Step 4: Access

```bash
# Open the viewer
open https://viewer-gz-sim.apps.<cluster>

# CLI access to a sim
oc rsh deploy/chris-sim-gazebo

# Fly the quadcopter
gz topic -t "/X3/gazebo/command/twist" -m gz.msgs.Twist \
  -p "linear: {z: 0.5}"
```

### Step 5: Teardown

```bash
helm uninstall chris-sim        # Remove one sim
helm uninstall viewer mediamtx coturn  # Remove shared services
oc delete project gz-sim        # Remove everything
```
