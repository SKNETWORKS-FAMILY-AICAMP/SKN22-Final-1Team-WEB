/**
 * MirrAI Camera Service
 * Handles camera stream, preview, photo capture, and device switching.
 */
(function () {
  'use strict';

  // DOM Elements - Camera
  const videoEl = document.getElementById("cameraPreview");
  const videoBlurEl = document.getElementById("cameraPreviewBlur");
  const statusEl = document.getElementById("cameraStatus");
  const toggleBtn = document.getElementById("cameraToggleBtn");
  const captureBtn = document.getElementById("captureBtn");
  const switchBtn = document.getElementById("cameraSwitchBtn");
  const fallbackEl = document.getElementById("cameraFallback");
  const cameraGuide = document.getElementById("cameraGuide");
  const cameraControls = document.getElementById("cameraControls");

  // DOM Elements - Preview
  const previewContainer = document.getElementById("photoPreviewContainer");
  const previewImg = document.getElementById("photoPreview");
  const previewControls = document.getElementById("previewControls");
  const confirmBtn = document.getElementById("confirmBtn");
  const retakeBtn = document.getElementById("retakeBtn");
  const captureCanvas = document.getElementById("captureCanvas");

  // State
  let stream = null;
  let isCameraOn = false;
  let facingMode = "user"; // 'user' for front, 'environment' for back
  let capturedBlob = null;
  let previewUrl = null;

  // Initialize
  function init() {
    if (!videoEl || !statusEl || !toggleBtn || !captureBtn || !previewContainer) {
      console.error("Required Camera UI elements not found.");
      return;
    }

    // Check for MediaDevices support
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      handleError({ name: "NotSupportedError" });
      return;
    }

    // Event Listeners
    toggleBtn.addEventListener("click", handleToggle);
    captureBtn.addEventListener("click", handleCapture);
    switchBtn.addEventListener("click", handleSwitch);
    retakeBtn.addEventListener("click", handleRetake);
    confirmBtn.addEventListener("click", handleConfirm);

    // Cleanup on exit
    window.addEventListener("beforeunload", cleanup);
    window.addEventListener("pagehide", cleanup);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") stopStream();
    });

    updateStatus("카메라를 활성화하여 페이스 스캔을 시작하세요.");
    
    // Auto-start camera on load
    startCamera();
  }

  /**
   * Updates the UI status message
   */
  function updateStatus(message, type = "") {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = "camera-status " + type;
  }

  /**
   * Stops all active video tracks and cleans up
   */
  function stopStream() {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      stream = null;
    }
    if (videoEl) {
      videoEl.srcObject = null;
    }
    if (videoBlurEl) {
      videoBlurEl.srcObject = null;
    }
    isCameraOn = false;
    toggleBtn.textContent = "카메라 활성화";
    captureBtn.classList.add("is-hidden");
    fallbackEl.classList.remove("is-hidden");
  }

  function cleanup() {
    stopStream();
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
  }

  /**
   * Starts the camera
   */
  async function startCamera() {
    updateStatus("카메라 연결 중...", "loading");
    
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
      if (stream) stopStream();
      stream = await navigator.mediaDevices.getUserMedia(constraints);
      videoEl.srcObject = stream;
      if (videoBlurEl) {
        videoBlurEl.srcObject = stream;
      }
      
      videoEl.onloadedmetadata = () => {
        videoEl.play();
        if (videoBlurEl) videoBlurEl.play();
        isCameraOn = true;
        toggleBtn.textContent = "카메라 끄기";
        captureBtn.classList.remove("is-hidden");
        fallbackEl.classList.add("is-hidden");
        updateStatus("가이드 라인에 얼굴을 맞춰 주세요~", "success");
      };
    } catch (err) {
      handleError(err);
    }
  }

  /**
   * Captures a photo from the video stream
   */
  function handleCapture() {
    if (!isCameraOn || !videoEl) return;

    // We want a 3:4 portrait crop from the video stream
    // Calculate dimensions based on video height (assuming landscape/4:3 stream)
    const videoHeight = videoEl.videoHeight;
    const videoWidth = videoEl.videoWidth;
    
    // Target ratio 3:4
    const targetHeight = videoHeight;
    const targetWidth = (videoHeight * 3) / 4;
    
    // Center crop coordinates
    const sx = (videoWidth - targetWidth) / 2;
    const sy = 0;

    // Set canvas dimensions to 3:4
    captureCanvas.width = targetWidth;
    captureCanvas.height = targetHeight;

    const ctx = captureCanvas.getContext("2d");
    
    // Draw the cropped area from the video
    ctx.drawImage(
      videoEl, 
      sx, sy, targetWidth, targetHeight, // Source crop
      0, 0, targetWidth, targetHeight    // Destination
    );

    captureCanvas.toBlob((blob) => {
      if (blob) {
        capturedBlob = blob;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = URL.createObjectURL(blob);
        
        // Show Preview UI
        previewImg.src = previewUrl;
        previewContainer.classList.remove("is-hidden");
        previewControls.classList.remove("is-hidden");
        
        // Hide Camera UI
        videoEl.classList.add("is-hidden");
        cameraGuide.classList.add("is-hidden");
        cameraControls.classList.add("is-hidden");
        
        updateStatus("사진이 촬영되었습니다. 결과를 확인해 주세요.", "success");
      }
    }, "image/jpeg", 0.95);
  }

  /**
   * Resets the UI to take another photo
   */
  function handleRetake() {
    if (capturedBlob && !confirm("이 사진을 버리고 다시 촬영하시겠습니까?")) {
      return;
    }

    // Clear preview
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
    previewImg.src = "";
    capturedBlob = null;

    // Show Camera UI
    videoEl.classList.remove("is-hidden");
    cameraGuide.classList.remove("is-hidden");
    cameraControls.classList.remove("is-hidden");
    
    // Hide Preview UI
    previewContainer.classList.add("is-hidden");
    previewControls.classList.add("is-hidden");

    updateStatus("정면 가이드에 맞춰 다시 촬영해 주세요.", "success");
    
    // Ensure video is playing
    if (isCameraOn && videoEl.paused) {
      videoEl.play();
    }
  }

  /**
   * Confirms the photo and uploads it to the server
   */
  async function handleConfirm() {
    if (!capturedBlob) return;
    
    // Get config from global object passed by Django template
    const config = window.MirrAIConfig || {};
    const customerId = config.customerId;
    const csrfToken = config.csrfToken || getCookie("csrftoken");

    if (!customerId) {
      alert("고객 정보가 세션에 없습니다. 다시 시작해 주세요.");
      window.location.href = "/customer/";
      return;
    }

    updateStatus("이미지를 서버로 전송하고 분석을 시작합니다...", "loading");
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

      if (!response.ok) throw new Error("Upload failed");

      const data = await response.json();
      console.log("Upload Success:", data);
      
      // Handle navigation based on the 'nextAction' field (supporting both snake_case and camelCase)
      const nextAction = data.nextAction || data.next_action;
      let targetUrl = "/customer/result/"; // default
      
      if (nextAction === "dashboard") {
        targetUrl = "/customer/dashboard/";
      } else if (nextAction === "client_input") {
        targetUrl = "/customer/survey/";
      } else if (nextAction === "capture") {
        targetUrl = "/customer/camera/"; // stay on camera if needed
      }

      updateStatus("분석이 시작되었습니다. 이동 중입니다...", "success");
      
      setTimeout(() => {
        window.location.href = targetUrl;
      }, 1000);

    } catch (error) {
      console.error("Upload Error:", error);
      // Support for standardized error envelope
      let errorMessage = "업로드 중 오류가 발생했습니다. 다시 시도해 주세요.";
      if (error.response && error.response.data && error.response.data.detail) {
          errorMessage = error.response.data.detail;
      } else if (error.message) {
          errorMessage = error.message;
      }
      updateStatus(errorMessage, "error");
      confirmBtn.disabled = false;
      retakeBtn.disabled = false;
    }
  }

  // Helper to get CSRF token
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
    if (isCameraOn) {
      stopStream();
      updateStatus("카메라가 중지되었습니다.");
    } else {
      startCamera();
    }
  }

  async function handleSwitch() {
    facingMode = (facingMode === "user") ? "environment" : "user";
    if (isCameraOn) await startCamera();
    else updateStatus(facingMode === "user" ? "전면 카메라 모드" : "후면 카메라 모드");
  }

  function handleError(err) {
    console.error("Camera Error:", err);
    stopStream();
    let message = "카메라를 시작할 수 없습니다.";
    if (err.name === "NotAllowedError") message = "카메라 권한이 거부되었습니다.";
    else if (err.name === "NotFoundError") message = "카메라 장치를 찾을 수 없습니다.";
    updateStatus(message, "error");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();
