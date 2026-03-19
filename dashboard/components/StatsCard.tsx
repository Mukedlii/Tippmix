interface StatsCardProps {
  title: string;
  stats: any;
  color: 'blue' | 'purple' | 'green';
}

const colorClasses = {
  blue: 'from-blue-500 to-blue-600',
  purple: 'from-purple-500 to-purple-600',
  green: 'from-green-500 to-green-600',
};

export default function StatsCard({ title, stats, color }: StatsCardProps) {
  if (!stats) return null;

  const roiColor = stats.roi > 0 ? 'text-green-600' : stats.roi < 0 ? 'text-red-600' : 'text-gray-600';

  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      <div className={`bg-gradient-to-r ${colorClasses[color]} text-white px-6 py-4`}>
        <h3 className="text-lg font-semibold">{title}</h3>
      </div>
      <div className="p-6 space-y-3">
        {/* ROI */}
        <div className="flex justify-between items-center">
          <span className="text-gray-600">ROI:</span>
          <span className={`text-2xl font-bold ${roiColor}`}>
            {stats.roi > 0 && '+'}{stats.roi}%
          </span>
        </div>

        {/* Hit Rate */}
        <div className="flex justify-between items-center">
          <span className="text-gray-600">Hit Rate:</span>
          <span className="text-xl font-semibold text-gray-900">
            {stats.hit_rate}%
          </span>
        </div>

        {/* Win/Loss Record */}
        <div className="flex justify-between items-center">
          <span className="text-gray-600">Record:</span>
          <span className="text-gray-900">
            {stats.wins}W - {stats.losses}L - {stats.pending}P
          </span>
        </div>

        {/* Profit */}
        <div className="flex justify-between items-center">
          <span className="text-gray-600">Profit:</span>
          <span className={`font-semibold ${roiColor}`}>
            {stats.profit > 0 && '+'}{stats.profit.toFixed(0)} Ft
          </span>
        </div>

        {/* Avg Odds */}
        <div className="flex justify-between items-center">
          <span className="text-gray-600">Avg Odds:</span>
          <span className="text-gray-900">{stats.avg_odds}</span>
        </div>

        {/* Best Streak */}
        <div className="flex justify-between items-center text-sm">
          <span className="text-gray-500">Best Streak:</span>
          <span className="text-green-600">🔥 {stats.best_streak}</span>
        </div>
      </div>
    </div>
  );
}
