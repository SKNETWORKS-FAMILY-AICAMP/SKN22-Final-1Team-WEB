/**
 * MirrAI Camera Service
 * Handles camera stream, preview, photo capture, and upload navigation.
 */
(function () {
  "use strict";

  const videoEl = document.getElementById("cameraPreview");
  const videoBlurEl = document.getElementById("cameraPreviewBlur");
  const statusEl = document.getElementById("cameraStatus");
  const toggleBtn = document.getElementById("cameraToggleBtn");
  const captureBtn = document.getElementById("captureBtn");
  const switchBtn = document.getElementById("cameraSwitchBtn");
  const fallbackEl = document.getElementById("cameraFallback");
  const cameraGuide = document.getElementById("cameraGuide");
  const cameraControls = document.getElementById("cameraControls");
  const previewContainer = document.getElementById("photoPreviewContainer");
  const previewImg = document.getElementById("photoPreview");
  const previewControls = document.getElementById("previewControls");
  const confirmBtn = document.getElementById("confirmBtn");
  const retakeBtn = document.getElementById("retakeBtn");
  const captureCanvas = document.getElementById("captureCanvas");

  let stream = null;
  let isCameraOn = false;
  let facingMode = "user";
  let capturedBlob = null;
  let previewUrl = null;

  function init() {
    if (!videoEl || !statusEl || !toggleBtn || !captureBtn || !previewContainer) {
      console.error("Required camera UI elements were not found.");
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      handleError({ name: "NotSupportedError" });
      return;
    }

    toggleBtn.addEventListener("click", handleToggle);
    captureBtn.addEventListener("click", handleCapture);
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

    updateStatus("카메라를 활성화하면 촬영을 시작할 수 있습니다.");
    startCamera();
  }

  function updateStatus(message, type = "") {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = "camera-status " + type;
  }

  function stopStream() {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }

    if (videoEl) {
      videoEl.srcObject = null;
    }
    if (videoBlurEl) {
      videoBlurEl.srcObject = null;
    }

    isCameraOn = false;
    if (toggleBtn) toggleBtn.textContent = "카메라 켜기";
    if (captureBtn) captureBtn.classList.add("is-hidden");
    if (fallbackEl) fallbackEl.classList.remove("is-hidden");
  }

  function cleanup() {
    stopStream();
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
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
        updateStatus("가이드 라인에 얼굴을 맞춰 주세요.", "success");
      };
    } catch (error) {
      handleError(error);
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
    ctx.drawImage(
      videoEl,
      sx,
      sy,
      targetWidth,
      targetHeight,
      0,
      0,
      targetWidth,
      targetHeight
    );

    captureCanvas.toBlob((blob) => {
      if (!blob) return;

      capturedBlob = blob;
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
      previewUrl = URL.createObjectURL(blob);

      previewImg.src = previewUrl;
      previewContainer.classList.remove("is-hidden");
      previewControls.classList.remove("is-hidden");

      videoEl.classList.add("is-hidden");
      cameraGuide.classList.add("is-hidden");
      cameraControls.classList.add("is-hidden");

      updateStatus("사진을 촬영했습니다. 결과를 확인해 주세요.", "success");
    }, "image/jpeg", 0.95);
  }

  function handleRetake() {
    if (capturedBlob && !confirm("이 사진을 버리고 다시 촬영하시겠습니까?")) {
      return;
    }

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }

    previewImg.src = "";
    capturedBlob = null;

    videoEl.classList.remove("is-hidden");
    cameraGuide.classList.remove("is-hidden");
    cameraControls.classList.remove("is-hidden");
    previewContainer.classList.add("is-hidden");
    previewControls.classList.add("is-hidden");

    updateStatus("정면 가이드에 맞춰 다시 촬영해 주세요.", "success");

    if (isCameraOn && videoEl.paused) {
      videoEl.play();
    }
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
        confirmBtn.disabled = false;
        retakeBtn.disabled = false;
        return;
      }

      let targetUrl = "/customer/survey/";
      if (nextAction === "dashboard") {
        targetUrl = "/customer/dashboard/";
      } else if (nextAction === "result" || nextAction === "recommendations") {
        targetUrl = "/customer/result/";
      }

      updateStatus("분석을 시작했습니다. 다음 단계로 이동합니다...", "success");
      window.setTimeout(() => {
        window.location.replace(targetUrl);
      }, 800);
    } catch (error) {
      console.error("Upload Error:", error);
      updateStatus("업로드 중 오류가 발생했습니다. 다시 시도해주세요.", "error");
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
    facingMode = facingMode === "user" ? "environment" : "user";
    await startCamera();
  }

  function handleError(error) {
    console.error("Camera Error:", error);
    stopStream();

    let message = "카메라를 사용할 수 없습니다.";
    if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
      message = "카메라 권한이 필요합니다. 브라우저 설정에서 카메라 권한을 허용해 주세요.";
    } else if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
      message = "사용 가능한 카메라를 찾을 수 없습니다.";
    } else if (error.name === "NotSupportedError") {
      message = "이 브라우저는 카메라 기능을 지원하지 않습니다.";
    }

    updateStatus(message, "error");
  }

  init();
})();
