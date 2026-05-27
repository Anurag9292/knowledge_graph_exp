'use client';

import { useEffect } from 'react';
import { useAppStore } from '@/stores/appStore';
import { useExecutionStore } from '@/stores/executionStore';
import { useGraphStore } from '@/stores/graphStore';
import { agentsApi, graphsApi } from '@/lib/api';
import { AgentPalette } from '@/components/graph-editor/AgentPalette';
import { GraphCanvas } from '@/components/graph-editor/GraphCanvas';
import { Toolbar } from '@/components/graph-editor/Toolbar';
import { NodeInspector } from '@/components/node-inspector';
import { DocumentInput } from '@/components/document-input';
import { ExperimentDashboard } from '@/components/experiment';
import { KnowledgeGraphViewer } from '@/components/kg-viewer';
import { KnowledgeGraph } from '@/types';

export default function Home() {
  const { activeTab, setAgentTypes, agentTypesLoaded, kgViewerOpen, toggleKgViewer } = useAppStore();
  const { sharedState, nodeExecutions } = useExecutionStore();
  const { graphId, loadGraph, setGraphMeta } = useGraphStore();

  // Load agent types on mount
  useEffect(() => {
    if (!agentTypesLoaded) {
      agentsApi.listTypes().then(setAgentTypes).catch(console.error);
    }
  }, [agentTypesLoaded, setAgentTypes]);

  // Auto-load the default graph if canvas is empty
  useEffect(() => {
    if (!graphId) {
      graphsApi.list().then((graphs) => {
        if (graphs.length > 0) {
          const defaultGraph = graphs[0];
          loadGraph(defaultGraph.nodes_json || [], defaultGraph.edges_json || []);
          setGraphMeta(defaultGraph.id, defaultGraph.name, defaultGraph.description || '');
        }
      }).catch(console.error);
    }
  }, [graphId, loadGraph, setGraphMeta]);

  // Extract KG data from execution results
  const kgData: KnowledgeGraph = (() => {
    // Try shared state first (from run_complete event)
    const kg = sharedState?.knowledge_graph;
    if (kg && (kg.nodes?.length > 0 || kg.edges?.length > 0)) {
      return kg as KnowledgeGraph;
    }

    // Try extracting from node executions (kg_builder output)
    for (const [, exec] of Object.entries(nodeExecutions)) {
      const output = exec?.output_data_json;
      if (!output) continue;

      // Check graph_data.nodes (kg_builder nests output here)
      if (output?.graph_data?.nodes?.length > 0) {
        return {
          nodes: output.graph_data.nodes,
          edges: output.graph_data.edges || [],
          stats: output.stats,
        } as KnowledgeGraph;
      }
      // Check direct nodes/edges
      if (output?.nodes?.length > 0) {
        return { nodes: output.nodes, edges: output.edges || [] } as KnowledgeGraph;
      }
      if (output?.knowledge_graph?.nodes?.length > 0) {
        return output.knowledge_graph as KnowledgeGraph;
      }
      // Build KG from entities + relationships
      if (output?.entities?.length > 0 && output?.relationships?.length > 0) {
        return {
          nodes: output.entities.map((e: any) => ({
            id: e.name || e.id,
            label: e.name || e.id,
            type: e.type || 'Entity',
            description: e.description,
          })),
          edges: output.relationships.map((r: any) => ({
            source: r.source,
            target: r.target,
            type: r.type || r.relationship_type || 'related',
            confidence: r.confidence,
          })),
        };
      }
    }

    return { nodes: [], edges: [] };
  })();

  if (activeTab === 'experiments') {
    return (
      <div className="h-screen flex flex-col">
        <Toolbar />
        <ExperimentDashboard />
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Top toolbar */}
      <Toolbar />

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Agent Palette */}
        <AgentPalette />

        {/* Center: Graph Canvas + KG Viewer / Document Input */}
        <div className="flex-1 flex flex-col">
          {kgViewerOpen ? (
            <div className="flex-1 flex flex-col border-b border-gray-200">
              <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200">
                <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <span>🕸️</span> Knowledge Graph
                </h3>
                <button
                  onClick={() => toggleKgViewer(false)}
                  className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded border border-gray-300"
                >
                  Close
                </button>
              </div>
              <KnowledgeGraphViewer graph={kgData} />
            </div>
          ) : (
            <>
              <GraphCanvas />
              <DocumentInput />
            </>
          )}
        </div>

        {/* Right: Node Inspector */}
        <NodeInspector />
      </div>
    </div>
  );
}
