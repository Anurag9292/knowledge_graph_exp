'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Database, MessageSquare, CheckCircle, XCircle } from 'lucide-react';
import { QueryEvalRun, QueryResult, PipelineStep } from '@/types';
import { PipelineStepCard } from './PipelineStepCard';
import { EvalScoreCard } from './EvalScoreCard';

interface EvalResultsViewProps {
  run: QueryEvalRun;
}

export function EvalResultsView({ run }: EvalResultsViewProps) {
  const [expandedQuery, setExpandedQuery] = useState<number | null>(null);
  const results = run.query_results_json || [];

  return (
    <div className="space-y-3">
      {/* Summary header */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h4 className="text-sm font-semibold text-gray-800">Eval Results</h4>
            <p className="text-xs text-gray-500 mt-0.5">
              {run.queries_evaluated} queries evaluated | {run.queries_passed} passed | {run.total_duration_ms ? `${(run.total_duration_ms / 1000).toFixed(1)}s` : '...'}
            </p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-gray-800">{run.overall_score ? `${Math.round(run.overall_score * 100)}%` : '—'}</div>
            <div className="text-xs text-gray-500">overall score</div>
          </div>
        </div>
        {run.overall_score !== undefined && <EvalScoreCard score={run.overall_score} size="lg" />}
      </div>

      {/* Per-query results */}
      {results.map((result: QueryResult, i: number) => (
        <div key={i} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <button
            onClick={() => setExpandedQuery(expandedQuery === i ? null : i)}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-2 flex-1 min-w-0">
              {expandedQuery === i ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              {result.score >= 0.7 ? (
                <CheckCircle size={14} className="text-green-500 shrink-0" />
              ) : (
                <XCircle size={14} className="text-red-500 shrink-0" />
              )}
              <span className="text-sm text-gray-700 truncate">{result.question}</span>
            </div>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
              result.score >= 0.8 ? 'bg-green-100 text-green-700' :
              result.score >= 0.5 ? 'bg-yellow-100 text-yellow-700' :
              'bg-red-100 text-red-700'
            }`}>
              {Math.round(result.score * 100)}%
            </span>
          </button>

          {expandedQuery === i && (
            <div className="px-4 pb-4 border-t border-gray-100 space-y-3">
              {/* Schema Context (expandable) */}
              {result.schema_context && (
                <div className="mt-3">
                  <h5 className="text-xs font-semibold text-gray-600 mb-1">Schema Context</h5>
                  <div className="flex flex-wrap gap-1 mb-2">
                    <span className="px-1.5 py-0.5 text-[10px] bg-blue-100 text-blue-700 rounded">
                      {result.schema_context.node_labels.length} labels
                    </span>
                    <span className="px-1.5 py-0.5 text-[10px] bg-purple-100 text-purple-700 rounded">
                      {result.schema_context.relationship_types.length} rel types
                    </span>
                    <span className="px-1.5 py-0.5 text-[10px] bg-green-100 text-green-700 rounded">
                      {result.schema_context.entity_count} entities
                    </span>
                    <span className="px-1.5 py-0.5 text-[10px] bg-gray-100 text-gray-700 rounded">
                      {result.schema_context.constraints_count} constraints
                    </span>
                  </div>
                  <div className="bg-gray-50 rounded-md p-2 space-y-2 text-xs">
                    <div>
                      <span className="font-semibold text-blue-700">Node Labels: </span>
                      <span className="text-gray-700">
                        {result.schema_context.node_labels.join(', ')}
                      </span>
                    </div>
                    <div>
                      <span className="font-semibold text-purple-700">Relationship Types: </span>
                      <span className="text-gray-700">
                        {result.schema_context.relationship_types.join(', ')}
                      </span>
                    </div>
                    <div>
                      <span className="font-semibold text-green-700">Entities ({result.schema_context.entity_count}): </span>
                      {result.schema_context.entity_names && result.schema_context.entity_names.length > 0 ? (
                        <span className="text-gray-700">
                          {result.schema_context.entity_names.join(', ')}
                        </span>
                      ) : (
                        <span className="text-gray-400 italic">
                          Re-run eval to see entity names (run was created before this feature)
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Pipeline Trace */}
              {result.pipeline_trace && result.pipeline_trace.length > 0 && (
                <div className="mt-3">
                  <h5 className="text-xs font-semibold text-gray-600 mb-2">Pipeline Trace</h5>
                  <div className="space-y-1.5">
                    {result.pipeline_trace.map((step: PipelineStep, j: number) => (
                      <PipelineStepCard key={j} step={step} />
                    ))}
                  </div>
                </div>
              )}

              {/* Cypher queries */}
              {result.cypher_statements?.length > 0 && (
                <div className="mt-3">
                  <h5 className="text-xs font-semibold text-gray-600 flex items-center gap-1 mb-1">
                    <Database size={12} /> Cypher Queries
                  </h5>
                  {result.cypher_statements.map((cs, j) => (
                    <div key={j} className="bg-gray-900 rounded p-2 mb-1">
                      <code className="text-xs text-green-400 whitespace-pre-wrap break-all">{cs.cypher}</code>
                    </div>
                  ))}
                </div>
              )}

              {/* Generated answer */}
              <div>
                <h5 className="text-xs font-semibold text-gray-600 flex items-center gap-1 mb-1">
                  <MessageSquare size={12} /> Generated Answer
                </h5>
                <p className="text-xs text-gray-700 bg-blue-50 rounded p-2">{result.answer || 'No answer generated'}</p>
              </div>

              {/* Ground truth */}
              <div>
                <h5 className="text-xs font-semibold text-gray-600 mb-1">Ground Truth</h5>
                <p className="text-xs text-gray-700 bg-green-50 rounded p-2">{result.ground_truth}</p>
              </div>

              {/* Reasoning */}
              {result.reasoning && (
                <div>
                  <h5 className="text-xs font-semibold text-gray-600 mb-1">Reasoning</h5>
                  <p className="text-xs text-gray-600 italic">{result.reasoning}</p>
                </div>
              )}

              {/* Criteria scores */}
              {result.criteria_scores && (
                <div>
                  <h5 className="text-xs font-semibold text-gray-600 mb-1">Criteria Breakdown</h5>
                  <div className="space-y-1">
                    {Object.entries(result.criteria_scores).map(([key, val]) => (
                      <EvalScoreCard key={key} score={val.score} label={key} size="sm" />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
