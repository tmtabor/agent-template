# Sample run: Pipeline

*Recorded 2026-10-07 with `google:gemini-3.1-flash-lite` · 3 steps · 1,227 tokens · $0.0011 · 4.5 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py pipeline`.*

## Input

> Why unit tests are worth writing

## Steps

### 1. `pipeline.outline`
*188 tokens · $0.0002*

**Prompt**
> Topic: Why unit tests are worth writing

**Output**
```json
{
  "points": [
    "Unit tests provide immediate feedback that helps identify and fix bugs early in the development cycle.",
    "They act as living documentation, making it easier for developers to understand how specific parts of the codebase should function.",
    "Automated tests allow developers to refactor code with confidence, knowing that regressions will be quickly detected.",
    "Maintaining a comprehensive test suite reduces long-term technical debt and lowers the overall cost of software maintenance."
  ]
}
```

### 2. `pipeline.draft`
*461 tokens · $0.0005*

**Prompt**
> Outline:
> 1. Unit tests provide immediate feedback that helps identify and fix bugs early in the development cycle.
> 2. They act as living documentation, making it easier for developers to understand how specific parts of the codebase should function.
> 3. Automated tests allow developers to refactor code with confidence, knowing that regressions will be quickly detected.
> 4. Maintaining a comprehensive test suite reduces long-term technical debt and lowers the overall cost of software maintenance.

**Output**
```json
{
  "text": "Unit testing is a cornerstone of modern software development, providing critical benefits that extend well beyond simple bug detection.\n\nFirst, unit tests provide immediate feedback, allowing developers to identify and resolve defects early in the development cycle. By catching issues at the moment they are introduced, teams can address problems while the context is still fresh, avoiding the significantly higher costs associated with fixing bugs later in production.\n\nSecond, these tests act as living documentation for the project. For developers joining a new team or revisiting an old codebase, unit tests serve as a clear, executable reference for how specific functions and modules are expected to behave. Rather than relying solely on outdated manuals, developers can look at the tests to understand the intended functionality and logic of the code.\n\nThird, automated testing provides developers the confidence to refactor code. When a comprehensive suite of tests exists, developers can improve the design, readability, and efficiency of the codebase without the fear of breaking existing features. If a change introduces a regression, the automated suite will catch it immediately, ensuring that the software remains stable throughout the development process.\n\nFinally, maintaining a comprehensive test suite is an investment that reduces long-term technical debt. While writing tests requires an upfront time commitment, it significantly lowers the overall cost of software maintenance over the life of the product. By preventing the accumulation of hidden bugs and ensuring the codebase remains modular and understandable, unit tests make the system more sustainable and easier to evolve over time."
}
```

### 3. `pipeline.polish`
*578 tokens · $0.0004*

**Prompt**
> Draft:
> Unit testing is a cornerstone of modern software development, providing critical benefits that extend well beyond simple bug detection.
>
> First, unit tests provide immediate feedback, allowing developers to identify and resolve defects early in the development cycle. By catching issues at the moment they are introduced, teams can address problems while the context is still fresh, avoiding the significantly higher costs associated with fixing bugs later in production.
>
> Second, these tests a …

**Output**
```json
{
  "result": "Unit testing is a cornerstone of modern software development, offering benefits that extend well beyond basic bug detection.\n\nFirst, unit tests provide immediate feedback, allowing developers to resolve defects early. By catching issues as they are introduced, teams address problems while the context is fresh, avoiding the high costs of fixing bugs in production.\n\nSecond, tests serve as living documentation. For developers onboarding or revisiting a codebase, unit tests provide an executable reference for how functions and modules should behave, offering clearer insights than outdated manuals.\n\nThird, automated tests empower developers to refactor with confidence. A comprehensive suite allows for improvements in design, readability, and efficiency without the fear of breaking existing features. If a regression occurs, the tests catch it immediately, ensuring system stability.\n\nFinally, maintaining a test suite is an investment that reduces long-term technical debt. While writing tests requires an upfront time commitment, it lowers maintenance costs over the product's life. By preventing hidden bugs and encouraging modularity, unit tests make the system more sustainable and easier to evolve."
}
```

## Result

`run_pipeline(...).output`

```json
{
  "result": "Unit testing is a cornerstone of modern software development, offering benefits that extend well beyond basic bug detection.\n\nFirst, unit tests provide immediate feedback, allowing developers to resolve defects early. By catching issues as they are introduced, teams address problems while the context is fresh, avoiding the high costs of fixing bugs in production.\n\nSecond, tests serve as living documentation. For developers onboarding or revisiting a codebase, unit tests provide an executable reference for how functions and modules should behave, offering clearer insights than outdated manuals.\n\nThird, automated tests empower developers to refactor with confidence. A comprehensive suite allows for improvements in design, readability, and efficiency without the fear of breaking existing features. If a regression occurs, the tests catch it immediately, ensuring system stability.\n\nFinally, maintaining a test suite is an investment that reduces long-term technical debt. While writing tests requires an upfront time commitment, it lowers maintenance costs over the product's life. By preventing hidden bugs and encouraging modularity, unit tests make the system more sustainable and easier to evolve.",
  "outline": [
    "Unit tests provide immediate feedback that helps identify and fix bugs early in the development cycle.",
    "They act as living documentation, making it easier for developers to understand how specific parts of the codebase should function.",
    "Automated tests allow developers to refactor code with confidence, knowing that regressions will be quickly detected.",
    "Maintaining a comprehensive test suite reduces long-term technical debt and lowers the overall cost of software maintenance."
  ]
}
```
