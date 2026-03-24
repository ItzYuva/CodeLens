import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SourceFile } from '../../models/types';

@Component({
  selector: 'app-source-references',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './source-references.html',
  styleUrl: './source-references.css',
})
export class SourceReferences {
  @Input() sources: SourceFile[] = [];
  @Input() repoUrl = '';

  getGithubUrl(source: SourceFile): string {
    return `${this.repoUrl}/blob/main/${source.file_path}`;
  }
}
