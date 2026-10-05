# Sample run: Pipeline

*Recorded 2026-10-05 with `google:gemini-3.1-flash-lite` · 3 steps · 1,229 tokens · $0.0011 · 4.9 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py pipeline`.*

## Input

> Why unit tests are worth writing

## Steps

### 1. `pipeline.outline`
*210 tokens · $0.0002*

**Prompt**
> Topic: Why unit tests are worth writing

**Output**
```json
{
  "points": [
    "Unit tests provide immediate feedback that helps developers catch bugs early in the development cycle when they are easiest to fix.",
    "A robust suite of tests acts as a safety net, allowing developers to refactor code or add new features with the confidence that existing functionality remains intact.",
    "Well-written tests serve as living documentation, clearly illustrating the intended behavior and usage of code modules for other team members.",
    "Investing in unit tests improves overall software quality and long-term maintainability by encouraging the design of modular, loosely coupled code."
  ]
}
```

### 2. `pipeline.draft`
*474 tokens · $0.0005*

**Prompt**
> Outline:
> 1. Unit tests provide immediate feedback that helps developers catch bugs early in the development cycle when they are easiest to fix.
> 2. A robust suite of tests acts as a safety net, allowing developers to refactor code or add new features with the confidence that existing functionality remains intact.
> 3. Well-written tests serve as living documentation, clearly illustrating the intended behavior and usage of code modules for other team members.
> 4. Investing in unit tests improves over …

**Output**
```json
{
  "text": "Unit testing is a fundamental practice in modern software development, offering numerous benefits that extend far beyond simple bug detection.\n\nFirst, unit tests provide immediate feedback, which is crucial for developers. By running tests frequently, issues can be identified and addressed early in the development cycle. Catching bugs at this stage is significantly more efficient and cost-effective than discovering them later in production, where they are harder to isolate and fix.\n\nSecond, a robust suite of tests acts as a vital safety net for any codebase. When developers need to refactor existing code or introduce new features, the test suite provides the assurance that the current functionality remains intact. This confidence allows teams to make necessary changes and improvements without the constant fear of inadvertently breaking established features.\n\nThird, well-written unit tests serve as a form of living documentation. Unlike static manuals that can quickly become outdated, tests are constantly executed against the code. By reviewing these tests, other team members can gain a clear understanding of the intended behavior and usage of specific code modules, making onboarding and collaboration much smoother.\n\nFinally, investing in unit tests ultimately improves the overall software quality and long-term maintainability. The process of writing testable code naturally encourages developers to design modular, loosely coupled components. By focusing on how a unit of code behaves in isolation, developers create systems that are cleaner, more flexible, and significantly easier to maintain over time."
}
```

### 3. `pipeline.polish`
*545 tokens · $0.0004*

**Prompt**
> Draft:
> Unit testing is a fundamental practice in modern software development, offering numerous benefits that extend far beyond simple bug detection.
>
> First, unit tests provide immediate feedback, which is crucial for developers. By running tests frequently, issues can be identified and addressed early in the development cycle. Catching bugs at this stage is significantly more efficient and cost-effective than discovering them later in production, where they are harder to isolate and fix.
>
> Secon …

**Output**
```json
{
  "result": "Unit testing is a fundamental practice in modern software development, offering benefits that extend far beyond simple bug detection.\n\nFirst, unit tests provide immediate feedback. By running tests frequently, developers can identify and resolve issues early in the development cycle, which is far more efficient and cost-effective than fixing them in production.\n\nSecond, a robust test suite acts as a safety net. It allows developers to refactor code or add features with the confidence that existing functionality remains intact, eliminating the fear of breaking established code.\n\nThird, well-written tests serve as living documentation. Unlike static manuals, tests are constantly executed against the code, helping team members understand intended behavior and usage, which simplifies onboarding and collaboration.\n\nFinally, unit testing improves overall software quality and maintainability. The process of writing testable code encourages developers to create modular, loosely coupled components, resulting in systems that are cleaner, more flexible, and easier to maintain."
}
```

## Result

`run_pipeline(...).output`

```json
{
  "result": "Unit testing is a fundamental practice in modern software development, offering benefits that extend far beyond simple bug detection.\n\nFirst, unit tests provide immediate feedback. By running tests frequently, developers can identify and resolve issues early in the development cycle, which is far more efficient and cost-effective than fixing them in production.\n\nSecond, a robust test suite acts as a safety net. It allows developers to refactor code or add features with the confidence that existing functionality remains intact, eliminating the fear of breaking established code.\n\nThird, well-written tests serve as living documentation. Unlike static manuals, tests are constantly executed against the code, helping team members understand intended behavior and usage, which simplifies onboarding and collaboration.\n\nFinally, unit testing improves overall software quality and maintainability. The process of writing testable code encourages developers to create modular, loosely coupled components, resulting in systems that are cleaner, more flexible, and easier to maintain.",
  "outline": [
    "Unit tests provide immediate feedback that helps developers catch bugs early in the development cycle when they are easiest to fix.",
    "A robust suite of tests acts as a safety net, allowing developers to refactor code or add new features with the confidence that existing functionality remains intact.",
    "Well-written tests serve as living documentation, clearly illustrating the intended behavior and usage of code modules for other team members.",
    "Investing in unit tests improves overall software quality and long-term maintainability by encouraging the design of modular, loosely coupled code."
  ]
}
```
