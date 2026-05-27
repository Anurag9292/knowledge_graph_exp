'use client';

import { useState, useEffect } from 'react';
import { X, ArrowLeftRight, Zap, Clock, AlertTriangle, CheckCircle, MinusCircle } from 'lucide-react';
import { formatDuration, formatTokens } from '@/lib/utils';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface CompareViewProps {
  runAId: string;
  runBId: string;
  onClose: () => void;
}

interface AgentComparison {
  agent_type: string;
  in_run_a: boolean;
  in_run_b: boolean;
  run_a: NodeMetrics | null;
  run_b: NodeMetrics | null;
}

interface NodeMetrics {
  node_id: string;
  status: string;
  duration_ms: number;
  tokens_used: number;
  tok_per_sec: number;
  input_data: any;
  output_data: any;
  error: string | null;
}

interface CompareResult {
  run_a: { id: string; status: string; total_duration_ms: number; total_tokens_used: number; started_at: string };
  run_b: { id: string; status: string; total_duration_ms: number; total_tokens_used: number; started_at: string };
  comparisons: AgentComparison[];
  summary: { agents_matched: number; agents_only_in_a: number; agents_only_in_b: number; total_agents: number };
}

export function CompareView({ runAId, runBId, onClose }: CompareViewProps) {
  const [data, setData] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [diffView, setDiffView] = useState<'output' | 'input'>('output');

  useEffect(() => {
    fetchComparison();
  }, [runAId, runBId]);

  const fetchComparison = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/experiments/compare/runs?run_a=${runAId}&run_b=${runBId}`);
      if (!res.ok) throw new Error('Failed to load comparison');
      const result = await res.json();
      setData(result);
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
        <div className="bg-white rounded-lg p-8 text-center">
          <p className="text-gray-500">Loading comparison...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
        <div className="bg-white rounded-lg p-8 text-center">
          <p className="text-red-500">{error || 'Failed to load'}</p>
          <button onClick={onClose} className="mt-4 px-4 py-2 bg-gray-100 rounded text-sm">Close</button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ArrowLeftRight className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-bold text-gray-800">Run Comparison</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Run summary cards */}
        <div className="px-6 py-3 bg-gray-50 border-b border-gray-200 grid grid-cols-2 gap-4">
          <div className="p-3 bg-white rounded-lg border border-gray-200">
            <p className="text-xs text-gray-500 mb-1">Run A</p>
            <p className="text-sm font-medium text-gray-700">{data.run_a.started_at || data.run_a.id.slice(0, 8)}</p>
            <div className="flex gap-3 mt-1 text-xs text-gray-400">
              <span>⏱ {formatDuration(data.run_a.total_duration_ms || 0)}</span>
              <span>🎫 {formatTokens(data.run_a.total_tokens_used || 0)}</span>
              <span className={data.run_a.status === 'completed' ? 'text-green-600' : 'text-red-500'}>{data.run_a.status}</span>
            </div>
          </div>
          <div className="p-3 bg-white rounded-lg border border-gray-200">
            <p className="text-xs text-gray-500 mb-1">Run B</p>
            <p className="text-sm font-medium text-gray-700">{data.run_b.started_at || data.run_b.id.slice(0, 8)}</p>
            <div className="flex gap-3 mt-1 text-xs text-gray-400">
              <span>⏱ {formatDuration(data.run_b.total_duration_ms || 0)}</span>
              <span>🎫 {formatTokens(data.run_b.total_tokens_used || 0)}</span>
              <span className={data.run_b.status === 'completed' ? 'text-green-600' : 'text-red-500'}>{data.run_b.status}</span>
            </div>
          </div>
        </div>

        {/* Summary stats */}
        <div className="px-6 py-2 border-b border-gray-100 flex gap-4 text-xs text-gray-500">
          <span>Matched: <strong>{data.summary.agents_matched}</strong></span>
          {data.summary.agents_only_in_a > 0 && <span className="text-red-500">Only in A: {data.summary.agents_only_in_a}</span>}
          {data.summary.agents_only_in_b > 0 && <span className="text-green-600">Only in B: {data.summary.agents_only_in_b}</span>}
        </div>

        {/* Agent comparisons */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {data.comparisons.map((comp, i) => (
            <AgentComparisonCard
              key={i}
              comparison={comp}
              expanded={expandedAgent === `${comp.agent_type}_${i}`}
              onToggle={() => setExpandedAgent(expandedAgent === `${comp.agent_type}_${i}` ? null : `${comp.agent_type}_${i}`)}
              diffView={diffView}
              setDiffView={setDiffView}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function AgentComparisonCard({
  comparison,
  expanded,
  onToggle,
  diffView,
  setDiffView,
}: {
  comparison: AgentComparison;
  expanded: boolean;
  onToggle: () => void;
  diffView: 'output' | 'input';
  setDiffView: (v: 'output' | 'input') => void;
}) {
  const { agent_type, in_run_a, in_run_b, run_a, run_b } = comparison;

  // Determine status
  let statusIcon = <CheckCircle className="w-4 h-4 text-green-500" />;
  let statusLabel = 'Matched';
  if (!in_run_a) {
    statusIcon = <Zap className="w-4 h-4 text-green-600" />;
    statusLabel = 'New in B';
  } else if (!in_run_b) {
    statusIcon = <MinusCircle className="w-4 h-4 text-red-500" />;
    statusLabel = 'Removed in B';
  } else if (run_a?.status === 'failed' && run_b?.status === 'completed') {
    statusIcon = <CheckCircle className="w-4 h-4 text-green-500" />;
    statusLabel = 'Fixed';
  } else if (run_a?.status === 'completed' && run_b?.status === 'failed') {
    statusIcon = <AlertTriangle className="w-4 h-4 text-red-500" />;
    statusLabel = 'Regressed';
  }

  // Metrics delta
  const durationDelta = (run_a?.duration_ms && run_b?.duration_ms) ? run_b.duration_ms - run_a.duration_ms : null;
  const tokensDelta = (run_a?.tokens_used && run_b?.tokens_used) ? run_b.tokens_used - run_a.tokens_used : null;
  const tokSecA = run_a?.tok_per_sec || 0;
  const tokSecB = run_b?.tok_per_sec || 0;

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Card header */}
      <div
        className="px-4 py-3 bg-gray-50 flex items-center justify-between cursor-pointer hover:bg-gray-100 transition"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3">
          {statusIcon}
          <span className="text-sm font-semibold text-gray-700">{agent_type.replace(/_/g, ' ')}</span>
          <span className="text-xs text-gray-400">{statusLabel}</span>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          {run_a && run_b && (
            <>
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatDuration(run_a.duration_ms)} → {formatDuration(run_b.duration_ms)}
                {durationDelta !== null && (
                  <span className={durationDelta < 0 ? 'text-green-600' : durationDelta > 0 ? 'text-red-500' : 'text-gray-400'}>
                    ({durationDelta > 0 ? '+' : ''}{formatDuration(Math.abs(durationDelta))})
                  </span>
                )}
              </span>
              {(tokSecA > 0 || tokSecB > 0) && (
                <span className="flex items-center gap-1">
                  <Zap className="w-3 h-3" />
                  {tokSecA} → {tokSecB} tok/s
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="p-4 border-t border-gray-100">
          {/* Diff view toggle */}
          <div className="flex gap-2 mb-3">
            <button
              onClick={() => setDiffView('output')}
              className={`px-2 py-1 text-xs rounded ${diffView === 'output' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}`}
            >
              Output
            </button>
            <button
              onClick={() => setDiffView('input')}
              className={`px-2 py-1 text-xs rounded ${diffView === 'input' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}`}
            >
              Input
            </button>
          </div>

          {/* Side-by-side data */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Run A</p>
              <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-auto max-h-[300px] whitespace-pre-wrap">
                {run_a
                  ? JSON.stringify(diffView === 'output' ? run_a.output_data : run_a.input_data, null, 2)?.slice(0, 3000)
                  : 'Not present in this run'}
              </pre>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Run B</p>
              <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-auto max-h-[300px] whitespace-pre-wrap">
                {run_b
                  ? JSON.stringify(diffView === 'output' ? run_b.output_data : run_b.input_data, null, 2)?.slice(0, 3000)
                  : 'Not present in this run'}
              </pre>
            </div>
          </div>

          {/* Metrics table */}
          {run_a && run_b && (
            <div className="mt-3 border-t border-gray-100 pt-3">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500">
                    <th className="text-left py-1">Metric</th>
                    <th className="text-right py-1">Run A</th>
                    <th className="text-right py-1">Run B</th>
                    <th className="text-right py-1">Delta</th>
                  </tr>
                </thead>
                <tbody className="text-gray-700">
                  <tr>
                    <td className="py-1">Duration</td>
                    <td className="text-right">{formatDuration(run_a.duration_ms)}</td>
                    <td className="text-right">{formatDuration(run_b.duration_ms)}</td>
                    <td className={`text-right font-medium ${(durationDelta || 0) < 0 ? 'text-green-600' : (durationDelta || 0) > 0 ? 'text-red-500' : ''}`}>
                      {durationDelta !== null ? `${durationDelta > 0 ? '+' : ''}${formatDuration(Math.abs(durationDelta))}` : '—'}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-1">Tokens</td>
                    <td className="text-right">{run_a.tokens_used || '—'}</td>
                    <td className="text-right">{run_b.tokens_used || '—'}</td>
                    <td className={`text-right font-medium ${(tokensDelta || 0) < 0 ? 'text-green-600' : (tokensDelta || 0) > 0 ? 'text-amber-600' : ''}`}>
                      {tokensDelta !== null && tokensDelta !== 0 ? `${tokensDelta > 0 ? '+' : ''}${tokensDelta}` : '—'}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-1">Throughput</td>
                    <td className="text-right">{tokSecA > 0 ? `${tokSecA} tok/s` : '—'}</td>
                    <td className="text-right">{tokSecB > 0 ? `${tokSecB} tok/s` : '—'}</td>
                    <td className={`text-right font-medium ${tokSecB > tokSecA ? 'text-green-600' : tokSecB < tokSecA ? 'text-red-500' : ''}`}>
                      {tokSecA > 0 && tokSecB > 0 ? `${tokSecB > tokSecA ? '+' : ''}${Math.round(tokSecB - tokSecA)} tok/s` : '—'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
