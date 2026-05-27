'use client';

import { useCallback, useRef, useState, DragEvent } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  ReactFlowInstance,
  Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { useGraphStore } from '@/stores/graphStore';
import { useAppStore } from '@/stores/appStore';
import { AgentNode } from './AgentNode';
import { EdgeInspector } from './EdgeInspector';
import { getAgentColor } from '@/lib/utils';

const nodeTypes = { agentNode: AgentNode };

function GraphCanvasInner() {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const reactFlowInstance = useRef<ReactFlowInstance | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, addNode } = useGraphStore();
  const { agentTypes, selectNode } = useAppStore();

  const onInit = useCallback((instance: ReactFlowInstance) => {
    reactFlowInstance.current = instance;
  }, []);

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();

      const agentType = event.dataTransfer.getData('application/agentType');
      if (!agentType || !reactFlowInstance.current || !reactFlowWrapper.current) return;

      const bounds = reactFlowWrapper.current.getBoundingClientRect();
      const position = reactFlowInstance.current.project({
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
      });

      addNode(agentType, position);
    },
    [addNode]
  );

  const onPaneClick = useCallback(() => {
    selectNode(null);
    setSelectedEdgeId(null);
  }, [selectNode]);

  const onEdgeClick = useCallback((_event: React.MouseEvent, edge: Edge) => {
    setSelectedEdgeId(edge.id);
    selectNode(null);
  }, [selectNode]);

  return (
    <div ref={reactFlowWrapper} className="flex-1 h-full relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onInit={onInit}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onPaneClick={onPaneClick}
        onEdgeClick={onEdgeClick}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={{ type: 'smoothstep', animated: false }}
        fitView
        className="bg-gray-50"
        deleteKeyCode={['Backspace', 'Delete']}
      >
        <Background gap={20} size={1} color="#e5e7eb" />
        <Controls position="bottom-right" className="!shadow-md" />
        <MiniMap
          position="bottom-left"
          nodeColor={(node) => {
            const agentType = agentTypes.find((a) => a.name === node.data?.agentType);
            return getAgentColor(agentType?.category || 'custom');
          }}
          className="!shadow-md"
        />
      </ReactFlow>

      {/* Edge Inspector overlay */}
      {selectedEdgeId && (
        <EdgeInspector
          edgeId={selectedEdgeId}
          onClose={() => setSelectedEdgeId(null)}
        />
      )}
    </div>
  );
}

export function GraphCanvas() {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner />
    </ReactFlowProvider>
  );
}
