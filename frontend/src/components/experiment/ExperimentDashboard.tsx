'use client';

import { useState, useEffect } from 'react';
import { ArrowLeft, Clock, Zap } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { useExecutionStore } from '@/stores/executionStore';
import { useGraphStore } from '@/stores/graphStore';
import { experimentsApi } from '@/lib/api';
import { ExperimentSession, ExperimentRun } from '@/types';
import { formatDuration, formatTokens, getStatusColor } from '@/lib/utils';

export function ExperimentDashboard() {
  const { setActiveTab } = useAppStore();
  const { loadRunResults } = useExecutionStore();
  const { loadGraph } = useGraphStore();
  const [experiments, setExperiments] = useState<ExperimentSession[]>([]);
  const [selectedExp, setSelectedExp] = useState<string | null>(null);
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadExperiments();
  }, []);

  const loadExperiments = async () => {
    setLoading(true);
    try {
      const data = await experimentsApi.list();
      setExperiments(data);
    } catch (e) {
      console.error('Failed to load experiments:', e);
    }
    setLoading(false);
  };

  const loadRuns = async (sessionId: string) => {
    setSelectedExp(sessionId);
    try {
      const data = await experimentsApi.listRuns(sessionId);
      setRuns(data);
    } catch (e) {
      console.error('Failed to load runs:', e);
    }
  };

  const viewRun = async (sessionId: string, runId: string) => {
    try {
      const run = await experimentsApi.getRun(sessionId, runId);
      loadRunResults(run);
      // Load the graph from the snapshot
      if (run.graph_snapshot_json) {
        loadGraph(run.graph_snapshot_json.nodes || [], run.graph_snapshot_json.edges || []);
      }
      setActiveTab('editor');
    } catch (e) {
      console.error('Failed to load run:', e);
    }
  };

  return (
    <div className="flex-1 bg-gray-50 p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button onClick={() => setActiveTab('editor')} className="text-gray-400 hover:text-gray-600">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="text-xl font-bold text-gray-800">Experiments</h1>
          </div>
          <button onClick={loadExperiments} className="text-xs text-blue-600 hover:text-blue-700 font-medium">
            Refresh
          </button>
        </div>

        {loading ? (
          <div className="text-center text-gray-400 py-12">Loading experiments...</div>
        ) : experiments.length === 0 ? (
          <div className="text-center text-gray-400 py-12">
            <p className="text-lg mb-2">No experiments yet</p>
            <p className="text-sm">Run a pipeline to create your first experiment</p>
          </div>
        ) : (
          <div className="space-y-3">
            {experiments.map((exp) => (
              <div
                key={exp.id}
                className={`bg-white border rounded-lg p-4 cursor-pointer transition hover:shadow-md ${
                  selectedExp === exp.id ? 'border-blue-400 shadow-md' : 'border-gray-200'
                }`}
                onClick={() => loadRuns(exp.id)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700">{exp.name}</h3>
                    {exp.description && <p className="text-xs text-gray-400 mt-0.5">{exp.description}</p>}
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-gray-500">{exp.run_count} runs</span>
                    <p className="text-xs text-gray-400">{new Date(exp.created_at).toLocaleDateString()}</p>
                  </div>
                </div>

                {/* Runs for this experiment */}
                {selectedExp === exp.id && runs.length > 0 && (
                  <div className="mt-4 border-t border-gray-100 pt-3 space-y-2">
                    {runs.map((run) => (
                      <div
                        key={run.id}
                        onClick={(e) => { e.stopPropagation(); viewRun(exp.id, run.id); }}
                        className="flex items-center justify-between p-2 rounded-md hover:bg-gray-50 cursor-pointer"
                      >
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: getStatusColor(run.status) }} />
                          <span className="text-xs font-medium text-gray-600">{run.status}</span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-gray-400">
                          {run.total_duration_ms && (
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3" /> {formatDuration(run.total_duration_ms)}
                            </span>
                          )}
                          <span className="flex items-center gap-1">
                            <Zap className="w-3 h-3" /> {formatTokens(run.total_tokens_used)} tokens
                          </span>
                          <span>{new Date(run.created_at).toLocaleTimeString()}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
