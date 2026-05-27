'use client';

import { useEffect } from 'react';
import { useAppStore } from '@/stores/appStore';
import { useExecutionStore } from '@/stores/executionStore';
import { agentsApi } from '@/lib/api';
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

  // Load agent types on mount
  useEffect(() => {
    if (!agentTypesLoaded) {
      agentsApi.listTypes().then(setAgentTypes).catch(console.error);
    }
  }, [agentTypesLoaded, setAgentTypes]);

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
      if (output?.knowledge_graph) {
        return output.knowledge_graph as KnowledgeGraph;
      }
      // Also check for entities + relationships that can form a KG
      if (output?.entities && output?.relationships) {
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
