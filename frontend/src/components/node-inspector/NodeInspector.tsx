'use client';

import { useState } from 'react';
import { X, Brain, ArrowRightLeft, MemoryStick, ScrollText, Wrench, Plus, Trash2, FileText } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { useExecutionStore } from '@/stores/executionStore';
import { useGraphStore } from '@/stores/graphStore';
import { getAgentIcon, formatDuration, formatTokens } from '@/lib/utils';
import { ToolDefinition } from '@/types';
import yaml from 'js-yaml';

type Tab = 'config' | 'schema' | 'input' | 'output' | 'memory' | 'logs' | 'tools';

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

  const isDomainConfig = node.data.agentType === 'domain_config';
  const isSchemaArchitect = node.data.agentType === 'schema_architect';
  const hasSchemaTab = isDomainConfig || isSchemaArchitect;

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'config', label: 'Config', icon: <Brain className="w-3.5 h-3.5" /> },
    ...(hasSchemaTab ? [{ id: 'schema' as Tab, label: isDomainConfig ? 'Schema' : 'Schema Diff', icon: <FileText className="w-3.5 h-3.5" /> }] : []),
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
          {execution.tokens_used !== undefined && execution.tokens_used > 0 && <span>🎫 {formatTokens(execution.tokens_used)} tokens</span>}
          {execution.tokens_used !== undefined && execution.tokens_used > 0 && execution.duration_ms && execution.duration_ms > 0 && (
            <span>⚡ {Math.round(execution.tokens_used / (execution.duration_ms / 1000))} tok/s</span>
          )}
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
                  value={config.model || agentType?.default_model || 'gpt-4.1-mini'}
                  onChange={(e) => updateNodeConfig(selectedNodeId, { model: e.target.value })}
                  className="mt-1 w-full text-xs border border-gray-300 rounded-md p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                >
                  <option value="gpt-4.1-mini">gpt-4.1-mini</option>
                  <option value="gpt-4o">gpt-4o</option>
                  <option value="gpt-4o-mini">gpt-4o-mini</option>
                  <option value="gpt-4.1">gpt-4.1</option>
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

        {activeTab === 'schema' && isDomainConfig && (
          <SchemaEditor nodeId={selectedNodeId} config={config} />
        )}

        {activeTab === 'schema' && isSchemaArchitect && (
          <SchemaDiffView execution={execution} />
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
          <ToolsTab
            nodeId={selectedNodeId}
            config={config}
            execution={execution}
          />
        )}
      </div>
    </div>
  );
}


// ─── Tools Tab Component ─────────────────────────────────────────────────────

function ToolsTab({ nodeId, config, execution }: { nodeId: string; config: any; execution: any }) {
  const { updateNodeConfig } = useGraphStore();
  const tools: ToolDefinition[] = config.tools || [];
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const addTool = () => {
    const newTool: ToolDefinition = {
      name: '',
      description: '',
      parameters: { type: 'object', properties: {} },
      implementation_type: 'builtin',
    };
    updateNodeConfig(nodeId, { tools: [...tools, newTool] });
    setEditingIndex(tools.length);
  };

  const removeTool = (index: number) => {
    const updated = tools.filter((_, i) => i !== index);
    updateNodeConfig(nodeId, { tools: updated });
    if (editingIndex === index) setEditingIndex(null);
  };

  const updateTool = (index: number, updates: Partial<ToolDefinition>) => {
    const updated = tools.map((t, i) => (i === index ? { ...t, ...updates } : t));
    updateNodeConfig(nodeId, { tools: updated });
  };

  return (
    <div className="space-y-4">
      {/* Tool Configuration */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-semibold text-gray-600">Configured Tools</h4>
          <button
            onClick={addTool}
            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
          >
            <Plus className="w-3 h-3" /> Add Tool
          </button>
        </div>

        {tools.length === 0 ? (
          <p className="text-xs text-gray-400 italic">No tools configured. Add tools to enable function calling.</p>
        ) : (
          <div className="space-y-2">
            {tools.map((tool, i) => (
              <div key={i} className="border border-gray-200 rounded-md overflow-hidden">
                <div
                  className="px-3 py-2 bg-gray-50 flex items-center justify-between cursor-pointer"
                  onClick={() => setEditingIndex(editingIndex === i ? null : i)}
                >
                  <span className="text-xs font-medium text-gray-700 flex items-center gap-1">
                    <Wrench className="w-3 h-3" />
                    {tool.name || '(unnamed)'}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">{tool.implementation_type}</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeTool(i); }}
                      className="text-red-400 hover:text-red-600"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                {editingIndex === i && (
                  <div className="p-3 space-y-2 border-t border-gray-200">
                    <div>
                      <label className="text-xs text-gray-500">Name</label>
                      <input
                        type="text"
                        value={tool.name}
                        onChange={(e) => updateTool(i, { name: e.target.value })}
                        placeholder="e.g. search_web"
                        className="mt-0.5 w-full text-xs border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">Description</label>
                      <input
                        type="text"
                        value={tool.description}
                        onChange={(e) => updateTool(i, { description: e.target.value })}
                        placeholder="What this tool does"
                        className="mt-0.5 w-full text-xs border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">Implementation Type</label>
                      <select
                        value={tool.implementation_type}
                        onChange={(e) => updateTool(i, { implementation_type: e.target.value as any })}
                        className="mt-0.5 w-full text-xs border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                      >
                        <option value="builtin">Built-in</option>
                        <option value="custom_python">Custom Python</option>
                        <option value="api_call">API Call</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">Parameters (JSON Schema)</label>
                      <textarea
                        value={JSON.stringify(tool.parameters, null, 2)}
                        onChange={(e) => {
                          try { updateTool(i, { parameters: JSON.parse(e.target.value) }); } catch {}
                        }}
                        className="mt-0.5 w-full h-16 text-xs font-mono border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                      />
                    </div>
                    {tool.implementation_type === 'custom_python' && (
                      <div>
                        <label className="text-xs text-gray-500">Python Code</label>
                        <textarea
                          value={tool.implementation_code || ''}
                          onChange={(e) => updateTool(i, { implementation_code: e.target.value })}
                          placeholder="def execute(**kwargs):&#10;    return result"
                          className="mt-0.5 w-full h-24 text-xs font-mono border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                        />
                      </div>
                    )}
                    {tool.implementation_type === 'api_call' && (
                      <div>
                        <label className="text-xs text-gray-500">API Endpoint</label>
                        <input
                          type="text"
                          value={tool.api_endpoint || ''}
                          onChange={(e) => updateTool(i, { api_endpoint: e.target.value })}
                          placeholder="https://api.example.com/tool"
                          className="mt-0.5 w-full text-xs border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tool Call History (from execution) */}
      {execution?.tool_calls_json && execution.tool_calls_json.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-gray-600 mb-2">Tool Call History</h4>
          <div className="space-y-2">
            {execution.tool_calls_json.map((tc: any, i: number) => (
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
        </div>
      )}
    </div>
  );
}


// ─── Schema Editor (for domain_config nodes) ────────────────────────────────

const DEFAULT_SCHEMA_YAML = `# Domain Schema Configuration
# Edit this YAML to define your domain's entity and relationship types.
# This schema guides all downstream extraction agents.

entity_types:
  Person:
    description: A human individual
    properties: [name, role, organization]
    aliases: {}
  Organization:
    description: A company, institution, or government body
    properties: [name, org_type, country]
    aliases: {}
  Country:
    description: A sovereign nation or territory
    properties: [name, iso_code, region]
    aliases: {}
  Product:
    description: A product, commodity, or service
    properties: [name, category, code]
    aliases: {}
  Concept:
    description: An abstract idea, policy, or domain concept
    properties: [name, domain]
    aliases: {}

relationship_types:
  PRODUCES:
    description: Entity produces/manufactures a product
    from_types: [Country, Organization]
    to_types: [Product]
    properties: [value, unit, year]
  EXPORTS_TO:
    description: Entity exports to another entity
    from_types: [Country]
    to_types: [Country]
    properties: [value, unit, year, product]
  PART_OF:
    description: Entity is part of another entity
    from_types: [Person, Organization, Product]
    to_types: [Organization, Country, Concept]
    properties: []
  IMPLEMENTS:
    description: Entity implements a policy/scheme
    from_types: [Country, Organization]
    to_types: [Concept]
    properties: [year, budget]
  RELATED_TO:
    description: General relationship between entities
    from_types: ["*"]
    to_types: ["*"]
    properties: []

aliases: {}
`;

function SchemaEditor({ nodeId, config }: { nodeId: string; config: any }) {
  const { updateNodeConfig } = useGraphStore();
  const [schemaYaml, setSchemaYaml] = useState(() => {
    if (config.schema) {
      try {
        return yaml.dump(config.schema, { indent: 2, lineWidth: 120 });
      } catch {
        return JSON.stringify(config.schema, null, 2);
      }
    }
    return DEFAULT_SCHEMA_YAML;
  });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    try {
      const parsed = yaml.load(schemaYaml) as any;
      if (!parsed || typeof parsed !== 'object') {
        setError('Invalid YAML: must be an object');
        return;
      }
      updateNodeConfig(nodeId, { schema: parsed });
      setError(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(`YAML Error: ${e.message}`);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-gray-600">Domain Schema (YAML)</label>
        <div className="flex items-center gap-2">
          {saved && <span className="text-xs text-green-600">✓ Saved</span>}
          <button
            onClick={handleSave}
            className="px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 transition"
          >
            Save Schema
          </button>
        </div>
      </div>
      <p className="text-xs text-gray-400">
        Define entity types, relationship types, and aliases for your domain.
        This schema guides all downstream extraction agents.
      </p>
      <textarea
        value={schemaYaml}
        onChange={(e) => { setSchemaYaml(e.target.value); setError(null); }}
        className="w-full h-[400px] text-xs font-mono border border-gray-300 rounded-md p-3 focus:outline-none focus:ring-1 focus:ring-blue-400 resize-y bg-gray-50"
        spellCheck={false}
      />
      {error && (
        <div className="p-2 bg-red-50 border border-red-200 rounded text-xs text-red-600">
          {error}
        </div>
      )}
    </div>
  );
}


// ─── Schema Diff View (for schema_architect nodes) ──────────────────────────

function SchemaDiffView({ execution }: { execution: any }) {
  if (!execution?.output_data_json) {
    return (
      <p className="text-xs text-gray-400 italic">
        Run the pipeline to see schema analysis results.
      </p>
    );
  }

  const output = execution.output_data_json;
  const extensions = output.extensions || {};
  const newEntityTypes = extensions.new_entity_types || [];
  const newRelTypes = extensions.new_relationship_types || [];
  const newAliases = extensions.new_aliases || {};
  const observations = extensions.observations || '';
  const schemaBefore = output.schema_before || {};
  const schemaAfter = output.schema_after || {};

  const baseEntityCount = Object.keys(schemaBefore.entity_types || {}).length;
  const baseRelCount = Object.keys(schemaBefore.relationship_types || {}).length;

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="p-3 bg-gray-50 rounded-md border border-gray-200">
        <h4 className="text-xs font-semibold text-gray-700 mb-2">Schema Analysis Summary</h4>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="p-2 bg-white rounded border border-gray-100">
            <span className="text-gray-500">Base Schema</span>
            <p className="font-medium text-gray-700">{baseEntityCount} entity types, {baseRelCount} rel types</p>
          </div>
          <div className="p-2 bg-white rounded border border-gray-100">
            <span className="text-gray-500">Extensions Found</span>
            <p className="font-medium text-green-700">+{newEntityTypes.length} entities, +{newRelTypes.length} rels</p>
          </div>
        </div>
      </div>

      {/* New Entity Types */}
      {newEntityTypes.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-green-700 mb-1 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            New Entity Types ({newEntityTypes.length})
          </h4>
          <div className="space-y-1">
            {newEntityTypes.map((et: any, i: number) => (
              <div key={i} className="p-2 bg-green-50 border border-green-100 rounded text-xs">
                <span className="font-semibold text-green-800">{et.name}</span>
                <span className="text-green-600 ml-2">{et.description}</span>
                {et.properties?.length > 0 && (
                  <p className="text-green-500 mt-0.5">Properties: {et.properties.join(', ')}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* New Relationship Types */}
      {newRelTypes.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-green-700 mb-1 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            New Relationship Types ({newRelTypes.length})
          </h4>
          <div className="space-y-1">
            {newRelTypes.map((rt: any, i: number) => (
              <div key={i} className="p-2 bg-green-50 border border-green-100 rounded text-xs">
                <span className="font-semibold text-green-800">{rt.name}</span>
                <span className="text-green-600 ml-2">{rt.description}</span>
                {rt.from_types && rt.to_types && (
                  <p className="text-green-500 mt-0.5">
                    {rt.from_types.join('|')} → {rt.to_types.join('|')}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* New Aliases */}
      {Object.keys(newAliases).length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-blue-700 mb-1">New Aliases</h4>
          <div className="p-2 bg-blue-50 border border-blue-100 rounded text-xs space-y-0.5">
            {Object.entries(newAliases).map(([alias, canonical]) => (
              <div key={alias} className="text-blue-700">
                "{alias}" → <span className="font-medium">{canonical as string}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Observations */}
      {observations && (
        <div>
          <h4 className="text-xs font-semibold text-gray-600 mb-1">Observations</h4>
          <p className="text-xs text-gray-600 bg-gray-50 p-2 rounded border border-gray-100 italic">
            {observations}
          </p>
        </div>
      )}

      {/* No extensions found */}
      {newEntityTypes.length === 0 && newRelTypes.length === 0 && Object.keys(newAliases).length === 0 && (
        <div className="p-3 bg-gray-50 rounded text-xs text-gray-500 text-center">
          No schema extensions needed — the base schema covers this document well.
        </div>
      )}

      {/* Full schema after (collapsible) */}
      <details className="text-xs">
        <summary className="text-gray-500 cursor-pointer hover:text-gray-700 font-medium">
          View merged schema (YAML)
        </summary>
        <pre className="mt-2 p-2 bg-gray-50 border border-gray-200 rounded overflow-x-auto text-xs max-h-[300px] overflow-y-auto">
          {(() => { try { return yaml.dump(schemaAfter, { indent: 2 }); } catch { return JSON.stringify(schemaAfter, null, 2); } })()}
        </pre>
      </details>
    </div>
  );
}
