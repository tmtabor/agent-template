# Sample run: Single agent

*Recorded 2026-10-07 with `google:gemini-3.1-flash-lite` · 1 step · 339 tokens · $0.0003 · 1.3 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py single`.*

## Input

> Hello, what can you do?

## Steps

### 1. `single`
*339 tokens · $0.0003*

**Prompt**
> Hello, what can you do?

**Output**
```json
{
  "result": "I am a helpful, accurate, and concise AI assistant. I can help you with a wide range of tasks, including:\n\n*   **Answering questions:** Providing information on a vast range of topics.\n*   **Writing and editing:** Creating emails, essays, stories, reports, or refining your existing text.\n*   **Summarization:** Condensing long articles, documents, or conversations into key points.\n*   **Coding and technical help:** Writing, debugging, and explaining code in various programming languages.\n*   **Brainstorming:** Generating ideas for projects, marketing, or creative tasks.\n*   **Translation:** Translating text between many different languages.\n*   **Data Analysis and Formatting:** Helping organize information or performing calculations.\n\nIs there something specific you would like help with today?",
  "confidence": 1.0
}
```

## Result

`run_agent(...).output`

```json
{
  "result": "I am a helpful, accurate, and concise AI assistant. I can help you with a wide range of tasks, including:\n\n*   **Answering questions:** Providing information on a vast range of topics.\n*   **Writing and editing:** Creating emails, essays, stories, reports, or refining your existing text.\n*   **Summarization:** Condensing long articles, documents, or conversations into key points.\n*   **Coding and technical help:** Writing, debugging, and explaining code in various programming languages.\n*   **Brainstorming:** Generating ideas for projects, marketing, or creative tasks.\n*   **Translation:** Translating text between many different languages.\n*   **Data Analysis and Formatting:** Helping organize information or performing calculations.\n\nIs there something specific you would like help with today?",
  "confidence": 1.0
}
```
