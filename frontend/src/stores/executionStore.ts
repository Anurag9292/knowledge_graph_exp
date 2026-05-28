import { create } from 'zustand';
import { StreamEvent, NodeExecution, ExperimentRun } from '@/types';
import { executionWs } from '@/lib/websocket';
import { useChunkStore } from '@/stores/chunkStore';

type NodeStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed';

interface ExecutionState {
  // Current execution
  isRunning: boolean;
  isPaused: boolean;
  currentRunId: string | null;
  currentSessionId: string | null;

  // Node statuses (node_id -> status)
  nodeStatuses: Record<string, NodeStatus>;

  // Node execution data (node_id -> data)
  nodeExecutions: Record<string, Partial<NodeExecution>>;

  // Events log
  events: StreamEvent[];

  // Shared state (from run)
  sharedState: Record<string, any>;

  // Actions
  startExecution: (sessionId: string, runId: string) => void;
  stopExecution: () => void;
  pauseExecution: () => void;
  resumeExecution: () => void;
  stepExecution: () => void;
  handleEvent: (event: StreamEvent) => void;
  setNodeStatus: (nodeId: string, status: NodeStatus) => void;
  reset: () => void;
  loadRunResults: (run: ExperimentRun) => void;
}

export const useExecutionStore = create<ExecutionState>((set, get) => ({
  isRunning: false,
  isPaused: false,
  currentRunId: null,
  currentSessionId: null,
  nodeStatuses: {},
  nodeExecutions: {},
  events: [],
  sharedState: {},

  startExecution: (sessionId, runId) => {
    set({
      isRunning: true,
      isPaused: false,
      currentRunId: runId,
      currentSessionId: sessionId,
      nodeStatuses: {},
      nodeExecutions: {},
      events: [],
      sharedState: {},
    });

    executionWs.connect(runId);
    executionWs.on('*', (event) => get().handleEvent(event));
  },

  stopExecution: () => {
    executionWs.send('cancel');
    executionWs.disconnect();
    set({ isRunning: false, isPaused: false });
  },

  pauseExecution: () => {
    executionWs.send('pause');
    set({ isPaused: true });
  },

  resumeExecution: () => {
    executionWs.send('resume');
    set({ isPaused: false });
  },

  stepExecution: () => {
    executionWs.send('step');
  },

  handleEvent: (event) => {
    set((state) => {
      const newState: Partial<ExecutionState> = {
        events: [...state.events, event],
      };

      switch (event.event_type) {
        case 'run_start':
          // Mark all nodes as pending
          const order = event.data.execution_order || [];
          const statuses: Record<string, NodeStatus> = {};
          order.forEach((id: string) => { statuses[id] = 'pending'; });
          newState.nodeStatuses = statuses;
          break;

        case 'node_start':
          newState.nodeStatuses = { ...state.nodeStatuses, [event.node_id]: 'running' };
          newState.nodeExecutions = {
            ...state.nodeExecutions,
            [event.node_id]: {
              node_id: event.node_id,
              agent_type_name: event.data.agent_type,
              system_prompt: event.data.system_prompt,
              status: 'running',
            },
          };
          break;

        case 'node_input':
          newState.nodeExecutions = {
            ...state.nodeExecutions,
            [event.node_id]: {
              ...state.nodeExecutions[event.node_id],
              input_data_json: event.data.input,
              memory_before_json: event.data.memory_before,
            },
          };
          break;

        case 'node_complete':
          newState.nodeStatuses = { ...state.nodeStatuses, [event.node_id]: 'completed' };
          newState.nodeExecutions = {
            ...state.nodeExecutions,
            [event.node_id]: {
              ...state.nodeExecutions[event.node_id],
              status: 'completed',
              output_data_json: event.data.output,
              memory_after_json: event.data.memory_after,
              logs_json: event.data.logs,
              tool_calls_json: event.data.tool_calls,
              duration_ms: event.data.duration_ms,
              tokens_used: event.data.tokens_used,
            },
          };
          break;

        case 'node_error':
          newState.nodeStatuses = { ...state.nodeStatuses, [event.node_id]: 'failed' };
          newState.nodeExecutions = {
            ...state.nodeExecutions,
            [event.node_id]: {
              ...state.nodeExecutions[event.node_id],
              status: 'failed',
              error_message: event.data.error,
              logs_json: event.data.logs,
              duration_ms: event.data.duration_ms,
            },
          };
          break;

        case 'run_complete':
          newState.isRunning = false;
          newState.sharedState = event.data.shared_state || {};
          executionWs.disconnect();
          break;

        // ─── Chunk-level events (streaming ingestion) ───────────────
        case 'chunk_start' as any:
          useChunkStore.getState().setActiveChunk(event.data.chunk_index);
          useChunkStore.getState().setChunkStatus(event.data.chunk_index, 'processing');
          break;

        case 'chunk_complete' as any:
          useChunkStore.getState().addChunkResult(event.data as any);
          useChunkStore.getState().setActiveChunk(null);
          break;

        case 'chunk_error' as any:
          useChunkStore.getState().setChunkStatus(event.data.chunk_index, 'error');
          useChunkStore.getState().setActiveChunk(null);
          break;

        case 'run_cancelled':
          newState.isRunning = false;
          executionWs.disconnect();
          break;

        case 'execution_paused':
          newState.isPaused = true;
          break;

        case 'execution_resumed':
          newState.isPaused = false;
          break;
      }

      return newState;
    });
  },

  setNodeStatus: (nodeId, status) => set((state) => ({
    nodeStatuses: { ...state.nodeStatuses, [nodeId]: status },
  })),

  reset: () => {
    executionWs.disconnect();
    set({
      isRunning: false,
      isPaused: false,
      currentRunId: null,
      currentSessionId: null,
      nodeStatuses: {},
      nodeExecutions: {},
      events: [],
      sharedState: {},
    });
  },

  loadRunResults: (run) => {
    const statuses: Record<string, NodeStatus> = {};
    const executions: Record<string, Partial<NodeExecution>> = {};
    
    (run.node_executions || []).forEach((ne) => {
      statuses[ne.node_id] = ne.status as NodeStatus;
      executions[ne.node_id] = ne;
    });

    set({
      isRunning: false,
      currentRunId: run.id,
      currentSessionId: run.session_id,
      nodeStatuses: statuses,
      nodeExecutions: executions,
    });
  },
}));
