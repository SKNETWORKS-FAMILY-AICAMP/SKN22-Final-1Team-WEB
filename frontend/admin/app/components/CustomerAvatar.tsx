interface CustomerAvatarProps {
  gender: 'M' | 'F';
  size?: number;
  isNew?: boolean;
}

export function CustomerAvatar({ gender, size = 56, isNew = false }: CustomerAvatarProps) {
  const bgColor = gender === 'F' ? '#1A3A5C' : '#1C2A4A';
  const bodyColor = gender === 'F' ? '#C49A3C' : '#8A7A5A';

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <div
        className="rounded-lg flex items-end justify-center overflow-hidden"
        style={{
          width: size,
          height: size,
          background: `linear-gradient(135deg, ${bgColor} 0%, #0D1825 100%)`,
          border: '1px solid #2A3A4A',
        }}
      >
        <svg
          width={size * 0.7}
          height={size * 0.75}
          viewBox="0 0 56 60"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          {/* Head */}
          <circle cx="28" cy="18" r="12" fill={bodyColor} />
          {/* Body */}
          {gender === 'F' ? (
            <path d="M8 60 C8 40 20 32 28 32 C36 32 48 40 48 60 Z" fill={bodyColor} />
          ) : (
            <path d="M10 60 L12 34 C14 32 22 30 28 30 C34 30 42 32 44 34 L46 60 Z" fill={bodyColor} />
          )}
        </svg>
      </div>
      {isNew && (
        <div
          className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full border-2"
          style={{ background: '#E53535', borderColor: '#0A0A0A' }}
        />
      )}
    </div>
  );
}

export function StyleThumbnail({ imageUrl, size = 120 }: { imageUrl: string; size?: number }) {
  return (
    <div
      className="rounded-lg overflow-hidden flex-shrink-0"
      style={{
        width: size,
        height: size * 1.1,
        border: '1px solid #2A2A2A',
      }}
    >
      <img
        src={imageUrl}
        alt="헤어스타일"
        className="w-full h-full object-cover"
        style={{ filter: 'brightness(0.85) saturate(0.9)' }}
      />
    </div>
  );
}
