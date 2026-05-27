'use client';

import { useState } from 'react';
import { X, GitBranch, RefreshCw, ArrowRight } from 'lucide-react';
import { useGraphStore } from '@/stores/graphStore';
import { EdgeCondition } from '@/types';

interface Props {
  edgeId: string;
  onClose: () => void;
}

export function EdgeInspector({ edgeId, onClose }: Props) {
  const { edges, updateEdgeType, updateEdgeCondition, updateEdgeMapping } = useGraphStore();
  const edge = edges.find((e) => e.id === edgeId);

  if (!edge) return null;

  const edgeType = edge.data?.edgeType || 'default';
  const condition: EdgeCondition | undefined = edge.data?.condition;
  const mapping: Record<string, string> = edge.data?.mapping || {};

  const [condField, setCondField] = useState(condition?.field || '');
  const [condOperator, setCondOperator] = useState(condition?.operator || 'exists');
  const [condValue, setCondValue] = useState(condition?.value ?? '');
  const [maxIterations, setMaxIterations] = useState(condition?.max_iterations || 5);
  const [mappingStr, setMappingStr] = useState(JSON.stringify(mapping, null, 2));

  const handleTypeChange = (newType: 'default' | 'conditional' | 'loop') => {
    updateEdgeType(edgeId, newType);
    if (newType === 'default') {
      updateEdgeCondition(edgeId, undefined);
    }
  };

  const handleConditionSave = () => {
    if (edgeType === 'default') return;
    const cond: EdgeCondition = {
      field: condField,
      operator: condOperator as EdgeCondition['operator'],
      value: condValue || undefined,
      max_iterations: edgeType === 'loop' ? maxIterations : undefined,
    };
    updateEdgeCondition(edgeId, cond);
  };

  const handleMappingSave = () => {
    try {
      const parsed = JSON.parse(mappingStr);
      updateEdgeMapping(edgeId, parsed);
    } catch {
      // Invalid JSON, don't save
    }
  };

  return (
    <div className="absolute top-4 right-4 z-50 w-80 bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <ArrowRight className="w-4 h-4" />
          Edge Configuration
        </h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-4 space-y-4 max-h-[400px] overflow-y-auto">
        {/* Edge Type */}
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-2">Edge Type</label>
          <div className="grid grid-cols-3 gap-2">
            <button
              onClick={() => handleTypeChange('default')}
              className={`px-2 py-1.5 text-xs rounded border flex items-center gap-1 justify-center ${
                edgeType === 'default' ? 'bg-blue-50 border-blue-300 text-blue-700' : 'border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              <ArrowRight className="w-3 h-3" /> Default
            </button>
            <button
              onClick={() => handleTypeChange('conditional')}
              className={`px-2 py-1.5 text-xs rounded border flex items-center gap-1 justify-center ${
                edgeType === 'conditional' ? 'bg-amber-50 border-amber-300 text-amber-700' : 'border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              <GitBranch className="w-3 h-3" /> Conditional
            </button>
            <button
              onClick={() => handleTypeChange('loop')}
              className={`px-2 py-1.5 text-xs rounded border flex items-center gap-1 justify-center ${
                edgeType === 'loop' ? 'bg-purple-50 border-purple-300 text-purple-700' : 'border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              <RefreshCw className="w-3 h-3" /> Loop
            </button>
          </div>
        </div>

        {/* Condition (for conditional/loop edges) */}
        {edgeType !== 'default' && (
          <div className="space-y-3 p-3 bg-gray-50 rounded-md border border-gray-200">
            <h4 className="text-xs font-semibold text-gray-600">
              {edgeType === 'conditional' ? '⚡ Condition' : '🔄 Loop Condition'}
            </h4>
            <div>
              <label className="text-xs text-gray-500">Field (dot notation)</label>
              <input
                type="text"
                value={condField}
                onChange={(e) => setCondField(e.target.value)}
                placeholder="e.g. flags.needs_review"
                className="mt-0.5 w-full text-xs border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">Operator</label>
              <select
                value={condOperator}
                onChange={(e) => setCondOperator(e.target.value as any)}
                className="mt-0.5 w-full text-xs border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                <option value="exists">exists</option>
                <option value="not_exists">not exists</option>
                <option value="equals">equals</option>
                <option value="not_equals">not equals</option>
                <option value="contains">contains</option>
                <option value="greater_than">greater than</option>
                <option value="less_than">less than</option>
              </select>
            </div>
            {!['exists', 'not_exists'].includes(condOperator) && (
              <div>
                <label className="text-xs text-gray-500">Value</label>
                <input
                  type="text"
                  value={condValue}
                  onChange={(e) => setCondValue(e.target.value)}
                  placeholder="Comparison value"
                  className="mt-0.5 w-full text-xs border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
            )}
            {edgeType === 'loop' && (
              <div>
                <label className="text-xs text-gray-500">Max Iterations</label>
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(parseInt(e.target.value) || 5)}
                  className="mt-0.5 w-full text-xs border border-gray-300 rounded p-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
            )}
            <button
              onClick={handleConditionSave}
              className="w-full text-xs bg-blue-500 text-white rounded py-1.5 hover:bg-blue-600 transition"
            >
              Save Condition
            </button>
          </div>
        )}

        {/* Data Mapping */}
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">
            Data Mapping (JSON)
          </label>
          <p className="text-xs text-gray-400 mb-1">Maps source output fields to target input fields</p>
          <textarea
            value={mappingStr}
            onChange={(e) => setMappingStr(e.target.value)}
            className="w-full h-20 text-xs font-mono border border-gray-300 rounded p-2 focus:outline-none focus:ring-1 focus:ring-blue-400"
            placeholder='{"source_field": "target_field"}'
          />
          <button
            onClick={handleMappingSave}
            className="mt-1 w-full text-xs bg-gray-100 text-gray-700 border border-gray-300 rounded py-1.5 hover:bg-gray-200 transition"
          >
            Save Mapping
          </button>
        </div>
      </div>
    </div>
  );
}
