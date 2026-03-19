'use client';

import { useEffect, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';

export default function RecentBets() {
  const [bets, setBets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchBets() {
      try {
        const res = await fetch(`${API_URL}/api/recent-bets?limit=20`);
        const data = await res.json();
        setBets(data);
      } catch (error) {
        console.error('Failed to fetch bets:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchBets();
  }, []);

  if (loading) {
    return <div className="text-center text-gray-500">Loading bets...</div>;
  }

  const getOutcomeColor = (outcome: string) => {
    switch (outcome) {
      case 'won':
        return 'bg-green-100 text-green-800';
      case 'lost':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getOutcomeIcon = (outcome: string) => {
    switch (outcome) {
      case 'won':
        return '✅';
      case 'lost':
        return '❌';
      default:
        return '⏳';
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Match</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">League</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tip</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Odds</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tier</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Result</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {bets.map((bet) => (
            <tr key={bet.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 text-sm font-medium text-gray-900">
                {bet.match}
              </td>
              <td className="px-4 py-3 text-sm text-gray-600">
                {bet.league}
              </td>
              <td className="px-4 py-3 text-sm text-gray-700">
                {bet.tip}
              </td>
              <td className="px-4 py-3 text-sm font-semibold text-gray-900">
                {bet.odds ? `@${bet.odds}` : '-'}
              </td>
              <td className="px-4 py-3 text-sm">
                <span className={`px-2 py-1 rounded text-xs font-semibold ${
                  bet.tier === 'VIP' ? 'bg-purple-100 text-purple-800' : 'bg-blue-100 text-blue-800'
                }`}>
                  {bet.tier}
                </span>
              </td>
              <td className="px-4 py-3 text-sm text-gray-600">
                {bet.result || '-'}
              </td>
              <td className="px-4 py-3 text-sm">
                <span className={`px-2 py-1 rounded text-xs font-semibold ${getOutcomeColor(bet.outcome)}`}>
                  {getOutcomeIcon(bet.outcome)} {bet.outcome.toUpperCase()}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
