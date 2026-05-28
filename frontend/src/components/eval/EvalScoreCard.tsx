'use client';

interface EvalScoreCardProps {
  score: number;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function EvalScoreCard({ score, label, size = 'md' }: EvalScoreCardProps) {
  const percentage = Math.round(score * 100);
  const color = score >= 0.8 ? 'bg-green-500' : score >= 0.5 ? 'bg-yellow-500' : 'bg-red-500';
  const textColor = score >= 0.8 ? 'text-green-700' : score >= 0.5 ? 'text-yellow-700' : 'text-red-700';
  const sizes = { sm: 'h-2', md: 'h-3', lg: 'h-4' };

  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-xs text-gray-500 w-20 truncate">{label}</span>}
      <div className={`flex-1 ${sizes[size]} bg-gray-200 rounded-full overflow-hidden`}>
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${percentage}%` }} />
      </div>
      <span className={`text-xs font-semibold ${textColor} w-10 text-right`}>{percentage}%</span>
    </div>
  );
}
