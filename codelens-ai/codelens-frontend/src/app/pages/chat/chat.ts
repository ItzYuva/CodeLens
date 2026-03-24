import {
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { ApiService } from '../../services/api.service';
import {
  ConnectionStatus,
  WebSocketService,
} from '../../services/websocket.service';
import { ChatMessageComponent } from '../../components/chat-message/chat-message';
import {
  ChatMessage,
  RepoStatus,
  WSMessage,
} from '../../models/types';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, ChatMessageComponent],
  templateUrl: './chat.html',
  styleUrl: './chat.css',
})
export class Chat implements OnInit, OnDestroy {
  @ViewChild('messagesContainer') messagesContainer!: ElementRef;
  @ViewChild('queryInput') queryInput!: ElementRef<HTMLTextAreaElement>;

  repoId = '';
  repo: RepoStatus | null = null;
  messages: ChatMessage[] = [];
  query = '';
  isStreaming = false;
  connectionStatus: ConnectionStatus = 'disconnected';

  suggestedQuestions = [
    'What does this project do?',
    'How is the project structured?',
    'What are the main dependencies?',
  ];

  private subs: Subscription[] = [];

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    private ws: WebSocketService,
  ) {}

  ngOnInit(): void {
    this.repoId = this.route.snapshot.paramMap.get('repoId') || '';

    // Load repo info
    this.api.getStatus(this.repoId).subscribe({
      next: (status) => {
        this.repo = status;
        if (status.status !== 'ready') {
          this.router.navigate(['/']);
          return;
        }
        this.ws.connect(this.repoId);
      },
      error: () => this.router.navigate(['/']),
    });

    // WebSocket status
    this.subs.push(
      this.ws.connectionStatus$.subscribe(
        (s) => (this.connectionStatus = s),
      ),
    );

    // WebSocket messages
    this.subs.push(
      this.ws.messages$.subscribe((msg) => this.handleMessage(msg)),
    );
  }

  ngOnDestroy(): void {
    this.ws.disconnect();
    this.subs.forEach((s) => s.unsubscribe());
  }

  sendQuery(text?: string): void {
    const q = (text || this.query).trim();
    if (!q || this.isStreaming) return;

    // User message
    this.messages.push({
      id: crypto.randomUUID(),
      role: 'user',
      content: q,
      thinkingSteps: [],
      sources: [],
      isStreaming: false,
      timestamp: new Date(),
    });

    // Empty assistant message
    this.messages.push({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      thinkingSteps: [],
      sources: [],
      isStreaming: true,
      timestamp: new Date(),
    });

    this.isStreaming = true;
    this.query = '';
    this.ws.sendQuery(q);
    this.scrollToBottom();
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendQuery();
    }
  }

  goBack(): void {
    this.router.navigate(['/']);
  }

  openGithub(): void {
    if (this.repo?.url) {
      window.open(this.repo.url, '_blank');
    }
  }

  trackMessage(_index: number, msg: ChatMessage): string {
    return msg.id;
  }

  private handleMessage(msg: WSMessage): void {
    const current = this.currentAssistantMessage;
    if (!current) return;

    switch (msg.type) {
      case 'thinking':
        current.thinkingSteps.push(msg);
        break;
      case 'answer_chunk':
        current.content += msg.content;
        break;
      case 'sources':
        current.sources = msg.files;
        break;
      case 'done':
        current.isStreaming = false;
        this.isStreaming = false;
        break;
      case 'error':
        current.content += `\n\n**Error:** ${msg.message}`;
        current.isStreaming = false;
        this.isStreaming = false;
        break;
    }

    this.scrollToBottom();
  }

  private get currentAssistantMessage(): ChatMessage | null {
    for (let i = this.messages.length - 1; i >= 0; i--) {
      if (this.messages[i].role === 'assistant') {
        return this.messages[i];
      }
    }
    return null;
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      const el = this.messagesContainer?.nativeElement;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    }, 0);
  }
}
