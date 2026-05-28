'use client';

import { useState } from 'react';
import { Play, Pause, Square, SkipForward, Save, Trash2, Network } from 'lucide-react';
import { useGraphStore } from '@/stores/graphStore';
import { useExecutionStore } from '@/stores/executionStore';
import { useAppStore } from '@/stores/appStore';
import { graphsApi, experimentsApi } from '@/lib/api';

export function Toolbar() {
  const { graphId, graphName, graphDescription, setGraphMeta, getGraphJson, clearGraph } = useGraphStore();
  const { isRunning, isPaused, startExecution, stopExecution, pauseExecution, resumeExecution, stepExecution } = useExecutionStore();
  const { inputText, setActiveTab, kgViewerOpen, toggleKgViewer } = useAppStore();
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const graphJson = getGraphJson();
      if (graphId) {
        await graphsApi.update(graphId, { name: graphName, description: graphDescription, nodes_json: graphJson.nodes, edges_json: graphJson.edges });
      } else {
        const result = await graphsApi.create({ name: graphName, description: graphDescription, nodes_json: graphJson.nodes, edges_json: graphJson.edges });
        setGraphMeta(result.id, result.name, result.description || '');
      }
    } catch (e) {
      console.error('Save failed:', e);
    }
    setSaving(false);
  };

  const handleRun = async () => {
    if (!graphId) {
      await handleSave();
    }
    const currentGraphId = useGraphStore.getState().graphId;
    if (!currentGraphId || !inputText) return;

    setRunning(true);
    try {
      // Create experiment
      const experiment = await experimentsApi.create({
        name: `Run - ${new Date().toLocaleString()}`,
        graph_id: currentGraphId,
        input_text: inputText,
      });
      // Start run
      const run = await experimentsApi.createRun(experiment.id);
      startExecution(experiment.id, run.run_id);
    } catch (e) {
      console.error('Run failed:', e);
    }
    setRunning(false);
  };

  return (
    <div className="h-12 bg-white border-b border-gray-200 flex items-center px-4 gap-3">
      {/* Graph name */}
      <input
        type="text"
        value={graphName}
        onChange={(e) => setGraphMeta(graphId, e.target.value, graphDescription)}
        className="text-sm font-semibold text-gray-700 bg-transparent border-none focus:outline-none focus:ring-1 focus:ring-blue-300 rounded px-2 py-1"
        placeholder="Pipeline name..."
      />

      <div className="flex-1" />

      {/* Save */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 rounded-md hover:bg-gray-200 disabled:opacity-50 transition"
      >
        <Save className="w-3.5 h-3.5" />
        {saving ? 'Saving...' : 'Save'}
      </button>

      {/* Clear */}
      <button
        onClick={clearGraph}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 rounded-md hover:bg-gray-200 transition"
      >
        <Trash2 className="w-3.5 h-3.5" />
        Clear
      </button>

      <div className="w-px h-6 bg-gray-200" />

      {/* Run controls */}
      {!isRunning ? (
        <button
          onClick={handleRun}
          disabled={running}
          className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-50 transition"
        >
          <Play className="w-3.5 h-3.5" />
          {running ? 'Starting...' : 'Run'}
        </button>
      ) : (
        <>
          {!isPaused ? (
            <button
              onClick={pauseExecution}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-yellow-500 rounded-md hover:bg-yellow-600 transition"
            >
              <Pause className="w-3.5 h-3.5" />
              Pause
            </button>
          ) : (
            <>
              <button
                onClick={resumeExecution}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-green-600 rounded-md hover:bg-green-700 transition"
              >
                <Play className="w-3.5 h-3.5" />
                Resume
              </button>
              <button
                onClick={stepExecution}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition"
              >
                <SkipForward className="w-3.5 h-3.5" />
                Step
              </button>
            </>
          )}
          <button
            onClick={stopExecution}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-red-600 rounded-md hover:bg-red-700 transition"
          >
            <Square className="w-3.5 h-3.5" />
            Stop
          </button>
        </>
      )}

      <div className="w-px h-6 bg-gray-200" />

      {/* KG Viewer toggle */}
      <button
        onClick={() => toggleKgViewer()}
        className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition ${
          kgViewerOpen
            ? 'text-purple-700 bg-purple-100 hover:bg-purple-200'
            : 'text-gray-600 bg-gray-100 hover:bg-gray-200'
        }`}
      >
        <Network className="w-3.5 h-3.5" />
        KG View
      </button>

      {/* Navigation */}
      <button
        onClick={() => setActiveTab('experiments')}
        className="text-xs text-gray-500 hover:text-gray-700 font-medium transition"
      >
        Experiments
      </button>
      <button
        onClick={() => setActiveTab('eval')}
        className="text-xs text-gray-500 hover:text-gray-700 font-medium transition"
      >
        Eval
      </button>
    </div>
  );
}
