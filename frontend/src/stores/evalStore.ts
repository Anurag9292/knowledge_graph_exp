import { create } from 'zustand';
import { QueryEvalConfig, QueryEvalRun } from '@/types';
import { queryEvalApi } from '@/lib/api';

interface EvalState {
  // Data
  configs: QueryEvalConfig[];
  runs: QueryEvalRun[];
  selectedConfig: QueryEvalConfig | null;
  selectedRun: QueryEvalRun | null;

  // UI
  loading: boolean;
  error: string | null;
  showConfigEditor: boolean;
  showRunTrigger: boolean;

  // Actions
  fetchConfigs: () => Promise<void>;
  fetchRuns: (configId?: string) => Promise<void>;
  fetchRunDetails: (runId: string) => Promise<void>;
  selectConfig: (config: QueryEvalConfig | null) => void;
  selectRun: (run: QueryEvalRun | null) => void;
  createConfig: (data: any) => Promise<void>;
  deleteConfig: (id: string) => Promise<void>;
  startEvalRun: (configId: string, ingestionRunId: string) => Promise<string>;
  setShowConfigEditor: (show: boolean) => void;
  setShowRunTrigger: (show: boolean) => void;
  clearError: () => void;
}

export const useEvalStore = create<EvalState>((set, get) => ({
  configs: [],
  runs: [],
  selectedConfig: null,
  selectedRun: null,
  loading: false,
  error: null,
  showConfigEditor: false,
  showRunTrigger: false,

  fetchConfigs: async () => {
    set({ loading: true, error: null });
    try {
      const configs = await queryEvalApi.listConfigs();
      set({ configs, loading: false });
    } catch (e: any) {
      set({ error: e.message, loading: false });
    }
  },

  fetchRuns: async (configId?: string) => {
    set({ loading: true, error: null });
    try {
      const runs = await queryEvalApi.listRuns(configId);
      set({ runs, loading: false });
    } catch (e: any) {
      set({ error: e.message, loading: false });
    }
  },

  fetchRunDetails: async (runId: string) => {
    set({ loading: true, error: null });
    try {
      const run = await queryEvalApi.getRun(runId);
      set({ selectedRun: run, loading: false });
    } catch (e: any) {
      set({ error: e.message, loading: false });
    }
  },

  selectConfig: (config) => set({ selectedConfig: config }),
  selectRun: (run) => set({ selectedRun: run }),

  createConfig: async (data) => {
    set({ loading: true, error: null });
    try {
      await queryEvalApi.createConfig(data);
      await get().fetchConfigs();
      set({ showConfigEditor: false, loading: false });
    } catch (e: any) {
      set({ error: e.message, loading: false });
    }
  },

  deleteConfig: async (id) => {
    try {
      await queryEvalApi.deleteConfig(id);
      await get().fetchConfigs();
      set({ selectedConfig: null });
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  startEvalRun: async (configId, ingestionRunId) => {
    set({ loading: true, error: null });
    try {
      const result = await queryEvalApi.createRun({ config_id: configId, ingestion_run_id: ingestionRunId });
      await get().fetchRuns();
      set({ loading: false });
      return result.id;
    } catch (e: any) {
      set({ error: e.message, loading: false });
      throw e;
    }
  },

  setShowConfigEditor: (show) => set({ showConfigEditor: show }),
  setShowRunTrigger: (show) => set({ showRunTrigger: show }),
  clearError: () => set({ error: null }),
}));
