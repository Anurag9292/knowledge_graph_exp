'use client';

import { useMemo } from 'react';
import { KnowledgeGraph, KGNode } from '@/types';

interface Props {
  graph: KnowledgeGraph;
}

export function KnowledgeGraphViewer({ graph }: Props) {
  const layout = useMemo(() => {
    // Simple force-directed-like layout
    const nodePositions: Record<string, { x: number; y: number }> = {};
    const width = 600;
    const height = 400;
    const centerX = width / 2;
    const centerY = height / 2;

    graph.nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / graph.nodes.length;
      const radius = Math.min(width, height) * 0.35;
      nodePositions[node.id] = {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      };
    });

    return { nodePositions, width, height };
  }, [graph]);

  const typeColors: Record<string, string> = {
    Person: '#3b82f6',
    Organization: '#10b981',
    Place: '#f59e0b',
    Concept: '#8b5cf6',
    Event: '#ec4899',
  };

  const getNodeColor = (node: KGNode) => typeColors[node.type] || '#6b7280';

  if (graph.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        No knowledge graph data yet. Run a pipeline with a KG Builder agent.
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col">
      {/* Stats bar */}
      {graph.stats && (
        <div className="flex gap-4 px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs text-gray-500">
          <span>Nodes: <strong>{graph.stats.node_count}</strong></span>
          <span>Edges: <strong>{graph.stats.edge_count}</strong></span>
          <span>Components: <strong>{graph.stats.connected_components}</strong></span>
        </div>
      )}

      {/* SVG Graph */}
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="flex-1 w-full"
        style={{ minHeight: 300 }}
      >
        {/* Edges */}
        {graph.edges.map((edge, i) => {
          const source = layout.nodePositions[edge.source];
          const target = layout.nodePositions[edge.target];
          if (!source || !target) return null;
          return (
            <g key={i}>
              <line
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="#d1d5db"
                strokeWidth={1.5}
                markerEnd="url(#arrowhead)"
              />
              <text
                x={(source.x + target.x) / 2}
                y={(source.y + target.y) / 2 - 5}
                fontSize={8}
                fill="#9ca3af"
                textAnchor="middle"
              >
                {edge.type}
              </text>
            </g>
          );
        })}

        {/* Nodes */}
        {graph.nodes.map((node) => {
          const pos = layout.nodePositions[node.id];
          if (!pos) return null;
          return (
            <g key={node.id}>
              <circle
                cx={pos.x}
                cy={pos.y}
                r={20}
                fill={getNodeColor(node)}
                opacity={0.9}
                className="cursor-pointer hover:opacity-100"
              />
              <text
                x={pos.x}
                y={pos.y + 30}
                fontSize={9}
                fill="#374151"
                textAnchor="middle"
                fontWeight="500"
              >
                {node.label.length > 15 ? node.label.slice(0, 15) + '...' : node.label}
              </text>
              <text
                x={pos.x}
                y={pos.y + 4}
                fontSize={8}
                fill="white"
                textAnchor="middle"
                fontWeight="600"
              >
                {node.type.slice(0, 3).toUpperCase()}
              </text>
            </g>
          );
        })}

        {/* Arrow marker */}
        <defs>
          <marker
            id="arrowhead"
            markerWidth="10"
            markerHeight="7"
            refX="10"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#d1d5db" />
          </marker>
        </defs>
      </svg>

      {/* Legend */}
      <div className="flex gap-3 px-4 py-2 border-t border-gray-200">
        {Object.entries(typeColors).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1 text-xs text-gray-500">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            {type}
          </div>
        ))}
      </div>
    </div>
  );
}
