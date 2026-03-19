'use client';

import { useEffect, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';

export default function ROIChart() {
  const [data, setData] = useState<any[]>([]);

  useEffect(() => {
    async function fetchData() {
      try {
        // Fetch stats for last 30 days in 5-day intervals
        const days = [5, 10, 15, 20, 25, 30];
        const promises = days.map(d =>
          fetch(`${API_URL}/api/stats?days=${d}`).then(r => r.json())
        );
        
        const results = await Promise.all(promises);
        
        const chartData = results.map((stats, i) => ({
          label: `${days[i]}d`,
          roi: stats.roi || 0,
          hitRate: stats.hit_rate || 0,
        }));
        
        setData(chartData);
      } catch (error) {
        console.error('Failed to fetch chart data:', error);
      }
    }

    fetchData();
  }, []);

  if (data.length === 0) {
    return <div className="text-center text-gray-500">Loading chart...</div>;
  }

  // Simple bar chart
  const maxROI = Math.max(...data.map(d => Math.abs(d.roi)));
  const scale = maxROI > 0 ? 100 / maxROI : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-end space-x-4 h-64">
        {data.map((item, i) => {
          const height = Math.abs(item.roi) * scale;
          const isPositive = item.roi > 0;
          
          return (
            <div key={i} className="flex-1 flex flex-col items-center">
              <div className="text-sm font-semibold mb-2">
                {item.roi > 0 && '+'}{item.roi.toFixed(1)}%
              </div>
              <div
                className={`w-full rounded-t transition-all ${
                  isPositive ? 'bg-green-500' : 'bg-red-500'
                }`}
                style={{ height: `${height}%` }}
              />
              <div className="text-xs text-gray-600 mt-2">{item.label}</div>
              <div className="text-xs text-gray-500">{item.hitRate}% hit</div>
            </div>
          );
        })}
      </div>
      
      <div className="border-t pt-4 grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-600">Trend:</span>
          <span className="ml-2 font-semibold">
            {data[data.length - 1].roi > data[0].roi ? '📈 Up' : '📉 Down'}
          </span>
        </div>
        <div>
          <span className="text-gray-600">30-day ROI:</span>
          <span className={`ml-2 font-bold ${
            data[data.length - 1].roi > 0 ? 'text-green-600' : 'text-red-600'
          }`}>
            {data[data.length - 1].roi > 0 && '+'}
            {data[data.length - 1].roi.toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
}
