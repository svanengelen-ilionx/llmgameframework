# PLAN

## Architecture

Build a small framework where an Engine runs games defined by GameModules.

Core split:

- Engine owns runtime execution, current game state, controller calls, limits, and logging.
- GameModule defines game state shape, rules, available actions, action handlers, observations, and terminal conditions.
- PlayerController decides what a player wants to do.
- LLMController is a PlayerController backed by an LLM provider.
- MessagingService routes player-to-player messages.

## Core Contracts

### GameModule

A GameModule should expose:

```text
getInfo() -> GameInfo
createInitialState(players, seed) -> GameState
getObservation(state, playerId) -> Observation
getAvailableActions(state, playerId) -> ActionDefinition[]
getResult(state) -> GameResult
isTerminal(state) -> Boolean
```

A GameModule should also expose an action registry:

```text
actions: Map<ActionName, ActionDefinition>
```

Each ActionDefinition should contain:

```text
name
description
inputSchema
canUse(state, playerId) -> Boolean
handler(state, playerId, input, context) -> ActionResult
```

### Player Intent

Controllers return structured intent:

```text
{
  action: string,
  input: object,
  message?: string,
  rationale?: string
}
```

The Engine rejects intents with unknown actions, unavailable actions, or invalid input.

### ActionResult

Action handlers return:

```text
{
  success: boolean,
  statePatch?: object,
  events?: Event[],
  messages?: Message[],
  error?: string
}
```

The Engine applies state changes and records events.

## Implementation Phase 1: Framework Core

Implement the minimum framework pieces:

- Engine.
- GameModule interface.
- GameState storage in Engine.
- PlayerController interface.
- ScriptedController for tests.
- PlayerIntent structure.
- ActionDefinition structure.
- ActionResult structure.
- Basic event logger.
- Run configuration.

Engine loop:

```text
1. Load GameModule.
2. Create initial state.
3. While game is not terminal:
   - For each active player, build Observation.
   - Ask controller for PlayerIntent.
   - Validate action exists.
   - Validate action is available.
   - Validate input schema.
   - Call action handler.
   - Apply ActionResult.
   - Record events.
   - Check limits.
4. Return GameResult.
```

Keep this first version turn-based and sequential unless the first game requires simultaneous input.

## Implementation Phase 2: First GameModule

Implement Split or Steal.

Game state:

- Players.
- Current phase.
- Conversation messages.
- Player choices.
- Scores.
- Turn/message limits.

Actions:

- `send_message`
- `choose_split`
- `choose_steal`
- `end_turn` or `ready`

Flow:

```text
1. Setup.
2. Conversation phase.
3. Choice phase.
4. Resolution.
5. End.
```

Acceptance criteria:

- Game runs with two ScriptedControllers.
- Both split/steal outcomes work.
- Invalid actions are rejected.
- Game always terminates.

## Implementation Phase 3: LLM Integration

Implement:

- LLMProvider interface.
- LLMController.
- Prompt builder from Observation and available actions.
- Structured response parser.
- Retry on invalid response.

LLM prompt should include:

- Rules visible to the player.
- Current observation.
- Available action names.
- Input schema for each action.
- Required response format.

Acceptance criteria:

- One LLM can play against one ScriptedController.
- Two LLMs can play against each other.
- Invalid LLM output is retried or converted to a deterministic fallback.

## Implementation Phase 4: GameModule Authoring Guide

Write a short guide for creating new GameModules.

The guide should explain:

- Required exported functions.
- How to define GameState.
- How to define action registry entries.
- How to write action handlers.
- How to build Observations.
- How to define terminal conditions.
- How to return ActionResult.
- What not to do.

Include Split or Steal as the reference example.

Acceptance criteria:

- A second simple GameModule can be written using only the guide.
- The second GameModule runs with ScriptedControllers.

## Implementation Phase 5: Cleanup And Extension

After the first game and LLM integration work:

- Add simultaneous-action support if not already needed.
- Add private messages.
- Add better state patching or state snapshots.
- Add stronger schema validation.
- Add better run configuration.
- Add more GameModules.

## Design Rules

- Engine stores the live GameState object.
- GameModule defines the GameState type and all legal state transitions.
- GameModule action handlers are called only through the action registry.
- Controllers never mutate GameState directly.
- LLMs never call GameModule functions directly.
- GameModules do not call LLM APIs directly.
- GameModules do not use unbounded loops.
- GameModules do not use system randomness directly.
- Engine enforces global limits.
- Engine validates action name, availability, and input before calling handlers.
