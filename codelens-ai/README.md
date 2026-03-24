# CodeLens AI

**Chat with any GitHub repository -- no embeddings, no vector database.**

CodeLens AI lets you paste a GitHub repo URL and ask natural language questions about the codebase. It uses **Vectorless RAG** -- a tree-based retrieval approach that parses code into a hierarchy, summarizes each node, and traverses the tree intelligently at query time.

> Unlike traditional RAG that chunks code into flat pieces and relies on cosine similarity, CodeLens AI understands your codebase *structurally* -- it knows which files contain which classes, which functions call what, and navigates to the right code the way a developer would.

<!--
![CodeLens AI Demo](screenshots/demo.gif)
-->

---

## Features

- **Paste any GitHub URL** -- Public repos analyzed automatically
- **Vectorless RAG** -- No vector database, no embeddings. Tree-based retrieval with LLM reasoning
- **Real-time thinking steps** -- See exactly what the system is exploring as it searches your codebase
- **Streaming answers** -- Token-by-token response streaming with source references
- **Smart caching** -- Repos indexed once, cached by commit hash
- **BM25 pre-filtering** -- Keyword matching narrows candidates before tree traversal
- **Lazy tree traversal** -- Only expands relevant branches, saving tokens and time
- **Multi-language support** -- Python, JavaScript, TypeScript

---

## Architecture

### How Vectorless RAG Works

**Classical RAG:**
```
Document -> Chunk into flat pieces -> Embed each chunk -> Vector DB
Query -> Embed -> Cosine similarity -> Top-K chunks -> LLM -> Answer
```

**CodeLens AI (Vectorless RAG):**
```
Repository -> Parse into AST tree -> Summarize bottom-up -> JSON tree
Query -> BM25 pre-filter -> Lazy tree traversal -> Selected code -> LLM -> Answer
```

The key insight: code is *hierarchical*. A flat chunk of code loses context about where it lives, what class it belongs to, and what module it serves. By preserving the tree structure and summarizing bottom-up, the LLM can *reason* about which branches to explore -- like a developer navigating a codebase.
