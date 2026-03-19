'use client';

import { useEffect, useState } from 'react';
import StatsCard from '../components/StatsCard';
import RecentBets from '../components/RecentBets';
import ROIChart from '../components/ROIChart';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';

export default function Home() {
  const [stats, setStats] = useState<any>(null);
  const [vipStats, setVipStats] = useState<any>(null);
  const [freeStats, setFreeStats] = useState<any>(null);
  const [topWins, setTopWins] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [statsRes, vipRes, freeRes, winsRes] = await Promise.all([
          fetch(`${API_URL}/api/stats?days=7`),
          fetch(`${API_URL}/api/stats?days=7&tier=VIP`),
          fetch(`${API_URL}/api/stats?days=7&tier=FREE`),
          fetch(`${API_URL}/api/top-wins?days=7&limit=3`),
        ]);

        setStats(await statsRes.json());
        setVipStats(await vipRes.json());
        setFreeStats(await freeRes.json());
        setTopWins(await winsRes.json());
      } catch (error) {
        console.error('Failed to fetch data:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
    const interval = setInterval(fetchData, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-xl text-gray-600">Loading...</div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            📊 SZELVÉNYKIRÁLY Dashboard
          </h1>
          <p className="text-gray-600">Real-time betting performance analytics</p>
        </div>

        {/* Overall Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <StatsCard
            title="Overall (7 Days)"
            stats={stats}
            color="blue"
          />
          <StatsCard
            title="VIP Tips"
            stats={vipStats}
            color="purple"
          />
          <StatsCard
            title="Free Tips"
            stats={freeStats}
            color="green"
          />
        </div>

        {/* ROI Chart */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-2xl font-bold mb-4">ROI Trend (Last 30 Days)</h2>
          <ROIChart />
        </div>

        {/* Top Wins */}
        {topWins.length > 0 && (
          <div className="bg-white rounded-lg shadow-md p-6 mb-8">
            <h2 className="text-2xl font-bold mb-4">🏆 Top Wins (7 Days)</h2>
            <div className="space-y-3">
              {topWins.map((win, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between p-4 bg-gradient-to-r from-yellow-50 to-yellow-100 rounded-lg"
                >
                  <div>
                    <div className="font-semibold text-gray-900">{win.match}</div>
                    <div className="text-sm text-gray-600">
                      {win.tip} • {win.date}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-yellow-600">
                      @{win.odds}
                    </div>
                    <div className="text-sm text-gray-600">{win.score}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Bets */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-bold mb-4">Recent Bets</h2>
          <RecentBets />
        </div>
      </div>
    </main>
  );
}
