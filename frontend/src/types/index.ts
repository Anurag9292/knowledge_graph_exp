// Agent types
export interface AgentType {
  id: string;
  name: string;
  description: string;
  category: string;
  default_system_prompt: string;
  default_model: string;
  default_temperature: number;
  default_max_tokens: number;
  vision_enabled: boolean;
  input_schema_json: SchemaField[];
  output_schema_json: SchemaField[];
  tools_json: ToolDefinition[];
  memory_config_json: MemoryConfig;
  is_builtin: boolean;
}

export interface SchemaField {
  field_name: string;
  type: string;
  description: string;
  required?: boolean;
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, any>;
  implementation_type: 'builtin' | 'custom_python' | 'api_call';
  implementation_code?: string;
  api_endpoint?: string;
}

export interface MemoryConfig {
  type: 'scratchpad' | 'key_value' | 'accumulator' | 'conversational';
  initial_state: Record<string, any>;
  max_tokens: number;
  overflow_strategy: 'truncate_oldest' | 'summarize' | 'sliding_window' | 'relevance_filter';
  persistence: 'run_only' | 'session' | 'global';
  sharing: 'private' | 'read_shared' | 'write_shared' | 'full_access';
  injection_mode: 'full' | 'summary' | 'keys_only' | 'none';
}

// Graph types
export interface GraphDefinition {
  id: string;
  name: string;
  description?: string;
  nodes_json: GraphNode[];
  edges_json: GraphEdge[];
  created_at: string;
  updated_at?: string;
}

export interface GraphNode {
  id: string;
  agent_type: string;
  position_x: number;
  position_y: number;
  config: NodeConfig;
}

export interface NodeConfig {
  system_prompt?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  memory_config?: Partial<MemoryConfig>;
  tools?: ToolDefinition[];
}

export interface GraphEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  data_mapping: Record<string, string>;
}

// Experiment types
export interface ExperimentSession {
  id: string;
  name: string;
  description?: string;
  graph_id: string;
  input_text?: string;
  input_document_path?: string;
  experiment_memory_json?: Record<string, any>;
  created_at: string;
  updated_at?: string;
  run_count: number;
}

export interface ExperimentRun {
  id: string;
  session_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'cancelled';
  graph_snapshot_json?: Record<string, any>;
  total_tokens_used: number;
  total_duration_ms?: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  created_at: string;
  node_executions?: NodeExecution[];
}

export interface NodeExecution {
  id: string;
  run_id: string;
  node_id: string;
  agent_type_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  iteration: number;
  system_prompt?: string;
  input_data_json?: Record<string, any>;
  output_data_json?: Record<string, any>;
  memory_before_json?: Record<string, any>;
  memory_after_json?: Record<string, any>;
  logs_json?: LogEntry[];
  tool_calls_json?: ToolCallRecord[];
  tokens_used: number;
  duration_ms?: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

export interface LogEntry {
  timestamp: number;
  level: string;
  message: string;
}

export interface ToolCallRecord {
  id: string;
  tool_name: string;
  input_data: Record<string, any>;
  output_data: any;
  timestamp: number;
  duration_ms: number;
  error?: string;
}

// WebSocket event types
export interface StreamEvent {
  event_type: 'connected' | 'run_start' | 'node_start' | 'node_input' | 'node_stream' | 'node_complete' | 'node_error' | 'run_complete' | 'run_cancelled' | 'execution_paused' | 'execution_resumed';
  node_id: string;
  data: Record<string, any>;
  timestamp: number;
}

// Knowledge Graph types
export interface KGNode {
  id: string;
  label: string;
  type: string;
  description?: string;
  properties?: Record<string, any>;
}

export interface KGEdge {
  source: string;
  target: string;
  type: string;
  description?: string;
  confidence?: number;
}

export interface KnowledgeGraph {
  nodes: KGNode[];
  edges: KGEdge[];
  stats?: {
    node_count: number;
    edge_count: number;
    connected_components: number;
    entity_types: Record<string, number>;
    relationship_types: Record<string, number>;
  };
}
