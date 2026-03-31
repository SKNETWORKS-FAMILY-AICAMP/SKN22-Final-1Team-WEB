/**
 * MirrAI Camera Service with MediaPipe Face Landmarker & Checklist Auto-Capture
 * Optimized for robust auto-capture and real-time guidance (Reverted to Stable Version).
 */
(function () {
  'use strict';

  // DOM Elements
  const videoEl = document.getElementById("cameraPreview");
  const statusEl = document.getElementById("cameraStatus");
  const toggleBtn = document.getElementById("cameraToggleBtn");
  const captureBtn = document.getElementById("captureBtn");
  const switchBtn = document.getElementById("cameraSwitchBtn");
  const fallbackEl = document.getElementById("cameraFallback");
  const cameraGuide = document.getElementById("cameraGuide");
  const countdownOverlay = document.getElementById("countdownOverlay");
  const captureMessage = document.getElementById("captureMessage");

  const previewContainer = document.getElementById("photoPreviewContainer");
  const previewImg = document.getElementById("photoPreview");
  const previewControls = document.getElementById("previewControls");
  const confirmBtn = document.getElementById("confirmBtn");
  const retakeBtn = document.getElementById("retakeBtn");
  const captureCanvas = document.getElementById("captureCanvas");

  // Checklist DOM Elements
  const guideFaceDetected = document.getElementById("guideFaceDetected");
  const guideCentered = document.getElementById("guideCentered");
  const guideFrontal = document.getElementById("guideFrontal");

  // State
  let faceLandmarker = null;
  let isCameraOn = false;
  let facingMode = "user"; 
  let capturedBlob = null;
  let previewUrl = null;
  let stream = null;
  
  // Auto-Capture & Analysis State
  let countdownTimer = null;
  let countdownSeconds = 3;
  let isCapturing = false;
  let lastFaceResult = null;
  let isCountdownActive = false; // Flag to lock countdown calls

  // Thresholds (Slightly relaxed for better UX)
  const CENTER_THRESHOLD = 0.20;
  const ROTATION_THRESHOLD = 20;

  // Initialize
  async function init() {
    if (!videoEl || !statusEl || !toggleBtn || !captureBtn || !previewContainer) {
      console.error("Required UI elements not found.");
      return;
    }

    try {
      updateStatus("AI 모델 로딩 중...", "loading");
      const vision = window.vision;
      if (!vision) throw new Error("MediaPipe Tasks Vision library not loaded.");

      const filesetResolver = await vision.FilesetResolver.forVisionTasks(
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.3/wasm"
      );
      
      faceLandmarker = await vision.FaceLandmarker.createFromOptions(filesetResolver, {
        baseOptions: {
          modelAssetPath: `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`,
          delegate: "GPU"
        },
        outputFaceBlendshapes: true,
        runningMode: "VIDEO",
        numFaces: 1
      });
      
      console.log("MediaPipe FaceLandmarker Ready.");
    } catch (err) {
      console.error("FaceLandmarker Init Error:", err);
      updateStatus("AI 모듈 로드 실패.", "error");
    }

    toggleBtn.addEventListener("click", handleToggle);
    captureBtn.addEventListener("click", handleCapture);
    switchBtn.addEventListener("click", handleSwitch);
    retakeBtn.addEventListener("click", handleRetake);
    confirmBtn.addEventListener("click", handleConfirm);

    window.addEventListener("beforeunload", cleanup);
    setTimeout(startCamera, 500);
  }

  async function predictWebcam() {
    if (!isCameraOn || !faceLandmarker || isCapturing) return;

    if (videoEl.readyState >= 2) {
      const startTimeMs = performance.now();
      const results = faceLandmarker.detectForVideo(videoEl, startTimeMs);
      processFaceResults(results);
    }
    
    if (isCameraOn) {
      window.requestAnimationFrame(predictWebcam);
    }
  }

  function processFaceResults(results) {
    const hasFace = results.faceLandmarks && results.faceLandmarks.length > 0;
    
    if (!hasFace) {
      updateGuideChecklist(null);
      if (isCountdownActive || !statusEl.textContent.includes("인식")) {
        updateStatus("얼굴이 인식되지 않았습니다.", "warning");
        cancelAutoCaptureCountdown();
      }
      return;
    }

    const landmarks = results.faceLandmarks[0];
    const analysis = analyzeFaceQuality(landmarks);
    lastFaceResult = analysis;
    updateGuideChecklist(analysis);

    if (!analysis.quality_flags.centered) {
      if (isCountdownActive || !statusEl.textContent.includes("중앙")) {
        updateStatus("얼굴을 화면 중앙에 맞춰주세요.", "warning");
        cancelAutoCaptureCountdown();
      }
    } else if (!analysis.quality_flags.frontal) {
      if (isCountdownActive || !statusEl.textContent.includes("정면")) {
        updateStatus("고개를 정면으로 똑바로 해주세요.", "warning");
        cancelAutoCaptureCountdown();
      }
    } else if (analysis.quality_flags.ui_capture_ready) {
      if (!isCountdownActive) {
        updateStatus("준비되었습니다! 움직이지 마세요.", "success");
        startAutoCaptureCountdown();
      }
    }
  }

  function updateGuideChecklist(analysis) {
    const updateItem = (el, isChecked) => {
      if (!el) return;
      const checkMark = el.querySelector(".check-mark");
      if (isChecked) {
        el.style.opacity = "1";
        if (checkMark) checkMark.classList.remove("is-hidden");
      } else {
        el.style.opacity = "0.5";
        if (checkMark) checkMark.classList.add("is-hidden");
      }
    };

    if (!analysis) {
      updateItem(guideFaceDetected, false);
      updateItem(guideCentered, false);
      updateItem(guideFrontal, false);
      return;
    }

    updateItem(guideFaceDetected, true);
    updateItem(guideCentered, analysis.quality_flags.centered);
    updateItem(guideFrontal, analysis.quality_flags.frontal);
  }

  function analyzeFaceQuality(landmarks) {
    let minX = 1, minY = 1, maxX = 0, maxY = 0;
    landmarks.forEach(p => {
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    });

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const leftEye = landmarks[33];
    const rightEye = landmarks[263];
    const nose = landmarks[1];
    
    const eyeDist = Math.abs(rightEye.x - leftEye.x);
    const noseRelPos = (nose.x - leftEye.x) / (eyeDist || 1);
    const yaw = (noseRelPos - 0.5) * 100;

    const centered = Math.abs(centerX - 0.5) < CENTER_THRESHOLD && Math.abs(centerY - 0.5) < CENTER_THRESHOLD;
    const frontal = Math.abs(yaw) < ROTATION_THRESHOLD;

    return {
      face_count: 1,
      face_bbox_norm: { left: minX, top: minY, right: maxX, bottom: maxY },
      quality_flags: {
        centered, frontal, stable: true, single_face: true, ui_capture_ready: centered && frontal
      },
      landmarks: landmarks
    };
  }

  function startAutoCaptureCountdown() {
    if (isCountdownActive) return;
    
    isCountdownActive = true;
    countdownSeconds = 3;
    showCountdownUI(countdownSeconds);
    if (captureMessage) {
      captureMessage.style.opacity = "1";
    }

    countdownTimer = setInterval(() => {
      countdownSeconds--;
      if (countdownSeconds > 0) {
        showCountdownUI(countdownSeconds);
      } else {
        clearInterval(countdownTimer);
        countdownTimer = null;
        hideCountdownUI();
        if (captureMessage) captureMessage.style.opacity = "0";
        isCapturing = true; 
        isCountdownActive = false;
        handleCapture();
      }
    }, 1000);
  }

  function cancelAutoCaptureCountdown() {
    if (!isCountdownActive) return;
    if (countdownTimer) clearInterval(countdownTimer);
    isCountdownActive = false;
    hideCountdownUI();
    if (captureMessage) captureMessage.style.opacity = "0";
  }

  function showCountdownUI(sec) {
    if (!countdownOverlay) return;
    countdownOverlay.textContent = sec;
    countdownOverlay.style.opacity = "1";
    countdownOverlay.style.transform = "scale(1.3)";
    setTimeout(() => {
      if (countdownOverlay) countdownOverlay.style.transform = "scale(1)";
    }, 100);
  }

  function hideCountdownUI() {
    if (!countdownOverlay) return;
    countdownOverlay.style.opacity = "0";
    countdownOverlay.style.transform = "scale(0.5)";
  }

  function updateStatus(message, type = "") {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = "camera-status " + type;
  }

  function stopStream() {
    if (stream) stream.getTracks().forEach(track => track.stop());
    isCameraOn = false;
    videoEl.srcObject = null;
    toggleBtn.textContent = "카메라 활성화";
    captureBtn.classList.add("is-hidden");
    updateStatus("카메라가 꺼져 있습니다.");
    cancelAutoCaptureCountdown();
  }

  function cleanup() {
    stopStream();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }

  async function startCamera() {
    updateStatus("카메라 연결 중...", "loading");
    try {
      if (stream) stopStream();
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: facingMode, width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      videoEl.srcObject = stream;
      videoEl.onloadedmetadata = () => {
        videoEl.play().catch(console.error);
        isCameraOn = true;
        toggleBtn.textContent = "카메라 끄기";
        captureBtn.classList.remove("is-hidden");
        fallbackEl.classList.add("is-hidden");
        updateStatus("가이드 라인에 맞춰 주세요.", "success");
        predictWebcam();
      };
    } catch (err) {
      console.error(err);
      updateStatus("카메라 연결 실패.", "error");
      fallbackEl.classList.remove("is-hidden");
    }
  }

  function handleCapture() {
    if (!isCameraOn || !videoEl) return;
    const videoHeight = videoEl.videoHeight;
    const videoWidth = videoEl.videoWidth;
    const targetHeight = videoHeight;
    const targetWidth = (videoHeight * 3) / 4;
    const sx = (videoWidth - targetWidth) / 2;
    const sy = 0;
    
    captureCanvas.width = targetWidth;
    captureCanvas.height = targetHeight;
    const ctx = captureCanvas.getContext("2d");
    
    // Maintain mirroring in captured image
    if (facingMode === "user") {
        ctx.translate(targetWidth, 0);
        ctx.scale(-1, 1);
        ctx.drawImage(videoEl, sx, sy, targetWidth, targetHeight, 0, 0, targetWidth, targetHeight);
        ctx.setTransform(1, 0, 0, 1, 0, 0);
    } else {
        ctx.drawImage(videoEl, sx, sy, targetWidth, targetHeight, 0, 0, targetWidth, targetHeight);
    }
    
    captureCanvas.toBlob((blob) => {
      if (blob) {
        capturedBlob = blob;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = URL.createObjectURL(blob);
        previewImg.src = previewUrl;
        previewContainer.classList.remove("is-hidden");
        previewControls.classList.remove("is-hidden");
        videoEl.classList.add("is-hidden");
        cameraGuide.classList.add("is-hidden");
        cameraControls.classList.add("is-hidden");
        updateStatus("사진 촬영 완료!", "success");
      }
    }, "image/jpeg", 0.95);
  }

  function handleRetake() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewImg.src = "";
    capturedBlob = null;
    isCapturing = false; 
    isCountdownActive = false;
    videoEl.classList.remove("is-hidden");
    cameraGuide.classList.remove("is-hidden");
    cameraControls.classList.remove("is-hidden");
    previewContainer.classList.add("is-hidden");
    previewControls.classList.add("is-hidden");
    updateStatus("가이드 라인에 맞춰 주세요.", "success");
    predictWebcam();
  }

  async function handleConfirm() {
    if (!capturedBlob) return;
    const config = window.MirrAIConfig || {};
    const customerId = config.customerId;
    const csrfToken = config.csrfToken || getCookie("csrftoken");
    updateStatus("데이터 분석 중...", "loading");
    confirmBtn.disabled = true;
    retakeBtn.disabled = true;
    const formData = new FormData();
    formData.append("customer_id", customerId);
    formData.append("file", capturedBlob, "capture.jpg");
    if (lastFaceResult) {
      formData.append("metadata", JSON.stringify({
        captured_at: new Date().toISOString(),
        capture_mode: "auto_countdown_3s_mirrored",
        face_count: 1,
        face_bbox_norm: lastFaceResult.face_bbox_norm,
        quality_flags: lastFaceResult.quality_flags,
        ui_capture_ready: true,
        camera_facing: facingMode,
        capture_device: "web"
      }));
    }
    try {
      const response = await fetch("/api/v1/capture/upload/", {
        method: "POST",
        body: formData,
        headers: { "X-CSRFToken": csrfToken }
      });
      if (!response.ok) throw new Error("Upload error");
      const data = await response.json();
      // New Flow: Step 2 Camera -> Step 3 Survey
      window.location.href = "/customer/survey/";
    } catch (error) {
      updateStatus("업로드 오류.", "error");
      confirmBtn.disabled = false;
      retakeBtn.disabled = false;
      isCapturing = false; 
    }
  }

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + "=")) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function handleToggle() {
    if (isCameraOn) stopStream();
    else startCamera();
  }

  async function handleSwitch() {
    facingMode = (facingMode === "user") ? "environment" : "user";
    if (isCameraOn) await startCamera();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

})();
