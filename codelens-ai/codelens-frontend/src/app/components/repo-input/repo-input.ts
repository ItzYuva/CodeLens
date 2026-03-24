import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-repo-input',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './repo-input.html',
  styleUrl: './repo-input.css',
})
export class RepoInput {
  @Output() submitted = new EventEmitter<string>();

  url = '';
  isLoading = false;

  get isValid(): boolean {
    return /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(
      this.url.trim().replace(/\.git$/, '')
    );
  }

  submit(): void {
    if (this.isValid && !this.isLoading) {
      this.isLoading = true;
      this.submitted.emit(this.url.trim());
    }
  }

  fillExample(url: string): void {
    this.url = url;
  }

  reset(): void {
    this.isLoading = false;
  }
}
