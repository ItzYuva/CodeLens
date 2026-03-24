import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ThinkingMessage } from '../../models/types';

@Component({
  selector: 'app-thinking-steps',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './thinking-steps.html',
  styleUrl: './thinking-steps.css',
})
export class ThinkingSteps {
  @Input() steps: ThinkingMessage[] = [];
  @Input() isActive = false;
}
