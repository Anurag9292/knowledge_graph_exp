'use client';

import { useEffect, useState } from 'react';
import { Plus, Play, RefreshCw, Trash2, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { useEvalStore } from '@/stores/evalStore';
import { experimentsApi } from '@/lib/api';
import { QueryConfigEditor } from './QueryConfigEditor';
import { EvalResultsView } from './EvalResultsView';
import { EvalScoreCard } from './EvalScoreCard';
import { QueryEvalRun } from '@/types';

export function EvalDashboard() {
  const {
    configs, runs, selectedConfig, selectedRun, loading, error,
    fetchConfigs, fetchRuns, fetchRunDetails, selectConfig, selectRun,
    deleteConfig, startEvalRun, showConfigEditor, setShowConfigEditor,
    showRunTrigger, setShowRunTrigger, clearError,
  } = useEvalStore();

  const [completedRuns, setCompletedRuns] = useState<{id: string; label: string}[]>([]);
  const [selectedIngestionRun, setSelectedIngestionRun] = useState('');
  const [polling, setPolling] = useState<string | null>(null);

  useEffect(() => {
    fetchConfigs();
    fetchRuns();
    // Load all completed ingestion runs for the run trigger
    const loadCompletedRuns = async () => {
      try {
        const experiments = await experimentsApi.list();
        const allRuns: {id: string; label: string}[] = [];
        for (const exp of experiments) {
          try {
            const detail = await experimentsApi.get(exp.id);
            if (detail.runs) {
              for (const run of detail.runs) {
                if (run.status === 'completed') {
                  const date = run.started_at ? new Date(run.started_at).toLocaleString() : run.created_at ? new Date(run.created_at).toLocaleString() : 'unknown';
                  allRuns.push({ id: run.id, label: `${exp.name} — ${date}` });
                }
              }
            }
          } catch (e) { /* skip failed fetches */ }
        }
        setCompletedRuns(allRuns);
      } catch (e) {
        console.error('Failed to load runs:', e);
      }
    };
    loadCompletedRuns();
  }, [fetchConfigs, fetchRuns]);

  // Poll for running eval results
  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(async () => {
      await fetchRunDetails(polling);
      const run = useEvalStore.getState().selectedRun;
      if (run && (run.status === 'completed' || run.status === 'failed')) {
        setPolling(null);
        fetchRuns();
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [polling, fetchRunDetails, fetchRuns]);

  const handleStartEval = async () => {
    if (!selectedConfig || !selectedIngestionRun) return;
    try {
      const runId = await startEvalRun(selectedConfig.id, selectedIngestionRun);
      setShowRunTrigger(false);
      setPolling(runId);
      await fetchRunDetails(runId);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSelectRun = (run: QueryEvalRun) => {
    selectRun(run);
    if (run.status === 'running' || run.status === 'pending') {
      setPolling(run.id);
    }
    fetchRunDetails(run.id);
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col bg-gray-50 p-4">
      {/* Error banner */}
      {error && (
        <div className="mb-3 px-3 py-2 bg-red-50 border border-red-200 rounded-md flex items-center justify-between">
          <span className="text-xs text-red-700">{error}</span>
          <button onClick={clearError} className="text-red-400 hover:text-red-600 text-xs">dismiss</button>
        </div>
      )}

      <div className="flex-1 overflow-hidden flex gap-4">
        {/* Left panel: Configs + Runs */}
        <div className="w-80 shrink-0 flex flex-col gap-3 overflow-y-auto">
          {/* Test Suites */}
          <div className="bg-white border border-gray-200 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Test Suites</h3>
              <button
                onClick={() => setShowConfigEditor(true)}
                className="text-blue-600 hover:text-blue-800"
              >
                <Plus size={14} />
              </button>
            </div>

            {showConfigEditor && <QueryConfigEditor />}

            <div className="space-y-1 mt-2">
              {configs.map((config) => (
                <div
                  key={config.id}
                  onClick={() => selectConfig(config)}
                  className={`px-2 py-1.5 rounded-md cursor-pointer flex items-center justify-between group ${
                    selectedConfig?.id === config.id ? 'bg-blue-50 border border-blue-200' : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="min-w-0">
                    <div className="text-sm text-gray-700 truncate">{config.name}</div>
                    <div className="text-xs text-gray-400">{config.query_count} queries</div>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteConfig(config.id); }}
                    className="text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
              {configs.length === 0 && !showConfigEditor && (
                <p className="text-xs text-gray-400 text-center py-2">No test suites yet</p>
              )}
            </div>
          </div>

          {/* Run Trigger */}
          {selectedConfig && (
            <div className="bg-white border border-gray-200 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Run Eval</h3>
              </div>
              <select
                value={selectedIngestionRun}
                onChange={(e) => setSelectedIngestionRun(e.target.value)}
                className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded-md mb-2"
              >
                <option value="">Select a completed ingestion run...</option>
                {completedRuns.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.label}
                  </option>
                ))}
              </select>
              {completedRuns.length === 0 && (
                <p className="text-xs text-gray-400 text-center py-1">No completed runs found</p>
              )}
              <button
                onClick={handleStartEval}
                disabled={!selectedIngestionRun || loading}
                className="w-full mt-2 px-3 py-2 text-xs font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-1"
              >
                <Play size={12} /> Run Evaluation
              </button>
            </div>
          )}

          {/* Eval Runs List */}
          <div className="bg-white border border-gray-200 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Eval Runs</h3>
              <button onClick={() => fetchRuns()} className="text-gray-400 hover:text-gray-600">
                <RefreshCw size={12} />
              </button>
            </div>
            <div className="space-y-1">
              {runs.map((run) => (
                <div
                  key={run.id}
                  onClick={() => handleSelectRun(run)}
                  className={`px-2 py-1.5 rounded-md cursor-pointer flex items-center justify-between ${
                    selectedRun?.id === run.id ? 'bg-blue-50 border border-blue-200' : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    {run.status === 'completed' && <CheckCircle size={12} className="text-green-500 shrink-0" />}
                    {run.status === 'failed' && <XCircle size={12} className="text-red-500 shrink-0" />}
                    {run.status === 'running' && <Loader2 size={12} className="text-blue-500 animate-spin shrink-0" />}
                    {run.status === 'pending' && <Clock size={12} className="text-gray-400 shrink-0" />}
                    <span className="text-xs text-gray-600 truncate">Run {run.id.slice(0, 8)}</span>
                  </div>
                  {run.overall_score !== undefined && run.overall_score !== null && (
                    <span className={`text-xs font-semibold ${
                      run.overall_score >= 0.7 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {Math.round(run.overall_score * 100)}%
                    </span>
                  )}
                </div>
              ))}
              {runs.length === 0 && (
                <p className="text-xs text-gray-400 text-center py-2">No eval runs yet</p>
              )}
            </div>
          </div>
        </div>

        {/* Right panel: Results */}
        <div className="flex-1 overflow-y-auto">
          {selectedRun ? (
            selectedRun.status === 'running' || selectedRun.status === 'pending' ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <Loader2 size={32} className="text-blue-500 animate-spin mx-auto mb-2" />
                  <p className="text-sm text-gray-600">Evaluation in progress...</p>
                  <p className="text-xs text-gray-400 mt-1">Polling every 3 seconds</p>
                </div>
              </div>
            ) : (
              <EvalResultsView run={selectedRun} />
            )
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
              Select an eval run to view results
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
