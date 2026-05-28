import { create } from 'zustand';
import type { ChunkPreviewItem, ChunkStatus, ChunkProcessingResult } from '@/types';

interface ChunkState {
  // Chunk preview data (from structural chunker)
  chunks: ChunkPreviewItem[];
  isLoading: boolean;

  // Processing state (during execution)
  chunkStatuses: Record<number, ChunkStatus>;
  activeChunkIndex: number | null;
  chunkResults: ChunkProcessingResult[];

  // Actions
  setChunks: (chunks: ChunkPreviewItem[]) => void;
  setLoading: (loading: boolean) => void;
  setChunkStatus: (index: number, status: ChunkStatus) => void;
  setActiveChunk: (index: number | null) => void;
  addChunkResult: (result: ChunkProcessingResult) => void;
  resetProcessing: () => void;
  reset: () => void;
}

export const useChunkStore = create<ChunkState>((set) => ({
  chunks: [],
  isLoading: false,
  chunkStatuses: {},
  activeChunkIndex: null,
  chunkResults: [],

  setChunks: (chunks) => set({ chunks, chunkStatuses: {}, chunkResults: [], activeChunkIndex: null }),
  setLoading: (loading) => set({ isLoading: loading }),

  setChunkStatus: (index, status) => set((state) => ({
    chunkStatuses: { ...state.chunkStatuses, [index]: status },
  })),

  setActiveChunk: (index) => set({ activeChunkIndex: index }),

  addChunkResult: (result) => set((state) => ({
    chunkResults: [...state.chunkResults, result],
    chunkStatuses: {
      ...state.chunkStatuses,
      [result.chunk_index]: result.error ? 'error' : 'completed',
    },
  })),

  resetProcessing: () => set({ chunkStatuses: {}, activeChunkIndex: null, chunkResults: [] }),

  reset: () => set({
    chunks: [],
    isLoading: false,
    chunkStatuses: {},
    activeChunkIndex: null,
    chunkResults: [],
  }),
}));
