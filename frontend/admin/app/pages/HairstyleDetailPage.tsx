import { useNavigate, useParams } from 'react-router';
import { NavBar } from '../components/NavBar';
import { hairstyles } from '../data/mockData';

export function HairstyleDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const style = hairstyles.find((h) => h.id === Number(id));

  if (!style) {
    return (
      <div
        className="flex items-center justify-center min-h-screen"
        style={{ background: '#0A0A0A', color: '#EDE8DE' }}
      >
        스타일 정보를 찾을 수 없습니다.
      </div>
    );
  }

  return (
    <div
      className="admin-page flex flex-col min-h-screen"
      style={{ background: '#0A0A0A', fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      <NavBar />

      <div className="admin-content px-10 py-8 flex gap-8 flex-1">
        {/* Main */}
        <div className="flex-1 flex flex-col gap-4">
          {/* Title */}
          <div
            className="px-8 py-5 rounded-2xl"
            style={{
              background: 'linear-gradient(90deg, #0D7FA3 0%, #0A6A8A 100%)',
              border: '1px solid #0D7FA360',
            }}
          >
            <h1 className="text-xl" style={{ color: '#FFFFFF' }}>
              헤어스타일 &lsquo;{style.universalName}&rsquo;
            </h1>
            <p className="text-sm mt-1" style={{ color: 'rgba(255,255,255,0.6)' }}>
              {style.koreanName} · AI 매칭률 {style.matchRate}%
            </p>
          </div>

          {/* Image + Keywords */}
          <div className="grid grid-cols-2 gap-4">
            {/* Large style image */}
            <div
              className="rounded-2xl overflow-hidden"
              style={{
                border: '1px solid #1E1E1E',
                height: '320px',
              }}
            >
              <img
                src={style.imageUrl}
                alt={style.koreanName}
                className="w-full h-full object-cover"
                style={{ filter: 'brightness(0.85) saturate(0.9)' }}
              />
            </div>

            {/* Keywords panel */}
            <div
              className="flex flex-col justify-center px-8 py-6 rounded-2xl gap-4"
              style={{
                background: 'linear-gradient(135deg, #AE0F52 0%, #8E0D42 100%)',
                border: '1px solid #C01060',
              }}
            >
              <div>
                <p className="text-xs tracking-widest mb-4" style={{ color: 'rgba(255,255,255,0.6)' }}>
                  추천 시 주요 키워드
                </p>
                <div className="flex flex-wrap gap-2">
                  {style.keywords.map((k) => (
                    <span
                      key={k}
                      className="px-4 py-2 rounded-xl text-sm"
                      style={{
                        background: 'rgba(255,255,255,0.15)',
                        color: '#FFFFFF',
                        border: '1px solid rgba(255,255,255,0.2)',
                      }}
                    >
                      #{k}
                    </span>
                  ))}
                </div>
              </div>

              <div
                className="w-full h-px"
                style={{ background: 'rgba(255,255,255,0.15)' }}
              />

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'rgba(255,255,255,0.6)' }}>
                    기장
                  </span>
                  <span className="text-sm" style={{ color: '#FFFFFF' }}>
                    {style.length}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'rgba(255,255,255,0.6)' }}>
                    예상 금액
                  </span>
                  <span className="text-sm" style={{ color: '#C49A3C' }}>
                    {style.priceRange}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'rgba(255,255,255,0.6)' }}>
                    AI 매칭률
                  </span>
                  <span className="text-sm" style={{ color: '#FFFFFF' }}>
                    {style.matchRate}%
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Style description */}
          <div
            className="px-8 py-6 rounded-2xl"
            style={{
              background: 'linear-gradient(135deg, #AE0F52 0%, #7B1232 100%)',
              border: '1px solid #C01060',
            }}
          >
            <p className="text-base mb-3" style={{ color: '#FFFFFF' }}>
              해당 스타일에 대한 해설
            </p>
            <p className="text-sm leading-relaxed mb-5" style={{ color: 'rgba(255,255,255,0.8)' }}>
              {style.description}
            </p>

            {/* 얼굴 비율 수치 데이터 */}
            <div
              className="rounded-xl p-5"
              style={{ background: 'rgba(0,0,0,0.3)' }}
            >
              <p className="text-xs tracking-widest mb-4" style={{ color: 'rgba(255,255,255,0.5)' }}>
                얼굴 비율 등 수치적 자료
              </p>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center">
                  <p className="text-xs mb-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
                    적정 황금비율
                  </p>
                  <p className="text-lg" style={{ color: '#C49A3C' }}>
                    {style.faceRatioData.golden}
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xs mb-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
                    이마 특성
                  </p>
                  <p className="text-sm" style={{ color: '#FFFFFF' }}>
                    {style.faceRatioData.forehead}
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xs mb-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
                    턱선 특성
                  </p>
                  <p className="text-sm" style={{ color: '#FFFFFF' }}>
                    {style.faceRatioData.jaw}
                  </p>
                </div>
              </div>

              <div className="mt-4">
                <p className="text-xs mb-2" style={{ color: 'rgba(255,255,255,0.5)' }}>
                  적합 얼굴형
                </p>
                <div className="flex gap-2">
                  {style.faceRatioData.suitableFaces.map((face) => (
                    <span
                      key={face}
                      className="text-xs px-3 py-1 rounded-full"
                      style={{ background: 'rgba(196, 154, 60, 0.2)', color: '#C49A3C', border: '1px solid rgba(196,154,60,0.4)' }}
                    >
                      {face}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right */}
        <div className="w-64 flex flex-col gap-4">
          <div
            className="p-5 rounded-2xl"
            style={{ background: '#141414', border: '1px solid #1E1E1E' }}
          >
            <h3 className="text-xs tracking-widest mb-4" style={{ color: '#6A6055' }}>
              다른 추천 스타일
            </h3>
            <div className="space-y-3">
              {hairstyles
                .filter((h) => h.id !== style.id)
                .map((h) => (
                  <button
                    key={h.id}
                    className="w-full flex items-center gap-3 p-3 rounded-xl text-left transition-all hover:opacity-80"
                    style={{ background: '#0D0D0D', border: '1px solid #1E1E1E' }}
                    onClick={() => navigate(`/hairstyle/${h.id}`)}
                  >
                    <div
                      className="w-10 h-10 rounded-lg overflow-hidden flex-shrink-0"
                    >
                      <img
                        src={h.imageUrl}
                        alt={h.koreanName}
                        className="w-full h-full object-cover"
                        style={{ filter: 'brightness(0.8)' }}
                      />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs truncate" style={{ color: '#EDE8DE' }}>
                        {h.koreanName}
                      </p>
                      <p className="text-xs" style={{ color: '#6A6055' }}>
                        {h.matchRate}% 매칭
                      </p>
                    </div>
                  </button>
                ))}
            </div>
          </div>

          <button
            onClick={() => navigate(-1)}
            className="w-full py-4 rounded-2xl text-sm transition-all hover:opacity-85"
            style={{
              background: '#141414',
              border: '1px solid #2A2A2A',
              color: '#9A8A7A',
            }}
          >
            ← 이전 페이지로
          </button>
        </div>
      </div>
    </div>
  );
}
