'use client';

import { useEffect } from 'react';
import { useAppStore } from '@/stores/appStore';
import { agentsApi } from '@/lib/api';
import { AgentPalette } from '@/components/graph-editor/AgentPalette';
import { GraphCanvas } from '@/components/graph-editor/GraphCanvas';
import { Toolbar } from '@/components/graph-editor/Toolbar';
import { NodeInspector } from '@/components/node-inspector';
import { DocumentInput } from '@/components/document-input';
import { ExperimentDashboard } from '@/components/experiment';

export default function Home() {
  const { activeTab, setAgentTypes, agentTypesLoaded } = useAppStore();

  // Load agent types on mount
  useEffect(() => {
    if (!agentTypesLoaded) {
      agentsApi.listTypes().then(setAgentTypes).catch(console.error);
    }
  }, [agentTypesLoaded, setAgentTypes]);

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

        {/* Center: Graph Canvas + Document Input */}
        <div className="flex-1 flex flex-col">
          <GraphCanvas />
          <DocumentInput />
        </div>

        {/* Right: Node Inspector */}
        <NodeInspector />
      </div>
    </div>
  );
}
