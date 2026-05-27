import { create } from 'zustand';
import { Node, Edge, Connection, addEdge, applyNodeChanges, applyEdgeChanges, NodeChange, EdgeChange } from 'reactflow';
import { GraphNode, GraphEdge, NodeConfig, EdgeCondition } from '@/types';

interface GraphState {
  // Graph metadata
  graphId: string | null;
  graphName: string;
  graphDescription: string;

  // React Flow state
  nodes: Node[];
  edges: Edge[];

  // Actions
  setGraphMeta: (id: string | null, name: string, description: string) => void;
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  addNode: (agentType: string, position: { x: number; y: number }, config?: NodeConfig) => void;
  removeNode: (nodeId: string) => void;
  updateNodeConfig: (nodeId: string, config: Partial<NodeConfig>) => void;
  updateEdgeMapping: (edgeId: string, mapping: Record<string, string>) => void;
  updateEdgeType: (edgeId: string, edgeType: 'default' | 'conditional' | 'loop') => void;
  updateEdgeCondition: (edgeId: string, condition: EdgeCondition | undefined) => void;
  loadGraph: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  clearGraph: () => void;
  getGraphJson: () => { nodes: GraphNode[]; edges: GraphEdge[] };
}

let nodeIdCounter = 0;
const generateNodeId = () => `node_${++nodeIdCounter}_${Date.now()}`;
const generateEdgeId = () => `edge_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

export const useGraphStore = create<GraphState>((set, get) => ({
  graphId: null,
  graphName: 'Untitled Pipeline',
  graphDescription: '',
  nodes: [],
  edges: [],

  setGraphMeta: (id, name, description) => set({ graphId: id, graphName: name, graphDescription: description }),

  onNodesChange: (changes) => set((state) => ({ nodes: applyNodeChanges(changes, state.nodes) })),

  onEdgesChange: (changes) => set((state) => ({ edges: applyEdgeChanges(changes, state.edges) })),

  onConnect: (connection) => set((state) => ({
    edges: addEdge({ ...connection, id: generateEdgeId(), type: 'smoothstep', animated: false, data: { mapping: {}, edgeType: 'default', condition: undefined } }, state.edges),
  })),

  addNode: (agentType, position, config) => {
    const id = generateNodeId();
    const newNode: Node = {
      id,
      type: 'agentNode',
      position,
      data: {
        agentType,
        config: config || {},
        status: 'idle',
      },
    };
    set((state) => ({ nodes: [...state.nodes, newNode] }));
  },

  removeNode: (nodeId) => set((state) => ({
    nodes: state.nodes.filter((n) => n.id !== nodeId),
    edges: state.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
  })),

  updateNodeConfig: (nodeId, config) => set((state) => ({
    nodes: state.nodes.map((n) =>
      n.id === nodeId ? { ...n, data: { ...n.data, config: { ...n.data.config, ...config } } } : n
    ),
  })),

  updateEdgeMapping: (edgeId, mapping) => set((state) => ({
    edges: state.edges.map((e) =>
      e.id === edgeId ? { ...e, data: { ...e.data, mapping } } : e
    ),
  })),

  updateEdgeType: (edgeId, edgeType) => set((state) => ({
    edges: state.edges.map((e) =>
      e.id === edgeId
        ? {
            ...e,
            animated: edgeType === 'loop',
            style: edgeType === 'conditional' ? { strokeDasharray: '5,5', stroke: '#f59e0b' } : edgeType === 'loop' ? { stroke: '#8b5cf6' } : undefined,
            data: { ...e.data, edgeType },
          }
        : e
    ),
  })),

  updateEdgeCondition: (edgeId, condition) => set((state) => ({
    edges: state.edges.map((e) =>
      e.id === edgeId ? { ...e, data: { ...e.data, condition } } : e
    ),
  })),

  loadGraph: (graphNodes, graphEdges) => {
    const nodes: Node[] = graphNodes.map((gn) => ({
      id: gn.id,
      type: 'agentNode',
      position: { x: gn.position_x, y: gn.position_y },
      data: { agentType: gn.agent_type, config: gn.config, status: 'idle' },
    }));
    const edges: Edge[] = graphEdges.map((ge) => ({
      id: ge.id,
      source: ge.source_node_id,
      target: ge.target_node_id,
      type: 'smoothstep',
      animated: ge.edge_type === 'loop',
      style: ge.edge_type === 'conditional' ? { strokeDasharray: '5,5', stroke: '#f59e0b' } : ge.edge_type === 'loop' ? { stroke: '#8b5cf6' } : undefined,
      data: { mapping: ge.data_mapping, edgeType: ge.edge_type || 'default', condition: ge.condition },
    }));
    set({ nodes, edges });
  },

  clearGraph: () => set({ nodes: [], edges: [], graphId: null, graphName: 'Untitled Pipeline', graphDescription: '' }),

  getGraphJson: () => {
    const { nodes, edges } = get();
    const graphNodes: GraphNode[] = nodes.map((n) => ({
      id: n.id,
      agent_type: n.data.agentType,
      position_x: n.position?.x || 0,
      position_y: n.position?.y || 0,
      config: n.data.config || {},
    }));
    const graphEdges: GraphEdge[] = edges.map((e) => ({
      id: e.id,
      source_node_id: e.source,
      target_node_id: e.target,
      data_mapping: e.data?.mapping || {},
      edge_type: e.data?.edgeType || 'default',
      condition: e.data?.condition,
    }));
    return { nodes: graphNodes, edges: graphEdges };
  },
}));
