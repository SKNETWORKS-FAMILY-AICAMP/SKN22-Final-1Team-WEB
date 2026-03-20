import { useNavigate } from 'react-router';
import { ChevronLeft } from 'lucide-react';

interface NavBarProps {
  showBack?: boolean;
  onBack?: () => void;
  rightContent?: React.ReactNode;
}

export function NavBar({ showBack = true, onBack, rightContent }: NavBarProps) {
  const navigate = useNavigate();

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      navigate(-1);
    }
  };

  const now = new Date();
  const timeStr = now.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
  const dateStr = now.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });

  return (
    <div
      className="border-b"
      style={{
        borderColor: '#232323',
        position: 'sticky',
        top: 0,
        zIndex: 30,
        backdropFilter: 'blur(10px)',
        background: 'rgba(10,10,10,0.86)',
      }}
    >
      <div className="admin-content flex items-center justify-between px-6 py-3">
        {/* Left: Logo + back */}
        <div className="flex items-center gap-4">
        <div
          className="px-3 py-1 rounded text-sm tracking-widest select-none"
          style={{
            background: 'linear-gradient(135deg, #1A2A1A 0%, #0D1A0D 100%)',
            color: '#C49A3C',
            border: '1px solid #2A3A1A',
            fontFamily: 'serif',
            letterSpacing: '0.15em',
          }}
        >
          MirrAI
        </div>
        {showBack && (
          <button
            onClick={handleBack}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-sm transition-all hover:opacity-80 active:scale-95"
            style={{
              background: '#1C1C1C',
              color: '#9A8A7A',
              border: '1px solid #2D2D2D',
            }}
          >
            <ChevronLeft size={14} />
            <span>뒤로가기</span>
          </button>
        )}
        </div>

        {/* Right */}
        <div className="flex items-center gap-6">
          {rightContent}
          <div className="text-right" style={{ color: '#6A6055' }}>
            <div className="text-xs">{dateStr}</div>
            <div className="text-sm" style={{ color: '#8A7A6A' }}>{timeStr}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
