import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { IndexResponse, RepoListItem, RepoStatus } from '../models/types';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private baseUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  indexRepo(url: string): Observable<IndexResponse> {
    return this.http.post<IndexResponse>(`${this.baseUrl}/api/index`, {
      repo_url: url,
    });
  }

  getStatus(repoId: string): Observable<RepoStatus> {
    return this.http.get<RepoStatus>(`${this.baseUrl}/api/status/${repoId}`);
  }

  listRepos(): Observable<RepoListItem[]> {
    return this.http.get<RepoListItem[]>(`${this.baseUrl}/api/repos`);
  }

  deleteRepo(repoId: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(
      `${this.baseUrl}/api/repos/${repoId}`
    );
  }

  healthCheck(): Observable<{ status: string; service: string }> {
    return this.http.get<{ status: string; service: string }>(
      `${this.baseUrl}/api/health`
    );
  }
}
