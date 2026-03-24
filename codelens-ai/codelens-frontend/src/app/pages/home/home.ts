import { Component, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { RepoInput } from '../../components/repo-input/repo-input';
import { IndexingProgress } from '../../components/indexing-progress/indexing-progress';
import { RepoListItem } from '../../models/types';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, RepoInput, IndexingProgress],
  templateUrl: './home.html',
  styleUrl: './home.css',
})
export class Home implements OnInit {
  @ViewChild(RepoInput) repoInput!: RepoInput;

  recentRepos: RepoListItem[] = [];
  indexingRepoId: string | null = null;
  indexingRepoName = '';
  errorMessage = '';

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

  onSubmit(url: string): void {
    this.errorMessage = '';
    this.api.indexRepo(url).subscribe({
      next: (res) => {
        if (res.status === 'ready') {
          this.router.navigate(['/chat', res.repo_id]);
        } else {
          this.indexingRepoId = res.repo_id;
          this.indexingRepoName = res.name;
        }
        this.repoInput?.reset();
      },
      error: (err) => {
        this.errorMessage =
          err.error?.detail || 'Failed to start indexing';
        this.repoInput?.reset();
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
  }

  fillExample(url: string): void {
    this.repoInput?.fillExample(url);
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
