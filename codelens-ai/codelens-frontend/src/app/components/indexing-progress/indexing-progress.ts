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
  elapsed = '';
  currentAction = '';

  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private elapsedTimer: ReturnType<typeof setInterval> | null = null;
  private startTime = Date.now();

  // Stuck detection: if progress+status haven't changed for 90s, show error
  private lastStatusKey = '';
  private lastStatusChangeTime = Date.now();
  private readonly STUCK_TIMEOUT_MS = 90_000;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.startTime = Date.now();
    this.lastStatusChangeTime = Date.now();
    this.resetSteps();
    this.poll();
    this.pollTimer = setInterval(() => this.poll(), 2000);
    this.elapsedTimer = setInterval(() => this.updateElapsed(), 1000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.elapsedTimer) clearInterval(this.elapsedTimer);
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
    // Delete the stuck/failed repo so a fresh indexing job can start
    this.api.deleteRepo(this.repoId).subscribe({
      next: () => this.cancelled.emit(),
      error: () => this.cancelled.emit(),
    });
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
    // ── Stuck detection ──────────────────────────────────────────
    const statusKey = `${status.status}:${status.progress}`;
    if (statusKey !== this.lastStatusKey) {
      this.lastStatusKey = statusKey;
      this.lastStatusChangeTime = Date.now();
    } else if (
      Date.now() - this.lastStatusChangeTime > this.STUCK_TIMEOUT_MS &&
      status.status !== 'ready' &&
      status.status !== 'failed'
    ) {
      this.failed = true;
      this.errorMessage =
        'Indexing appears stuck (no progress for 90s). Click Retry to re-queue.';
      this.currentAction = 'Stuck';
      if (this.pollTimer) clearInterval(this.pollTimer);
      if (this.elapsedTimer) clearInterval(this.elapsedTimer);
      this.updateSteps(status.status, status);
      return;
    }

    // ── Map each phase to a progress range ───────────────────────
    if (status.status === 'queued') {
      this.progress = 2;
      this.currentAction = 'Waiting in queue...';
    } else if (status.status === 'cloning') {
      this.progress = 10;
      this.currentAction = 'Cloning repository from GitHub...';
    } else if (status.status === 'parsing') {
      this.progress = 20;
      this.currentAction = status.total_nodes > 0
        ? `Parsed ${status.total_nodes} code nodes`
        : 'Parsing code into AST...';
    } else if (status.status === 'summarizing') {
      // Summarizing maps from 25% to 95%
      this.progress = 25 + Math.round(status.progress * 0.7);
      this.currentAction = `Summarizing code with AI... ${status.progress}%`;
    } else if (status.status === 'ready') {
      this.progress = 100;
      this.currentAction = 'Analysis complete';
    }

    if (status.status === 'failed') {
      this.failed = true;
      this.errorMessage = status.error_message || 'Indexing failed';
      this.currentAction = 'Failed';
      if (this.pollTimer) clearInterval(this.pollTimer);
      if (this.elapsedTimer) clearInterval(this.elapsedTimer);
      this.updateSteps(status.status, status);
      return;
    }

    if (status.status === 'ready') {
      this.updateSteps('ready', status);
      if (this.pollTimer) clearInterval(this.pollTimer);
      if (this.elapsedTimer) clearInterval(this.elapsedTimer);
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

  private updateElapsed(): void {
    const seconds = Math.floor((Date.now() - this.startTime) / 1000);
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    this.elapsed = mins > 0
      ? `${mins}m ${secs.toString().padStart(2, '0')}s`
      : `${secs}s`;
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
