'use client';

import { useState, useEffect, useMemo } from 'react';
import { Layers, Zap, Clock, AlertCircle, ChevronRight, FileText, Table2, Code2, List, Hash } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { useChunkStore } from '@/stores/chunkStore';
import { documentsApi } from '@/lib/api';
import type { ChunkPreviewItem, ChunkStatus } from '@/types';

// ─── Chunk Type Colors & Icons ───────────────────────────────────────────────

const CHUNK_TYPE_CONFIG: Record<string, { color: string; bg: string; border: string; icon: typeof FileText }> = {
  section: { color: 'text-blue-700', bg: 'bg-blue-50', border: 'border-blue-200', icon: Hash },
  table: { color: 'text-orange-700', bg: 'bg-orange-50', border: 'border-orange-200', icon: Table2 },
  code_block: { color: 'text-purple-700', bg: 'bg-purple-50', border: 'border-purple-200', icon: Code2 },
  list_block: { color: 'text-green-700', bg: 'bg-green-50', border: 'border-green-200', icon: List },
  paragraph_group: { color: 'text-gray-700', bg: 'bg-gray-50', border: 'border-gray-200', icon: FileText },
};

const STATUS_COLORS: Record<ChunkStatus, string> = {
  pending: 'bg-gray-200',
  processing: 'bg-blue-400 animate-pulse',
  completed: 'bg-green-400',
  error: 'bg-red-400',
};

// ─── Main Component ──────────────────────────────────────────────────────────

export function ChunkViewer() {
  const { inputText } = useAppStore();
  const { chunks, chunkStatuses, activeChunkIndex, setChunks, setActiveChunk, isLoading, setLoading } = useChunkStore();
  const [selectedChunk, setSelectedChunk] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Auto-fetch chunk preview when input text changes
  useEffect(() => {
    if (!inputText || inputText.length < 100) {
      setChunks([]);
      return;
    }

    const debounceTimer = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await documentsApi.chunkPreview(inputText);
        setChunks(response.chunks);
      } catch (err: any) {
        setError(err.message || 'Failed to preview chunks');
        setChunks([]);
      } finally {
        setLoading(false);
      }
    }, 800); // Debounce: wait 800ms after typing stops

    return () => clearTimeout(debounceTimer);
  }, [inputText, setChunks, setLoading]);

  // Summary stats
  const stats = useMemo(() => {
    if (!chunks.length) return null;
    const types = chunks.reduce((acc, c) => {
      acc[c.chunk_type] = (acc[c.chunk_type] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);
    const avgComplexity = chunks.reduce((sum, c) => sum + c.complexity_score, 0) / chunks.length;
    const escalatedCount = chunks.filter(c => c.model_selected !== c.model_selected).length;
    const complexChunks = chunks.filter(c => c.complexity_score >= 5).length;
    return { types, avgComplexity, complexChunks, total: chunks.length };
  }, [chunks]);

  if (!inputText || inputText.length < 100) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400 text-xs">
        <div className="text-center">
          <Layers className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>Paste text (100+ chars) to see chunk boundaries</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500 text-xs">
        <div className="text-center">
          <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
          <p>Analyzing document structure...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center text-red-500 text-xs">
        <div className="text-center">
          <AlertCircle className="w-6 h-6 mx-auto mb-2" />
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header with stats */}
      {stats && (
        <div className="flex-shrink-0 px-3 py-2 border-b border-gray-200 bg-gray-50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-medium text-gray-700">
              <Layers className="w-3.5 h-3.5" />
              <span>{stats.total} chunks</span>
              {stats.complexChunks > 0 && (
                <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded text-[10px]">
                  {stats.complexChunks} complex
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              {Object.entries(stats.types).map(([type, count]) => {
                const config = CHUNK_TYPE_CONFIG[type] || CHUNK_TYPE_CONFIG.paragraph_group;
                return (
                  <span key={type} className={`px-1.5 py-0.5 rounded text-[10px] ${config.bg} ${config.color}`}>
                    {count} {type.replace('_', ' ')}
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Chunk Timeline Bar */}
      {chunks.length > 0 && (
        <div className="flex-shrink-0 px-3 py-2 border-b border-gray-100">
          <div className="flex gap-0.5 h-6 rounded overflow-hidden">
            {chunks.map((chunk) => {
              const config = CHUNK_TYPE_CONFIG[chunk.chunk_type] || CHUNK_TYPE_CONFIG.paragraph_group;
              const widthPercent = (chunk.char_count / inputText.length) * 100;
              const status = chunkStatuses[chunk.index] || 'pending';
              const isSelected = selectedChunk === chunk.index;
              const isActive = activeChunkIndex === chunk.index;

              return (
                <div
                  key={chunk.index}
                  className={`relative cursor-pointer transition-all rounded-sm ${config.bg} ${
                    isSelected ? `ring-2 ring-blue-500 ${config.border}` : `border ${config.border}`
                  } ${isActive ? 'ring-2 ring-amber-400' : ''}`}
                  style={{ width: `${Math.max(widthPercent, 2)}%` }}
                  onClick={() => setSelectedChunk(isSelected ? null : chunk.index)}
                  title={`Chunk ${chunk.index + 1}: ${chunk.chunk_type} (${chunk.char_count} chars)`}
                >
                  {/* Status indicator dot */}
                  {status !== 'pending' && (
                    <div className={`absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full ${STATUS_COLORS[status]}`} />
                  )}
                </div>
              );
            })}
          </div>
          <div className="flex justify-between mt-1 text-[9px] text-gray-400">
            <span>0</span>
            <span>{inputText.length.toLocaleString()} chars</span>
          </div>
        </div>
      )}

      {/* Chunk List */}
      <div className="flex-1 overflow-y-auto">
        {chunks.map((chunk) => (
          <ChunkListItem
            key={chunk.index}
            chunk={chunk}
            status={chunkStatuses[chunk.index] || 'pending'}
            isSelected={selectedChunk === chunk.index}
            isActive={activeChunkIndex === chunk.index}
            onSelect={() => setSelectedChunk(selectedChunk === chunk.index ? null : chunk.index)}
          />
        ))}
      </div>

      {/* Selected chunk detail */}
      {selectedChunk !== null && chunks[selectedChunk] && (
        <ChunkDetail chunk={chunks[selectedChunk]} />
      )}
    </div>
  );
}

// ─── Chunk List Item ─────────────────────────────────────────────────────────

function ChunkListItem({
  chunk,
  status,
  isSelected,
  isActive,
  onSelect,
}: {
  chunk: ChunkPreviewItem;
  status: ChunkStatus;
  isSelected: boolean;
  isActive: boolean;
  onSelect: () => void;
}) {
  const config = CHUNK_TYPE_CONFIG[chunk.chunk_type] || CHUNK_TYPE_CONFIG.paragraph_group;
  const Icon = config.icon;

  return (
    <div
      className={`px-3 py-2 border-b border-gray-100 cursor-pointer transition-colors hover:bg-gray-50 ${
        isSelected ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''
      } ${isActive ? 'bg-amber-50' : ''}`}
      onClick={onSelect}
    >
      <div className="flex items-center gap-2">
        {/* Index badge */}
        <span className={`flex-shrink-0 w-5 h-5 rounded flex items-center justify-center text-[10px] font-mono ${STATUS_COLORS[status]} text-white`}>
          {chunk.index + 1}
        </span>

        {/* Type icon */}
        <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${config.color}`} />

        {/* Section path */}
        <div className="flex-1 min-w-0">
          {chunk.section_path.length > 0 ? (
            <div className="flex items-center gap-1 text-xs text-gray-600 truncate">
              {chunk.section_path.map((part, i) => (
                <span key={i} className="flex items-center gap-0.5">
                  {i > 0 && <ChevronRight className="w-2.5 h-2.5 text-gray-300" />}
                  <span className="truncate">{part}</span>
                </span>
              ))}
            </div>
          ) : (
            <span className="text-xs text-gray-400 italic">
              {chunk.text.slice(0, 50).replace(/\n/g, ' ')}...
            </span>
          )}
        </div>

        {/* Complexity badge */}
        <span className={`flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] font-mono ${
          chunk.complexity_score >= 5 ? 'bg-red-100 text-red-700' :
          chunk.complexity_score >= 3 ? 'bg-amber-100 text-amber-700' :
          'bg-gray-100 text-gray-500'
        }`}>
          {chunk.complexity_score.toFixed(1)}
        </span>

        {/* Model badge */}
        <span className={`flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] ${
          chunk.model_selected.includes('4.1-mini') ? 'bg-gray-100 text-gray-600' : 'bg-purple-100 text-purple-700'
        }`}>
          {chunk.model_selected.replace('gpt-', '')}
        </span>
      </div>
    </div>
  );
}

// ─── Chunk Detail Panel ──────────────────────────────────────────────────────

function ChunkDetail({ chunk }: { chunk: ChunkPreviewItem }) {
  const config = CHUNK_TYPE_CONFIG[chunk.chunk_type] || CHUNK_TYPE_CONFIG.paragraph_group;

  return (
    <div className={`flex-shrink-0 border-t ${config.border} ${config.bg} max-h-48 overflow-y-auto`}>
      <div className="px-3 py-2">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <span className={`text-xs font-medium ${config.color}`}>
            Chunk {chunk.index + 1} &middot; {chunk.chunk_type.replace('_', ' ')}
          </span>
          <div className="flex items-center gap-2 text-[10px] text-gray-500">
            <span>{chunk.char_count.toLocaleString()} chars</span>
            <span>offset {chunk.char_offset_start}-{chunk.char_offset_end}</span>
          </div>
        </div>

        {/* Metadata tags */}
        <div className="flex flex-wrap gap-1 mb-2">
          {chunk.metadata.has_table && <span className="px-1.5 py-0.5 bg-orange-100 text-orange-700 rounded text-[10px]">table</span>}
          {chunk.metadata.has_code && <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-[10px]">code</span>}
          {chunk.metadata.has_list && <span className="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-[10px]">list</span>}
          {chunk.metadata.has_heading && <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-[10px]">heading</span>}
          <span className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px]">
            {chunk.metadata.block_count} blocks
          </span>
        </div>

        {/* Text preview */}
        <pre className="text-[11px] text-gray-700 font-mono whitespace-pre-wrap max-h-20 overflow-y-auto bg-white rounded p-2 border border-gray-200">
          {chunk.text.slice(0, 500)}{chunk.text.length > 500 ? '\n...' : ''}
        </pre>
      </div>
    </div>
  );
}
