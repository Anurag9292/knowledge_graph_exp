import { create } from 'zustand';
import { AgentType } from '@/types';

interface AppState {
  // Agent types loaded from API
  agentTypes: AgentType[];
  agentTypesLoaded: boolean;

  // UI state
  selectedNodeId: string | null;
  inspectorOpen: boolean;
  activeTab: 'editor' | 'experiments' | 'agents';
  inputPanelOpen: boolean;
  kgViewerOpen: boolean;

  // Input
  inputText: string;
  inputDocumentPath: string | null;

  // Actions
  setAgentTypes: (types: AgentType[]) => void;
  selectNode: (nodeId: string | null) => void;
  toggleInspector: (open?: boolean) => void;
  setActiveTab: (tab: 'editor' | 'experiments' | 'agents') => void;
  toggleInputPanel: (open?: boolean) => void;
  toggleKgViewer: (open?: boolean) => void;
  setInputText: (text: string) => void;
  setInputDocumentPath: (path: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  agentTypes: [],
  agentTypesLoaded: false,
  selectedNodeId: null,
  inspectorOpen: false,
  activeTab: 'editor',
  inputPanelOpen: true,
  kgViewerOpen: false,
  inputText: '',
  inputDocumentPath: null,

  setAgentTypes: (types) => set({ agentTypes: types, agentTypesLoaded: true }),
  selectNode: (nodeId) => set({ selectedNodeId: nodeId, inspectorOpen: nodeId !== null }),
  toggleInspector: (open) => set((state) => ({ inspectorOpen: open ?? !state.inspectorOpen })),
  setActiveTab: (tab) => set({ activeTab: tab }),
  toggleInputPanel: (open) => set((state) => ({ inputPanelOpen: open ?? !state.inputPanelOpen })),
  toggleKgViewer: (open) => set((state) => ({ kgViewerOpen: open ?? !state.kgViewerOpen })),
  setInputText: (text) => set({ inputText: text }),
  setInputDocumentPath: (path) => set({ inputDocumentPath: path }),
}));
