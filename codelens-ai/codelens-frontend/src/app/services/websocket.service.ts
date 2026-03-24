import { Injectable } from '@angular/core';
import { BehaviorSubject, Subject } from 'rxjs';
import { environment } from '../../environments/environment';
import { WSMessage } from '../models/types';

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private socket: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private currentRepoId: string | null = null;

  messages$ = new Subject<WSMessage>();
  connectionStatus$ = new BehaviorSubject<ConnectionStatus>('disconnected');

  connect(repoId: string): void {
    this.disconnect();
    this.currentRepoId = repoId;
    this.reconnectAttempts = 0;
    this.openConnection(repoId);
  }

  sendQuery(query: string): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ query }));
    }
  }

  disconnect(): void {
    this.currentRepoId = null;
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.connectionStatus$.next('disconnected');
  }

  private openConnection(repoId: string): void {
    this.connectionStatus$.next('connecting');
    const url = `${environment.wsUrl}/ws/query/${repoId}`;
    this.socket = new WebSocket(url);

    this.socket.onopen = () => {
      this.reconnectAttempts = 0;
      this.connectionStatus$.next('connected');
    };

    this.socket.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        this.messages$.next(msg);
      } catch {
        // ignore unparseable messages
      }
    };

    this.socket.onclose = () => {
      this.connectionStatus$.next('disconnected');
      this.attemptReconnect();
    };

    this.socket.onerror = () => {
      this.connectionStatus$.next('disconnected');
    };
  }

  private attemptReconnect(): void {
    if (
      !this.currentRepoId ||
      this.reconnectAttempts >= this.maxReconnectAttempts
    ) {
      return;
    }
    this.reconnectAttempts++;
    const delay = Math.min(2000 * Math.pow(2, this.reconnectAttempts - 1), 8000);
    setTimeout(() => {
      if (this.currentRepoId) {
        this.openConnection(this.currentRepoId);
      }
    }, delay);
  }
}
