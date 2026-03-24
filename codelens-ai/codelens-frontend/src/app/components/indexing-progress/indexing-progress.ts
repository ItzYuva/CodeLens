import {
  Component,
  EventEmitter,
  Input,
  OnDestroy,
  OnInit,
  Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../services/api.service';
import { RepoStatus } from '../../models/types';

interface IndexStep {
  label: string;
  key: string;
  status: 'pending' | 'active' | 'done';
  detail?: string;
}

@Component({
  selector: 'app-indexing-progress',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './indexing-progress.html',
  styleUrl: './indexing-progress.css',
})
export class IndexingProgress implements OnInit, OnDestroy {
  @Input() repoId = '';
  @Input() repoName = '';
  @Output() ready = new EventEmitter<void>();
  @Output() cancelled = new EventEmitter<void>();

  progress = 0;
  failed = false;
  errorMessage = '';
  steps: IndexStep[] = [];

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.resetSteps();
    this.poll();
    this.pollTimer = setInterval(() => this.poll(), 2000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
    }
  }

  cancel(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
    }
    this.api.deleteRepo(this.repoId).subscribe({
      next: () => this.cancelled.emit(),
      error: () => this.cancelled.emit(),
    });
  }

  retry(): void {
    this.failed = false;
    this.errorMessage = '';
    this.resetSteps();
    this.poll();
    this.pollTimer = setInterval(() => this.poll(), 2000);
  }

  private poll(): void {
    this.api.getStatus(this.repoId).subscribe({
      next: (status) => this.handleStatus(status),
      error: () => {
        this.failed = true;
        this.errorMessage = 'Failed to fetch status';
      },
    });
  }

  private handleStatus(status: RepoStatus): void {
    this.progress = status.progress;

    if (status.status === 'failed') {
      this.failed = true;
      this.errorMessage = status.error_message || 'Indexing failed';
      if (this.pollTimer) clearInterval(this.pollTimer);
      this.updateSteps(status.status, status);
      return;
    }

    if (status.status === 'ready') {
      this.progress = 100;
      this.updateSteps('ready', status);
      if (this.pollTimer) clearInterval(this.pollTimer);
      setTimeout(() => this.ready.emit(), 1000);
      return;
    }

    this.updateSteps(status.status, status);
  }

  private resetSteps(): void {
    this.steps = [
      { label: 'Cloning repository', key: 'cloning', status: 'pending' },
      { label: 'Parsing code structure', key: 'parsing', status: 'pending' },
      { label: 'Summarizing code', key: 'summarizing', status: 'pending' },
      { label: 'Ready', key: 'ready', status: 'pending' },
    ];
  }

  private updateSteps(currentStatus: string, status: RepoStatus): void {
    const order = ['queued', 'cloning', 'parsing', 'summarizing', 'ready'];
    const currentIdx = order.indexOf(currentStatus);

    this.steps.forEach((step, i) => {
      const stepIdx = order.indexOf(step.key);
      if (stepIdx < currentIdx) {
        step.status = 'done';
        step.detail = undefined;
      } else if (stepIdx === currentIdx) {
        step.status = currentStatus === 'ready' ? 'done' : 'active';
        if (step.key === 'parsing' && status.total_nodes > 0) {
          step.detail = `${status.total_nodes} nodes`;
        }
        if (step.key === 'summarizing' && status.progress > 0) {
          step.detail = `${status.progress}%`;
        }
      } else {
        step.status = 'pending';
        step.detail = undefined;
      }
    });
  }
}
