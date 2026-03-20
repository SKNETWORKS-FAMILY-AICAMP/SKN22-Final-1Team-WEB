import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { ChevronDown, ChevronUp, Phone, CheckCircle } from 'lucide-react';
import { NavBar } from '../components/NavBar';
import { CustomerAvatar, StyleThumbnail } from '../components/CustomerAvatar';
import { customers, hairstyles } from '../data/mockData';

export function CustomerDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [showEndDialog, setShowEndDialog] = useState(false);
  const [consultEnded, setConsultEnded] = useState(false);

  const customer = customers.find((c) => c.id === Number(id));
  if (!customer) {
    return (
      <div
        className="flex items-center justify-center min-h-screen"
        style={{ background: '#0A0A0A', color: '#EDE8DE' }}
      >
        <p>고객을 찾을 수 없습니다.</p>
      </div>
    );
  }

  const todayStyle = hairstyles.find((h) => h.id === customer.todayRecommendationId);

  const handleEndConsult = () => {
    setConsultEnded(true);
    setShowEndDialog(false);
    setTimeout(() => navigate('/customer-list'), 1500);
  };

  return (
    <div
      className="admin-page flex flex-col min-h-screen"
      style={{ background: '#0A0A0A', fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      <NavBar />

      <div className="admin-content px-10 py-8 flex gap-8 flex-1">
        {/* Main column */}
        <div className="flex-1 flex flex-col gap-4">
          {/* Title bar */}
          <div
            className="flex items-center justify-between px-8 py-5 rounded-2xl"
            style={{
              background: 'linear-gradient(90deg, #0D7FA3 0%, #0A6A8A 100%)',
              border: '1px solid #0D7FA360',
            }}
          >
            <div className="flex items-center gap-4">
              <CustomerAvatar gender={customer.gender} size={48} isNew={customer.isNew} />
              <div>
                <h1 className="text-xl" style={{ color: '#FFFFFF' }}>
                  고객명: {customer.name}
                </h1>
                <p className="text-sm mt-0.5" style={{ color: 'rgba(255,255,255,0.6)' }}>
                  {customer.gender === 'F' ? '여성' : '남성'} · {customer.age}세 ·{' '}
                  {customer.isNew ? '신규 고객' : '기존 고객'} · 최근 방문 {customer.lastVisit}
                </p>
              </div>
            </div>
            {customer.isNew && (
              <span
                className="text-xs px-3 py-1.5 rounded-full"
                style={{ background: '#E53535', color: '#FFFFFF' }}
              >
                신규 등록
              </span>
            )}
          </div>

          {/* Phone number */}
          <div
            className="flex items-center gap-4 px-8 py-4 rounded-2xl"
            style={{
              background: 'linear-gradient(90deg, #AE0F52 0%, #8E0D42 100%)',
              border: '1px solid #C01060',
            }}
          >
            <Phone size={18} style={{ color: 'rgba(255,255,255,0.7)' }} />
            <span className="text-base tracking-wider" style={{ color: '#FFFFFF' }}>
              고객 전화번호: {customer.phone}
            </span>
          </div>

          {/* 금일 선택 스타일 + 추천 상세 / 설문 */}
          <div className="grid grid-cols-2 gap-4">
            {/* Left: 금일 선택한 추천 스타일 */}
            <div
              className="flex flex-col gap-0 rounded-2xl overflow-hidden"
              style={{ border: '1px solid #1E1E1E' }}
            >
              <div
                className="px-5 py-3"
                style={{
                  background: 'linear-gradient(90deg, #0D7FA3 0%, #0A5A78 100%)',
                }}
              >
                <p className="text-xs tracking-widest" style={{ color: 'rgba(255,255,255,0.7)' }}>
                  금일 선택한 추천 스타일
                </p>
              </div>
              <div
                className="flex flex-col items-center justify-center p-5 gap-4 flex-1"
                style={{ background: '#141414' }}
              >
                {todayStyle && (
                  <>
                    <StyleThumbnail imageUrl={todayStyle.imageUrl} size={140} />
                    <div className="text-center">
                      <p className="text-sm mb-1" style={{ color: '#EDE8DE' }}>
                        {todayStyle.koreanName}
                      </p>
                      <div className="flex items-center justify-center gap-2">
                        <span
                          className="text-xs px-2 py-0.5 rounded"
                          style={{ background: '#C49A3C20', color: '#C49A3C', border: '1px solid #C49A3C40' }}
                        >
                          AI 매칭 {todayStyle.matchRate}%
                        </span>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Right: 추천 상세 + 설문 결과 */}
            <div className="flex flex-col gap-4">
              {/* 금일 추천 상세 */}
              <button
                onClick={() => navigate(`/customer/${customer.id}/recommendation`)}
                className="flex-1 flex flex-col items-start justify-center px-6 py-5 rounded-2xl text-left transition-all hover:opacity-85"
                style={{
                  background: 'linear-gradient(135deg, #AE0F52 0%, #8E0D42 100%)',
                  border: '1px solid #C01060',
                }}
              >
                <p className="text-base mb-1" style={{ color: '#FFFFFF' }}>
                  금일 추천 상세
                </p>
                <p className="text-xs" style={{ color: 'rgba(255,255,255,0.6)' }}>
                  점내 추천 스타일 전체 이동 →
                </p>
              </button>

              {/* 최근 취향 설문 결과 */}
              <div
                className="flex-1 px-6 py-5 rounded-2xl"
                style={{
                  background: '#141414',
                  border: '1px solid #1E1E1E',
                }}
              >
                <p className="text-xs tracking-widest mb-3" style={{ color: '#6A6055' }}>
                  최근 취향 설문 결과
                </p>
                <div className="space-y-2">
                  {[
                    { label: '선호 분위기', value: customer.surveyResults.atmosphere },
                    { label: '희망 길이', value: customer.surveyResults.length },
                    { label: '예산', value: customer.surveyResults.budget },
                    { label: '용도', value: customer.surveyResults.occasion },
                  ].map((item) => (
                    <div key={item.label} className="flex items-start justify-between gap-3">
                      <span className="text-xs flex-shrink-0" style={{ color: '#6A6055' }}>
                        {item.label}
                      </span>
                      <span className="text-xs text-right" style={{ color: '#EDE8DE' }}>
                        {item.value}
                      </span>
                    </div>
                  ))}
                  <div className="flex flex-wrap gap-1 mt-2">
                    {customer.surveyResults.preferences.map((p) => (
                      <span
                        key={p}
                        className="text-xs px-2 py-0.5 rounded"
                        style={{
                          background: '#AE0F5220',
                          color: '#C8406A',
                          border: '1px solid #AE0F5240',
                        }}
                      >
                        #{p}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 기존 추천 이력 (expandable) */}
          <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid #1E1E1E' }}>
            <button
              className="w-full flex items-center justify-between px-6 py-4 transition-all hover:opacity-85"
              style={{
                background: 'linear-gradient(90deg, #AE0F52 0%, #8E0D42 100%)',
              }}
              onClick={() => setHistoryExpanded(!historyExpanded)}
            >
              <div className="flex items-center gap-3">
                <span className="text-sm" style={{ color: '#FFFFFF' }}>
                  기존 추천 이력
                </span>
                <span
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(255,255,255,0.2)', color: '#FFFFFF' }}
                >
                  {customer.recommendationHistory.length}건
                </span>
              </div>
              {historyExpanded ? (
                <ChevronUp size={16} style={{ color: '#FFFFFF' }} />
              ) : (
                <ChevronDown size={16} style={{ color: '#FFFFFF' }} />
              )}
            </button>

            {historyExpanded && (
              <div className="p-4 space-y-2" style={{ background: '#111111' }}>
                {customer.recommendationHistory.map((rec, idx) => (
                  <div
                    key={idx}
                    className="px-5 py-4 rounded-xl"
                    style={{ background: '#171717', border: '1px solid #1E1E1E' }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm" style={{ color: '#EDE8DE' }}>
                        {rec.styleName}
                      </span>
                      <div className="flex items-center gap-3">
                        <span className="text-xs" style={{ color: '#6A6055' }}>
                          {rec.stylist}
                        </span>
                        <span
                          className="text-xs px-2 py-0.5 rounded"
                          style={{
                            background:
                              rec.result === '매우 만족'
                                ? '#C49A3C20'
                                : rec.result === '만족'
                                ? '#0D7FA320'
                                : '#2A2A2A',
                            color:
                              rec.result === '매우 만족'
                                ? '#C49A3C'
                                : rec.result === '만족'
                                ? '#0D7FA3'
                                : '#6A6055',
                          }}
                        >
                          {rec.result}
                        </span>
                        <span className="text-xs" style={{ color: '#4A4035' }}>
                          {rec.date}
                        </span>
                      </div>
                    </div>
                    {rec.note && (
                      <p className="text-xs" style={{ color: '#6A6055', lineHeight: 1.6 }}>
                        📝 {rec.note}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 상담 종료 */}
          {!consultEnded ? (
            <button
              onClick={() => setShowEndDialog(true)}
              className="w-full py-5 rounded-2xl text-base transition-all hover:opacity-85 active:scale-[0.99]"
              style={{
                background: 'linear-gradient(90deg, #7B1232 0%, #5A0D25 100%)',
                border: '1px solid #9B1A42',
                color: '#FFFFFF',
              }}
            >
              <div>상담 종료</div>
              <div className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
                고객 응대 사이클 종결
              </div>
            </button>
          ) : (
            <div
              className="w-full py-5 rounded-2xl text-base flex items-center justify-center gap-3"
              style={{ background: '#1A2A1A', border: '1px solid #2A4A2A', color: '#4AE54A' }}
            >
              <CheckCircle size={20} />
              <span>상담이 종료되었습니다</span>
            </div>
          )}
        </div>

        {/* Right: Designer memo + AI data */}
        <div className="w-72 flex flex-col gap-4">
          {/* AI 분석 데이터 */}
          <div
            className="p-5 rounded-2xl"
            style={{ background: '#141414', border: '1px solid #1E1E1E' }}
          >
            <h3 className="text-xs tracking-widest mb-4" style={{ color: '#6A6055' }}>
              AI 분석 결과
            </h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span
                  className="text-xs px-3 py-1.5 rounded-lg"
                  style={{ background: '#1C1C1C', color: '#9A8A7A', border: '1px solid #2A2A2A' }}
                >
                  얼굴형 <strong style={{ color: '#EDE8DE' }}>{customer.faceShape}</strong>
                </span>
                <span
                  className="text-xs px-3 py-1.5 rounded-lg"
                  style={{
                    background: '#C49A3C20',
                    color: '#C49A3C',
                    border: '1px solid #C49A3C40',
                  }}
                >
                  황금비율 <strong>{customer.goldenRatio}</strong>
                </span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: '#6A6055' }}>
                {customer.faceShape} 얼굴에 청순한 분위기의 중단발 웨이브를 추천드립니다.
              </p>
            </div>
          </div>

          {/* 디자이너 메모 */}
          <div
            className="flex-1 p-5 rounded-2xl flex flex-col"
            style={{
              background: 'linear-gradient(135deg, #1C0A18 0%, #140818 100%)',
              border: '1px solid #2A1A2A',
            }}
          >
            <h3 className="text-xs tracking-widest mb-3" style={{ color: '#6A5060' }}>
              디자이너 메모
            </h3>
            <p className="text-xs leading-relaxed mb-3" style={{ color: '#8A7A8A' }}>
              시술 시 관찰 내역 기록용
            </p>
            <textarea
              defaultValue={customer.designerNote}
              placeholder="메모를 입력하세요..."
              className="flex-1 w-full rounded-xl p-3 text-xs outline-none resize-none"
              style={{
                background: '#0D0A0D',
                border: '1px solid #2A1A2A',
                color: '#EDE8DE',
                minHeight: '120px',
              }}
            />
            <button
              className="w-full mt-3 py-2 rounded-lg text-xs transition-all hover:opacity-80"
              style={{
                background: 'linear-gradient(135deg, #7B1232 0%, #5A0D25 100%)',
                color: '#FFFFFF',
              }}
            >
              저장
            </button>
          </div>

          {/* 금일 사진 자료 */}
          <button
            className="w-full py-4 rounded-2xl text-sm transition-all hover:opacity-85"
            style={{
              background: 'linear-gradient(135deg, #7B1232 0%, #5A0D25 100%)',
              border: '1px solid #9B1A42',
              color: '#FFFFFF',
            }}
          >
            <div>금일 사진 자료 전체 일람</div>
            <div className="text-xs mt-0.5" style={{ color: 'rgba(255,255,255,0.5)' }}>
              점내 촬영자료 이동 →
            </div>
          </button>
        </div>
      </div>

      {/* End consultation dialog */}
      {showEndDialog && (
        <div
          className="fixed inset-0 flex items-center justify-center z-50"
          style={{ background: 'rgba(0,0,0,0.75)' }}
        >
          <div
            className="p-8 rounded-2xl max-w-md w-full mx-6"
            style={{ background: '#1A1A1A', border: '1px solid #2A2A2A' }}
          >
            <h3 className="text-lg mb-3" style={{ color: '#EDE8DE' }}>
              상담을 종료하시겠습니까?
            </h3>
            <p className="text-sm mb-6" style={{ color: '#6A6055' }}>
              {customer.name} 고객의 응대 사이클이 종결됩니다. 이 작업은 되돌릴 수 없습니다.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowEndDialog(false)}
                className="flex-1 py-3 rounded-xl text-sm"
                style={{ background: '#141414', color: '#9A8A7A', border: '1px solid #2A2A2A' }}
              >
                취소
              </button>
              <button
                onClick={handleEndConsult}
                className="flex-1 py-3 rounded-xl text-sm"
                style={{
                  background: 'linear-gradient(135deg, #7B1232 0%, #5A0D25 100%)',
                  color: '#FFFFFF',
                }}
              >
                종료 확인
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}