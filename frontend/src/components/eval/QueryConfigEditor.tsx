'use client';

import { useState, useEffect } from 'react';
import { Plus, Trash2, Save, X } from 'lucide-react';
import { useEvalStore } from '@/stores/evalStore';
import { QueryEvalConfig } from '@/types';
import { queryEvalApi } from '@/lib/api';

interface QueryRow {
  question: string;
  ground_truth: string;
}

interface QueryConfigEditorProps {
  editConfig?: QueryEvalConfig | null;
  onClose: () => void;
}

export function QueryConfigEditor({ editConfig, onClose }: QueryConfigEditorProps) {
  const { fetchConfigs } = useEvalStore();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [queries, setQueries] = useState<QueryRow[]>([{ question: '', ground_truth: '' }]);
  const [saving, setSaving] = useState(false);

  // Pre-fill when editing
  useEffect(() => {
    if (editConfig) {
      setName(editConfig.name);
      setDescription(editConfig.description || '');
      const existingQueries = (editConfig.queries_json || []).map((q: any) => ({
        question: q.question || '',
        ground_truth: q.ground_truth || '',
      }));
      setQueries(existingQueries.length > 0 ? existingQueries : [{ question: '', ground_truth: '' }]);
    }
  }, [editConfig]);

  const addQuery = () => setQueries([...queries, { question: '', ground_truth: '' }]);
  const removeQuery = (i: number) => setQueries(queries.filter((_, idx) => idx !== i));
  const updateQuery = (i: number, field: keyof QueryRow, value: string) => {
    const updated = [...queries];
    updated[i] = { ...updated[i], [field]: value };
    setQueries(updated);
  };

  const handleSave = async () => {
    if (!name.trim()) return;
    const validQueries = queries.filter(q => q.question.trim() && q.ground_truth.trim());
    if (validQueries.length === 0) return;

    setSaving(true);
    try {
      const payload = { name, description, queries: validQueries, scoring_model: 'gpt-4.1' };
      if (editConfig) {
        await queryEvalApi.updateConfig(editConfig.id, payload);
      } else {
        await queryEvalApi.createConfig(payload);
      }
      await fetchConfigs();
      onClose();
    } catch (e) {
      console.error('Save failed:', e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-800">
          {editConfig ? 'Edit Test Suite' : 'New Test Suite'}
        </h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          <X size={16} />
        </button>
      </div>

      <div className="space-y-3 mb-4">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Test suite name..."
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)..."
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="space-y-3 max-h-64 overflow-y-auto">
        {queries.map((q, i) => (
          <div key={i} className="flex gap-2 items-start p-2 bg-gray-50 rounded-md">
            <div className="flex-1 space-y-1">
              <input
                value={q.question}
                onChange={(e) => updateQuery(i, 'question', e.target.value)}
                placeholder={`Question ${i + 1}...`}
                className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <textarea
                value={q.ground_truth}
                onChange={(e) => updateQuery(i, 'ground_truth', e.target.value)}
                placeholder="Expected answer (ground truth)..."
                rows={2}
                className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
              />
            </div>
            {queries.length > 1 && (
              <button onClick={() => removeQuery(i)} className="text-red-400 hover:text-red-600 mt-1">
                <Trash2 size={14} />
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between mt-3">
        <button onClick={addQuery} className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
          <Plus size={12} /> Add query
        </button>
        <button
          onClick={handleSave}
          disabled={!name.trim() || queries.every(q => !q.question.trim()) || saving}
          className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
        >
          <Save size={12} /> {saving ? 'Saving...' : editConfig ? 'Update' : 'Save'}
        </button>
      </div>
    </div>
  );
}
