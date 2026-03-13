/**
 * main.js
 * 키오스크 형태의 Step 전환 로직 및 S3 Upload / Mocking API Call 구현
 */

const API_BASE_URL = "http://localhost:8000/api/v1";

document.addEventListener("DOMContentLoaded", () => {
    // ---------------------------------
    // 1. UI Step Navigation Logic
    // ---------------------------------
    const nextBtns = document.querySelectorAll('.next-step-btn');
    const stepItems = document.querySelectorAll('.step-item');
    const stepContents = document.querySelectorAll('.step-content');

    function goToStep(stepIndex) {
        // 좌측 사이드바 하이라이트 변경 (0~5번 스텝에만 적용)
        if (stepIndex >= 0 && stepIndex <= 5) {
            stepItems.forEach(item => item.classList.remove('active'));
            const activeItem = document.querySelector(`.step-item[data-step="${stepIndex}"]`);
            if (activeItem) activeItem.classList.add('active');
        }

        // 우측 화면 전환
        stepContents.forEach(content => content.classList.remove('active'));
        const activeContent = document.getElementById(`step-${stepIndex}`);
        if (activeContent) activeContent.classList.add('active');
    }

    // "다음 단계" 버튼 클릭 이벤트 바인딩
    nextBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const targetStep = e.target.getAttribute('data-target');
            if (targetStep) goToStep(targetStep);
        });
    });

    // 사이드바 스텝 클릭 이벤트 바인딩 (데모/테스트 목적)
    stepItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetStep = item.getAttribute('data-step');
            if (targetStep) goToStep(targetStep);
        });
    });

    // ---------------------------------
    // 2. Survey Pills Selection (Step 2)
    // ---------------------------------
    const pillGroups = document.querySelectorAll('.pill-group');
    pillGroups.forEach(group => {
        group.addEventListener('click', (e) => {
            if(e.target.classList.contains('pill')) {
                // 기존 active 제거
                group.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
                // 현재 클릭한 요소 active 추가
                e.target.classList.add('active');
            }
        });
    });

    // ---------------------------------
    // 3. Camera / Image Preview Logic (Step 3)
    // ---------------------------------
    const fileInput = document.getElementById("face-image");
    const previewImg = document.getElementById("image-preview");
    const mainUploadBtn = document.getElementById("upload-btn"); 

    if (fileInput) {
        fileInput.addEventListener("change", (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (ev) => {
                    previewImg.src = ev.target.result;
                    previewImg.style.display = "block";
                }
                reader.readAsDataURL(file);
            }
        });
    }

    // 재촬영 버튼 (미리보기 초기화)
    const retryBtn = document.querySelector('.btn-outline');
    if (retryBtn) {
        retryBtn.addEventListener('click', () => {
            if(fileInput) fileInput.value = "";
            if(previewImg) {
                previewImg.src = "";
                previewImg.style.display = "none";
            }
        });
    }

    // ---------------------------------
    // 4. Final Submit & AI Simulation (Mocking S3 Upload)
    // ---------------------------------
    if (mainUploadBtn) {
        mainUploadBtn.addEventListener('click', async () => {
            const file = fileInput.files[0];
            if (!file) {
                alert("사진을 첨부하거나 단말기 카메라로 촬영해주세요.");
                return;
            }

            // Step Loading 화면으로 강제 이동 유도
            goToStep('loading');

            try {
                // 1. [Backend] Presigned URL Fetch
                // const presignedData = await getPresignedUrl(file.name, file.type);
                
                // 2. [AWS S3] PUT Direct Upload
                // await uploadToS3(presignedData.presigned_url, file);

                // 3. [Backend] Send Final Data & Start AI Simulation
                const finalResult = await startSimulation("fake_object_key");

                // Simulation 완료 후 실제 결과 화면(Step 4)으로 이동
                setTimeout(() => {
                    goToStep('4');
                }, 2500);

            } catch (error) {
                console.error("AI 시뮬레이션 에러:", error);
                alert(`오류가 발생했습니다: ${error.message}`);
                goToStep('3'); // 심각한 에러 발생 시 사진 촬영 화면으로 복귀
            }
        });
    }

    // ---------------------------------
    // 5. Thumbnails Selection (Step 5)
    // ---------------------------------
    const thumbItems = document.querySelectorAll('.thumb-item');
    const simAvatarHair = document.querySelector('.sim-hair');
    const simLabel = document.querySelector('.sim-label');

    // 썸네일 클릭 시 메인 이미지 변경 더미 로직
    thumbItems.forEach(item => {
        item.addEventListener('click', (e) => {
            thumbItems.forEach(t => t.classList.remove('active'));
            item.classList.add('active');
            
            // 이모지 및 텍스트 교체 (Mocking)
            const icon = item.querySelector('.thumb-icon').innerText;
            if(simAvatarHair) simAvatarHair.innerText = icon;
            
            if(simLabel) {
                if(icon === '🌸') simLabel.innerText = "레이어드 미디엄 웨이브";
                else if(icon === '🌿') simLabel.innerText = "내추럴 C컬";
                else if(icon === '🎀') simLabel.innerText = "히메컷 웨이브";
                else if(icon === '🍂') simLabel.innerText = "단발 스트레이트";
                else if(icon === '🌙') simLabel.innerText = "숏컷 스타일";
            }
        });
    });

});


// ===============================================
// API 통신 함수 
// ===============================================

async function getPresignedUrl(filename, fileType) {
    const response = await fetch(`${API_BASE_URL}/upload/presigned-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, file_type: fileType })
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.message || "서버 통신 실패");
    }
    return await response.json();
}

async function uploadToS3(url, file) {
    const response = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file
    });
    if (!response.ok) throw new Error("S3 이미지 올리기 실패");
}

async function startSimulation(objectKey) {
    // Collect Pill group values
    const length = document.querySelector('.pill-group[data-id="length"] .pill.active')?.dataset.value;
    const atmosphere = document.querySelector('.pill-group[data-id="atmosphere"] .pill.active')?.dataset.value;
    const condition = document.querySelector('.pill-group[data-id="condition"] .pill.active')?.dataset.value;
    const color = document.querySelector('.pill-group[data-id="color"] .pill.active')?.dataset.value;
    const budget = document.querySelector('.pill-group[data-id="budget"] .pill.active')?.dataset.value;

    const surveyData = {
        name: document.getElementById("name")?.value || "",
        contact: document.getElementById("contact")?.value || "",
        preferences: { length, atmosphere, condition, color, budget },
        image_key: objectKey
    };
    
    console.log("Transmission Data: ", surveyData);
    // 모의 딜레이
    await new Promise(resolve => setTimeout(resolve, 1500));
    return { success: true, fake_results: [] };
}
