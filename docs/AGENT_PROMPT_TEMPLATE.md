# Agent Prompt Template

Give this prompt to an autonomous AI coding agent when you want it to create a game using `llmgames`.

```text
Use these implementation instructions:
https://github.com/<owner>/<repo>/blob/main/docs/AGENT_GAME_AUTHORING.md

Create a game with this concept:
<describe the game concept here>

Constraints:
- Use llmgames as an installed Python package.
- Do not clone, inspect, or modify the llmgames framework repository unless I explicitly ask for framework changes.
- Create game code in my project, not inside the llmgames package.
- Include tests for validate_kernel(), scripted replay, invalid submissions, and at least one LLM player.
- If the game has hidden information, include player and LLM privacy tests.
- Prioritize a good end-user experience: clear phases, readable visible_state, legal action labels, useful events, and helpful validation errors.
- Run the relevant tests and report the commands and results.

Expected output:
- generated game module path
- generated test path
- brief gameplay summary
- test commands and results
- any limitations or framework capabilities that were missing
```

Replace `<owner>/<repo>` with the GitHub repository that hosts this document, and replace `<describe the game concept here>` with the user's desired game.

## Example Request

```text
Use these implementation instructions:
https://github.com/example/llmgames/blob/main/docs/AGENT_GAME_AUTHORING.md

Create a game called Council of Embers. It should support four players, one LLM-controlled player, hidden roles, simultaneous voting, negotiation resources, and a public reveal phase.

Constraints:
- Use llmgames as an installed Python package.
- Do not clone, inspect, or modify the llmgames framework repository unless I explicitly ask for framework changes.
- Create game code in my project, not inside the llmgames package.
- Include tests for validate_kernel(), scripted replay, invalid submissions, hidden-information privacy, and at least one LLM player.
- Prioritize a good end-user experience: clear phases, readable visible_state, legal action labels, useful events, and helpful validation errors.
- Run the relevant tests and report the commands and results.
```
