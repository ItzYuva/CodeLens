import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { timeout, catchError, throwError } from 'rxjs';
import { ApiService } from '../../services/api.service';
import { IndexingProgress } from '../../components/indexing-progress/indexing-progress';
import { RepoListItem } from '../../models/types';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, FormsModule, IndexingProgress],
  templateUrl: './home.html',
  styleUrl: './home.css',
})
export class Home implements OnInit {
  recentRepos: RepoListItem[] = [];
  indexingRepoId: string | null = null;
  indexingRepoName = '';
  errorMessage = '';
  url = '';
  isLoading = false;

  examples = [
    { name: 'pallets/flask', url: 'https://github.com/pallets/flask' },
    { name: 'tiangolo/fastapi', url: 'https://github.com/tiangolo/fastapi' },
    { name: 'expressjs/express', url: 'https://github.com/expressjs/express' },
  ];

  constructor(
    private api: ApiService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.loadRepos();
  }

  get isValid(): boolean {
    return /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(
      this.url.trim().replace(/\.git$/, '')
    );
  }

  submit(): void {
    if (!this.isValid || this.isLoading) return;
    this.isLoading = true;
    this.errorMessage = '';

    this.api
      .indexRepo(this.url.trim())
      .pipe(
        timeout(15_000), // 15s — if backend doesn't respond, don't spin forever
        catchError((err) => {
          if (err.name === 'TimeoutError') {
            return throwError(() => ({
              error: { detail: 'Backend did not respond in time. Is the server running?' },
            }));
          }
          return throwError(() => err);
        }),
      )
      .subscribe({
        next: (res) => {
          this.isLoading = false;
          if (res.status === 'ready') {
            this.router.navigate(['/chat', res.repo_id]);
          } else {
            // Switch to progress view
            this.indexingRepoId = res.repo_id;
            this.indexingRepoName = res.name;
          }
          this.loadRepos();
        },
        error: (err) => {
          this.isLoading = false;
          this.errorMessage = err.error?.detail || 'Failed to start indexing';
        },
      });
  }

  onReady(): void {
    if (this.indexingRepoId) {
      this.router.navigate(['/chat', this.indexingRepoId]);
    }
  }

  onCancelled(): void {
    this.indexingRepoId = null;
    this.indexingRepoName = '';
    // Keep the URL so the user can easily click Analyze again
    this.isLoading = false;
    this.loadRepos();
  }

  fillExample(exUrl: string): void {
    this.url = exUrl;
  }

  goToChat(repoId: string): void {
    this.router.navigate(['/chat', repoId]);
  }

  getTimeAgo(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
    if (seconds < 60) return 'Just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  private loadRepos(): void {
    this.api.listRepos().subscribe({
      next: (repos) => (this.recentRepos = repos),
    });
  }
}
