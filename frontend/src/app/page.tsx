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
import { EvalDashboard } from '@/components/eval';
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

  // Auto-load the default pipeline if canvas is empty
  useEffect(() => {
    if (!graphId) {
      graphsApi.list().then((graphs) => {
        if (graphs.length > 0) {
          // Prefer the "Knowledge Graph Pipeline" if it exists
          const defaultGraph = graphs.find((g: any) => g.name === 'Knowledge Graph Pipeline') || graphs[0];
          loadGraph(defaultGraph.nodes_json || [], defaultGraph.edges_json || []);
          setGraphMeta(defaultGraph.id, defaultGraph.name, defaultGraph.description || '');
        }
      }).catch(console.error);
    }
  }, [graphId, loadGraph, setGraphMeta]);

  // Extract KG data from execution results — merge nodes from kg_builder + edges from relationships
  const kgData: KnowledgeGraph = (() => {
    // Try shared state first
    const kg = sharedState?.knowledge_graph;
    if (kg && (kg.nodes?.length > 0) && (kg.edges?.length > 0)) {
      return kg as KnowledgeGraph;
    }

    // Collect best nodes and edges from all execution outputs
    let bestNodes: any[] = [];
    let bestEdges: any[] = [];
    let relationships: any[] = [];

    for (const [, exec] of Object.entries(nodeExecutions)) {
      const output = exec?.output_data_json;
      if (!output) continue;

      // Collect nodes from kg_builder (graph_data.nodes) or ontology_extractor (entities)
      if (output.graph_data?.nodes?.length > 0 && output.graph_data.nodes.length > bestNodes.length) {
        bestNodes = output.graph_data.nodes;
        if (output.graph_data.edges?.length > 0) {
          bestEdges = output.graph_data.edges;
        }
      }
      if (output.nodes?.length > 0 && output.nodes.length > bestNodes.length) {
        bestNodes = output.nodes;
        if (output.edges?.length > 0) bestEdges = output.edges;
      }

      // Collect relationships (from relationship_extractor or entity_resolver)
      if (output.relationships?.length > 0 && output.relationships.length > relationships.length) {
        relationships = output.relationships;
      }

      // Collect entities as fallback nodes
      if (output.entities?.length > 0 && bestNodes.length === 0) {
        bestNodes = output.entities.map((e: any) => ({
          id: (e.name || e.id || '').toLowerCase().replace(/[^a-z0-9]+/g, '_'),
          label: e.name || e.id || '',
          type: e.type || 'Entity',
          description: e.description,
        }));
      }
    }

    // If we have nodes but no edges, convert relationships to edges
    if (bestNodes.length > 0 && bestEdges.length === 0 && relationships.length > 0) {
      // Build a lookup from label (lowercased) → node id
      const labelToId: Record<string, string> = {};
      bestNodes.forEach((n: any) => {
        const id = n.id || '';
        const label = (n.label || n.id || '').toLowerCase();
        labelToId[label] = id;
        // Also map the ID itself
        labelToId[id.toLowerCase()] = id;
      });

      bestEdges = relationships.map((r: any) => {
        const srcName = (r.source || '').toLowerCase();
        const tgtName = (r.target || '').toLowerCase();
        return {
          source: labelToId[srcName] || srcName.replace(/[^a-z0-9]+/g, '_'),
          target: labelToId[tgtName] || tgtName.replace(/[^a-z0-9]+/g, '_'),
          type: r.type || 'related',
          description: r.description || '',
          confidence: r.confidence,
        };
      });
    }

    if (bestNodes.length === 0) return { nodes: [], edges: [] };

    return {
      nodes: bestNodes,
      edges: bestEdges,
      stats: { node_count: bestNodes.length, edge_count: bestEdges.length, connected_components: 0, entity_types: {}, relationship_types: {} },
    } as KnowledgeGraph;
  })();

  if (activeTab === 'experiments') {
    return (
      <div className="h-screen flex flex-col">
        <Toolbar />
        <ExperimentDashboard />
      </div>
    );
  }

  if (activeTab === 'eval') {
    return (
      <div className="h-screen flex flex-col">
        <Toolbar />
        <EvalDashboard />
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
