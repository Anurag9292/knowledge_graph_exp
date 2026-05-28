'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Brain, Zap, Database, MessageSquare, CheckCircle } from 'lucide-react';

interface PipelineStep {
  agent: string;
  step: number;
  duration_ms: number;
  input_summary: string;
  output_summary: string;
  full_output: any;
}

const AGENT_CONFIG: Record<string, { icon: any; label: string; color: string }> = {
  query_planner: { icon: Brain, label: 'Query Planner', color: 'text-purple-600 bg-purple-50 border-purple-200' },
  cypher_generator: { icon: Zap, label: 'Cypher Generator', color: 'text-blue-600 bg-blue-50 border-blue-200' },
  cypher_executor: { icon: Database, label: 'Cypher Executor', color: 'text-green-600 bg-green-50 border-green-200' },
  answer_synthesizer: { icon: MessageSquare, label: 'Answer Synthesizer', color: 'text-orange-600 bg-orange-50 border-orange-200' },
  eval_scorer: { icon: CheckCircle, label: 'Eval Scorer', color: 'text-teal-600 bg-teal-50 border-teal-200' },
};

interface PipelineStepCardProps {
  step: PipelineStep;
}

export function PipelineStepCard({ step }: PipelineStepCardProps) {
  const [expanded, setExpanded] = useState(false);
  const config = AGENT_CONFIG[step.agent] || { icon: Brain, label: step.agent, color: 'text-gray-600 bg-gray-50 border-gray-200' };
  const Icon = config.icon;

  return (
    <div className={`border rounded-lg overflow-hidden ${config.color}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2 flex items-center justify-between hover:opacity-80 transition-opacity"
      >
        <div className="flex items-center gap-2 min-w-0">
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <Icon size={14} />
          <span className="text-xs font-semibold">Step {step.step}: {config.label}</span>
        </div>
        <span className="text-xs opacity-70">{step.duration_ms}ms</span>
      </button>

      {!expanded && (
        <div className="px-3 pb-2">
          <p className="text-xs opacity-80 truncate">{step.output_summary}</p>
        </div>
      )}

      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-current/10">
          <div className="mt-2">
            <span className="text-[10px] uppercase font-semibold opacity-60">Input</span>
            <p className="text-xs opacity-80">{step.input_summary}</p>
          </div>
          <div>
            <span className="text-[10px] uppercase font-semibold opacity-60">Output</span>
            <p className="text-xs opacity-80">{step.output_summary}</p>
          </div>
          {step.full_output && (
            <div>
              <span className="text-[10px] uppercase font-semibold opacity-60">Details</span>
              <pre className="text-[10px] opacity-70 bg-white/50 rounded p-2 overflow-x-auto max-h-40 overflow-y-auto">
                {JSON.stringify(step.full_output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
