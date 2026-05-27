'use client';

import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { useAppStore } from '@/stores/appStore';
import { useExecutionStore } from '@/stores/executionStore';
import { getAgentColor, getAgentIcon, getStatusColor } from '@/lib/utils';

interface AgentNodeData {
  agentType: string;
  config: Record<string, any>;
  status?: string;
}

function AgentNodeComponent({ id, data, selected }: NodeProps<AgentNodeData>) {
  const { agentTypes, selectNode } = useAppStore();
  const { nodeStatuses } = useExecutionStore();

  const agentType = agentTypes.find((a) => a.name === data.agentType);
  const status = nodeStatuses[id] || 'idle';
  const color = getAgentColor(agentType?.category || 'custom');
  const icon = getAgentIcon(data.agentType);
  const statusColor = getStatusColor(status);

  return (
    <div
      className={`relative rounded-lg border-2 bg-white shadow-md transition-all duration-200 min-w-[180px] ${
        selected ? 'ring-2 ring-blue-400' : ''
      } ${status === 'running' ? 'animate-pulse' : ''}`}
      style={{ borderColor: status !== 'idle' ? statusColor : color }}
      onClick={() => selectNode(id)}
    >
      {/* Status indicator */}
      {status !== 'idle' && (
        <div
          className="absolute -top-2 -right-2 w-4 h-4 rounded-full border-2 border-white"
          style={{ backgroundColor: statusColor }}
        />
      )}

      {/* Header */}
      <div
        className="px-3 py-2 rounded-t-md text-white text-xs font-semibold flex items-center gap-2"
        style={{ backgroundColor: color }}
      >
        <span className="text-sm">{icon}</span>
        <span className="truncate">{agentType?.name || data.agentType}</span>
      </div>

      {/* Body */}
      <div className="px-3 py-2 text-xs text-gray-600">
        <div className="truncate">
          {data.config?.model || agentType?.default_model || 'gpt-4o'}
        </div>
        {status !== 'idle' && (
          <div className="mt-1 font-medium" style={{ color: statusColor }}>
            {status === 'running' && '● Processing...'}
            {status === 'completed' && '✓ Done'}
            {status === 'failed' && '✗ Error'}
            {status === 'pending' && '○ Waiting'}
          </div>
        )}
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !bg-gray-400 !border-2 !border-white"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!w-3 !h-3 !border-2 !border-white"
        style={{ backgroundColor: color }}
      />
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);
