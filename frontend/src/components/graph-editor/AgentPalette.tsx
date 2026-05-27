'use client';

import { useState } from 'react';
import { useAppStore } from '@/stores/appStore';
import { getAgentColor, getAgentIcon } from '@/lib/utils';
import { Search, ChevronDown, ChevronRight } from 'lucide-react';

export function AgentPalette() {
  const { agentTypes } = useAppStore();
  const [search, setSearch] = useState('');
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['analysis', 'extraction', 'transformation', 'ingestion', 'custom']));

  const filteredAgents = agentTypes.filter((a) =>
    a.name.toLowerCase().includes(search.toLowerCase()) ||
    a.description.toLowerCase().includes(search.toLowerCase())
  );

  const categories = Array.from(new Set(filteredAgents.map((a) => a.category)));

  const toggleCategory = (cat: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const onDragStart = (event: React.DragEvent, agentType: string) => {
    event.dataTransfer.setData('application/agentType', agentType);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="w-60 bg-gray-50 border-r border-gray-200 flex flex-col h-full">
      {/* Header */}
      <div className="p-3 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-700 mb-2">Agent Palette</h2>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search agents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
        </div>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {categories.map((category) => (
          <div key={category}>
            <button
              onClick={() => toggleCategory(category)}
              className="flex items-center gap-1 w-full px-2 py-1 text-xs font-semibold text-gray-500 uppercase tracking-wider hover:text-gray-700"
            >
              {expandedCategories.has(category) ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
              {category}
            </button>

            {expandedCategories.has(category) && (
              <div className="space-y-1 ml-1">
                {filteredAgents
                  .filter((a) => a.category === category)
                  .map((agent) => (
                    <div
                      key={agent.name}
                      draggable
                      onDragStart={(e) => onDragStart(e, agent.name)}
                      className="flex items-center gap-2 px-2 py-2 rounded-md bg-white border border-gray-200 cursor-grab hover:border-gray-400 hover:shadow-sm transition-all text-xs"
                      title={agent.description}
                    >
                      <span
                        className="w-6 h-6 rounded flex items-center justify-center text-sm"
                        style={{ backgroundColor: `${getAgentColor(agent.category)}20` }}
                      >
                        {getAgentIcon(agent.name)}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-gray-700 truncate">{agent.name.replace(/_/g, ' ')}</div>
                        <div className="text-gray-400 truncate">{agent.description.slice(0, 40)}...</div>
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer hint */}
      <div className="p-3 border-t border-gray-200 text-xs text-gray-400 text-center">
        Drag agents onto the canvas
      </div>
    </div>
  );
}
