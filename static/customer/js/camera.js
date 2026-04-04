/**
 * MirrAI Camera Service
 * Handles camera stream, MediaPipe face alignment, auto capture, preview, and upload navigation.
 */
(function () {
  "use strict";

  const AUTO_CAPTURE_SECONDS = 3;
  const DETECTION_INTERVAL_MS = 140;
  const STABLE_ALIGNMENT_THRESHOLD = 3;
  const MISALIGNMENT_THRESHOLD = 2;
  const MEDIAPIPE_VERSION = "0.10.34";
  const MEDIAPIPE_MODULE_URL =
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@" +
    MEDIAPIPE_VERSION +
    "/vision_bundle.mjs";
  const MEDIAPIPE_WASM_URL =
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@" +
    MEDIAPIPE_VERSION +
    "/wasm";
  const MEDIAPIPE_MODEL_URL =
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
  const HAND_MEDIAPIPE_MODEL_URL =
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

  const LANDMARK_INDEX = {
    noseTip: 1,
    leftEyeOuter: 33,
    rightEyeOuter: 263
  };

  const videoEl = document.getElementById("cameraPreview");
  const statusEl = document.getElementById("cameraStatus");
  const toggleBtn = document.getElementById("cameraToggleBtn");
  const captureBtn = document.getElementById("captureBtn");
  const switchBtn = document.getElementById("cameraSwitchBtn");
  const fallbackEl = document.getElementById("cameraFallback");
  const cameraGuide = document.getElementById("cameraGuide");
  const guideOutlineEl = document.getElementById("cameraGuideOutline");
  const guideCenterLineEl = document.getElementById("cameraGuideCenterLine");
  const guideEyeLineEl = document.getElementById("cameraGuideEyeLine");
  const guideNoseLineEl = document.getElementById("cameraGuideNoseLine");
  const shutterFlashEl = document.getElementById("cameraShutterFlash");
  const autoHintEl = document.getElementById("cameraAutoHint");
  const countdownEl = document.getElementById("cameraCountdown");
  const countdownValueEl = document.getElementById("cameraCountdownValue");
  const cameraControls = document.getElementById("cameraControls");
  const previewContainer = document.getElementById("photoPreviewContainer");
  const previewImg = document.getElementById("photoPreview");
  const previewControls = document.getElementById("previewControls");
  const confirmBtn = document.getElementById("confirmBtn");
  const retakeBtn = document.getElementById("retakeBtn");
  const captureCanvas = document.getElementById("captureCanvas");
  const conditionSummaryEl = document.getElementById("cameraConditionSummary");

  const conditionEls = {
    face: {
      item: document.getElementById("conditionFaceItem"),
      icon: document.getElementById("conditionFaceIcon"),
      status: document.getElementById("conditionFaceStatus")
    },
    obstruction: {
      item: document.getElementById("conditionObstructionItem"),
      icon: document.getElementById("conditionObstructionIcon"),
      status: document.getElementById("conditionObstructionStatus")
    },
    center: {
      item: document.getElementById("conditionCenterItem"),
      icon: document.getElementById("conditionCenterIcon"),
      status: document.getElementById("conditionCenterStatus")
    },
    distance: {
      item: document.getElementById("conditionDistanceItem"),
      icon: document.getElementById("conditionDistanceIcon"),
      status: document.getElementById("conditionDistanceStatus")
    },
    angle: {
      item: document.getElementById("conditionAngleItem"),
      icon: document.getElementById("conditionAngleIcon"),
      status: document.getElementById("conditionAngleStatus")
    }
  };

  let stream = null;
  let isCameraOn = false;
  let facingMode = "user";
  let capturedBlob = null;
  let previewUrl = null;
  let faceLandmarker = null;
  let handLandmarker = null;
  let mediaPipeLoadPromise = null;
  let autoCaptureSupported = true;
  let detectorFrameHandle = null;
  let countdownTimer = null;
  let countdownDeadline = 0;
  let stableAlignmentCount = 0;
  let misalignmentCount = 0;
  let lastVideoTime = -1;
  let lastDetectionAt = 0;
  let lastGuidanceKey = "";
  let audioContext = null;

  function init() {
    if (
      !videoEl ||
      !statusEl ||
      !toggleBtn ||
      !captureBtn ||
      !previewContainer ||
      !captureCanvas
    ) {
      console.error("Required camera UI elements were not found.");
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      handleError({ name: "NotSupportedError" });
      return;
    }

    toggleBtn.addEventListener("click", handleToggle);
    captureBtn.addEventListener("click", () => handleCapture({ source: "manual" }));
    switchBtn.addEventListener("click", handleSwitch);
    retakeBtn.addEventListener("click", handleRetake);
    confirmBtn.addEventListener("click", handleConfirm);

    window.addEventListener("beforeunload", cleanup);
    window.addEventListener("pagehide", cleanup);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        stopStream();
      }
    });

    updateChecklist(getLoadingChecklistState());
    updateStatus("카메라와 MediaPipe 얼굴 분석 모델을 준비하는 중입니다...", "loading");
    updateAutoHint("MediaPipe 얼굴 분석 모델을 불러오는 중입니다.", "idle");

    startCamera();
    ensureFaceLandmarker().catch((error) => {
      console.error("MediaPipe initialization failed.", error);
      activateManualMode(
        "MediaPipe 얼굴 분석 모델을 불러오지 못해 수동 촬영으로 전환했습니다."
      );
    });
  }

  function updateStatus(message, type = "") {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = "camera-status " + type;
  }

  function updateAutoHint(message, tone = "idle") {
    if (!autoHintEl) return;

    const toneStyles = {
      idle: {
        borderColor: "rgba(0, 255, 157, 0.28)",
        backgroundColor: "rgba(8, 13, 11, 0.72)",
        color: "rgba(255, 255, 255, 0.92)"
      },
      ready: {
        borderColor: "rgba(255, 214, 107, 0.52)",
        backgroundColor: "rgba(43, 34, 8, 0.78)",
        color: "#fff6d6"
      },
      error: {
        borderColor: "rgba(255, 122, 122, 0.42)",
        backgroundColor: "rgba(42, 12, 12, 0.78)",
        color: "#ffe0e0"
      },
      manual: {
        borderColor: "rgba(255, 255, 255, 0.18)",
        backgroundColor: "rgba(20, 20, 20, 0.72)",
        color: "rgba(255, 255, 255, 0.82)"
      }
    };

    const style = toneStyles[tone] || toneStyles.idle;
    autoHintEl.textContent = message;
    autoHintEl.style.borderColor = style.borderColor;
    autoHintEl.style.backgroundColor = style.backgroundColor;
    autoHintEl.style.color = style.color;
  }

  function setGuideState(state) {
    const palette = {
      idle: {
        outline: "rgba(255, 255, 255, 0.92)",
        center: "rgba(255, 255, 255, 0.22)",
        eye: "rgba(255, 255, 255, 0.18)",
        nose: "rgba(255, 255, 255, 0.74)",
        glow: "drop-shadow(0 0 10px rgba(255, 255, 255, 0.18))",
        opacity: "0.94"
      },
      ready: {
        outline: "rgba(255, 255, 255, 1)",
        center: "rgba(255, 255, 255, 0.3)",
        eye: "rgba(255, 255, 255, 0.24)",
        nose: "rgba(255, 255, 255, 0.96)",
        glow: "drop-shadow(0 0 18px rgba(255, 255, 255, 0.3))",
        opacity: "1"
      },
      error: {
        outline: "rgba(255, 146, 146, 0.95)",
        center: "rgba(255, 146, 146, 0.22)",
        eye: "rgba(255, 146, 146, 0.18)",
        nose: "rgba(255, 170, 170, 0.82)",
        glow: "none",
        opacity: "0.96"
      },
      manual: {
        outline: "rgba(255, 255, 255, 0.62)",
        center: "rgba(255, 255, 255, 0.16)",
        eye: "rgba(255, 255, 255, 0.14)",
        nose: "rgba(255, 255, 255, 0.52)",
        glow: "none",
        opacity: "0.82"
      }
    };

    const style = palette[state] || palette.idle;

    if (guideOutlineEl) {
      guideOutlineEl.style.stroke = style.outline;
      guideOutlineEl.style.filter = style.glow;
      guideOutlineEl.style.opacity = style.opacity;
    }

    if (guideCenterLineEl) {
      guideCenterLineEl.style.stroke = style.center;
      guideCenterLineEl.style.opacity = style.opacity;
    }

    if (guideEyeLineEl) {
      guideEyeLineEl.style.stroke = style.eye;
      guideEyeLineEl.style.opacity = style.opacity;
    }

    if (guideNoseLineEl) {
      guideNoseLineEl.style.stroke = style.nose;
      guideNoseLineEl.style.opacity = style.opacity;
    }
  }

  function buildChecklistState(summary, overrides = {}) {
    const items = {
      face: {
        state: "pending",
        text: "얼굴을 찾는 중입니다."
      },
      obstruction: {
        state: "pending",
        text: "손이나 가림 요소를 확인하는 중입니다."
      },
      center: {
        state: "pending",
        text: "얼굴이 감지되면 바로 확인합니다."
      },
      distance: {
        state: "pending",
        text: "거리를 아직 확인하지 못했습니다."
      },
      angle: {
        state: "pending",
        text: "정면 각도를 아직 확인하지 못했습니다."
      }
    };

    Object.keys(overrides).forEach((key) => {
      items[key] = {
        ...items[key],
        ...overrides[key]
      };
    });

    return {
      summary,
      items
    };
  }

  function getLoadingChecklistState() {
    return buildChecklistState("모델 준비 중", {
      face: { text: "MediaPipe 모델을 불러오는 중입니다." },
      obstruction: { text: "손 가림 감지 모델을 불러오는 중입니다." },
      center: { text: "모델 로드 후 중앙 정렬을 확인합니다." },
      distance: { text: "모델 로드 후 거리 조건을 확인합니다." },
      angle: { text: "모델 로드 후 정면 각도를 확인합니다." }
    });
  }

  function getPausedChecklistState() {
    return buildChecklistState("카메라 대기", {
      face: { text: "카메라를 켜면 얼굴 감지를 시작합니다." },
      obstruction: { text: "카메라를 켜면 손 가림 여부를 확인합니다." },
      center: { text: "카메라가 켜지면 중앙 정렬을 확인합니다." },
      distance: { text: "카메라가 켜지면 거리 조건을 확인합니다." },
      angle: { text: "카메라가 켜지면 정면 각도를 확인합니다." }
    });
  }

  function getManualChecklistState() {
    return buildChecklistState("수동 모드", {
      face: { text: "자동 체크를 사용할 수 없어 수동 촬영을 사용합니다." },
      obstruction: { text: "가림 감지를 사용할 수 없어 자동 촬영을 중지했습니다." },
      center: { text: "즉시 촬영 버튼으로 바로 촬영할 수 있습니다." },
      distance: { text: "촬영 전에 얼굴 크기만 눈으로 한 번 확인해 주세요." },
      angle: { text: "정면을 바라보고 촬영하면 분석 품질이 더 좋아집니다." }
    });
  }

  function updateChecklist(checklist) {
    if (!checklist) return;

    if (conditionSummaryEl) {
      conditionSummaryEl.textContent = checklist.summary;
    }

    Object.keys(conditionEls).forEach((key) => {
      const config = conditionEls[key];
      const itemState = checklist.items[key];

      if (!config || !itemState) return;

      config.item.dataset.state = itemState.state;
      config.status.textContent = itemState.text;

      if (itemState.state === "valid") {
        config.icon.textContent = "✓";
      } else if (itemState.state === "invalid") {
        config.icon.textContent = "!";
      } else {
        config.icon.textContent = "○";
      }
    });
  }

  function showCountdown(value) {
    if (!countdownEl || !countdownValueEl) return;
    countdownValueEl.textContent = String(value);
    countdownEl.classList.remove("is-hidden");
  }

  function hideCountdown() {
    if (!countdownEl) return;
    countdownEl.classList.add("is-hidden");
  }

  function cleanupPreviewUrl() {
    if (!previewUrl) return;
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }

  function triggerShutterFlash() {
    if (!shutterFlashEl) return;
    shutterFlashEl.classList.remove("is-active");
    void shutterFlashEl.offsetWidth;
    shutterFlashEl.classList.add("is-active");
  }

  function playShutterSound() {
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;

    if (!AudioContextCtor) {
      return;
    }

    try {
      if (!audioContext) {
        audioContext = new AudioContextCtor();
      }

      if (audioContext.state === "suspended") {
        audioContext.resume().catch(() => undefined);
      }

      const now = audioContext.currentTime;
      const gainNode = audioContext.createGain();
      gainNode.connect(audioContext.destination);
      gainNode.gain.setValueAtTime(0.0001, now);
      gainNode.gain.exponentialRampToValueAtTime(0.12, now + 0.01);
      gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.14);

      const tone = audioContext.createOscillator();
      tone.type = "triangle";
      tone.frequency.setValueAtTime(920, now);
      tone.frequency.exponentialRampToValueAtTime(260, now + 0.12);
      tone.connect(gainNode);
      tone.start(now);
      tone.stop(now + 0.14);

      const clickGain = audioContext.createGain();
      clickGain.connect(audioContext.destination);
      clickGain.gain.setValueAtTime(0.0001, now);
      clickGain.gain.exponentialRampToValueAtTime(0.08, now + 0.005);
      clickGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.04);

      const click = audioContext.createOscillator();
      click.type = "square";
      click.frequency.setValueAtTime(1800, now);
      click.frequency.exponentialRampToValueAtTime(600, now + 0.03);
      click.connect(clickGain);
      click.start(now);
      click.stop(now + 0.04);
    } catch (error) {
      console.warn("Unable to play shutter sound.", error);
    }
  }

  async function ensureFaceLandmarker() {
    if (faceLandmarker) {
      return faceLandmarker;
    }

    if (mediaPipeLoadPromise) {
      return mediaPipeLoadPromise;
    }

    mediaPipeLoadPromise = (async () => {
      const visionModule = await import(MEDIAPIPE_MODULE_URL);
      const vision = await visionModule.FilesetResolver.forVisionTasks(
        MEDIAPIPE_WASM_URL
      );

      faceLandmarker = await visionModule.FaceLandmarker.createFromOptions(
        vision,
        {
          baseOptions: {
            modelAssetPath: MEDIAPIPE_MODEL_URL
          },
          runningMode: "VIDEO",
          numFaces: 1,
          minFaceDetectionConfidence: 0.55,
          minFacePresenceConfidence: 0.55,
          minTrackingConfidence: 0.55
        }
      );

      return faceLandmarker;
    })().catch((error) => {
      mediaPipeLoadPromise = null;
      faceLandmarker = null;
      throw error;
    });

    return mediaPipeLoadPromise;
  }

  async function ensureHandLandmarker() {
    if (handLandmarker) {
      return handLandmarker;
    }

    const visionModule = await import(MEDIAPIPE_MODULE_URL);
    const vision = await visionModule.FilesetResolver.forVisionTasks(
      MEDIAPIPE_WASM_URL
    );

    handLandmarker = await visionModule.HandLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: HAND_MEDIAPIPE_MODEL_URL
      },
      runningMode: "VIDEO",
      numHands: 2,
      minHandDetectionConfidence: 0.55,
      minHandPresenceConfidence: 0.55,
      minTrackingConfidence: 0.55
    });

    return handLandmarker;
  }

  function stopStream() {
    stopDetectionLoop();

    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }

    if (videoEl) {
      videoEl.srcObject = null;
    }

    isCameraOn = false;

    if (toggleBtn) toggleBtn.textContent = "카메라 켜기";
    if (captureBtn) captureBtn.classList.add("is-hidden");
    if (fallbackEl) fallbackEl.classList.remove("is-hidden");

    updateChecklist(autoCaptureSupported ? getPausedChecklistState() : getManualChecklistState());
    updateAutoHint("카메라를 켜면 얼굴 정렬 체크를 다시 시작합니다.", "manual");
    setGuideState(autoCaptureSupported ? "idle" : "manual");
  }

  function cleanup() {
    stopStream();
    cleanupPreviewUrl();
  }

  async function startCamera() {
    updateStatus("카메라 연결 중입니다...", "loading");

    const constraints = {
      video: {
        facingMode: facingMode,
        width: { ideal: 1280 },
        height: { ideal: 720 },
        aspectRatio: { ideal: 1.333333 }
      },
      audio: false
    };

    try {
      if (stream) {
        stopStream();
      }

      stream = await navigator.mediaDevices.getUserMedia(constraints);
      videoEl.srcObject = stream;

      videoEl.onloadedmetadata = async () => {
        try {
          await videoEl.play();
        } catch (error) {
          console.warn("Unable to autoplay the camera preview.", error);
        }

        isCameraOn = true;
        toggleBtn.textContent = "카메라 끄기";
        captureBtn.classList.remove("is-hidden");
        fallbackEl.classList.add("is-hidden");

        updateStatus("MediaPipe 기준으로 얼굴 조건을 확인하는 중입니다...", "loading");
        updateAutoHint(
          "얼굴이 감지되면 오른쪽 체크리스트가 실시간으로 갱신됩니다.",
          "idle"
        );
        setGuideState("idle");

        startDetectionLoop();
      };
    } catch (error) {
      handleError(error);
    }
  }

  function getCaptureCropBox(videoWidth, videoHeight) {
    const targetHeight = videoHeight;
    const targetWidth = (videoHeight * 3) / 4;

    return {
      sx: (videoWidth - targetWidth) / 2,
      sy: 0,
      width: targetWidth,
      height: targetHeight
    };
  }

  function getNormalizedCropBox(videoWidth, videoHeight) {
    const crop = getCaptureCropBox(videoWidth, videoHeight);

    return {
      minX: crop.sx / videoWidth,
      maxX: (crop.sx + crop.width) / videoWidth,
      width: crop.width / videoWidth,
      minY: 0,
      maxY: 1,
      height: 1
    };
  }

  function isDetectionReady() {
    return (
      isCameraOn &&
      !capturedBlob &&
      videoEl &&
      videoEl.readyState >= 2 &&
      previewContainer &&
      previewContainer.classList.contains("is-hidden")
    );
  }

  function startDetectionLoop() {
    stopDetectionLoop({ preserveHint: true });

    if (!autoCaptureSupported) {
      updateChecklist(getManualChecklistState());
      captureBtn.textContent = "사진 촬영";
      updateAutoHint("즉시 촬영 버튼을 눌러 수동으로 촬영해 주세요.", "manual");
      setGuideState("manual");
      return;
    }

    Promise.all([ensureFaceLandmarker(), ensureHandLandmarker()])
      .then(() => {
        if (!isDetectionReady()) {
          return;
        }

        captureBtn.textContent = "즉시 촬영";
        lastVideoTime = -1;
        lastDetectionAt = 0;
        stableAlignmentCount = 0;
        misalignmentCount = 0;
        lastGuidanceKey = "";
        updateChecklist(getLoadingChecklistState());
        detectorFrameHandle = window.requestAnimationFrame(runDetectionLoop);
      })
      .catch((error) => {
        console.error("MediaPipe face detection could not start.", error);
        activateManualMode(
          "MediaPipe 얼굴 분석 모델을 불러오지 못해 수동 촬영으로 전환했습니다."
        );
      });
  }

  function stopDetectionLoop(options = {}) {
    if (detectorFrameHandle) {
      window.cancelAnimationFrame(detectorFrameHandle);
      detectorFrameHandle = null;
    }

    stableAlignmentCount = 0;
    misalignmentCount = 0;
    lastVideoTime = -1;
    lastDetectionAt = 0;
    lastGuidanceKey = "";

    cancelCountdown({ preserveHint: options.preserveHint });
  }

  function activateManualMode(message) {
    autoCaptureSupported = false;
    stopDetectionLoop({ preserveHint: true });
    captureBtn.textContent = "사진 촬영";
    updateChecklist(getManualChecklistState());
    updateStatus(message, "error");
    updateAutoHint("즉시 촬영 버튼을 눌러 수동으로 촬영해 주세요.", "manual");
    setGuideState("manual");
  }

  function runDetectionLoop(now) {
    detectorFrameHandle = null;

    if (!isDetectionReady() || !faceLandmarker) {
      return;
    }

    if (
      videoEl.currentTime === lastVideoTime ||
      now - lastDetectionAt < DETECTION_INTERVAL_MS
    ) {
      detectorFrameHandle = window.requestAnimationFrame(runDetectionLoop);
      return;
    }

    lastVideoTime = videoEl.currentTime;
    lastDetectionAt = now;

    try {
      const faceResult = faceLandmarker.detectForVideo(videoEl, now);
      const handResult = handLandmarker
        ? handLandmarker.detectForVideo(videoEl, now)
        : null;
      const evaluation = evaluateDetection(faceResult, handResult);
      applyDetectionResult(evaluation);
    } catch (error) {
      console.error("MediaPipe detectForVideo failed.", error);
      activateManualMode("MediaPipe 가림 감지 중 오류가 발생해 수동 촬영으로 전환했습니다.");
      return;
    }

    if (isDetectionReady() && autoCaptureSupported) {
      detectorFrameHandle = window.requestAnimationFrame(runDetectionLoop);
    }
  }

  function getLandmarkBounds(points) {
    let minX = 1;
    let minY = 1;
    let maxX = 0;
    let maxY = 0;

    points.forEach((point) => {
      minX = Math.min(minX, point.x);
      minY = Math.min(minY, point.y);
      maxX = Math.max(maxX, point.x);
      maxY = Math.max(maxY, point.y);
    });

    return {
      minX,
      minY,
      maxX,
      maxY,
      width: Math.max(0.0001, maxX - minX),
      height: Math.max(0.0001, maxY - minY),
      centerX: (minX + maxX) / 2,
      centerY: (minY + maxY) / 2
    };
  }

  function rectsOverlap(a, b) {
    return (
      a.minX < b.maxX &&
      a.maxX > b.minX &&
      a.minY < b.maxY &&
      a.maxY > b.minY
    );
  }

  function pointInGuideEllipse(point, crop) {
    const localX = (point.x - crop.minX) / crop.width;
    const localY = point.y;
    const dx = (localX - 0.5) / 0.245;
    const dy = (localY - 0.435) / 0.255;

    return dx * dx + dy * dy <= 1;
  }

  function handBlocksFaceGuide(handResult, crop, faceBounds) {
    const handLandmarks = handResult && Array.isArray(handResult.landmarks)
      ? handResult.landmarks
      : [];

    if (!handLandmarks.length) {
      return false;
    }

    const expandedFaceBounds = {
      minX: Math.max(crop.minX, faceBounds.minX - 0.045),
      maxX: Math.min(crop.maxX, faceBounds.maxX + 0.045),
      minY: Math.max(0, faceBounds.minY - 0.05),
      maxY: Math.min(1, faceBounds.maxY + 0.05)
    };

    return handLandmarks.some((handPoints) => {
      const handBounds = getLandmarkBounds(handPoints);
      const handCenter = {
        x: handBounds.centerX,
        y: handBounds.centerY
      };

      return (
        rectsOverlap(handBounds, expandedFaceBounds) ||
        pointInGuideEllipse(handCenter, crop)
      );
    });
  }

  function evaluateDetection(faceResult, handResult) {
    const faceLandmarks = faceResult && Array.isArray(faceResult.faceLandmarks)
      ? faceResult.faceLandmarks
      : [];

    if (faceLandmarks.length === 0) {
      return {
        messageKey: "no_face",
        message: "얼굴을 가이드 안에 맞춰 주세요.",
        hint: "얼굴이 감지되면 조건 체크가 켜집니다.",
        type: "",
        tone: "idle",
        guideState: "idle",
        allValid: false,
        checklist: buildChecklistState("0 / 5 완료", {
          face: { state: "invalid", text: "얼굴이 아직 감지되지 않았습니다." },
          obstruction: { text: "얼굴이 감지되면 손 가림 여부를 확인합니다." },
          center: { text: "얼굴이 감지되면 중앙 정렬을 확인합니다." },
          distance: { text: "얼굴이 감지되면 거리 조건을 확인합니다." },
          angle: { text: "얼굴이 감지되면 정면 각도를 확인합니다." }
        })
      };
    }

    if (faceLandmarks.length > 1) {
      return {
        messageKey: "multiple_faces",
        message: "한 사람만 화면에 나오도록 조정해 주세요.",
        hint: "프레임 안에는 한 사람의 얼굴만 남겨 주세요.",
        type: "error",
        tone: "error",
        guideState: "error",
        allValid: false,
        checklist: buildChecklistState("0 / 5 완료", {
          face: { state: "invalid", text: "여러 얼굴이 보여 한 사람만 남겨야 합니다." },
          obstruction: { text: "한 사람만 남으면 손 가림 여부를 확인합니다." },
          center: { text: "한 사람만 남으면 중앙 정렬을 확인합니다." },
          distance: { text: "한 사람만 남으면 거리 조건을 확인합니다." },
          angle: { text: "한 사람만 남으면 정면 각도를 확인합니다." }
        })
      };
    }

    const points = faceLandmarks[0];
    const bounds = getLandmarkBounds(points);
    const crop = getNormalizedCropBox(videoEl.videoWidth, videoEl.videoHeight);
    const localCenterX = (bounds.centerX - crop.minX) / crop.width;
    const localCenterY = bounds.centerY;
    const faceWidthRatio = bounds.width / crop.width;
    const faceHeightRatio = bounds.height;
    const leftEye = points[LANDMARK_INDEX.leftEyeOuter];
    const rightEye = points[LANDMARK_INDEX.rightEyeOuter];
    const nose = points[LANDMARK_INDEX.noseTip] || {
      x: bounds.centerX,
      y: bounds.centerY
    };
    const eyeSlope = leftEye && rightEye ? Math.abs(leftEye.y - rightEye.y) : 0;
    const noseBias = Math.abs(
      ((nose.x - bounds.minX) / Math.max(bounds.width, 0.0001)) - 0.5
    );

    const faceVisible =
      bounds.minX >= crop.minX + 0.02 &&
      bounds.maxX <= crop.maxX - 0.02 &&
      bounds.minY >= 0.08 &&
      bounds.maxY <= 0.84;

    const centered =
      faceVisible &&
      Math.abs(localCenterX - 0.5) <= 0.14 &&
      Math.abs(localCenterY - 0.39) <= 0.12;

    const distanceOk =
      faceWidthRatio >= 0.28 &&
      faceWidthRatio <= 0.58 &&
      faceHeightRatio >= 0.30 &&
      faceHeightRatio <= 0.72;

    const angleOk = eyeSlope <= 0.03 && noseBias <= 0.14;
    const obstructionFree = !handBlocksFaceGuide(handResult, crop, bounds);

    const checklist = buildChecklistState(
      [faceVisible, obstructionFree, centered, distanceOk, angleOk].filter(Boolean).length + " / 5 완료",
      {
        face: {
          state: "valid",
          text: "한 명의 얼굴이 안정적으로 감지되었습니다."
        },
        obstruction: {
          state: obstructionFree ? "valid" : "invalid",
          text: obstructionFree
            ? "손이나 가림 요소가 얼굴 가이드 밖에 있습니다."
            : "손이나 물체가 얼굴 가이드와 겹쳐 자동 촬영이 중지되었습니다."
        },
        center: {
          state: centered ? "valid" : "invalid",
          text: centered
            ? "얼굴 중심이 가이드 중앙에 잘 맞았습니다."
            : "얼굴을 조금만 좌우 또는 위아래로 옮겨 중앙에 맞춰 주세요."
        },
        distance: {
          state: distanceOk ? "valid" : "invalid",
          text: distanceOk
            ? "거리가 적절해 얼굴 전체가 자연스럽게 들어왔습니다."
            : faceWidthRatio < 0.28
              ? "얼굴이 조금 멉니다. 카메라에 더 가까이 와 주세요."
              : "얼굴이 조금 가깝습니다. 한 걸음만 뒤로 가 주세요."
        },
        angle: {
          state: angleOk ? "valid" : "invalid",
          text: angleOk
            ? "정면 각도가 안정적이라 자동 촬영에 적합합니다."
            : "고개 기울임을 줄이고 정면을 바라봐 주세요."
        }
      }
    );

    if (!obstructionFree) {
      return {
        messageKey: "obstruction",
        message: "손이나 다른 가림 요소를 얼굴 가이드 밖으로 빼 주세요.",
        hint: "얼굴 주변의 손, 휴대폰, 머리카락이 겹치면 자동 촬영되지 않습니다.",
        type: "error",
        tone: "error",
        guideState: "error",
        allValid: false,
        checklist
      };
    }

    if (!centered) {
      return {
        messageKey: "off_center",
        message: "얼굴을 가이드 중앙에 맞춰 주세요.",
        hint: "윤곽선 중앙에 얼굴을 맞추면 다음 체크가 켜집니다.",
        type: "",
        tone: "idle",
        guideState: "idle",
        allValid: false,
        checklist
      };
    }

    if (!distanceOk) {
      return {
        messageKey: faceWidthRatio < 0.28 ? "too_far" : "too_close",
        message:
          faceWidthRatio < 0.28
            ? "얼굴이 조금 멉니다. 카메라에 더 가까이 와 주세요."
            : "얼굴이 조금 가깝습니다. 한 걸음만 뒤로 가 주세요.",
        hint: "얼굴 전체가 가이드 안에 자연스럽게 들어오게 맞춰 주세요.",
        type: "",
        tone: "idle",
        guideState: "idle",
        allValid: false,
        checklist
      };
    }

    if (!angleOk) {
      return {
        messageKey: "angle",
        message: "고개를 바로 세우고 정면을 바라봐 주세요.",
        hint: "눈높이를 맞추고 정면을 보면 자동 촬영이 더 안정적입니다.",
        type: "",
        tone: "idle",
        guideState: "idle",
        allValid: false,
        checklist
      };
    }

    return {
      messageKey: "aligned",
      message: "좋아요. 모든 조건이 맞았습니다. 3초 뒤 자동으로 촬영됩니다.",
      hint: "움직이지 말고 그대로 유지해 주세요.",
      type: "success",
      tone: "ready",
      guideState: "ready",
      allValid: true,
      checklist
    };
  }

  function syncGuidance(result) {
    if (lastGuidanceKey === result.messageKey) {
      return;
    }

    lastGuidanceKey = result.messageKey;
    updateStatus(result.message, result.type || "");
    updateAutoHint(result.hint, result.tone || "idle");
    setGuideState(result.guideState || "idle");
  }

  function applyDetectionResult(result) {
    updateChecklist(result.checklist);

    if (!result.allValid) {
      stableAlignmentCount = 0;
      misalignmentCount = Math.min(misalignmentCount + 1, MISALIGNMENT_THRESHOLD);

      if (countdownTimer && misalignmentCount < MISALIGNMENT_THRESHOLD) {
        return;
      }

      cancelCountdown();
      syncGuidance(result);
      return;
    }

    misalignmentCount = 0;
    stableAlignmentCount = Math.min(
      stableAlignmentCount + 1,
      STABLE_ALIGNMENT_THRESHOLD
    );

    syncGuidance(result);

    if (stableAlignmentCount >= STABLE_ALIGNMENT_THRESHOLD) {
      startCountdown();
    }
  }

  function startCountdown() {
    if (countdownTimer || !isDetectionReady()) return;

    countdownDeadline = Date.now() + AUTO_CAPTURE_SECONDS * 1000;
    updateStatus("좋아요. 3초 동안 그대로 유지하면 자동으로 촬영됩니다.", "success");
    updateAutoHint("체크가 모두 켜졌습니다. 움직이지 말고 그대로 유지해 주세요.", "ready");
    setGuideState("ready");
    showCountdown(AUTO_CAPTURE_SECONDS);

    countdownTimer = window.setInterval(() => {
      if (!isDetectionReady()) {
        cancelCountdown();
        return;
      }

      const remainingMs = countdownDeadline - Date.now();
      const remainingSeconds = Math.max(0, Math.ceil(remainingMs / 1000));

      showCountdown(remainingSeconds || 1);

      if (remainingMs <= 0) {
        window.clearInterval(countdownTimer);
        countdownTimer = null;
        countdownDeadline = 0;
        hideCountdown();
        handleCapture({ source: "auto" });
      }
    }, 100);
  }

  function cancelCountdown(options = {}) {
    if (countdownTimer) {
      window.clearInterval(countdownTimer);
      countdownTimer = null;
    }

    countdownDeadline = 0;
    hideCountdown();

    if (!options.preserveHint && isDetectionReady() && autoCaptureSupported) {
      updateAutoHint(
        "얼굴 조건이 모두 맞으면 3초 후 자동으로 촬영됩니다.",
        "idle"
      );
    }
  }

  function handleCapture(options = {}) {
    if (!isCameraOn || !videoEl || videoEl.readyState < 2 || capturedBlob) return;

    stopDetectionLoop({ preserveHint: true });
    triggerShutterFlash();
    playShutterSound();

    const cropBox = getCaptureCropBox(videoEl.videoWidth, videoEl.videoHeight);

    captureCanvas.width = cropBox.width;
    captureCanvas.height = cropBox.height;

    const ctx = captureCanvas.getContext("2d");

    if (!ctx) {
      updateStatus("촬영 이미지를 준비하지 못했습니다. 다시 시도해 주세요.", "error");
      startDetectionLoop();
      return;
    }

    ctx.drawImage(
      videoEl,
      cropBox.sx,
      cropBox.sy,
      cropBox.width,
      cropBox.height,
      0,
      0,
      cropBox.width,
      cropBox.height
    );

    captureCanvas.toBlob(
      (blob) => {
        if (!blob) {
          updateStatus("촬영에 실패했습니다. 다시 시도해 주세요.", "error");
          startDetectionLoop();
          return;
        }

        capturedBlob = blob;
        cleanupPreviewUrl();
        previewUrl = URL.createObjectURL(blob);

        previewImg.src = previewUrl;
        previewContainer.classList.remove("is-hidden");
        previewControls.classList.remove("is-hidden");

        videoEl.classList.add("is-hidden");
        cameraGuide.classList.add("is-hidden");
        cameraControls.classList.add("is-hidden");

        updateStatus(
          options.source === "auto"
            ? "조건이 맞아 자동으로 사진을 촬영했습니다. 결과를 확인해 주세요."
            : "사진을 촬영했습니다. 결과를 확인해 주세요.",
          "success"
        );
        updateAutoHint("촬영 결과를 확인한 뒤 업로드를 진행해 주세요.", "ready");
      },
      "image/jpeg",
      0.95
    );
  }

  function handleRetake() {
    if (capturedBlob && !confirm("이 사진을 버리고 다시 촬영하시겠습니까?")) {
      return;
    }

    cleanupPreviewUrl();
    previewImg.src = "";
    capturedBlob = null;

    confirmBtn.disabled = false;
    retakeBtn.disabled = false;

    videoEl.classList.remove("is-hidden");
    cameraGuide.classList.remove("is-hidden");
    cameraControls.classList.remove("is-hidden");
    previewContainer.classList.add("is-hidden");
    previewControls.classList.add("is-hidden");

    updateStatus(
      autoCaptureSupported
        ? "얼굴 조건이 맞으면 3초 뒤 자동으로 다시 촬영됩니다."
        : "정면을 바라본 뒤 즉시 촬영 버튼으로 다시 촬영해 주세요.",
      "success"
    );

    updateAutoHint(
      autoCaptureSupported
        ? "오른쪽 체크리스트를 모두 켜면 자동 촬영됩니다."
        : "자동 체크를 사용할 수 없어 수동 촬영 모드입니다.",
      autoCaptureSupported ? "idle" : "manual"
    );

    setGuideState(autoCaptureSupported ? "idle" : "manual");

    if (isCameraOn && videoEl.paused) {
      videoEl.play().catch(() => undefined);
    }

    startDetectionLoop();
  }

  async function handleConfirm() {
    if (!capturedBlob) return;

    const config = window.MirrAIConfig || {};
    const customerId = config.customerId;
    const csrfToken = config.csrfToken || getCookie("csrftoken");

    if (!customerId) {
      alert("고객 정보가 만료되었습니다. 다시 시작해 주세요.");
      window.location.href = "/customer/";
      return;
    }

    updateStatus("이미지를 서버로 전송하고 분석을 시작합니다...", "loading");
    updateAutoHint("분석 준비 중입니다. 잠시만 기다려 주세요.", "ready");
    confirmBtn.disabled = true;
    retakeBtn.disabled = true;

    const formData = new FormData();
    formData.append("customer_id", customerId);
    formData.append("file", capturedBlob, "capture.jpg");

    try {
      const response = await fetch("/api/v1/capture/upload/", {
        method: "POST",
        body: formData,
        headers: {
          "X-CSRFToken": csrfToken
        }
      });

      if (!response.ok) {
        throw new Error("Upload failed");
      }

      const data = await response.json();
      const nextAction = data.nextAction || data.next_action;
      const uploadStatus = String(data.status || "").toLowerCase();

      if (uploadStatus === "needs_retake" || nextAction === "capture") {
        updateStatus(data.message || "사진을 다시 촬영해주세요.", "error");
        updateAutoHint("사진을 다시 맞춘 뒤 재촬영해 주세요.", "error");
        confirmBtn.disabled = false;
        retakeBtn.disabled = false;
        return;
      }

      let targetUrl = "/customer/survey/";
      if (nextAction === "dashboard") {
        targetUrl = "/customer/dashboard/";
      } else if (nextAction === "result" || nextAction === "recommendations") {
        targetUrl = "/customer/recommendations/";
      }

      updateStatus("분석을 시작했습니다. 다음 단계로 이동합니다...", "success");
      updateAutoHint("다음 화면으로 이동하고 있습니다.", "ready");
      window.setTimeout(() => {
        window.location.replace(targetUrl);
      }, 800);
    } catch (error) {
      console.error("Upload Error:", error);
      updateStatus("업로드 중 오류가 발생했습니다. 다시 시도해주세요.", "error");
      updateAutoHint("네트워크 상태를 확인한 뒤 다시 시도해 주세요.", "error");
      confirmBtn.disabled = false;
      retakeBtn.disabled = false;
    }
  }

  function getCookie(name) {
    let cookieValue = null;

    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");

      for (let i = 0; i < cookies.length; i += 1) {
        const cookie = cookies[i].trim();

        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }

    return cookieValue;
  }

  function handleToggle() {
    if (isCameraOn) {
      stopStream();
      updateStatus("카메라가 꺼졌습니다. 다시 켜서 촬영을 시작해 주세요.");
    } else {
      startCamera();
    }
  }

  async function handleSwitch() {
    updateStatus("카메라를 전환하는 중입니다...", "loading");
    facingMode = facingMode === "user" ? "environment" : "user";
    stopDetectionLoop({ preserveHint: true });
    await startCamera();
  }

  function handleError(error) {
    console.error("Camera Error:", error);
    stopStream();

    let message = "카메라를 사용할 수 없습니다.";
    if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
      message =
        "카메라 권한이 필요합니다. 브라우저 설정에서 카메라 권한을 허용해 주세요.";
    } else if (
      error.name === "NotFoundError" ||
      error.name === "DevicesNotFoundError"
    ) {
      message = "사용 가능한 카메라를 찾을 수 없습니다.";
    } else if (error.name === "NotSupportedError") {
      message = "이 브라우저는 카메라 기능을 지원하지 않습니다.";
    }

    updateStatus(message, "error");
    updateAutoHint("브라우저 권한 설정을 확인한 뒤 다시 시도해 주세요.", "error");
    setGuideState("error");
    updateChecklist(buildChecklistState("카메라 오류", {
      face: { state: "invalid", text: "카메라 연결이 필요합니다." },
      obstruction: { text: "카메라 연결 후 손 가림 여부를 확인합니다." },
      center: { text: "카메라 연결 후 자동 체크를 시작합니다." },
      distance: { text: "카메라 연결 후 자동 체크를 시작합니다." },
      angle: { text: "카메라 연결 후 자동 체크를 시작합니다." }
    }));
  }

  init();
})();
