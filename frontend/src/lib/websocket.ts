import { StreamEvent } from '@/types';

export class ExecutionWebSocket {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<(event: StreamEvent) => void>> = new Map();
  private reconnectTimer: NodeJS.Timeout | null = null;
  private runId: string = '';

  connect(runId: string) {
    this.runId = runId;
    const wsBase = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace('http', 'ws');
    this.ws = new WebSocket(`${wsBase}/api/ws/execution/${runId}`);

    this.ws.onmessage = (event) => {
      try {
        const streamEvent: StreamEvent = JSON.parse(event.data);
        this.emit(streamEvent.event_type, streamEvent);
        this.emit('*', streamEvent); // wildcard listener
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    this.ws.onclose = () => {
      this.emit('disconnected', { event_type: 'disconnected', node_id: '', data: {}, timestamp: Date.now() / 1000 } as any);
    };

    this.ws.onerror = (err) => {
      console.error('WebSocket error:', err);
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  send(action: 'pause' | 'resume' | 'cancel' | 'step') {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action }));
    }
  }

  on(eventType: string, callback: (event: StreamEvent) => void) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(callback);
    return () => {
      this.listeners.get(eventType)?.delete(callback);
    };
  }

  private emit(eventType: string, event: StreamEvent) {
    this.listeners.get(eventType)?.forEach((cb) => cb(event));
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Singleton instance
export const executionWs = new ExecutionWebSocket();
