# OpenShift 4.21 Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the gz-camera-stream pipeline (Gazebo + CameraStream plugin + MediaMTX + viewer) on OpenShift 4.21 as a reusable dev platform with per-engineer simulation instances, WebRTC video via coturn, and multi-GPU support.

**Architecture:** Shared services (MediaMTX, coturn, viewer) deployed once per namespace. Per-engineer Gazebo pods deployed via Helm chart. WebRTC media relayed through coturn (hostNetwork) so it works through OpenShift Routes. Stream paths namespaced per engineer.

**Tech Stack:** OpenShift 4.21, Helm 3, UBI 10.x container images, coturn, MediaMTX, Gazebo Sim, FFmpeg, nginx

**Spec:** `docs/superpowers/specs/2026-06-05-openshift-deployment-design.md`

---

## File Structure

```
gz-camera-stream/
  Containerfile.gazebo                    # NEW - gz-sim-streamer image
  Containerfile.viewer                    # NEW - gz-viewer image
  nginx.conf                          # NEW - viewer nginx config
  mediamtx-cluster.yml                 # NEW - cluster-adapted MediaMTX config
  src/
    CameraStream.cc                    # MODIFY - read stream_prefix, mediamtx_base
  viewer.html                          # MODIFY - configurable endpoints, sim selector
  charts/
    coturn/
      Chart.yaml                       # NEW
      values.yaml                      # NEW
      templates/
        deployment.yaml                # NEW
        configmap.yaml                 # NEW
        _helpers.tpl                   # NEW
    mediamtx/
      Chart.yaml                       # NEW
      values.yaml                      # NEW
      templates/
        deployment.yaml                # NEW
        service.yaml                   # NEW
        route.yaml                     # NEW
        configmap.yaml                 # NEW
        _helpers.tpl                   # NEW
    viewer/
      Chart.yaml                       # NEW
      values.yaml                      # NEW
      templates/
        deployment.yaml                # NEW
        service.yaml                   # NEW
        route.yaml                     # NEW
        _helpers.tpl                   # NEW
    gz-sim/
      Chart.yaml                       # NEW
      values.yaml                      # NEW
      templates/
        deployment.yaml                # NEW
        service.yaml                   # NEW
        route.yaml                     # NEW
        configmap.yaml                 # NEW
        pvc.yaml                       # NEW
        _helpers.tpl                   # NEW
```

---

## Task 1: Plugin Code Change - Stream Prefix and MediaMTX Base URL

**Files:**
- Modify: `src/CameraStream.cc:55-117` (CameraStreamPrivate class) and `src/CameraStream.cc:426-458` (Configure method)

This adds two new configuration options that enable cluster deployment. When `MEDIAMTX_WHIP_BASE` is set, the plugin constructs WHIP URLs internally instead of requiring them in the start command. When `STREAM_PREFIX` is set, it namespaces all stream paths.

- [ ] **Step 1: Add stream_prefix and mediamtx_base members to CameraStreamPrivate**

In `src/CameraStream.cc`, add two new members to the `CameraStreamPrivate` class (after the `defaultFps` member at line 110):

```cpp
  /// \brief Stream path prefix for namespacing (e.g., engineer name)
  public: std::string streamPrefix;

  /// \brief MediaMTX WHIP base URL (e.g., http://mediamtx:8889)
  public: std::string mediamtxBase;
```

- [ ] **Step 2: Read config in Configure()**

In `src/CameraStream.cc`, add the following after the `defaultFps` config read (after line 443):

```cpp
  if (_sdf->HasElement("stream_prefix"))
  {
    this->dataPtr->streamPrefix = _sdf->Get<std::string>("stream_prefix");
  }
  if (this->dataPtr->streamPrefix.empty())
  {
    const char *envPrefix = std::getenv("STREAM_PREFIX");
    if (envPrefix)
      this->dataPtr->streamPrefix = envPrefix;
  }

  if (_sdf->HasElement("mediamtx_base"))
  {
    this->dataPtr->mediamtxBase = _sdf->Get<std::string>("mediamtx_base");
  }
  if (this->dataPtr->mediamtxBase.empty())
  {
    const char *envBase = std::getenv("MEDIAMTX_WHIP_BASE");
    if (envBase)
      this->dataPtr->mediamtxBase = envBase;
  }
```

Also add to the existing log message at the end of Configure():

```cpp
  if (!this->dataPtr->streamPrefix.empty())
  {
    gzmsg << "Stream prefix: [" << this->dataPtr->streamPrefix << "]"
           << std::endl;
  }
  if (!this->dataPtr->mediamtxBase.empty())
  {
    gzmsg << "MediaMTX base: [" << this->dataPtr->mediamtxBase << "]"
           << std::endl;
  }
```

You will also need to add `#include <cstdlib>` to the includes at the top of `CameraStream.cc`.

- [ ] **Step 3: Modify OnControlMessage to construct URLs when mediamtx_base is set**

In `src/CameraStream.cc`, replace the start action block in `OnControlMessage()` (lines 136-159) with:

```cpp
  if (action == "start")
  {
    std::string url;

    if (!this->mediamtxBase.empty())
    {
      // Construct URL from base + prefix + camera name
      std::string path = cameraName;
      // Strip leading slash if present
      if (!path.empty() && path[0] == '/')
        path = path.substr(1);
      // Replace slashes with underscores for MediaMTX path
      for (auto &c : path)
        if (c == '/') c = '_';

      url = this->mediamtxBase + "/";
      if (!this->streamPrefix.empty())
        url += this->streamPrefix + "/";
      url += path + "/whip";
    }
    else if (_msg.data_size() >= 3)
    {
      url = _msg.data(2);
    }
    else
    {
      gzerr << "Stream start requires URL in data[2] or "
             << "MEDIAMTX_WHIP_BASE to be set" << std::endl;
      return;
    }

    unsigned int bitrate = this->defaultBitrate;
    unsigned int fps = this->defaultFps;

    if (_msg.data_size() >= 4 && !_msg.data(3).empty())
    {
      try { bitrate = std::stoul(_msg.data(3)); }
      catch (...) {}
    }
    if (_msg.data_size() >= 5 && !_msg.data(4).empty())
    {
      try { fps = std::stoul(_msg.data(4)); }
      catch (...) {}
    }

    this->StartStream(cameraName, url, bitrate, fps);
  }
```

- [ ] **Step 4: Build and verify**

```bash
cd /Users/ccustine/development/gazebo/gz-camera-stream
cmake -B build -DCMAKE_PREFIX_PATH=/opt/homebrew
cmake --build build
```

Expected: Builds successfully with no warnings related to the new code.

- [ ] **Step 5: Commit**

```bash
git add src/CameraStream.cc
git commit -m "Add stream_prefix and mediamtx_base config for cluster deployment"
```

---

## Task 2: MediaMTX Cluster Configuration

**Files:**
- Create: `mediamtx-cluster.yml`

This is the cluster-adapted version of `mediamtx-gazebo.yml`. Key differences: no loopback restriction, wider path pattern for namespaced streams, no runOnDemand (Gazebo pushes directly), coturn ICE server config.

- [ ] **Step 1: Create mediamtx-cluster.yml**

```yaml
# MediaMTX configuration for OpenShift cluster deployment.
#
# Key differences from local mediamtx-gazebo.yml:
# - No IPv4 loopback restriction (pods communicate over cluster network)
# - Wider path pattern for namespaced streams (engineer/camera)
# - No runOnDemand (Gazebo pods push directly via WHIP)
# - ICE servers configured to point at coturn TURN relay

logLevel: info

api: yes
apiAddress: :9997

rtsp: yes
rtspAddress: :8554

webrtc: yes
webrtcAddress: :8889

# Bind all interfaces - cluster networking handles routing
webrtcLocalUDPAddress: ""
webrtcIPsFromInterfaces: yes
webrtcAdditionalHosts: []

# TURN server for relaying WebRTC media through the cluster boundary.
# Values are templated by Helm - __COTURN_HOST__ and __COTURN_PORT__
# are replaced at ConfigMap creation time.
webrtcICEServers2:
  - url: turn:__COTURN_HOST__:__COTURN_PORT__
    username: gzsim
    password: gzsimpass

hls: yes
hlsAddress: :8888

pathDefaults:
  # No demand-based lifecycle in cluster mode.
  # Gazebo pods start/stop streams explicitly via WHIP.

paths:
  # Match any namespaced path (engineer/camera_name)
  # or simple paths (camera_name) for backward compatibility.
  ~^(.+)$:
```

- [ ] **Step 2: Commit**

```bash
git add mediamtx-cluster.yml
git commit -m "Add cluster-adapted MediaMTX config for OpenShift deployment"
```

---

## Task 3: Viewer Modifications

**Files:**
- Modify: `viewer.html`

Three changes: (1) replace hardcoded localhost URLs with substitution placeholders, (2) add a simulation selector for connecting to different engineers' Gazebo WebSocket, (3) parse WHEP Link headers for ICE server discovery.

- [ ] **Step 1: Replace hardcoded URLs with placeholders**

In `viewer.html`, replace the constants block at lines 702-705:

```javascript
    const WS_URL = 'ws://localhost:9002';
    const STREAM_CONTROL_TOPIC = '/stream/control';
    const MEDIAMTX_BASE = 'http://localhost:8889';
    const MEDIAMTX_API = 'http://localhost:9997';
```

With:

```javascript
    const WS_URL = '__WS_URL__' !== '__' + 'WS_URL' + '__'
        ? '__WS_URL__' : 'ws://localhost:9002';
    const STREAM_CONTROL_TOPIC = '/stream/control';
    const MEDIAMTX_BASE = '__MEDIAMTX_BASE__' !== '__' + 'MEDIAMTX_BASE' + '__'
        ? '__MEDIAMTX_BASE__' : 'http://localhost:8889';
    const MEDIAMTX_API = '__MEDIAMTX_API__' !== '__' + 'MEDIAMTX_API' + '__'
        ? '__MEDIAMTX_API__' : 'http://localhost:9997';
```

This pattern falls back to localhost when not substituted (local dev), and uses the injected values when running in a container with envsubst.

- [ ] **Step 2: Add simulation selector to the masthead**

In `viewer.html`, add a simulation selector dropdown in the masthead. Find the `<div id="status"` element (line 667) and add before it:

```html
    <div style="display:flex;align-items:center;gap:8px;">
      <label for="sim-select" style="color:#aaa;font-size:0.8em;">Sim:</label>
      <select id="sim-select" class="filter-select" style="background:#222;color:#fff;border-color:#444;" onchange="switchSimulation()">
        <option value="">Local</option>
      </select>
      <div id="status" class="connecting">Connecting...</div>
    </div>
```

And remove the standalone `<div id="status"` line that was there before.

- [ ] **Step 3: Add switchSimulation() function**

In `viewer.html`, add the following function after the `doConnect()` function definition (around line 956):

```javascript
    function switchSimulation() {
      const sel = document.getElementById('sim-select');
      const simUrl = sel.value;
      if (ws) {
        ws.close();
        ws = null;
      }
      connectPhase = 'idle';
      autoStreamDone = false;
      topicTypes = {};
      subscriptions = {};
      document.getElementById('topic-tree').innerHTML = '';
      document.getElementById('live-data').innerHTML = '';

      if (simUrl) {
        // Connect to a specific engineer's Gazebo instance
        doConnectTo(simUrl);
      } else {
        doConnect();
      }
    }

    function doConnectTo(url) {
      if (ws && ws.readyState === WebSocket.OPEN) return;
      setStatus('Connecting...', 'connecting');
      connectPhase = 'auth';
      protoRoot = null;
      autoStreamDone = false;

      ws = new WebSocket(url);
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => { ws.send('auth,,,'); };
      ws.onclose = () => { setStatus('Disconnected', 'disconnected'); connectPhase = 'idle'; ws = null; stopStreamsPoll(); };
      ws.onerror = () => { setStatus('Connection error', 'disconnected'); };
      ws.onmessage = (event) => {
        const raw = (event.data instanceof ArrayBuffer) ? new Uint8Array(event.data) : new TextEncoder().encode(event.data);
        if (connectPhase === 'auth') {
          if (new TextDecoder().decode(raw) === 'authorized') { connectPhase = 'protos'; ws.send('protos,,,'); }
          else { setStatus('Auth failed', 'disconnected'); }
          return;
        }
        if (connectPhase === 'protos') {
          try { protoRoot = protobuf.parse(new TextDecoder().decode(raw), { keepCase: true }).root; connectPhase = 'ready'; setStatus('Connected', 'connected'); ws.send('topics-types,,,'); startStreamsPoll(); }
          catch (e) { setStatus('Proto parse failed', 'disconnected'); }
          return;
        }
        handleMessage(raw);
      };
    }
```

- [ ] **Step 4: Add URL parameter support for pre-selecting a simulation**

Add this at the bottom of the script, before the closing `</script>` tag, replacing the existing `doConnect()` and `setTimeout()` calls (lines 1653-1654):

```javascript
    // Check URL params for sim selection
    const urlParams = new URLSearchParams(window.location.search);
    const simParam = urlParams.get('sim');
    if (simParam) {
      // Auto-populate sim selector with the param value
      const sel = document.getElementById('sim-select');
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const simWsUrl = wsProto + '//' + window.location.hostname.replace('viewer', 'gz-' + simParam) + '/';
      const opt = document.createElement('option');
      opt.value = simWsUrl;
      opt.textContent = simParam;
      opt.selected = true;
      sel.appendChild(opt);
      doConnectTo(simWsUrl);
    } else {
      doConnect();
    }
    setTimeout(() => renderTopicTree(), 0);
```

- [ ] **Step 5: Update connectWebRTC to parse WHEP Link headers for ICE servers**

In `viewer.html`, replace the `connectWebRTC()` function (lines 1514-1570) with a version that fetches ICE server config from the WHEP endpoint first:

```javascript
    async function connectWebRTC(streamPath) {
      disconnectWebRTC();

      const whepUrl = MEDIAMTX_BASE + '/' + streamPath + '/whep';
      const videoEl = document.getElementById('webrtc-player');

      try {
        // Fetch ICE server config from WHEP OPTIONS (Link headers)
        let iceServers = [];
        try {
          const optResp = await fetch(whepUrl, { method: 'OPTIONS' });
          const linkHeader = optResp.headers.get('Link');
          if (linkHeader) {
            const turnMatch = linkHeader.match(/<(turn:[^>]+)>/);
            if (turnMatch) {
              const credMatch = linkHeader.match(/username="([^"]+)".*credential="([^"]+)"/);
              iceServers.push({
                urls: turnMatch[1],
                username: credMatch ? credMatch[1] : '',
                credential: credMatch ? credMatch[2] : ''
              });
            }
          }
        } catch (e) {
          // OPTIONS may not be supported - proceed without ICE servers
        }

        webrtcPc = new RTCPeerConnection({ iceServers: iceServers });
        webrtcPc.addTransceiver('video', { direction: 'recvonly' });

        webrtcPc.ontrack = (event) => {
          videoEl.srcObject = event.streams[0];
          videoInfoEl.innerHTML = 'Playing <span class="stream-name">/' +
            escHtml(streamPath) + '</span> - H.264 via WebRTC';
        };

        webrtcPc.oniceconnectionstatechange = () => {
          if (webrtcPc && (webrtcPc.iceConnectionState === 'disconnected' ||
              webrtcPc.iceConnectionState === 'failed')) {
            videoInfoEl.textContent = 'WebRTC disconnected';
          }
        };

        const offer = await webrtcPc.createOffer();
        await webrtcPc.setLocalDescription(offer);

        await new Promise((resolve) => {
          if (webrtcPc.iceGatheringState === 'complete') {
            resolve();
          } else {
            webrtcPc.onicegatheringstatechange = () => {
              if (webrtcPc.iceGatheringState === 'complete') resolve();
            };
          }
        });

        const resp = await fetch(whepUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/sdp' },
          body: webrtcPc.localDescription.sdp
        });

        if (!resp.ok) {
          console.log('WHEP not ready yet:', resp.status);
          disconnectWebRTC();
          return false;
        }

        const answer = await resp.text();
        await webrtcPc.setRemoteDescription({ type: 'answer', sdp: answer });
        return true;
      } catch (e) {
        console.error('WebRTC connection failed:', e);
        disconnectWebRTC();
        return false;
      }
    }
```

- [ ] **Step 6: Test locally**

Open `viewer.html` in a browser with the dev server. Verify:
- No console errors on load (placeholder fallback to localhost)
- URL param `?sim=test` creates an entry in the sim dropdown

```bash
python3 -m http.server 8080
open http://localhost:8080/viewer.html
open http://localhost:8080/viewer.html?sim=test
```

- [ ] **Step 7: Commit**

```bash
git add viewer.html
git commit -m "Add configurable endpoints and sim selector for cluster deployment"
```

---

## Task 4: nginx Configuration

**Files:**
- Create: `nginx.conf`

- [ ] **Step 1: Create nginx.conf**

```nginx
server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add nginx.conf
git commit -m "Add nginx config for viewer container"
```

---

## Task 5: Containerfiles

**Files:**
- Create: `Containerfile.gazebo`
- Create: `Containerfile.viewer`

- [ ] **Step 1: Create Containerfile.gazebo**

```dockerfile
# gz-sim-streamer: Gazebo Sim with CameraStream plugin
# Supports NVIDIA GPU, AMD GPU, or CPU-only (Mesa llvmpipe) rendering.
# GPU selection happens at the pod level, not in this image.

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

- [ ] **Step 2: Create Containerfile.viewer**

```dockerfile
# gz-viewer: nginx serving viewer.html with runtime endpoint injection

FROM registry.access.redhat.com/ubi10/ubi-minimal:latest

RUN microdnf install -y nginx gettext && microdnf clean all

RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/gz-viewer.conf
COPY viewer.html /usr/share/nginx/html/viewer.html.template

RUN printf '#!/bin/sh\n\
envsubst '"'"'$WS_URL $MEDIAMTX_BASE $MEDIAMTX_API'"'"' \\\n\
  < /usr/share/nginx/html/viewer.html.template \\\n\
  > /usr/share/nginx/html/index.html\n\
exec nginx -g '"'"'daemon off;'"'"'\n' > /docker-entrypoint.sh \
  && chmod +x /docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
```

- [ ] **Step 3: Verify Containerfiles parse correctly**

```bash
podman build --dry-run -f Containerfile.gazebo . 2>&1 | head -5
podman build --dry-run -f Containerfile.viewer . 2>&1 | head -5
```

Expected: No syntax errors. Full builds require the Gazebo repos configured which may not be available locally.

- [ ] **Step 4: Commit**

```bash
git add Containerfile.gazebo Containerfile.viewer
git commit -m "Add Containerfiles for gz-sim-streamer and gz-viewer images"
```

---

## Task 6: Helm Chart - coturn

**Files:**
- Create: `charts/coturn/Chart.yaml`
- Create: `charts/coturn/values.yaml`
- Create: `charts/coturn/templates/_helpers.tpl`
- Create: `charts/coturn/templates/configmap.yaml`
- Create: `charts/coturn/templates/deployment.yaml`

- [ ] **Step 1: Create chart metadata**

`charts/coturn/Chart.yaml`:

```yaml
apiVersion: v2
name: coturn
description: TURN server for relaying WebRTC media through OpenShift
version: 0.1.0
appVersion: "4.6"
```

- [ ] **Step 2: Create values.yaml**

`charts/coturn/values.yaml`:

```yaml
image:
  repository: coturn/coturn
  tag: latest
  pullPolicy: IfNotPresent

initImage:
  repository: registry.access.redhat.com/ubi10/ubi-micro
  tag: latest

credentials:
  username: gzsim
  password: gzsimpass
  realm: gz-sim.local

ports:
  listening: 3478
  minRelay: 49152
  maxRelay: 49252

resources:
  requests:
    cpu: 250m
    memory: 128Mi
  limits:
    cpu: "1"
    memory: 512Mi
```

- [ ] **Step 3: Create _helpers.tpl**

`charts/coturn/templates/_helpers.tpl`:

```yaml
{{- define "coturn.fullname" -}}
{{- .Release.Name }}-coturn
{{- end }}

{{- define "coturn.labels" -}}
app.kubernetes.io/name: coturn
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
```

- [ ] **Step 4: Create configmap.yaml**

`charts/coturn/templates/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "coturn.fullname" . }}-config
  labels:
    {{- include "coturn.labels" . | nindent 4 }}
data:
  turnserver.conf: |
    listening-port={{ .Values.ports.listening }}
    min-port={{ .Values.ports.minRelay }}
    max-port={{ .Values.ports.maxRelay }}
    realm={{ .Values.credentials.realm }}
    user={{ .Values.credentials.username }}:{{ .Values.credentials.password }}
    lt-cred-mech
    no-tls
    no-dtls
    external-ip=__NODE_EXTERNAL_IP__
```

- [ ] **Step 5: Create deployment.yaml**

`charts/coturn/templates/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "coturn.fullname" . }}
  labels:
    {{- include "coturn.labels" . | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: coturn
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: coturn
        app.kubernetes.io/instance: {{ .Release.Name }}
    spec:
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      initContainers:
      - name: discover-ip
        image: {{ .Values.initImage.repository }}:{{ .Values.initImage.tag }}
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
      containers:
      - name: coturn
        image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        args:
        - "-c"
        - "/config/turnserver.conf"
        ports:
        - containerPort: {{ .Values.ports.listening }}
          protocol: UDP
        - containerPort: {{ .Values.ports.listening }}
          protocol: TCP
        volumeMounts:
        - name: config-rendered
          mountPath: /config
          readOnly: true
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
      volumes:
      - name: config-template
        configMap:
          name: {{ include "coturn.fullname" . }}-config
      - name: config-rendered
        emptyDir: {}
```

- [ ] **Step 6: Lint the chart**

```bash
helm lint charts/coturn
```

Expected: `1 chart(s) linted, 0 chart(s) failed`

- [ ] **Step 7: Test template rendering**

```bash
helm template test-coturn charts/coturn | head -80
```

Expected: Valid YAML output with hostNetwork: true, init container, correct ports.

- [ ] **Step 8: Commit**

```bash
git add charts/coturn/
git commit -m "Add Helm chart for coturn TURN server"
```

---

## Task 7: Helm Chart - MediaMTX

**Files:**
- Create: `charts/mediamtx/Chart.yaml`
- Create: `charts/mediamtx/values.yaml`
- Create: `charts/mediamtx/templates/_helpers.tpl`
- Create: `charts/mediamtx/templates/configmap.yaml`
- Create: `charts/mediamtx/templates/deployment.yaml`
- Create: `charts/mediamtx/templates/service.yaml`
- Create: `charts/mediamtx/templates/route.yaml`

- [ ] **Step 1: Create chart metadata**

`charts/mediamtx/Chart.yaml`:

```yaml
apiVersion: v2
name: mediamtx
description: MediaMTX streaming server for Gazebo camera streams
version: 0.1.0
appVersion: "1.18"
```

- [ ] **Step 2: Create values.yaml**

`charts/mediamtx/values.yaml`:

```yaml
image:
  repository: bluenviron/mediamtx
  tag: latest
  pullPolicy: IfNotPresent

coturn:
  host: ""
  port: 3478
  username: gzsim
  password: gzsimpass

route:
  enabled: true

resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

- [ ] **Step 3: Create _helpers.tpl**

`charts/mediamtx/templates/_helpers.tpl`:

```yaml
{{- define "mediamtx.fullname" -}}
{{- .Release.Name }}
{{- end }}

{{- define "mediamtx.labels" -}}
app.kubernetes.io/name: mediamtx
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "mediamtx.selectorLabels" -}}
app.kubernetes.io/name: mediamtx
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

- [ ] **Step 4: Create configmap.yaml**

`charts/mediamtx/templates/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "mediamtx.fullname" . }}-config
  labels:
    {{- include "mediamtx.labels" . | nindent 4 }}
data:
  mediamtx.yml: |
    logLevel: info

    api: yes
    apiAddress: :9997

    rtsp: yes
    rtspAddress: :8554

    webrtc: yes
    webrtcAddress: :8889

    webrtcLocalUDPAddress: ""
    webrtcIPsFromInterfaces: yes
    webrtcAdditionalHosts: []

    {{- if .Values.coturn.host }}
    webrtcICEServers2:
      - url: turn:{{ .Values.coturn.host }}:{{ .Values.coturn.port }}
        username: {{ .Values.coturn.username }}
        password: {{ .Values.coturn.password }}
    {{- end }}

    hls: yes
    hlsAddress: :8888

    pathDefaults:

    paths:
      ~^(.+)$:
```

- [ ] **Step 5: Create deployment.yaml**

`charts/mediamtx/templates/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "mediamtx.fullname" . }}
  labels:
    {{- include "mediamtx.labels" . | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "mediamtx.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "mediamtx.selectorLabels" . | nindent 8 }}
    spec:
      containers:
      - name: mediamtx
        image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        args: ["/mediamtx.yml"]
        ports:
        - containerPort: 8889
          name: webrtc
        - containerPort: 9997
          name: api
        - containerPort: 8554
          name: rtsp
        - containerPort: 8888
          name: hls
        volumeMounts:
        - name: config
          mountPath: /mediamtx.yml
          subPath: mediamtx.yml
          readOnly: true
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
      volumes:
      - name: config
        configMap:
          name: {{ include "mediamtx.fullname" . }}-config
```

- [ ] **Step 6: Create service.yaml**

`charts/mediamtx/templates/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "mediamtx.fullname" . }}-webrtc
  labels:
    {{- include "mediamtx.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  ports:
  - port: 8889
    targetPort: webrtc
    name: webrtc
  selector:
    {{- include "mediamtx.selectorLabels" . | nindent 4 }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ include "mediamtx.fullname" . }}-api
  labels:
    {{- include "mediamtx.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  ports:
  - port: 9997
    targetPort: api
    name: api
  selector:
    {{- include "mediamtx.selectorLabels" . | nindent 4 }}
```

- [ ] **Step 7: Create route.yaml**

`charts/mediamtx/templates/route.yaml`:

```yaml
{{- if .Values.route.enabled }}
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {{ include "mediamtx.fullname" . }}
  labels:
    {{- include "mediamtx.labels" . | nindent 4 }}
spec:
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: {{ include "mediamtx.fullname" . }}-webrtc
  port:
    targetPort: webrtc
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {{ include "mediamtx.fullname" . }}-api
  labels:
    {{- include "mediamtx.labels" . | nindent 4 }}
spec:
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: {{ include "mediamtx.fullname" . }}-api
  port:
    targetPort: api
{{- end }}
```

- [ ] **Step 8: Lint and test**

```bash
helm lint charts/mediamtx
helm template test-mtx charts/mediamtx --set coturn.host=10.0.0.1 | head -120
```

Expected: Lints clean. Template output includes coturn ICE server config, two Services, two Routes.

- [ ] **Step 9: Commit**

```bash
git add charts/mediamtx/
git commit -m "Add Helm chart for MediaMTX streaming server"
```

---

## Task 8: Helm Chart - Viewer

**Files:**
- Create: `charts/viewer/Chart.yaml`
- Create: `charts/viewer/values.yaml`
- Create: `charts/viewer/templates/_helpers.tpl`
- Create: `charts/viewer/templates/deployment.yaml`
- Create: `charts/viewer/templates/service.yaml`
- Create: `charts/viewer/templates/route.yaml`

- [ ] **Step 1: Create chart metadata**

`charts/viewer/Chart.yaml`:

```yaml
apiVersion: v2
name: gz-viewer
description: Web viewer for Gazebo camera streams
version: 0.1.0
appVersion: "0.1.0"
```

- [ ] **Step 2: Create values.yaml**

`charts/viewer/values.yaml`:

```yaml
image:
  repository: quay.io/gz-sim/gz-viewer
  tag: latest
  pullPolicy: IfNotPresent

mediamtx:
  base: ""
  api: ""

route:
  enabled: true

resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 100m
    memory: 128Mi
```

- [ ] **Step 3: Create _helpers.tpl**

`charts/viewer/templates/_helpers.tpl`:

```yaml
{{- define "viewer.fullname" -}}
{{- .Release.Name }}-viewer
{{- end }}

{{- define "viewer.labels" -}}
app.kubernetes.io/name: gz-viewer
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "viewer.selectorLabels" -}}
app.kubernetes.io/name: gz-viewer
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

- [ ] **Step 4: Create deployment.yaml**

`charts/viewer/templates/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "viewer.fullname" . }}
  labels:
    {{- include "viewer.labels" . | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "viewer.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "viewer.selectorLabels" . | nindent 8 }}
    spec:
      containers:
      - name: viewer
        image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - containerPort: 8080
          name: http
        env:
        - name: MEDIAMTX_BASE
          value: {{ .Values.mediamtx.base | quote }}
        - name: MEDIAMTX_API
          value: {{ .Values.mediamtx.api | quote }}
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
```

- [ ] **Step 5: Create service.yaml**

`charts/viewer/templates/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "viewer.fullname" . }}
  labels:
    {{- include "viewer.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  ports:
  - port: 8080
    targetPort: http
    name: http
  selector:
    {{- include "viewer.selectorLabels" . | nindent 4 }}
```

- [ ] **Step 6: Create route.yaml**

`charts/viewer/templates/route.yaml`:

```yaml
{{- if .Values.route.enabled }}
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {{ include "viewer.fullname" . }}
  labels:
    {{- include "viewer.labels" . | nindent 4 }}
spec:
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: {{ include "viewer.fullname" . }}
  port:
    targetPort: http
{{- end }}
```

- [ ] **Step 7: Lint and test**

```bash
helm lint charts/viewer
helm template test-viewer charts/viewer \
  --set mediamtx.base=https://mediamtx.apps.cluster.local \
  --set mediamtx.api=https://mediamtx-api.apps.cluster.local
```

Expected: Lints clean. Template shows env vars with correct MediaMTX URLs.

- [ ] **Step 8: Commit**

```bash
git add charts/viewer/
git commit -m "Add Helm chart for viewer web UI"
```

---

## Task 9: Helm Chart - gz-sim (Per-Engineer Gazebo)

**Files:**
- Create: `charts/gz-sim/Chart.yaml`
- Create: `charts/gz-sim/values.yaml`
- Create: `charts/gz-sim/templates/_helpers.tpl`
- Create: `charts/gz-sim/templates/deployment.yaml`
- Create: `charts/gz-sim/templates/service.yaml`
- Create: `charts/gz-sim/templates/route.yaml`
- Create: `charts/gz-sim/templates/configmap.yaml`
- Create: `charts/gz-sim/templates/pvc.yaml`

This is the most complex chart - it handles GPU selection, stream prefixing, custom worlds, and persistent fuel cache.

- [ ] **Step 1: Create chart metadata**

`charts/gz-sim/Chart.yaml`:

```yaml
apiVersion: v2
name: gz-sim
description: Per-engineer Gazebo simulation instance with camera streaming
version: 0.1.0
appVersion: "0.1.0"
```

- [ ] **Step 2: Create values.yaml**

`charts/gz-sim/values.yaml`:

```yaml
engineer: ""

world: quadcopter_demo
customWorldConfigMap: ""

image:
  repository: quay.io/gz-sim/gz-sim-streamer
  tag: latest
  pullPolicy: IfNotPresent

gpu:
  vendor: none    # none | nvidia | amd

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
  keep: true
  size: 5Gi
  storageClass: ""

route:
  enabled: true
```

- [ ] **Step 3: Create _helpers.tpl**

`charts/gz-sim/templates/_helpers.tpl`:

```yaml
{{- define "gzsim.fullname" -}}
{{- .Release.Name }}-gazebo
{{- end }}

{{- define "gzsim.labels" -}}
app.kubernetes.io/name: gz-sim
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- if .Values.engineer }}
gz-sim/engineer: {{ .Values.engineer }}
{{- end }}
{{- end }}

{{- define "gzsim.selectorLabels" -}}
app.kubernetes.io/name: gz-sim
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

- [ ] **Step 4: Create deployment.yaml**

`charts/gz-sim/templates/deployment.yaml`:

```yaml
{{- if not .Values.engineer }}
{{- fail "engineer is required: --set engineer=<name>" }}
{{- end }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "gzsim.fullname" . }}
  labels:
    {{- include "gzsim.labels" . | nindent 4 }}
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      {{- include "gzsim.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "gzsim.selectorLabels" . | nindent 8 }}
    spec:
      {{- if eq .Values.gpu.vendor "nvidia" }}
      runtimeClassName: nvidia
      nodeSelector:
        nvidia.com/gpu.present: "true"
      {{- else if eq .Values.gpu.vendor "amd" }}
      nodeSelector:
        amd.com/gpu.present: "true"
      securityContext:
        supplementalGroups: [44]
      {{- end }}
      containers:
      - name: gazebo
        image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        command: ["gz", "sim", "-s", "-r", "--headless-rendering"]
        args:
        - "/worlds/{{ .Values.world }}.sdf"
        - "-v"
        - "{{ .Values.gazebo.verbosity }}"
        env:
        - name: GZ_SIM_SYSTEM_PLUGIN_PATH
          value: /usr/local/lib
        - name: GZ_FUEL_CACHE_PATH
          value: /fuel-cache
        - name: STREAM_PREFIX
          value: {{ .Values.engineer | quote }}
        - name: MEDIAMTX_WHIP_BASE
          value: "http://{{ .Values.mediamtx.host }}:{{ .Values.mediamtx.port }}"
        {{- if eq .Values.gpu.vendor "none" }}
        - name: LIBGL_ALWAYS_SOFTWARE
          value: "1"
        - name: MESA_GL_VERSION_OVERRIDE
          value: "3.3"
        - name: GALLIUM_DRIVER
          value: llvmpipe
        {{- end }}
        ports:
        - containerPort: 9002
          name: ws
        volumeMounts:
        {{- if .Values.persistence.enabled }}
        - name: fuel-cache
          mountPath: /fuel-cache
        {{- end }}
        {{- if .Values.customWorldConfigMap }}
        - name: custom-world
          mountPath: /worlds/{{ .Values.world }}.sdf
          subPath: {{ .Values.world }}.sdf
        {{- end }}
        resources:
          {{- if eq .Values.gpu.vendor "nvidia" }}
          requests:
            cpu: {{ .Values.resources.requests.cpu | quote }}
            memory: {{ .Values.resources.requests.memory | quote }}
          limits:
            cpu: {{ .Values.resources.limits.cpu | quote }}
            memory: {{ .Values.resources.limits.memory | quote }}
            nvidia.com/gpu: 1
          {{- else if eq .Values.gpu.vendor "amd" }}
          requests:
            cpu: {{ .Values.resources.requests.cpu | quote }}
            memory: {{ .Values.resources.requests.memory | quote }}
          limits:
            cpu: {{ .Values.resources.limits.cpu | quote }}
            memory: {{ .Values.resources.limits.memory | quote }}
            amd.com/gpu: 1
          {{- else }}
          {{- toYaml .Values.resources | nindent 10 }}
          {{- end }}
      volumes:
      {{- if .Values.persistence.enabled }}
      - name: fuel-cache
        persistentVolumeClaim:
          claimName: {{ .Values.engineer }}-fuel-cache
      {{- end }}
      {{- if .Values.customWorldConfigMap }}
      - name: custom-world
        configMap:
          name: {{ .Values.customWorldConfigMap }}
      {{- end }}
```

- [ ] **Step 5: Create service.yaml**

`charts/gz-sim/templates/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "gzsim.fullname" . }}-ws
  labels:
    {{- include "gzsim.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  ports:
  - port: 9002
    targetPort: ws
    name: ws
  selector:
    {{- include "gzsim.selectorLabels" . | nindent 4 }}
```

- [ ] **Step 6: Create route.yaml**

`charts/gz-sim/templates/route.yaml`:

```yaml
{{- if .Values.route.enabled }}
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: gz-{{ .Values.engineer }}
  labels:
    {{- include "gzsim.labels" . | nindent 4 }}
  annotations:
    haproxy.router.openshift.io/timeout: 300s
spec:
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: {{ include "gzsim.fullname" . }}-ws
  port:
    targetPort: ws
{{- end }}
```

- [ ] **Step 7: Create configmap.yaml (for built-in world overrides)**

`charts/gz-sim/templates/configmap.yaml`:

```yaml
{{- if .Values.customWorldConfigMap }}
# Custom world files are provided via the ConfigMap named in
# .Values.customWorldConfigMap. No additional ConfigMap needed here.
{{- end }}
```

This is intentionally minimal - custom worlds are provided by the user creating their own ConfigMap before `helm install`.

- [ ] **Step 8: Create pvc.yaml**

`charts/gz-sim/templates/pvc.yaml`:

```yaml
{{- if .Values.persistence.enabled }}
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ .Values.engineer }}-fuel-cache
  labels:
    {{- include "gzsim.labels" . | nindent 4 }}
  {{- if .Values.persistence.keep }}
  annotations:
    helm.sh/resource-policy: keep
  {{- end }}
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: {{ .Values.persistence.size }}
  {{- if .Values.persistence.storageClass }}
  storageClassName: {{ .Values.persistence.storageClass }}
  {{- end }}
{{- end }}
```

- [ ] **Step 9: Lint and test all GPU modes**

```bash
helm lint charts/gz-sim --set engineer=test

# CPU-only
helm template test-sim charts/gz-sim --set engineer=chris | grep -A5 "LIBGL\|GALLIUM\|STREAM_PREFIX\|MEDIAMTX"

# NVIDIA
helm template test-sim charts/gz-sim --set engineer=chris --set gpu.vendor=nvidia | grep -A2 "runtimeClassName\|nvidia.com"

# AMD
helm template test-sim charts/gz-sim --set engineer=chris --set gpu.vendor=amd | grep -A2 "amd.com\|supplementalGroups"

# Missing engineer should fail
helm template test-sim charts/gz-sim 2>&1 | grep "engineer is required"
```

Expected:
- Lints clean
- CPU mode shows LIBGL_ALWAYS_SOFTWARE, GALLIUM_DRIVER, STREAM_PREFIX
- NVIDIA mode shows runtimeClassName: nvidia, nvidia.com/gpu: 1
- AMD mode shows amd.com/gpu: 1, supplementalGroups
- Missing engineer fails with error message

- [ ] **Step 10: Commit**

```bash
git add charts/gz-sim/
git commit -m "Add Helm chart for per-engineer Gazebo simulation"
```

---

## Task 10: Update .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add Helm chart artifacts to .gitignore**

Append to `.gitignore`:

```
# Helm
charts/*/charts/
*.tgz
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "Add Helm artifacts to gitignore"
```

---

## Task 11: Integration Verification

This task verifies the complete chart structure renders correctly together by simulating a full deployment with `helm template`.

- [ ] **Step 1: Render all charts and count resources**

```bash
echo "=== coturn ===" && helm template coturn charts/coturn | grep "^kind:" | sort | uniq -c
echo "=== mediamtx ===" && helm template mediamtx charts/mediamtx --set coturn.host=10.0.0.1 | grep "^kind:" | sort | uniq -c
echo "=== viewer ===" && helm template viewer charts/viewer --set mediamtx.base=https://mtx.apps.test --set mediamtx.api=https://mtx-api.apps.test | grep "^kind:" | sort | uniq -c
echo "=== gz-sim ===" && helm template chris-sim charts/gz-sim --set engineer=chris | grep "^kind:" | sort | uniq -c
```

Expected resource counts:
- coturn: 1 ConfigMap, 1 Deployment
- mediamtx: 1 ConfigMap, 1 Deployment, 2 Route, 2 Service
- viewer: 1 Deployment, 1 Route, 1 Service
- gz-sim: 1 Deployment, 1 PersistentVolumeClaim, 1 Route, 1 Service

- [ ] **Step 2: Verify cross-chart service references**

```bash
# The gz-sim chart's MEDIAMTX_WHIP_BASE should reference the mediamtx service name
helm template chris-sim charts/gz-sim --set engineer=chris | grep MEDIAMTX_WHIP_BASE

# The mediamtx service name that gz-sim references
helm template mediamtx charts/mediamtx --set coturn.host=10.0.0.1 | grep "name:.*webrtc"
```

Expected: gz-sim references `mediamtx-webrtc.gz-sim.svc.cluster.local`. The mediamtx chart's fullname helper uses just the release name (no suffix), so `helm install mediamtx` produces a service named `mediamtx-webrtc` - matching the gz-sim default.

- [ ] **Step 3: Verify Route names don't collide**

```bash
helm template coturn charts/coturn | grep "name:" | head -5
helm template mediamtx charts/mediamtx --set coturn.host=10.0.0.1 | grep -E "^  name:"
helm template viewer charts/viewer --set mediamtx.base=x --set mediamtx.api=x | grep -E "^  name:"
helm template chris charts/gz-sim --set engineer=chris | grep -E "^  name:"
helm template dave charts/gz-sim --set engineer=dave | grep -E "^  name:"
```

Expected: All resource names are unique. Two gz-sim installs produce different names because the release name differs.

- [ ] **Step 4: Final commit if any adjustments were needed**

Only if step 2 revealed a service name mismatch or similar issue:

```bash
git add -A
git commit -m "Fix cross-chart service name references"
```
