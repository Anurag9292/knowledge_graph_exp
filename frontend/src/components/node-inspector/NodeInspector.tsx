'use client';

import { useState } from 'react';
import { X, Brain, ArrowRightLeft, MemoryStick, ScrollText, Wrench } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { useExecutionStore } from '@/stores/executionStore';
import { useGraphStore } from '@/stores/graphStore';
import { getAgentIcon, formatDuration, formatTokens } from '@/lib/utils';

type Tab = 'config' | 'input' | 'output' | 'memory' | 'logs' | 'tools';

export function NodeInspector() {
  const { selectedNodeId, inspectorOpen, selectNode, agentTypes } = useAppStore();
  const { nodeExecutions } = useExecutionStore();
  const { nodes, updateNodeConfig } = useGraphStore();
  const [activeTab, setActiveTab] = useState<Tab>('config');

  if (!inspectorOpen || !selectedNodeId) return null;

  const node = nodes.find((n) => n.id === selectedNodeId);
  if (!node) return null;

  const execution = nodeExecutions[selectedNodeId];
  const agentType = agentTypes.find((a) => a.name === node.data.agentType);
  const config = node.data.config || {};

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'config', label: 'Config', icon: <Brain className="w-3.5 h-3.5" /> },
    { id: 'input', label: 'Input', icon: <ArrowRightLeft className="w-3.5 h-3.5" /> },
    { id: 'output', label: 'Output', icon: <ArrowRightLeft className="w-3.5 h-3.5" /> },
    { id: 'memory', label: 'Memory', icon: <MemoryStick className="w-3.5 h-3.5" /> },
    { id: 'logs', label: 'Logs', icon: <ScrollText className="w-3.5 h-3.5" /> },
    { id: 'tools', label: 'Tools', icon: <Wrench className="w-3.5 h-3.5" /> },
  ];

  return (
    <div className="w-96 bg-white border-l border-gray-200 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <span className="text-lg">{getAgentIcon(node.data.agentType)}</span>
          <div>
            <h3 className="text-sm font-semibold text-gray-700">
              {agentType?.name?.replace(/_/g, ' ') || node.data.agentType}
            </h3>
            <p className="text-xs text-gray-400">{selectedNodeId}</p>
          </div>
        </div>
        <button onClick={() => selectNode(null)} className="text-gray-400 hover:text-gray-600">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Execution stats */}
      {execution && (
        <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 flex gap-4 text-xs text-gray-500">
          {execution.duration_ms && <span>⏱ {formatDuration(execution.duration_ms)}</span>}
          {execution.tokens_used !== undefined && <span>🎫 {formatTokens(execution.tokens_used)} tokens</span>}
          <span className={`font-medium ${execution.status === 'completed' ? 'text-green-600' : execution.status === 'failed' ? 'text-red-600' : 'text-blue-600'}`}>
            {execution.status}
          </span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-gray-200 px-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1 px-3 py-2 text-xs font-medium transition border-b-2 ${
              activeTab === tab.id
                ? 'text-blue-600 border-blue-600'
                : 'text-gray-500 border-transparent hover:text-gray-700'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'config' && (
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-gray-600">System Prompt</label>
              <textarea
                value={config.system_prompt || agentType?.default_system_prompt || ''}
                onChange={(e) => updateNodeConfig(selectedNodeId, { system_prompt: e.target.value })}
                className="mt-1 w-full h-32 text-xs border border-gray-300 rounded-md p-2 focus:outline-none focus:ring-1 focus:ring-blue-400 resize-y"
                placeholder="System prompt..."
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-600">Model</label>
                <select
                  value={config.model || agentType?.default_model || 'gpt-4o'}
                  onChange={(e) => updateNodeConfig(selectedNodeId, { model: e.target.value })}
                  className="mt-1 w-full text-xs border border-gray-300 rounded-md p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                >
                  <option value="gpt-4o">gpt-4o</option>
                  <option value="gpt-4o-mini">gpt-4o-mini</option>
                  <option value="gpt-4-turbo">gpt-4-turbo</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600">Temperature</label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={config.temperature ?? agentType?.default_temperature ?? 0.2}
                  onChange={(e) => updateNodeConfig(selectedNodeId, { temperature: parseFloat(e.target.value) })}
                  className="mt-1 w-full text-xs border border-gray-300 rounded-md p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600">Max Tokens</label>
              <input
                type="number"
                step="256"
                min="256"
                max="128000"
                value={config.max_tokens || agentType?.default_max_tokens || 4096}
                onChange={(e) => updateNodeConfig(selectedNodeId, { max_tokens: parseInt(e.target.value) })}
                className="mt-1 w-full text-xs border border-gray-300 rounded-md p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>
          </div>
        )}

        {activeTab === 'input' && (
          <div>
            <h4 className="text-xs font-semibold text-gray-600 mb-2">Input Data</h4>
            {execution?.input_data_json ? (
              <pre className="text-xs bg-gray-50 border border-gray-200 rounded-md p-3 overflow-x-auto whitespace-pre-wrap max-h-[500px] overflow-y-auto">
                {JSON.stringify(execution.input_data_json, null, 2)}
              </pre>
            ) : (
              <p className="text-xs text-gray-400 italic">No input data yet. Run the pipeline to see inputs.</p>
            )}
          </div>
        )}

        {activeTab === 'output' && (
          <div>
            <h4 className="text-xs font-semibold text-gray-600 mb-2">Output Data</h4>
            {execution?.output_data_json ? (
              <pre className="text-xs bg-gray-50 border border-gray-200 rounded-md p-3 overflow-x-auto whitespace-pre-wrap max-h-[500px] overflow-y-auto">
                {JSON.stringify(execution.output_data_json, null, 2)}
              </pre>
            ) : (
              <p className="text-xs text-gray-400 italic">No output data yet. Run the pipeline to see outputs.</p>
            )}
            {execution?.error_message && (
              <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded-md">
                <p className="text-xs text-red-600 font-medium">Error</p>
                <p className="text-xs text-red-500 mt-1">{execution.error_message}</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'memory' && (
          <div className="space-y-4">
            <div>
              <h4 className="text-xs font-semibold text-gray-600 mb-2">Memory Before</h4>
              {execution?.memory_before_json ? (
                <pre className="text-xs bg-gray-50 border border-gray-200 rounded-md p-3 overflow-x-auto whitespace-pre-wrap max-h-[200px] overflow-y-auto">
                  {JSON.stringify(execution.memory_before_json, null, 2)}
                </pre>
              ) : (
                <p className="text-xs text-gray-400 italic">No memory data.</p>
              )}
            </div>
            <div>
              <h4 className="text-xs font-semibold text-gray-600 mb-2">Memory After</h4>
              {execution?.memory_after_json ? (
                <pre className="text-xs bg-green-50 border border-green-200 rounded-md p-3 overflow-x-auto whitespace-pre-wrap max-h-[200px] overflow-y-auto">
                  {JSON.stringify(execution.memory_after_json, null, 2)}
                </pre>
              ) : (
                <p className="text-xs text-gray-400 italic">No memory data.</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'logs' && (
          <div>
            <h4 className="text-xs font-semibold text-gray-600 mb-2">Execution Logs</h4>
            {execution?.logs_json && execution.logs_json.length > 0 ? (
              <div className="space-y-1">
                {execution.logs_json.map((log, i) => (
                  <div key={i} className={`text-xs p-1.5 rounded ${
                    log.level === 'error' ? 'bg-red-50 text-red-700' :
                    log.level === 'warning' ? 'bg-yellow-50 text-yellow-700' :
                    'bg-gray-50 text-gray-600'
                  }`}>
                    <span className="font-mono text-gray-400">
                      [{new Date(log.timestamp * 1000).toLocaleTimeString()}]
                    </span>{' '}
                    {log.message}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-400 italic">No logs yet.</p>
            )}
          </div>
        )}

        {activeTab === 'tools' && (
          <div>
            <h4 className="text-xs font-semibold text-gray-600 mb-2">Tool Calls</h4>
            {execution?.tool_calls_json && execution.tool_calls_json.length > 0 ? (
              <div className="space-y-3">
                {execution.tool_calls_json.map((tc, i) => (
                  <div key={i} className="border border-gray-200 rounded-md overflow-hidden">
                    <div className="px-3 py-1.5 bg-gray-50 flex items-center justify-between">
                      <span className="text-xs font-medium text-gray-700">🔧 {tc.tool_name}</span>
                      <span className="text-xs text-gray-400">{tc.duration_ms}ms</span>
                    </div>
                    <div className="p-2">
                      <p className="text-xs text-gray-500 mb-1">Input:</p>
                      <pre className="text-xs bg-gray-50 rounded p-1.5 overflow-x-auto">
                        {JSON.stringify(tc.input_data, null, 2)}
                      </pre>
                      {tc.output_data && (
                        <>
                          <p className="text-xs text-gray-500 mt-2 mb-1">Output:</p>
                          <pre className="text-xs bg-green-50 rounded p-1.5 overflow-x-auto">
                            {JSON.stringify(tc.output_data, null, 2)}
                          </pre>
                        </>
                      )}
                      {tc.error && (
                        <p className="text-xs text-red-500 mt-1">Error: {tc.error}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-400 italic">No tool calls recorded.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
