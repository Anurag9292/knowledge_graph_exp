import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

export function formatTokens(tokens: number): string {
  if (tokens < 1000) return `${tokens}`;
  return `${(tokens / 1000).toFixed(1)}k`;
}

export function getAgentColor(category: string): string {
  const colors: Record<string, string> = {
    analysis: '#3b82f6',     // blue
    extraction: '#10b981',   // green
    transformation: '#f59e0b', // amber
    ingestion: '#8b5cf6',    // purple
    configuration: '#475569', // slate (for domain_config, schema_architect)
    custom: '#ec4899',       // pink
  };
  return colors[category] || '#6b7280'; // gray default
}

export function getAgentIcon(agentType: string): string {
  const icons: Record<string, string> = {
    structure_inferrer: '🔍',
    ontology_extractor: '🧬',
    visual_analyzer: '👁',
    kg_builder: '🕸',
    streaming_ingestion: '📜',
    entity_resolver: '🔗',
    relationship_extractor: '🔀',
    summarizer: '📝',
    domain_config: '📋',
    schema_architect: '🏗',
  };
  return icons[agentType] || '🤖';
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    pending: '#6b7280',
    running: '#3b82f6',
    completed: '#10b981',
    failed: '#ef4444',
    paused: '#f59e0b',
    cancelled: '#6b7280',
  };
  return colors[status] || '#6b7280';
}
