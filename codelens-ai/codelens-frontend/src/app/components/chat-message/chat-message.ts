import {
  Component,
  Input,
  OnChanges,
  SimpleChanges,
  ViewEncapsulation,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChatMessage } from '../../models/types';
import { ThinkingSteps } from '../thinking-steps/thinking-steps';
import { SourceReferences } from '../source-references/source-references';
import { Marked } from 'marked';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-typescript';
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-json';

const marked = new Marked();

@Component({
  selector: 'app-chat-message',
  standalone: true,
  imports: [CommonModule, ThinkingSteps, SourceReferences],
  templateUrl: './chat-message.html',
  styleUrl: './chat-message.css',
  encapsulation: ViewEncapsulation.None,
})
export class ChatMessageComponent implements OnChanges {
  @Input() message!: ChatMessage;
  @Input() repoUrl = '';

  renderedHtml = '';

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['message']) {
      this.renderContent();
    }
  }

  private renderContent(): void {
    if (this.message.role === 'user' || !this.message.content) {
      this.renderedHtml = '';
      return;
    }
    const raw = marked.parse(this.message.content) as string;
    this.renderedHtml = raw;

    // Highlight code blocks after render
    setTimeout(() => Prism.highlightAll(), 0);
  }
}
