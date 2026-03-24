export interface IndexRequest {
  repo_url: string;
}

export interface IndexResponse {
  repo_id: string;
  name: string;
  status: string;
  message: string;
}

export interface RepoStatus {
  repo_id: string;
  url: string;
  name: string;
  status: 'queued' | 'cloning' | 'parsing' | 'summarizing' | 'ready' | 'failed';
  progress: number;
  total_nodes: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepoListItem {
  repo_id: string;
  url: string;
  name: string;
  status: string;
  progress: number;
  created_at: string;
}

export interface ThinkingMessage {
  type: 'thinking';
  step_type: 'searching' | 'filtering' | 'exploring' | 'reading' | 'generating' | 'error';
  message: string;
}

export interface AnswerChunkMessage {
  type: 'answer_chunk';
  content: string;
}

export interface SourcesMessage {
  type: 'sources';
  files: SourceFile[];
}

export interface SourceFile {
  file_path: string;
  node_name: string;
  node_type: string;
}

export interface DoneMessage {
  type: 'done';
}

export interface ErrorMessage {
  type: 'error';
  message: string;
}

export type WSMessage =
  | ThinkingMessage
  | AnswerChunkMessage
  | SourcesMessage
  | DoneMessage
  | ErrorMessage;

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinkingSteps: ThinkingMessage[];
  sources: SourceFile[];
  isStreaming: boolean;
  timestamp: Date;
}
