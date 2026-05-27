'use client';

import { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  SimulationNodeDatum,
  SimulationLinkDatum,
} from 'd3-force';
import { select } from 'd3-selection';
import { zoom, zoomIdentity, ZoomBehavior, ZoomTransform } from 'd3-zoom';
import { drag } from 'd3-drag';
import { KnowledgeGraph, KGNode, KGEdge } from '@/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  graph: KnowledgeGraph;
  onNodeSelect?: (nodeId: string) => void;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  label: string;
  type: string;
  description?: string;
  properties?: Record<string, any>;
  radius: number;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  type: string;
  description?: string;
  confidence?: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TYPE_COLORS: Record<string, string> = {
  organization: '#4A6FA5',
  org: '#4A6FA5',
  product: '#5BA4A4',
  pro: '#5BA4A4',
  goal: '#D4A853',
  goa: '#D4A853',
  activity: '#6BA368',
  act: '#6BA368',
  sector: '#7B6BA3',
  sec: '#7B6BA3',
  concept: '#6B7B8A',
  con: '#6B7B8A',
};

const DEFAULT_COLOR = '#8B95A0';
const EDGE_COLOR = '#CBD5E1';
const EDGE_HIGHLIGHT_COLOR = '#475569';
const MIN_RADIUS = 20;
const MAX_RADIUS = 40;

function getNodeColor(type: string): string {
  const key = type.toLowerCase();
  return TYPE_COLORS[key] || TYPE_COLORS[key.slice(0, 3)] || DEFAULT_COLOR;
}

function getAbbreviation(type: string): string {
  return (type || '?').slice(0, 3).toUpperCase();
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function KnowledgeGraphViewer({ graph, onNodeSelect }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const simulationRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null);
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const transformRef = useRef<ZoomTransform>(zoomIdentity);

  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilters, setTypeFilters] = useState<Record<string, boolean>>({});
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    node: SimNode;
  } | null>(null);

  // Compute unique types
  const nodeTypes = useMemo(() => {
    const types = new Set<string>();
    graph.nodes.forEach((n) => types.add(n.type));
    return Array.from(types).sort();
  }, [graph.nodes]);

  // Initialize type filters
  useEffect(() => {
    const filters: Record<string, boolean> = {};
    nodeTypes.forEach((t) => {
      filters[t] = typeFilters[t] !== undefined ? typeFilters[t] : true;
    });
    setTypeFilters(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeTypes]);

  // Degree map for sizing
  const degreeMap = useMemo(() => {
    const map: Record<string, number> = {};
    graph.nodes.forEach((n) => (map[n.id] = 0));
    graph.edges.forEach((e) => {
      map[e.source] = (map[e.source] || 0) + 1;
      map[e.target] = (map[e.target] || 0) + 1;
    });
    return map;
  }, [graph]);

  const maxDegree = useMemo(
    () => Math.max(1, ...Object.values(degreeMap)),
    [degreeMap]
  );

  // Filtered nodes & edges
  const filteredNodes = useMemo(() => {
    return graph.nodes.filter((n) => typeFilters[n.type] !== false);
  }, [graph.nodes, typeFilters]);

  const filteredNodeIds = useMemo(
    () => new Set(filteredNodes.map((n) => n.id)),
    [filteredNodes]
  );

  const filteredEdges = useMemo(() => {
    return graph.edges.filter(
      (e) => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target)
    );
  }, [graph.edges, filteredNodeIds]);

  // Search matches
  const searchMatches = useMemo(() => {
    if (!searchQuery.trim()) return new Set<string>();
    const q = searchQuery.toLowerCase();
    return new Set(
      filteredNodes
        .filter(
          (n) =>
            n.label.toLowerCase().includes(q) ||
            n.type.toLowerCase().includes(q) ||
            (n.description || '').toLowerCase().includes(q)
        )
        .map((n) => n.id)
    );
  }, [searchQuery, filteredNodes]);

  // Connected nodes for hover highlight
  const connectedNodes = useMemo(() => {
    if (!hoveredNode) return new Set<string>();
    const connected = new Set<string>([hoveredNode]);
    filteredEdges.forEach((e) => {
      if (e.source === hoveredNode) connected.add(e.target);
      if (e.target === hoveredNode) connected.add(e.source);
    });
    return connected;
  }, [hoveredNode, filteredEdges]);

  // Sidebar data
  const selectedNodeData = useMemo(
    () => graph.nodes.find((n) => n.id === selectedNode) || null,
    [graph.nodes, selectedNode]
  );

  const outgoingEdges = useMemo(
    () => graph.edges.filter((e) => e.source === selectedNode),
    [graph.edges, selectedNode]
  );

  const incomingEdges = useMemo(
    () => graph.edges.filter((e) => e.target === selectedNode),
    [graph.edges, selectedNode]
  );

  // ResizeObserver
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setDimensions({ width, height });
        }
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // D3 Simulation
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || filteredNodes.length === 0) return;

    const { width, height } = dimensions;

    // Build sim nodes
    const simNodes: SimNode[] = filteredNodes.map((n) => {
      const degree = degreeMap[n.id] || 0;
      const radius =
        MIN_RADIUS + (degree / maxDegree) * (MAX_RADIUS - MIN_RADIUS);
      return {
        id: n.id,
        label: n.label,
        type: n.type,
        description: n.description,
        properties: n.properties,
        radius,
      };
    });

    const nodeMap = new Map(simNodes.map((n) => [n.id, n]));

    // Build sim links
    const simLinks: SimLink[] = filteredEdges
      .map((e) => ({
        source: nodeMap.get(e.source)!,
        target: nodeMap.get(e.target)!,
        type: e.type,
        description: e.description,
        confidence: e.confidence,
      }))
      .filter((l) => l.source && l.target);

    // If no edges, cluster by type
    const hasEdges = simLinks.length > 0;
    if (!hasEdges) {
      const typeGroups: Record<string, SimNode[]> = {};
      simNodes.forEach((n) => {
        if (!typeGroups[n.type]) typeGroups[n.type] = [];
        typeGroups[n.type].push(n);
      });
      const types = Object.keys(typeGroups);
      const colWidth = width / (types.length + 1);
      types.forEach((type, colIdx) => {
        const nodes = typeGroups[type];
        const rowHeight = height / (nodes.length + 1);
        nodes.forEach((n, rowIdx) => {
          n.x = colWidth * (colIdx + 1);
          n.y = rowHeight * (rowIdx + 1);
          n.fx = n.x;
          n.fy = n.y;
        });
      });
    }

    // Create simulation
    const simulation = forceSimulation<SimNode>(simNodes)
      .force('center', forceCenter(width / 2, height / 2))
      .force(
        'charge',
        forceManyBody<SimNode>().strength(-300).distanceMax(400)
      )
      .force(
        'link',
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(120)
          .strength(0.7)
      )
      .force(
        'collide',
        forceCollide<SimNode>().radius((d) => d.radius + 8)
      )
      .alphaDecay(0.02);

    simulationRef.current = simulation;

    // D3 selections
    const svgSel = select(svg);
    svgSel.selectAll('*').remove();

    // Defs
    const defs = svgSel.append('defs');
    defs
      .append('marker')
      .attr('id', 'kg-arrowhead')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 10)
      .attr('refY', 0)
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-4L10,0L0,4')
      .attr('fill', EDGE_COLOR);

    defs
      .append('marker')
      .attr('id', 'kg-arrowhead-highlight')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 10)
      .attr('refY', 0)
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-4L10,0L0,4')
      .attr('fill', EDGE_HIGHLIGHT_COLOR);

    // Graph container (zoomable)
    const g = svgSel.append('g').attr('class', 'kg-graph-container');

    // Edges
    const linkGroup = g.append('g').attr('class', 'kg-links');
    const links = linkGroup
      .selectAll('path')
      .data(simLinks)
      .join('path')
      .attr('fill', 'none')
      .attr('stroke', EDGE_COLOR)
      .attr('stroke-width', 1.5)
      .attr('marker-end', 'url(#kg-arrowhead)');

    // Node groups
    const nodeGroup = g.append('g').attr('class', 'kg-nodes');
    const nodeGs = nodeGroup
      .selectAll('g')
      .data(simNodes)
      .join('g')
      .attr('cursor', 'pointer');

    // Node circles
    nodeGs
      .append('circle')
      .attr('r', (d) => d.radius)
      .attr('fill', (d) => getNodeColor(d.type))
      .attr('stroke', '#fff')
      .attr('stroke-width', 2);

    // Type abbreviation inside node
    nodeGs
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('font-size', '10px')
      .attr('font-weight', '600')
      .attr('fill', '#fff')
      .attr('pointer-events', 'none')
      .text((d) => getAbbreviation(d.type));

    // Label below node
    nodeGs
      .append('rect')
      .attr('class', 'kg-label-bg')
      .attr('rx', 4)
      .attr('ry', 4)
      .attr('fill', 'rgba(255,255,255,0.85)')
      .attr('stroke', 'rgba(0,0,0,0.06)')
      .attr('stroke-width', 0.5);

    nodeGs
      .append('text')
      .attr('class', 'kg-label')
      .attr('text-anchor', 'middle')
      .attr('dy', (d) => d.radius + 16)
      .attr('font-size', '10px')
      .attr('font-weight', '500')
      .attr('fill', '#374151')
      .attr('pointer-events', 'none')
      .text((d) => {
        const lbl = d.label || d.id || '';
        return lbl.length > 18 ? lbl.slice(0, 18) + '…' : lbl;
      });

    // Measure label bounding boxes and set bg rects
    nodeGs.each(function (d) {
      const group = select(this);
      const labelEl = group.select<SVGTextElement>('.kg-label').node();
      const bgEl = group.select<SVGRectElement>('.kg-label-bg');
      if (labelEl) {
        const bbox = labelEl.getBBox();
        bgEl
          .attr('x', bbox.x - 4)
          .attr('y', bbox.y - 2)
          .attr('width', bbox.width + 8)
          .attr('height', bbox.height + 4);
      }
    });

    // Interactions on nodes
    nodeGs
      .on('mouseenter', (event, d) => {
        setHoveredNode(d.id);
        const rect = svg.getBoundingClientRect();
        setTooltip({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top - 10,
          node: d,
        });
      })
      .on('mouseleave', () => {
        setHoveredNode(null);
        setTooltip(null);
      })
      .on('click', (_, d) => {
        setSelectedNode(d.id);
        setSidebarOpen(true);
        onNodeSelect?.(d.id);
      });

    // Drag behavior
    const dragBehavior = drag<SVGGElement, SimNode>()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });

    (nodeGs as unknown as ReturnType<typeof select<SVGGElement, SimNode>>).call(dragBehavior);

    // Zoom behavior
    const zoomBehavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 5])
      .on('zoom', (event) => {
        g.attr('transform', event.transform.toString());
        transformRef.current = event.transform;
      });

    svgSel.call(zoomBehavior);
    zoomRef.current = zoomBehavior;

    // Edge path helper (quadratic bezier)
    function linkPath(l: SimLink) {
      const s = l.source as SimNode;
      const t = l.target as SimNode;
      if (!s.x || !s.y || !t.x || !t.y) return '';
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      // Offset for curve
      const curvature = 0.15;
      const mx = (s.x + t.x) / 2 - dy * curvature;
      const my = (s.y + t.y) / 2 + dx * curvature;
      // Shorten by target radius for arrowhead
      const ratio = (dist - (t.radius + 10)) / dist;
      const ex = s.x + dx * ratio;
      const ey = s.y + dy * ratio;
      return `M${s.x},${s.y} Q${mx},${my} ${ex},${ey}`;
    }

    // Tick handler
    simulation.on('tick', () => {
      links.attr('d', (l) => linkPath(l));

      nodeGs.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    // Fit to viewport after stabilization
    simulation.on('end', () => {
      fitToViewport(svgSel, g, zoomBehavior, width, height, simNodes);
    });

    // Cleanup
    return () => {
      simulation.stop();
      simulationRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredNodes, filteredEdges, dimensions, degreeMap, maxDegree]);

  // Update visual states for hover/search highlights
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const svgSel = select(svg);
    const nodeGs = svgSel.selectAll<SVGGElement, SimNode>('.kg-nodes g');
    const links = svgSel.selectAll<SVGPathElement, SimLink>('.kg-links path');

    if (hoveredNode) {
      nodeGs
        .transition()
        .duration(150)
        .attr('opacity', (d) => (connectedNodes.has(d.id) ? 1 : 0.2));
      links
        .transition()
        .duration(150)
        .attr('opacity', (l) => {
          const s = (l.source as SimNode).id;
          const t = (l.target as SimNode).id;
          return s === hoveredNode || t === hoveredNode ? 1 : 0.2;
        })
        .attr('stroke', (l) => {
          const s = (l.source as SimNode).id;
          const t = (l.target as SimNode).id;
          return s === hoveredNode || t === hoveredNode
            ? EDGE_HIGHLIGHT_COLOR
            : EDGE_COLOR;
        })
        .attr('marker-end', (l) => {
          const s = (l.source as SimNode).id;
          const t = (l.target as SimNode).id;
          return s === hoveredNode || t === hoveredNode
            ? 'url(#kg-arrowhead-highlight)'
            : 'url(#kg-arrowhead)';
        });
    } else {
      nodeGs.transition().duration(150).attr('opacity', 1);
      links
        .transition()
        .duration(150)
        .attr('opacity', 1)
        .attr('stroke', EDGE_COLOR)
        .attr('marker-end', 'url(#kg-arrowhead)');
    }

    // Search highlighting
    if (searchQuery.trim() && searchMatches.size > 0) {
      nodeGs.select('circle').attr('stroke', (d) =>
        searchMatches.has(d.id) ? '#F59E0B' : '#fff'
      ).attr('stroke-width', (d) =>
        searchMatches.has(d.id) ? 3 : 2
      );
    } else {
      nodeGs.select('circle').attr('stroke', '#fff').attr('stroke-width', 2);
    }
  }, [hoveredNode, connectedNodes, searchQuery, searchMatches]);

  // Fit to viewport utility
  const fitToViewport = useCallback(
    (
      svgSel: ReturnType<typeof select<SVGSVGElement, unknown>>,
      g: ReturnType<typeof select<SVGGElement, unknown>>,
      zoomBehavior: ZoomBehavior<SVGSVGElement, unknown>,
      width: number,
      height: number,
      nodes: SimNode[]
    ) => {
      if (nodes.length === 0) return;
      let minX = Infinity,
        minY = Infinity,
        maxX = -Infinity,
        maxY = -Infinity;
      nodes.forEach((n) => {
        const x = n.x ?? 0;
        const y = n.y ?? 0;
        const r = n.radius;
        minX = Math.min(minX, x - r);
        minY = Math.min(minY, y - r);
        maxX = Math.max(maxX, x + r);
        maxY = Math.max(maxY, y + r);
      });
      const graphWidth = maxX - minX + 80;
      const graphHeight = maxY - minY + 80;
      const scale = Math.min(
        width / graphWidth,
        height / graphHeight,
        1.5
      );
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      const tx = width / 2 - centerX * scale;
      const ty = height / 2 - centerY * scale;
      const t = zoomIdentity.translate(tx, ty).scale(scale);
      svgSel.transition().duration(500).call(zoomBehavior.transform as any, t);
    },
    []
  );

  // Action: fit to screen
  const handleFitToScreen = useCallback(() => {
    const svg = svgRef.current;
    if (!svg || !zoomRef.current || !simulationRef.current) return;
    const svgSel = select(svg);
    const g = svgSel.select<SVGGElement>('.kg-graph-container');
    const nodes = simulationRef.current.nodes();
    fitToViewport(
      svgSel as any,
      g as any,
      zoomRef.current,
      dimensions.width,
      dimensions.height,
      nodes
    );
  }, [dimensions, fitToViewport]);

  // Action: reset view
  const handleResetView = useCallback(() => {
    const svg = svgRef.current;
    if (!svg || !zoomRef.current) return;
    const svgSel = select(svg);
    svgSel
      .transition()
      .duration(400)
      .call(zoomRef.current.transform as any, zoomIdentity);
  }, []);

  // Toggle type filter
  const toggleTypeFilter = useCallback((type: string) => {
    setTypeFilters((prev) => ({ ...prev, [type]: !prev[type] }));
  }, []);

  // ---------------------------------------------------------------------------
  // Render: Empty state
  // ---------------------------------------------------------------------------

  if (graph.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-white rounded-lg border border-gray-200">
        <div className="text-center p-8">
          <div className="text-gray-300 text-5xl mb-4">◇</div>
          <p className="text-gray-500 text-sm font-medium">
            No knowledge graph data available
          </p>
          <p className="text-gray-400 text-xs mt-1">
            Run a pipeline with a KG Builder agent to generate graph data.
          </p>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex flex-col h-full w-full bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Header bar */}
      <div className="flex-shrink-0 border-b border-gray-200 bg-gray-50 px-4 py-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          {/* Stats */}
          <div className="flex items-center gap-3">
            <StatCard
              label="Nodes"
              value={graph.stats?.node_count ?? graph.nodes.length}
            />
            <StatCard
              label="Edges"
              value={graph.stats?.edge_count ?? graph.edges.length}
            />
            <StatCard
              label="Components"
              value={graph.stats?.connected_components ?? '—'}
            />
            {graph.edges.length === 0 && (
              <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded font-medium">
                ⚠ No relationships detected
              </span>
            )}
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleFitToScreen}
              className="px-2 py-1 text-xs font-medium text-gray-600 bg-white border border-gray-300 rounded hover:bg-gray-100 transition-colors"
              title="Fit to screen"
            >
              Fit
            </button>
            <button
              onClick={handleResetView}
              className="px-2 py-1 text-xs font-medium text-gray-600 bg-white border border-gray-300 rounded hover:bg-gray-100 transition-colors"
              title="Reset view"
            >
              Reset
            </button>
          </div>
        </div>

        {/* Search + Legend + Filters */}
        <div className="mt-2 flex items-center gap-4 flex-wrap">
          {/* Search */}
          <input
            type="text"
            placeholder="Search nodes…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="px-2 py-1 text-xs border border-gray-300 rounded w-48 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />

          {/* Legend */}
          <div className="flex items-center gap-2 flex-wrap">
            {nodeTypes.map((type) => (
              <label
                key={type}
                className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer select-none"
              >
                <input
                  type="checkbox"
                  checked={typeFilters[type] !== false}
                  onChange={() => toggleTypeFilter(type)}
                  className="w-3 h-3 rounded border-gray-300"
                />
                <span
                  className="w-2.5 h-2.5 rounded-full inline-block"
                  style={{ backgroundColor: getNodeColor(type) }}
                />
                <span className="capitalize">{type}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Graph area */}
        <div ref={containerRef} className="flex-1 relative overflow-hidden">
          <svg
            ref={svgRef}
            width={dimensions.width}
            height={dimensions.height}
            className="w-full h-full block bg-white"
          />

          {/* Tooltip */}
          {tooltip && (
            <div
              className="absolute pointer-events-none z-50 bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs max-w-[240px]"
              style={{
                left: tooltip.x + 12,
                top: tooltip.y - 8,
                transform: 'translateY(-100%)',
              }}
            >
              <div className="font-semibold text-gray-800">
                {tooltip.node.label}
              </div>
              <div className="text-gray-500 capitalize mt-0.5">
                {tooltip.node.type}
              </div>
              {tooltip.node.description && (
                <div className="text-gray-600 mt-1 leading-tight">
                  {tooltip.node.description.length > 100
                    ? tooltip.node.description.slice(0, 100) + '…'
                    : tooltip.node.description}
                </div>
              )}
              <div className="text-gray-400 mt-1">
                Connections: {degreeMap[tooltip.node.id] || 0}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        {sidebarOpen && selectedNodeData && (
          <div className="w-80 flex-shrink-0 border-l border-gray-200 bg-white overflow-y-auto">
            <div className="p-4">
              {/* Sidebar header */}
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-800 truncate pr-2">
                  {selectedNodeData.label}
                </h3>
                <button
                  onClick={() => {
                    setSidebarOpen(false);
                    setSelectedNode(null);
                  }}
                  className="text-gray-400 hover:text-gray-600 text-lg leading-none"
                >
                  ×
                </button>
              </div>

              {/* Node info */}
              <div className="space-y-2 mb-4">
                <div className="flex items-center gap-2">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{
                      backgroundColor: getNodeColor(selectedNodeData.type),
                    }}
                  />
                  <span className="text-xs text-gray-600 capitalize">
                    {selectedNodeData.type}
                  </span>
                </div>
                {selectedNodeData.description && (
                  <p className="text-xs text-gray-600 leading-relaxed">
                    {selectedNodeData.description}
                  </p>
                )}
                <div className="text-xs text-gray-400">
                  Connections: {degreeMap[selectedNodeData.id] || 0}
                </div>
              </div>

              {/* Outgoing */}
              {outgoingEdges.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-xs font-semibold text-gray-700 mb-1">
                    Outgoing ({outgoingEdges.length})
                  </h4>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {outgoingEdges.map((e, i) => {
                      const target = graph.nodes.find(
                        (n) => n.id === e.target
                      );
                      return (
                        <div
                          key={i}
                          className="text-xs text-gray-600 py-0.5 flex items-center gap-1"
                        >
                          <span className="text-gray-400">—[</span>
                          <span className="font-medium text-gray-700">
                            {e.type}
                          </span>
                          <span className="text-gray-400">]→</span>
                          <span className="truncate">
                            {target?.label || e.target}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Incoming */}
              {incomingEdges.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-xs font-semibold text-gray-700 mb-1">
                    Incoming ({incomingEdges.length})
                  </h4>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {incomingEdges.map((e, i) => {
                      const source = graph.nodes.find(
                        (n) => n.id === e.source
                      );
                      return (
                        <div
                          key={i}
                          className="text-xs text-gray-600 py-0.5 flex items-center gap-1"
                        >
                          <span className="truncate">
                            {source?.label || e.source}
                          </span>
                          <span className="text-gray-400">—[</span>
                          <span className="font-medium text-gray-700">
                            {e.type}
                          </span>
                          <span className="text-gray-400">]→</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* All relationships table */}
              <div>
                <h4 className="text-xs font-semibold text-gray-700 mb-1">
                  All Relationships ({graph.edges.length})
                </h4>
                <div className="max-h-60 overflow-y-auto border border-gray-100 rounded">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        <th className="text-left p-1 text-gray-500 font-medium">
                          Source
                        </th>
                        <th className="text-left p-1 text-gray-500 font-medium">
                          Type
                        </th>
                        <th className="text-left p-1 text-gray-500 font-medium">
                          Target
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {graph.edges.map((e, i) => {
                        const src = graph.nodes.find(
                          (n) => n.id === e.source
                        );
                        const tgt = graph.nodes.find(
                          (n) => n.id === e.target
                        );
                        return (
                          <tr
                            key={i}
                            className="border-t border-gray-50 hover:bg-gray-50"
                          >
                            <td className="p-1 text-gray-600 truncate max-w-[80px]">
                              {src?.label || e.source}
                            </td>
                            <td className="p-1 text-gray-700 font-medium">
                              {e.type}
                            </td>
                            <td className="p-1 text-gray-600 truncate max-w-[80px]">
                              {tgt?.label || e.target}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components (inline)
// ---------------------------------------------------------------------------

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex items-center gap-1.5 px-2 py-1 bg-white border border-gray-200 rounded text-xs">
      <span className="text-gray-500">{label}</span>
      <span className="font-semibold text-gray-800">{value}</span>
    </div>
  );
}
