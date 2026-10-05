# Sample run: Single agent

*Recorded 2026-10-05 with `google:gemini-3.1-flash-lite` · 1 step · 398 tokens · $0.0004 · 1.9 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py single`.*

## Input

> Hello, what can you do?

## Steps

### 1. `single`
*398 tokens · $0.0004*

**Prompt**
> Hello, what can you do?

**Output**
```json
{
  "result": "I am a versatile AI assistant designed to help you with a wide range of tasks. Here are some of the things I can do for you:\n\n*   **Answering questions:** I can provide information on a vast array of topics, from history and science to pop culture and general knowledge.\n*   **Writing and editing:** I can draft emails, essays, creative stories, code, and reports, or help you proofread and improve text you've already written.\n*   **Summarization:** I can take long articles, documents, or transcripts and provide concise summaries.\n*   **Problem-solving and analysis:** I can help you brainstorm ideas, analyze data, perform calculations, or walk you through step-by-step logic.\n*   **Translation:** I can translate text between many different languages.\n*   **Coding:** I can help write, debug, and explain code snippets in various programming languages.\n*   **Organization:** I can help you draft schedules, create to-do lists, or structure complex information.\n\nIs there something specific you’d like help with today?",
  "confidence": 1.0
}
```

## Result

`run_agent(...).output`

```json
{
  "result": "I am a versatile AI assistant designed to help you with a wide range of tasks. Here are some of the things I can do for you:\n\n*   **Answering questions:** I can provide information on a vast array of topics, from history and science to pop culture and general knowledge.\n*   **Writing and editing:** I can draft emails, essays, creative stories, code, and reports, or help you proofread and improve text you've already written.\n*   **Summarization:** I can take long articles, documents, or transcripts and provide concise summaries.\n*   **Problem-solving and analysis:** I can help you brainstorm ideas, analyze data, perform calculations, or walk you through step-by-step logic.\n*   **Translation:** I can translate text between many different languages.\n*   **Coding:** I can help write, debug, and explain code snippets in various programming languages.\n*   **Organization:** I can help you draft schedules, create to-do lists, or structure complex information.\n\nIs there something specific you’d like help with today?",
  "confidence": 1.0
}
```
