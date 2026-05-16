# Claude Code Built-in Tools Complete Reference

> This document contains the complete information for all built-in tools in Claude Code, including tool name, full description/prompt, and full input_schema (JSON Schema format).
>
> Generated from source code at `src/tools/` — tool registration is in `src/tools.ts:getAllBaseTools()`.

---

## Table of Contents

1. [Bash](#1-bash)
2. [Read](#2-read)
3. [Edit](#3-edit)
4. [Write](#4-write)
5. [Glob](#5-glob)
6. [Grep](#6-grep)
7. [WebFetch](#7-webfetch)
8. [WebSearch](#8-websearch)
9. [NotebookEdit](#9-notebookedit)
10. [TodoWrite](#10-todowrite)
11. [Agent](#11-agent)
12. [TaskOutput](#12-taskoutput)
13. [TaskStop](#13-taskstop)
14. [AskUserQuestion](#14-askuserquestion)
15. [Skill](#15-skill)
16. [EnterPlanMode](#16-enterplanmode)
17. [ExitPlanMode](#17-exitplanmode)
18. [EnterWorktree](#18-enterworktree)
19. [ExitWorktree](#19-exitworktree)
20. [SendMessage](#20-sendmessage)
21. [TaskCreate](#21-taskcreate)
22. [TaskGet](#22-taskget)
23. [TaskUpdate](#23-taskupdate)
24. [TaskList](#24-tasklist)
25. [TeamCreate](#25-teamcreate)
26. [TeamDelete](#26-teamdelete)
27. [ListMcpResources](#27-listmcpresources)
28. [ReadMcpResource](#28-readmcpresource)
29. [ToolSearch](#29-toolsearch)
30. [Brief / SendUserMessage](#30-brief--sendusermessage)
31. [Config](#31-config)
32. [LSP](#32-lsp)
33. [MCP](#33-mcp)
34. [PowerShell](#34-powershell)
35. [CronCreate](#35-croncreate)
36. [CronDelete](#36-crondelete)
37. [CronList](#37-cronlist)
38. [RemoteTrigger](#38-remotetrigger)
39. [Sleep](#39-sleep)

---

## 1. Bash

**Tool Name:** `Bash`
**Source:** `src/tools/BashTool/`

### Full Description

```
Executes a given bash command and returns its output.

The working directory persists between commands, but shell state does not. The shell environment is initialized from the user's profile (bash or zsh).

IMPORTANT: Avoid using this tool to run `find`, `grep`, `cat`, `head`, `tail`, `sed`, `awk`, or `echo` commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:

 - File search: Use Glob (NOT find or ls)
 - Content search: Use Grep (NOT grep or rg)
 - Read files: Use Read (NOT cat/head/tail)
 - Edit files: Use Edit (NOT sed/awk)
 - Write files: Use Write (NOT echo >/cat <<EOF)
 - Communication: Output text directly (NOT echo/printf)

While the Bash tool can do similar things, it's better to use the built-in tools as they provide a better user experience and make it easier to review tool calls and give permission.

# Instructions
 - If your command will create new directories or files, first use this tool to run `ls` to verify the parent directory exists and is the correct location.
 - Always quote file paths that contain spaces with double quotes in your command (e.g., cd "path with spaces/file.txt")
 - Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly requests it. In particular, never prepend `cd <current-directory>` to a `git` command — `git` already operates on the current working tree, and the compound triggers a permission prompt.
 - You may specify an optional timeout in milliseconds (up to 600000ms / 10 minutes). By default, your command will timeout after 120000ms (2 minutes).
 - You can use the `run_in_background` parameter to run the command in the background. Only use this if you don't need the result immediately and are OK being notified when the command completes later. You do not need to check the output right away - you'll be notified when it finishes. You do not need to use '&' at the end of the command when using this parameter.
 - When issuing multiple commands:
   - If the commands are independent and can run in parallel, make multiple Bash tool calls in a single message. Example: if you need to run "git status" and "git diff", send a single message with two Bash tool calls in parallel.
   - If the commands depend on each other and must run sequentially, use a single Bash call with '&&' to chain them together.
   - Use ';' only when you need to run commands sequentially but don't care if earlier commands fail.
   - DO NOT use newlines to separate commands (newlines are ok in quoted strings).
 - For git commands:
   - Prefer to create a new commit rather than amending an existing commit.
   - Before running destructive operations (e.g., git reset --hard, git push --force, git checkout --), consider whether there is a safer alternative that achieves the same goal. Only use destructive operations when they are truly the best approach.
   - Never skip hooks (--no-verify) or bypass signing (--no-gpg-sign, -c commit.gpgsign=false) unless the user has explicitly asked for it. If a hook fails, investigate and fix the underlying issue.
 - Avoid unnecessary `sleep` commands:
   - Do not sleep between commands that can run immediately — just run them.
   - If your command is long running and you would like to be notified when it finishes — use `run_in_background`. No sleep needed.
   - Do not retry failing commands in a sleep loop — diagnose the root cause.
   - If waiting for a background task you started with `run_in_background`, you will be notified when it completes — do not poll.
   - If you must poll an external process, use a check command (e.g. `gh run view`) rather than sleeping first.
   - If you must sleep, keep the duration short (1-5 seconds) to avoid blocking the user.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "command": {
      "type": "string",
      "description": "The command to execute"
    },
    "timeout": {
      "type": "number",
      "description": "Optional timeout in milliseconds (max 600000)"
    },
    "description": {
      "type": "string",
      "description": "Clear, concise description of what this command does in active voice. Never use words like \"complex\" or \"risk\" in the description - just describe what it does."
    },
    "run_in_background": {
      "type": "boolean",
      "description": "Set to true to run this command in the background. Use Read to read the output later."
    },
    "dangerouslyDisableSandbox": {
      "type": "boolean",
      "description": "Set this to true to dangerously override sandbox mode and run commands without sandboxing."
    }
  },
  "required": ["command"],
  "additionalProperties": false
}
```

---

## 2. Read

**Tool Name:** `Read`
**Source:** `src/tools/FileReadTool/`

### Full Description

```
Reads a file from the local filesystem. You can access any file directly by using this tool.
Assume this tool is able to read all files on the machine. If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 2000 lines starting from the beginning of the file
- You can optionally specify a line offset and limit (especially handy for long files), but it's recommended to read the whole file by not providing these parameters
- Results are returned using cat -n format, with line numbers starting at 1
- This tool allows Claude Code to read images (eg PNG, JPG, etc). When reading an image file the contents are presented visually as Claude Code is a multimodal LLM.
- This tool can read PDF files (.pdf). For large PDFs (more than 10 pages), you MUST provide the pages parameter to read specific page ranges (e.g., pages: "1-5"). Reading a large PDF without the pages parameter will fail. Maximum 20 pages per request.
- This tool can read Jupyter notebooks (.ipynb files) and returns all cells with their outputs, combining code, text, and visualizations.
- This tool can only read files, not directories. To read a directory, use an ls command via the Bash tool.
- You will regularly be asked to read screenshots. If the user provides a path to a screenshot, ALWAYS use this tool to view the file at the path. This tool will work with all temporary file paths.
- If you read a file that exists but has empty contents you will receive a system reminder warning in place of file contents.
- Do NOT re-read a file you just edited to verify — Edit/Write would have errored if the change failed, and the harness tracks file state for you.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "The absolute path to the file to read"
    },
    "offset": {
      "type": "integer",
      "minimum": 0,
      "description": "The line number to start reading from. Only provide if the file is too large to read at once"
    },
    "limit": {
      "type": "integer",
      "exclusiveMinimum": 0,
      "description": "The number of lines to read. Only provide if the file is too large to read at once."
    },
    "pages": {
      "type": "string",
      "description": "Page range for PDF files (e.g., \"1-5\", \"3\", \"10-20\"). Only applicable to PDF files. Maximum 20 pages per request."
    }
  },
  "required": ["file_path"],
  "additionalProperties": false
}
```

---

## 3. Edit

**Tool Name:** `Edit`
**Source:** `src/tools/FileEditTool/`

### Full Description

```
Performs exact string replacements in files.

Usage:
- You must use your `Read` tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file.
- When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format is: line number + tab. Everything after that is the actual file content to match. Never include any part of the line number prefix in the old_string or new_string.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- The edit will FAIL if `old_string` is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance of `old_string`.
- Use `replace_all` for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "The absolute path to the file to modify"
    },
    "old_string": {
      "type": "string",
      "description": "The text to replace"
    },
    "new_string": {
      "type": "string",
      "description": "The text to replace it with (must be different from old_string)"
    },
    "replace_all": {
      "type": "boolean",
      "default": false,
      "description": "Replace all occurrences of old_string (default false)"
    }
  },
  "required": ["file_path", "old_string", "new_string"],
  "additionalProperties": false
}
```

---

## 4. Write

**Tool Name:** `Write`
**Source:** `src/tools/FileWriteTool/`

### Full Description

```
Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- If this is an existing file, you MUST use the Read tool first to read the file's contents. This tool will fail if you did not read the file first.
- Prefer the Edit tool for modifying existing files — it only sends the diff. Only use this tool to create new files or for complete rewrites.
- NEVER create documentation files (*.md) or README files unless explicitly requested by the User.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "The absolute path to the file to write (must be absolute, not relative)"
    },
    "content": {
      "type": "string",
      "description": "The content to write to the file"
    }
  },
  "required": ["file_path", "content"],
  "additionalProperties": false
}
```

---

## 5. Glob

**Tool Name:** `Glob`
**Source:** `src/tools/GlobTool/`

### Full Description

```
- Fast file pattern matching tool that works with any codebase size
- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "pattern": {
      "type": "string",
      "description": "The glob pattern to match files against"
    },
    "path": {
      "type": "string",
      "description": "The directory to search in. Defaults to current working directory."
    }
  },
  "required": ["pattern"],
  "additionalProperties": false
}
```

---

## 6. Grep

**Tool Name:** `Grep`
**Source:** `src/tools/GrepTool/`

### Full Description

```
A powerful search tool built on ripgrep

Usage:
- ALWAYS use Grep for search tasks. NEVER invoke `grep` or `rg` as a Bash command. The Grep tool has been optimized for correct permissions and access.
- Supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")
- Filter files with glob parameter (e.g., "*.js", "**/*.tsx") or type parameter (e.g., "js", "py", "rust")
- Output modes: "content" shows matching lines, "files_with_matches" shows only file paths (default), "count" shows match counts
- Use Agent tool for open-ended searches requiring multiple rounds
- Pattern syntax: Uses ripgrep (not grep) - literal braces need escaping (use `interface\\{\\}` to find `interface{}` in Go code)
- Multiline matching: By default patterns match within single lines only. For cross-line patterns like `struct \\{[\\s\\S]*?field`, use `multiline: true`
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "pattern": {
      "type": "string",
      "description": "The regular expression pattern to search for"
    },
    "path": {
      "type": "string",
      "description": "File or directory to search in. Defaults to current working directory."
    },
    "glob": {
      "type": "string",
      "description": "Glob pattern to filter files (e.g. \"*.js\", \"*.{ts,tsx}\")"
    },
    "type": {
      "type": "string",
      "description": "File type to search. Wraps the glob for common file extensions."
    },
    "output_mode": {
      "type": "string",
      "enum": ["content", "files_with_matches", "count"],
      "description": "Output mode - content: shows matching lines, files_with_matches: shows file paths, count: shows match counts"
    },
    "-B": {
      "type": "number",
      "description": "Number of lines to show before the match"
    },
    "-A": {
      "type": "number",
      "description": "Number of lines to show after the match"
    },
    "-C": {
      "type": "number",
      "description": "Alias for context."
    },
    "context": {
      "type": "number",
      "description": "Number of lines to show before and after the match"
    },
    "-n": {
      "type": "boolean",
      "description": "Show line numbers"
    },
    "-i": {
      "type": "boolean",
      "description": "Case insensitive search"
    },
    "head_limit": {
      "type": "number",
      "description": "Maximum number of matches to return"
    },
    "offset": {
      "type": "number",
      "description": "Offset to start showing results from (useful for pagination)"
    },
    "multiline": {
      "type": "boolean",
      "description": "Enable multiline mode where patterns can match across lines"
    }
  },
  "required": ["pattern"],
  "additionalProperties": false
}
```

---

## 7. WebFetch

**Tool Name:** `WebFetch`
**Source:** `src/tools/WebFetchTool/`

### Full Description

```
- Fetches content from a specified URL and processes it using an AI model
- Takes a URL and a prompt as input
- Fetches the URL content, converts HTML to markdown
- Processes the content with the prompt using a small, fast model
- Returns the model's response about the content
- Use this tool when you need to retrieve and analyze web content

Usage notes:
  - IMPORTANT: If an MCP-provided web fetch tool is available, prefer using that tool instead of this one, as it may have fewer restrictions.
  - The URL must be a fully-formed valid URL
  - HTTP URLs will be automatically upgraded to HTTPS
  - The prompt should describe what information you want to extract from the page
  - This tool is read-only and does not modify any files
  - Results may be summarized if the content is very large
  - Includes a self-cleaning 15-minute cache for faster responses when repeatedly accessing the same URL
  - When a URL redirects to a different host, the tool will inform you and provide the redirect URL in a special format. You should then make a new WebFetch request with the redirect URL to fetch the content.
  - For GitHub URLs, prefer using the gh CLI via Bash instead (e.g., gh pr view, gh issue view, gh api).
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "format": "uri",
      "description": "The URL to fetch content from"
    },
    "prompt": {
      "type": "string",
      "description": "The prompt to run on the fetched content"
    }
  },
  "required": ["url", "prompt"],
  "additionalProperties": false
}
```

---

## 8. WebSearch

**Tool Name:** `WebSearch`
**Source:** `src/tools/WebSearchTool/`

### Full Description

```
- Allows Claude to search the web and use the results to inform responses
- Provides up-to-date information for current events and recent data
- Returns search result information formatted as search result blocks, including links as markdown hyperlinks
- Use this tool for accessing information beyond Claude's knowledge cutoff
- Searches are performed automatically within a single API call

CRITICAL REQUIREMENT - You MUST follow this:
  - After answering the user's question, you MUST include a "Sources:" section at the end of your response
  - In the Sources section, list all relevant URLs from the search results as markdown hyperlinks: [Title](URL)
  - This is MANDATORY - never skip including sources in your response

Usage notes:
  - Domain filtering is supported to include or block specific websites
  - Web search is only available in the US

IMPORTANT - Use the correct year in search queries:
  - The current month is May 2026. You MUST use this year when searching for recent information, documentation, or current events.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "minLength": 2,
      "description": "The search query to use"
    },
    "allowed_domains": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Only include search results from these domains"
    },
    "blocked_domains": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Never include search results from these domains"
    }
  },
  "required": ["query"],
  "additionalProperties": false
}
```

---

## 9. NotebookEdit

**Tool Name:** `NotebookEdit`
**Source:** `src/tools/NotebookEditTool/`

### Full Description

```
Completely replaces the contents of a specific cell in a Jupyter notebook (.ipynb file) with new source. Jupyter notebooks are interactive documents that combine code, text, and visualizations, commonly used for data analysis and scientific computing. The notebook_path parameter must be an absolute path, not a relative path. The cell_number is 0-indexed. Use edit_mode=insert to add a new cell at the index specified by cell_number. Use edit_mode=delete to delete the cell at the index specified by cell_number.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "notebook_path": {
      "type": "string",
      "description": "The absolute path to the Jupyter notebook file to edit (must be absolute, not relative)"
    },
    "cell_number": {
      "type": "integer",
      "description": "The index of the cell to edit (0-based). Use with edit_mode=replace to edit a specific cell."
    },
    "cell_id": {
      "type": "string",
      "description": "The ID of the cell to edit. When inserting a new cell, the new cell will be inserted after the cell with this ID, or at the beginning if not specified."
    },
    "new_source": {
      "type": "string",
      "description": "The new source for the cell"
    },
    "cell_type": {
      "type": "string",
      "enum": ["code", "markdown"],
      "description": "The type of the cell (code or markdown). Required when edit_mode=insert."
    },
    "edit_mode": {
      "type": "string",
      "enum": ["replace", "insert", "delete"],
      "description": "The type of edit to make. Defaults to replace."
    }
  },
  "required": ["notebook_path", "new_source"],
  "additionalProperties": false
}
```

---

## 10. TodoWrite

**Tool Name:** `TodoWrite`
**Source:** `src/tools/TodoWriteTool/`

### Full Description

```
Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool

Use this tool proactively in these scenarios:

1. Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos
6. When you start working on a task - Mark it as in_progress BEFORE beginning work
7. After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Exactly ONE task must be in_progress at any time (not less, not more)

3. **Task Completion Requirements**:
   - ONLY mark a task as completed when you have FULLY accomplished it
   - If you encounter errors, blockers, or cannot finish, keep the task as in_progress
   - Never mark a task as completed if:
     - Tests are failing
     - Implementation is partial
     - You encountered unresolved errors
     - You couldn't find necessary files or dependencies

4. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names
   - Always provide both forms:
     - content: "Fix authentication bug"
     - activeForm: "Fixing authentication bug"
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "todos": {
      "type": "array",
      "description": "The updated todo list",
      "items": {
        "type": "object",
        "properties": {
          "content": { "type": "string", "description": "The task content (imperative form)" },
          "activeForm": { "type": "string", "description": "Present continuous form (e.g., 'Running tests')" },
          "status": { "type": "string", "enum": ["pending", "in_progress", "completed"] }
        },
        "required": ["content", "status"]
      }
    }
  },
  "required": ["todos"],
  "additionalProperties": false
}
```

---

## 11. Agent

**Tool Name:** `Agent`
**Legacy Name:** `Task`
**Source:** `src/tools/AgentTool/`

### Full Description

```
Launch a new agent to handle complex, multi-step tasks autonomously.

The Agent tool launches specialized agents (subprocesses) that autonomously handle complex tasks. Each agent type has specific capabilities and tools available to it.

Available agent types and the tools they have access to:
( Dynamically populated at runtime — see formatAgentLine() in prompt.ts )

When using the Agent tool, specify a subagent_type parameter to select which agent type to use. If omitted, the general-purpose agent is used.

When NOT to use the Agent tool:
- If you want to read a specific file path, use the Read tool or the Glob tool instead of the Agent tool, to find the match more quickly
- If you are searching for a specific class definition like "class Foo", use the Glob tool instead, to find the match more quickly
- If you are searching for code within a specific file or set of 2-3 files, use the Read tool instead of the Agent tool, to find the match more quickly
- Other tasks that are not related to the agent descriptions above

Usage notes:
- Always include a short description (3-5 words) summarizing what the agent will do
- Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
- When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
- You can optionally run agents in the background using the run_in_background parameter. When an agent runs in the background, you will be automatically notified when it completes — do NOT sleep, poll, or proactively check on its progress. Continue with other work or respond to the user instead.
- **Foreground vs background**: Use foreground (default) when you need the agent's results before you can proceed — e.g., research agents whose findings inform your next steps. Use background when you have genuinely independent work to do in parallel.
- To continue a previously spawned agent, use SendMessage with the agent's ID or name as the `to` field. The agent resumes with its full context preserved. Each Agent invocation starts fresh — provide a complete task description.
- The agent's outputs should generally be trusted
- Clearly tell the agent whether you expect it to write code or just to do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent
- If the agent description mentions that it should be used proactively, then you should try your best to use it without the user having to ask for it first.
- If the user specifies that they want you to run agents "in parallel", you MUST send a single message with multiple Agent tool use content blocks.
- You can optionally set `isolation: "worktree"` to run the agent in a temporary git worktree, giving it an isolated copy of the repository.

## Writing the prompt

Brief the agent like a smart colleague who just walked into the room — it hasn't seen this conversation, doesn't know what you've tried, doesn't understand why this task matters.
- Explain what you're trying to accomplish and why.
- Describe what you've already learned or ruled out.
- Give enough context about the surrounding problem that the agent can make judgment calls rather than just following a narrow instruction.
- If you need a short response, say so ("report in under 200 words").
- Lookups: hand over the exact command. Investigations: hand over the question — prescribed steps become dead weight when the premise is wrong.

Terse command-style prompts produce shallow, generic work.

**Never delegate understanding.** Don't write "based on your findings, fix the bug" or "based on the research, implement it." Those phrases push synthesis onto the agent instead of doing it yourself. Write prompts that prove you understood: include file paths, line numbers, what specifically to change.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "description": {
      "type": "string",
      "description": "A short (3-5 word) description of the task"
    },
    "prompt": {
      "type": "string",
      "description": "The task for the agent to perform"
    },
    "subagent_type": {
      "type": "string",
      "description": "The type of specialized agent to use for this task"
    },
    "model": {
      "type": "string",
      "enum": ["sonnet", "opus", "haiku"],
      "description": "Optional model override for this agent. Takes precedence over the agent definition's model frontmatter. If omitted, uses the agent definition's model, or inherits from the parent."
    },
    "run_in_background": {
      "type": "boolean",
      "description": "Set to true to run this agent in the background. You will be notified when it completes."
    },
    "name": {
      "type": "string",
      "description": "Name for the spawned agent. Makes it addressable via SendMessage({to: name}) while running."
    },
    "team_name": {
      "type": "string",
      "description": "Team name for spawning. Uses current team context if omitted."
    },
    "mode": {
      "type": "string",
      "enum": ["acceptEdits", "auto", "bypassPermissions", "default", "dontAsk", "plan"],
      "description": "Permission mode for spawned teammate (e.g., \"plan\" to require plan approval)."
    },
    "isolation": {
      "type": "string",
      "enum": ["worktree"],
      "description": "Isolation mode. \"worktree\" creates a temporary git worktree so the agent works on an isolated copy of the repo."
    },
    "cwd": {
      "type": "string",
      "description": "Absolute path to run the agent in. Overrides the working directory for all filesystem and shell operations within this agent. Mutually exclusive with isolation: \"worktree\"."
    }
  },
  "required": ["description", "prompt"]
}
```

---

## 12. TaskOutput

**Tool Name:** `TaskOutput`
**Source:** `src/tools/TaskOutputTool/`

### Full Description

```
DEPRECATED: Background tasks return their output file path in the tool result, and you receive a <task-notification> with the same path when the task completes.
- For bash tasks: prefer using the Read tool on that output file path — it contains stdout/stderr.
- For local_agent tasks: use the Agent tool result directly. Do NOT Read the .output file — it is a symlink to the full sub-agent conversation transcript (JSONL) and will overflow your context window.
- For remote_agent tasks: prefer using the Read tool on the output file path — it contains the streamed remote session output (same as bash).

- Retrieves output from a running or completed task (background shell, agent, or remote session)
- Takes a task_id parameter identifying the task
- Returns the task output along with status information
- Use block=true (default) to wait for task completion
- Use block=false for non-blocking check of current status
- Task IDs can be found using the /tasks command
- Works with all task types: background shells, async agents, and remote sessions
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "task_id": {
      "type": "string",
      "description": "The task ID to get output from"
    },
    "block": {
      "type": "boolean",
      "default": true,
      "description": "Whether to wait for completion"
    },
    "timeout": {
      "type": "number",
      "minimum": 0,
      "maximum": 600000,
      "default": 30000,
      "description": "Max wait time in ms"
    }
  },
  "required": ["task_id"],
  "additionalProperties": false
}
```

---

## 13. TaskStop

**Tool Name:** `TaskStop`
**Source:** `src/tools/TaskStopTool/`

### Full Description

```
- Stops a running background task by its ID
- Takes a task_id parameter identifying the task to stop
- Returns a success or failure status
- Use this tool when you need to terminate a long-running task
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "task_id": {
      "type": "string",
      "description": "The ID of the background task to stop"
    },
    "shell_id": {
      "type": "string",
      "description": "Deprecated: use task_id instead"
    }
  },
  "additionalProperties": false
}
```

---

## 14. AskUserQuestion

**Tool Name:** `AskUserQuestion`
**Source:** `src/tools/AskUserQuestionTool/`

### Full Description

```
Use this tool when you need to ask the user questions during execution. This allows you to:
1. Gather user preferences or requirements
2. Clarify ambiguous instructions
3. Get decisions on implementation choices as you work
4. Offer choices to the user about what direction to take.

Usage notes:
- Users will always be able to select "Other" to provide custom text input
- Use multiSelect: true to allow multiple answers to be selected for a question
- If you recommend a specific option, make that the first option in the list and add "(Recommended)" at the end of the label

Preview feature:
Use the optional `preview` field on options when presenting concrete artifacts that users need to visually compare:
- ASCII mockups of UI layouts or components
- Code snippets showing different implementations
- Diagram variations
- Configuration examples

Preview content is rendered as markdown in a monospace box. Multi-line text with newlines is supported. When any option has a preview, the UI switches to a side-by-side layout with a vertical option list on the left and preview on the right. Do not use previews for simple preference questions where labels and descriptions suffice. Note: previews are only supported for single-select questions (not multiSelect).

Plan mode note: In plan mode, use this tool to clarify requirements or choose between approaches BEFORE finalizing your plan. Do NOT use this tool to ask "Is my plan ready?" or "Should I proceed?" - use ExitPlanMode for plan approval. IMPORTANT: Do not reference "the plan" in your questions.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "questions": {
      "type": "array",
      "minItems": 1,
      "maxItems": 4,
      "description": "Questions to ask the user (1-4 questions)",
      "items": {
        "type": "object",
        "properties": {
          "question": {
            "type": "string",
            "description": "The complete question to ask the user. Should be clear, specific, and end with a question mark."
          },
          "header": {
            "type": "string",
            "description": "Very short label displayed as a chip/tag (max 12 chars). Examples: \"Auth method\", \"Library\", \"Approach\"."
          },
          "options": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "description": "The available choices for this question. Must have 2-4 options.",
            "items": {
              "type": "object",
              "properties": {
                "label": {
                  "type": "string",
                  "description": "The display text for this option. Should be concise (1-5 words)."
                },
                "description": {
                  "type": "string",
                  "description": "Explanation of what this option means or what will happen if chosen."
                },
                "preview": {
                  "type": "string",
                  "description": "Optional preview content rendered when this option is focused."
                }
              },
              "required": ["label", "description"]
            }
          },
          "multiSelect": {
            "type": "boolean",
            "default": false,
            "description": "Set to true to allow the user to select multiple options instead of just one."
          }
        },
        "required": ["question", "header", "options", "multiSelect"]
      }
    },
    "answers": {
      "type": "object",
      "additionalProperties": { "type": "string" },
      "description": "User answers collected by the permission component"
    },
    "metadata": {
      "type": "object",
      "properties": {
        "source": {
          "type": "string",
          "description": "Optional identifier for the source of this question."
        }
      }
    }
  },
  "required": ["questions"],
  "additionalProperties": false
}
```

---

## 15. Skill

**Tool Name:** `Skill`
**Source:** `src/tools/SkillTool/`

### Full Description

```
Execute a skill within the main conversation

When users ask you to perform tasks, check if any of the available skills match. Skills provide specialized capabilities and domain knowledge.

When users reference a "slash command" or "/<something>" (e.g., "/commit", "/review-pr"), they are referring to a skill. Use this tool to invoke it.

How to invoke:
- Use this tool with the skill name and optional arguments
- Examples:
  - `skill: "pdf"` - invoke the pdf skill
  - `skill: "commit", args: "-m 'Fix bug'"` - invoke with arguments
  - `skill: "review-pr", args: "123"` - invoke with arguments
  - `skill: "ms-office-suite:pdf"` - invoke using fully qualified name

Important:
- Available skills are listed in system-reminder messages in the conversation
- When a skill matches the user's request, this is a BLOCKING REQUIREMENT: invoke the relevant Skill tool BEFORE generating any other response about the task
- NEVER mention a skill without actually calling this tool
- Do not invoke a skill that is already running
- Do not use this tool for built-in CLI commands (like /help, /clear, etc.)
- If you see a <command-name> tag in the current conversation turn, the skill has ALREADY been loaded - follow the instructions directly instead of calling this tool again
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "skill": {
      "type": "string",
      "description": "The name of a skill from the available-skills list. Do not guess names."
    },
    "args": {
      "type": "string",
      "description": "Optional arguments for the skill"
    }
  },
  "required": ["skill"]
}
```

---

## 16. EnterPlanMode

**Tool Name:** `EnterPlanMode`
**Source:** `src/tools/EnterPlanModeTool/`

### Full Description

```
Use this tool proactively when you're about to start a non-trivial implementation task. Getting user sign-off on your approach before writing code prevents wasted effort and ensures alignment. This tool transitions you into plan mode where you can explore the codebase and design an implementation approach for user approval.

## When to Use This Tool

**Prefer using EnterPlanMode** for implementation tasks unless they're simple. Use it when ANY of these conditions apply:

1. **New Feature Implementation**: Adding meaningful new functionality
2. **Multiple Valid Approaches**: The task can be solved in several different ways
3. **Code Modifications**: Changes that affect existing behavior or structure
4. **Architectural Decisions**: The task requires choosing between patterns or technologies
5. **Multi-File Changes**: The task will likely touch more than 2-3 files
6. **Unclear Requirements**: You need to explore before understanding the full scope
7. **User Preferences Matter**: The implementation could reasonably go multiple ways

## When NOT to Use This Tool

Only skip EnterPlanMode for simple tasks:
- Single-line or few-line fixes (typos, obvious bugs, small tweaks)
- Adding a single function with clear requirements
- Tasks where the user has given very specific, detailed instructions
- Pure research/exploration tasks (use the Agent tool with explore agent instead)

## What Happens in Plan Mode

In plan mode, you'll:
1. Thoroughly explore the codebase using Glob, Grep, and Read tools
2. Understand existing patterns and architecture
3. Design an implementation approach
4. Present your plan to the user for approval
5. Use AskUserQuestion if you need to clarify approaches
6. Exit plan mode with ExitPlanMode when ready to implement

## Important Notes

- This tool REQUIRES user approval - they must consent to entering plan mode
- If unsure whether to use it, err on the side of planning - it's better to get alignment upfront than to redo work
- Users appreciate being consulted before significant changes are made to their codebase
```

### input_schema

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

---

## 17. ExitPlanMode

**Tool Name:** `ExitPlanMode`
**Source:** `src/tools/ExitPlanModeTool/`

### Full Description

```
Use this tool when you are in plan mode and have finished writing your plan to the plan file and are ready for user approval.

## How This Tool Works
- You should have already written your plan to the plan file specified in the plan mode system message
- This tool does NOT take the plan content as a parameter - it will read the plan from the file you wrote
- This tool simply signals that you're done planning and ready for the user to review and approve
- The user will see the contents of your plan file when they review it

## When to Use This Tool
IMPORTANT: Only use this tool when the task requires planning the implementation steps of a task that requires writing code. For research tasks where you're gathering information, searching files, reading files or in general trying to understand the codebase - do NOT use this tool.

## Before Using This Tool
Ensure your plan is complete and unambiguous:
- If you have unresolved questions about requirements or approach, use AskUserQuestion first (in earlier phases)
- Once your plan is finalized, use THIS tool to request approval

**Important:** Do NOT use AskUserQuestion to ask "Is this plan okay?" or "Should I proceed?" - that's exactly what THIS tool does. ExitPlanMode inherently requests user approval of your plan.
```

### input_schema

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

---

## 18. EnterWorktree

**Tool Name:** `EnterWorktree`
**Source:** `src/tools/EnterWorktreeTool/`

### Full Description

```
Use this tool ONLY when the user explicitly asks to work in a worktree. This tool creates an isolated git worktree and switches the current session into it.

## When to Use

- The user explicitly says "worktree" (e.g., "start a worktree", "work in a worktree", "create a worktree", "use a worktree")

## When NOT to Use

- The user asks to create a branch, switch branches, or work on a different branch — use git commands instead
- The user asks to fix a bug or work on a feature — use normal git workflow unless they specifically mention worktrees
- Never use this tool unless the user explicitly mentions "worktree"

## Requirements

- Must be in a git repository, OR have WorktreeCreate/WorktreeRemove hooks configured in settings.json
- Must not already be in a worktree

## Behavior

- In a git repository: creates a new git worktree inside `.claude/worktrees/` with a new branch based on HEAD
- Outside a git repository: delegates to WorktreeCreate/WorktreeRemove hooks for VCS-agnostic isolation
- Switches the session's working directory to the new worktree
- Use ExitWorktree to leave the worktree mid-session (keep or remove). On session exit, if still in the worktree, the user will be prompted to keep or remove it

## Parameters

- `name` (optional): A name for the worktree. If not provided, a random name is generated.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Optional name for the worktree. Will be used as branch name."
    },
    "path": {
      "type": "string",
      "description": "Path to an existing worktree to enter (alternative to creating a new one)"
    }
  },
  "additionalProperties": false
}
```

---

## 19. ExitWorktree

**Tool Name:** `ExitWorktree`
**Source:** `src/tools/ExitWorktreeTool/`

### Full Description

```
Exit a worktree session created by EnterWorktree and return the session to the original working directory.

## Scope

This tool ONLY operates on worktrees created by EnterWorktree in this session. It will NOT touch:
- Worktrees you created manually with `git worktree add`
- Worktrees from a previous session (even if created by EnterWorktree then)
- The directory you're in if EnterWorktree was never called

If called outside an EnterWorktree session, the tool is a **no-op**: it reports that no worktree session is active and takes no action. Filesystem state is unchanged.

## When to Use

- The user explicitly asks to "exit the worktree", "leave the worktree", "go back", or otherwise end the worktree session
- Do NOT call this proactively — only when the user asks

## Parameters

- `action` (required): `"keep"` or `"remove"`
  - `"keep"` — leave the worktree directory and branch intact on disk.
  - `"remove"` — delete the worktree directory and its branch.
- `discard_changes` (optional, default false): only meaningful with `action: "remove"`. If the worktree has uncommitted files or commits not on the original branch, the tool will REFUSE to remove it unless this is set to `true`.

## Behavior

- Restores the session's working directory to where it was before EnterWorktree
- Clears CWD-dependent caches (system prompt sections, memory files, plans directory) so the session state reflects the original directory
- If a tmux session was attached to the worktree: killed on `remove`, left running on `keep`
- Once exited, EnterWorktree can be called again to create a fresh worktree
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["keep", "remove"],
      "description": "\"keep\" leaves the worktree on disk; \"remove\" deletes it."
    },
    "discard_changes": {
      "type": "boolean",
      "default": false,
      "description": "Required true when action is \"remove\" and the worktree has uncommitted files or unmerged commits."
    }
  },
  "required": ["action"],
  "additionalProperties": false
}
```

---

## 20. SendMessage

**Tool Name:** `SendMessage`
**Source:** `src/tools/SendMessageTool/`

### Full Description

```
# SendMessage

Send a message to another agent.

```json
{"to": "researcher", "summary": "assign task 1", "message": "start on task #1"}
```

| `to` | |
|---|---|
| `"researcher"` | Teammate by name |
| `"*"` | Broadcast to all teammates — expensive (linear in team size), use only when everyone genuinely needs it |

Your plain text output is NOT visible to other agents — to communicate, you MUST call this tool. Messages from teammates are delivered automatically; you don't check an inbox. Refer to teammates by name, never by UUID. When relaying, don't quote the original — it's already rendered to the user.

## Protocol responses (legacy)

If you receive a JSON message with `type: "shutdown_request"` or `type: "plan_approval_request"`, respond with the matching `_response` type — echo the `request_id`, set `approve` true/false:

```json
{"to": "team-lead", "message": {"type": "shutdown_response", "request_id": "...", "approve": true}}
{"to": "researcher", "message": {"type": "plan_approval_response", "request_id": "...", "approve": false, "feedback": "add error handling"}}
```

Approving shutdown terminates your process. Rejecting plan sends the teammate back to revise. Don't originate `shutdown_request` unless asked. Don't send structured JSON status messages — use TaskUpdate.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "to": {
      "type": "string",
      "description": "Recipient: teammate name"
    },
    "summary": {
      "type": "string",
      "description": "A 5-10 word summary shown as a preview in the UI (required when message is a string)"
    },
    "message": {
      "oneOf": [
        { "type": "string", "description": "Plain text message content" },
        {
          "type": "object",
          "properties": {
            "type": { "type": "string" },
            "request_id": { "type": "string" },
            "approve": { "type": "boolean" },
            "reason": { "type": "string" },
            "feedback": { "type": "string" }
          }
        }
      ],
      "description": "The message to send"
    }
  },
  "required": ["to", "message"]
}
```

---

## 21. TaskCreate

**Tool Name:** `TaskCreate`
**Source:** `src/tools/TaskCreateTool/`

### Full Description

```
Use this tool to create a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool

Use this tool proactively in these scenarios:

- Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
- Non-trivial and complex tasks - Tasks that require careful planning or multiple operations and potentially assigned to teammates
- Plan mode - When using plan mode, create a task list to track the work
- User explicitly requests todo list - When the user directly asks you to use the todo list
- User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
- After receiving new instructions - Immediately capture user requirements as tasks
- When you start working on a task - Mark it as in_progress BEFORE beginning work
- After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation

## When NOT to Use This Tool

Skip using this tool when:
- There is only a single, straightforward task
- The task is trivial and tracking it provides no organizational benefit
- The task can be completed in less than 3 trivial steps
- The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to do.

## Task Fields

- **subject**: A brief, actionable title in imperative form (e.g., "Fix authentication bug in login flow")
- **description**: What needs to be done
- **activeForm** (optional): Present continuous form shown in the spinner when the task is in_progress (e.g., "Fixing authentication bug"). If omitted, the spinner shows the subject instead.

All tasks are created with status `pending`.

## Tips

- Create tasks with clear, specific subjects that describe the outcome
- After creating tasks, use TaskUpdate to set up dependencies (blocks/blockedBy) if needed
- Include enough detail in the description for another agent to understand and complete the task
- New tasks are created with status 'pending' and no owner - use TaskUpdate with the `owner` parameter to assign them
- Check TaskList first to avoid creating duplicate tasks
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "subject": {
      "type": "string",
      "description": "A brief title for the task"
    },
    "description": {
      "type": "string",
      "description": "What needs to be done"
    },
    "activeForm": {
      "type": "string",
      "description": "Present continuous form shown in the spinner when the task is in_progress"
    },
    "metadata": {
      "type": "object",
      "additionalProperties": {},
      "description": "Arbitrary metadata to attach to the task"
    }
  },
  "required": ["subject", "description"],
  "additionalProperties": false
}
```

---

## 22. TaskGet

**Tool Name:** `TaskGet`
**Source:** `src/tools/TaskGetTool/`

### Full Description

```
Use this tool to retrieve a task by its ID from the task list.

## When to Use This Tool

- When you need the full description and context before starting work on a task
- To understand task dependencies (what it blocks, what blocks it)
- After being assigned a task, to get complete requirements

## Output

Returns full task details:
- **subject**: Task title
- **description**: Detailed requirements and context
- **status**: 'pending', 'in_progress', or 'completed'
- **blocks**: Tasks waiting on this one to complete
- **blockedBy**: Tasks that must complete before this one can start

## Tips

- After fetching a task, verify its blockedBy list is empty before beginning work.
- Use TaskList to see all tasks in summary form.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "taskId": {
      "type": "string",
      "description": "The ID of the task to retrieve"
    }
  },
  "required": ["taskId"],
  "additionalProperties": false
}
```

---

## 23. TaskUpdate

**Tool Name:** `TaskUpdate`
**Source:** `src/tools/TaskUpdateTool/`

### Full Description

```
Use this tool to update a task in the task list.

## When to Use This Tool

**Mark tasks as resolved:**
- When you have completed the work described in a task
- When a task is no longer needed or has been superseded
- IMPORTANT: Always mark your assigned tasks as resolved when you finish them
- After resolving, call TaskList to find your next task

- ONLY mark a task as completed when you have FULLY accomplished it
- If you encounter errors, blockers, or cannot finish, keep the task as in_progress
- When blocked, create a new task describing what needs to be resolved
- Never mark a task as completed if:
  - Tests are failing
  - Implementation is partial
  - You encountered unresolved errors
  - You couldn't find necessary files or dependencies

**Delete tasks:**
- When a task is no longer relevant or was created in error
- Setting status to `deleted` permanently removes the task

**Update task details:**
- When requirements change or become clearer
- When establishing dependencies between tasks

## Fields You Can Update

- **status**: The task status (see Status Workflow below)
- **subject**: Change the task title (imperative form, e.g., "Run tests")
- **description**: Change the task description
- **activeForm**: Present continuous form shown in spinner when in_progress (e.g., "Running tests")
- **owner**: Change the task owner (agent name)
- **metadata**: Merge metadata keys into the task (set a key to null to delete it)
- **addBlocks**: Mark tasks that cannot start until this one completes
- **addBlockedBy**: Mark tasks that must complete before this one can start

## Status Workflow

Status progresses: `pending` → `in_progress` → `completed`

Use `deleted` to permanently remove a task.

## Staleness

Make sure to read a task's latest state using `TaskGet` before updating it.

## Examples

Mark task as in progress when starting work:
```json
{"taskId": "1", "status": "in_progress"}
```

Mark task as completed after finishing work:
```json
{"taskId": "1", "status": "completed"}
```

Delete a task:
```json
{"taskId": "1", "status": "deleted"}
```

Claim a task by setting owner:
```json
{"taskId": "1", "owner": "my-name"}
```

Set up task dependencies:
```json
{"taskId": "2", "addBlockedBy": ["1"]}
```
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "taskId": {
      "type": "string",
      "description": "The ID of the task to update"
    },
    "subject": {
      "type": "string",
      "description": "New subject for the task"
    },
    "description": {
      "type": "string",
      "description": "New description for the task"
    },
    "activeForm": {
      "type": "string",
      "description": "Present continuous form shown in spinner when in_progress (e.g., \"Running tests\")"
    },
    "status": {
      "oneOf": [
        { "type": "string", "enum": ["pending", "in_progress", "completed"] },
        { "type": "string", "const": "deleted" }
      ],
      "description": "New status for the task"
    },
    "addBlocks": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Task IDs that this task blocks"
    },
    "addBlockedBy": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Task IDs that block this task"
    },
    "owner": {
      "type": "string",
      "description": "New owner for the task"
    },
    "metadata": {
      "type": "object",
      "additionalProperties": {},
      "description": "Metadata keys to merge into the task. Set a key to null to delete it."
    }
  },
  "required": ["taskId"],
  "additionalProperties": false
}
```

---

## 24. TaskList

**Tool Name:** `TaskList`
**Source:** `src/tools/TaskListTool/`

### Full Description

```
Use this tool to list all tasks in the task list.

## When to Use This Tool

- To see what tasks are available to work on (status: 'pending', no owner, not blocked)
- To check overall progress on the project
- To find tasks that are blocked and need dependencies resolved
- Before assigning tasks to teammates, to see what's available
- After completing a task, to check for newly unblocked work or claim the next available task
- **Prefer working on tasks in ID order** (lowest ID first) when multiple tasks are available

## Output

Returns a summary of each task:
- **id**: Task identifier (use with TaskGet, TaskUpdate)
- **subject**: Brief description of the task
- **status**: 'pending', 'in_progress', or 'completed'
- **owner**: Agent ID if assigned, empty if available
- **blockedBy**: List of open task IDs that must be resolved first

Use TaskGet with a specific task ID to view full details including description and comments.

## Teammate Workflow

When working as a teammate:
1. After completing your current task, call TaskList to find available work
2. Look for tasks with status 'pending', no owner, and empty blockedBy
3. **Prefer tasks in ID order** (lowest ID first) when multiple tasks are available
4. Claim an available task using TaskUpdate (set `owner` to your name), or wait for leader assignment
5. If blocked, focus on unblocking tasks or notify the team lead
```

### input_schema

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

---

## 25. TeamCreate

**Tool Name:** `TeamCreate`
**Source:** `src/tools/TeamCreateTool/`

### Full Description

```
# TeamCreate

## When to Use

Use this tool proactively whenever:
- The user explicitly asks to use a team, swarm, or group of agents
- The user mentions wanting agents to work together, coordinate, or collaborate
- A task is complex enough that it would benefit from parallel work by multiple agents

When in doubt about whether a task warrants a team, prefer spawning a team.

## Choosing Agent Types for Teammates

When spawning teammates via the Agent tool, choose the `subagent_type` based on what tools the agent needs for its task:
- **Read-only agents** (e.g., Explore, Plan) cannot edit or write files.
- **Full-capability agents** (e.g., general-purpose) have access to all tools.
- **Custom agents** defined in `.claude/agents/` may have their own tool restrictions.

Create a new team to coordinate multiple agents working on a project. Teams have a 1:1 correspondence with task lists (Team = TaskList).

```
{
  "team_name": "my-project",
  "description": "Working on feature X"
}
```

This creates:
- A team file at `~/.claude/teams/{team-name}/config.json`
- A corresponding task list directory at `~/.claude/tasks/{team-name}/`

## Team Workflow

1. **Create a team** with TeamCreate
2. **Create tasks** using the Task tools
3. **Spawn teammates** using the Agent tool with `team_name` and `name` parameters
4. **Assign tasks** using TaskUpdate with `owner`
5. **Teammates work on assigned tasks** and mark them completed via TaskUpdate
6. **Teammates go idle between turns** - after each turn, teammates automatically go idle and send a notification
7. **Shutdown your team** - gracefully shut down teammates via SendMessage with `message: {type: "shutdown_request"}`

## Task Ownership

Tasks are assigned using TaskUpdate with the `owner` parameter. Any agent can set or change task ownership.

## Automatic Message Delivery

**IMPORTANT**: Messages from teammates are automatically delivered to you. You do NOT need to manually check your inbox.

## Teammate Idle State

Teammates go idle after every turn—this is completely normal and expected. Idle simply means they are waiting for input.

## Discovering Team Members

Teammates can read the team config file to discover other team members:
- **Team config location**: `~/.claude/teams/{team-name}/config.json`

The config file contains a `members` array with each teammate's:
- `name`: Human-readable name (**always use this** for messaging and task assignment)
- `agentId`: Unique identifier (for reference only - do not use for communication)
- `agentType`: Role/type of the agent

**IMPORTANT**: Always refer to teammates by their NAME.

## Task List Coordination

Teams share a task list that all teammates can access at `~/.claude/tasks/{team-name}/`.

Teammates should:
1. Check TaskList periodically
2. Claim unassigned, unblocked tasks with TaskUpdate (set `owner` to your name)
3. Create new tasks with `TaskCreate` when identifying additional work
4. Mark tasks as completed with `TaskUpdate` when done
5. Coordinate with other teammates by reading the task list status
6. If all available tasks are blocked, notify the team lead

**IMPORTANT notes for communication with your team**:
- Do not use terminal tools to view your team's activity; always send a message to your teammates
- Your team cannot hear you if you do not use the SendMessage tool
- Do NOT send structured JSON status messages — just communicate in plain text
- Use TaskUpdate to mark tasks completed
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "team_name": {
      "type": "string",
      "description": "Name for the new team to create."
    },
    "description": {
      "type": "string",
      "description": "Team description/purpose."
    },
    "agent_type": {
      "type": "string",
      "description": "Type/role of the team lead (e.g., \"researcher\", \"test-runner\"). Used for team file and inter-agent coordination."
    }
  },
  "required": ["team_name"],
  "additionalProperties": false
}
```

---

## 26. TeamDelete

**Tool Name:** `TeamDelete`
**Source:** `src/tools/TeamDeleteTool/`

### Full Description

```
# TeamDelete

Remove team and task directories when the swarm work is complete.

This operation:
- Removes the team directory (`~/.claude/teams/{team-name}/`)
- Removes the task directory (`~/.claude/tasks/{team-name}/`)
- Clears team context from the current session

**IMPORTANT**: TeamDelete will fail if the team still has active members. Gracefully terminate teammates first, then call TeamDelete after all teammates have shut down.

Use this when all teammates have finished their work and you want to clean up the team resources. The team name is automatically determined from the current session's team context.
```

### input_schema

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

---

## 27. ListMcpResources

**Tool Name:** `ListMcpResourcesTool`
**Source:** `src/tools/ListMcpResourcesTool/`

### Full Description

```
List available resources from configured MCP servers.
Each returned resource will include all standard MCP resource fields plus a 'server' field
indicating which server the resource belongs to.

Parameters:
- server (optional): The name of a specific MCP server to get resources from. If not provided,
  resources from all servers will be returned.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "server": {
      "type": "string",
      "description": "Optional: The name of a specific MCP server to get resources from. If not provided, resources from all servers will be returned."
    }
  }
}
```

---

## 28. ReadMcpResource

**Tool Name:** `ReadMcpResource`
**Source:** `src/tools/ReadMcpResourceTool/`

### Full Description

```
Reads a specific resource from an MCP server, identified by server name and resource URI.

Parameters:
- server (required): The name of the MCP server from which to read the resource
- uri (required): The URI of the resource to read
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "server": {
      "type": "string",
      "description": "The MCP server name"
    },
    "uri": {
      "type": "string",
      "description": "The resource URI to read"
    }
  },
  "required": ["server", "uri"]
}
```

---

## 29. ToolSearch

**Tool Name:** `ToolSearch`
**Source:** `src/tools/ToolSearchTool/`

### Full Description

```
Fetches full schema definitions for deferred tools so they can be called.

Deferred tools appear by name in <system-reminder> messages. Until fetched, only the name is known — there is no parameter schema, so the tool cannot be invoked. This tool takes a query, matches it against the deferred tool list, and returns the matched tools' complete JSONSchema definitions inside a <functions> block. Once a tool's schema appears in that result, it is callable exactly like any tool defined at the top of the prompt.

Result format: each matched tool appears as one <function>{"description": "...", "name": "...", "parameters": {...}}</function> line inside the <functions> block — the same encoding as the tool list at the top of this prompt.

Query forms:
- "select:Read,Edit,Grep" — fetch these exact tools by name
- "notebook jupyter" — keyword search, up to max_results best matches
- "+slack send" — require "slack" in the name, rank by remaining terms
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Search query to match against deferred tool names and descriptions"
    },
    "max_results": {
      "type": "number",
      "description": "Maximum number of results to return (default 10)"
    }
  },
  "required": ["query"]
}
```

---

## 30. Brief / SendUserMessage

**Tool Name:** `SendUserMessage`
**Legacy Name:** `Brief`
**Source:** `src/tools/BriefTool/`

### Full Description

```
Send a message the user will read. Text outside this tool is visible in the detail view, but most won't open it — the answer lives here.

`message` supports markdown. `attachments` takes file paths (absolute or cwd-relative) for images, diffs, logs.

`status` labels intent: 'normal' when replying to what they just asked; 'proactive' when you're initiating — a scheduled task finished, a blocker surfaced during background work, you need input on something they haven't asked about. Set it honestly; downstream routing uses it.

## Talking to the user

SendUserMessage is where your replies go. Text outside it is visible if the user expands the detail view, but most won't — assume unread. Anything you want them to actually see goes through SendUserMessage.

So: every time the user says something, the reply they actually read comes through SendUserMessage. Even for "hi". Even for "thanks".

If you can answer right away, send the answer. If you need to go look — run a command, read files, check something — ack first in one line, then work, then send the result.

For longer work: ack → work → result. Between those, send a checkpoint when something useful happened — a decision you made, a surprise you hit, a phase boundary.

Keep messages tight — the decision, the file:line, the PR number. Second person always ("your config"), never third.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "message": {
      "type": "string",
      "description": "The message to send to the user"
    },
    "attachments": {
      "type": "array",
      "items": { "type": "string" },
      "description": "File paths to attach (images, diffs, logs)"
    },
    "status": {
      "type": "string",
      "enum": ["normal", "proactive"],
      "description": "Message intent: 'normal' for replies, 'proactive' for unsolicited updates"
    }
  },
  "required": ["message"],
  "additionalProperties": false
}
```

---

## 31. Config

**Tool Name:** `Config`
**Source:** `src/tools/ConfigTool/`

> Only available for `USER_TYPE === 'ant'` (internal Anthropic users).

### Full Description

```
Get or set Claude Code configuration settings.

View or change Claude Code settings. Use when the user requests configuration changes, asks about current settings, or when adjusting a setting would benefit them.

## Usage
- **Get current value:** Omit the "value" parameter
- **Set new value:** Include the "value" parameter

## Configurable settings list
(Dynamically generated from SUPPORTED_SETTINGS registry)

## Model
- model - Override the default model. Available options vary by build.

## Examples
- Get theme: { "setting": "theme" }
- Set dark theme: { "setting": "theme", "value": "dark" }
- Enable vim mode: { "setting": "editorMode", "value": "vim" }
- Enable verbose: { "setting": "verbose", "value": true }
- Change model: { "setting": "model", "value": "opus" }
- Change permission mode: { "setting": "permissions.defaultMode", "value": "plan" }
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "setting": {
      "type": "string",
      "description": "The configuration setting key to get or set"
    },
    "value": {
      "oneOf": [
        { "type": "string" },
        { "type": "boolean" },
        { "type": "number" }
      ],
      "description": "The value to set. Omit to get current value."
    }
  },
  "additionalProperties": false
}
```

---

## 32. LSP

**Tool Name:** `LSP`
**Source:** `src/tools/LSPTool/`

> Only available when `ENABLE_LSP_TOOL` env is set.

### Full Description

```
Interact with Language Server Protocol (LSP) servers to get code intelligence features.

Supported operations:
- goToDefinition: Find where a symbol is defined
- findReferences: Find all references to a symbol
- hover: Get hover information (documentation, type info) for a symbol
- documentSymbol: Get all symbols (functions, classes, variables) in a document
- workspaceSymbol: Search for symbols across the entire workspace
- goToImplementation: Find implementations of an interface or abstract method
- prepareCallHierarchy: Get call hierarchy item at a position (functions/methods)
- incomingCalls: Find all functions/methods that call the function at a position
- outgoingCalls: Find all functions/methods called by the function at a position

All operations require:
- filePath: The file to operate on
- line: The line number (1-based, as shown in editors)
- character: The character offset (1-based, as shown in editors)

Note: LSP servers must be configured for the file type. If no server is available, an error will be returned.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": ["goToDefinition", "findReferences", "hover", "documentSymbol", "workspaceSymbol", "goToImplementation", "prepareCallHierarchy", "incomingCalls", "outgoingCalls"],
      "description": "The LSP operation to perform"
    },
    "filePath": {
      "type": "string",
      "description": "The absolute or relative path to the file"
    },
    "line": {
      "type": "integer",
      "description": "The line number (1-based, as shown in editors)"
    },
    "character": {
      "type": "integer",
      "description": "The character offset (1-based, as shown in editors)"
    },
    "query": {
      "type": "string",
      "description": "Search query for workspaceSymbol operation"
    },
    "direction": {
      "type": "string",
      "enum": ["incoming", "outgoing"],
      "description": "Direction for callHierarchy operations"
    }
  },
  "required": ["operation", "filePath", "line", "character"],
  "additionalProperties": false
}
```

---

## 33. MCP

**Tool Name:** (Dynamic — set at runtime from MCP server configuration)
**Source:** `src/tools/MCPTool/`

### Full Description

```
(Actual prompt and description are overridden in mcpClient.ts at runtime based on MCP server tool definitions)
```

### input_schema

```json
{
  "type": "object",
  "additionalProperties": true
}
```

> The MCP tool schema is dynamically generated from MCP server definitions. The `z.object({}).passthrough()` schema accepts any shape.

---

## 34. PowerShell

**Tool Name:** `PowerShell`
**Source:** `src/tools/PowerShellTool/`

> Only available on Windows platforms.

### Full Description

```
Executes a given PowerShell command with optional timeout. Working directory persists between commands; shell state (variables, functions) does not.

IMPORTANT: This tool is for terminal operations via PowerShell: git, npm, docker, and PS cmdlets. DO NOT use it for file operations (reading, writing, editing, searching, finding files) - use the specialized tools for this instead.

PowerShell edition: varies by system (Windows PowerShell 5.1 or PowerShell 7+)

Before executing the command, please follow these steps:

1. Directory Verification:
   - If the command will create new directories or files, first use `Get-ChildItem` (or `ls`) to verify the parent directory exists and is the correct location

2. Command Execution:
   - Always quote file paths that contain spaces with double quotes
   - Capture the output of the command.

PowerShell Syntax Notes:
   - Variables use $ prefix: $myVar = "value"
   - Escape character is backtick (`), not backslash
   - Use Verb-Noun cmdlet naming: Get-ChildItem, Set-Location, New-Item, Remove-Item
   - Common aliases: ls (Get-ChildItem), cd (Set-Location), cat (Get-Content), rm (Remove-Item)
   - Pipe operator | works similarly to bash but passes objects, not text
   - Use Select-Object, Where-Object, ForEach-Object for filtering and transformation
   - String interpolation: "Hello $name" or "Hello $($obj.Property)"
   - Registry access uses PSDrive prefixes: `HKLM:\SOFTWARE\...`, `HKCU:\...` — NOT raw `HKEY_LOCAL_MACHINE\...`
   - Environment variables: read with `$env:NAME`, set with `$env:NAME = "value"`
   - Call native exe with spaces in path via call operator: `& "C:\Program Files\App\app.exe" arg1 arg2`

Interactive and blocking commands (will hang — this tool runs with -NonInteractive):
   - NEVER use `Read-Host`, `Get-Credential`, `Out-GridView`, `$Host.UI.PromptForChoice`, or `pause`
   - Destructive cmdlets (`Remove-Item`, `Stop-Process`, `Clear-Content`, etc.) may prompt for confirmation. Add `-Confirm:$false` when you intend the action to proceed.

Usage notes:
  - The command argument is required.
  - You can specify an optional timeout in milliseconds.
  - Avoid using PowerShell to run commands that have dedicated tools.
  - When issuing multiple commands:
    - If the commands are independent and can run in parallel, make multiple PowerShell tool calls in a single message.
    - If the commands depend on each other and must run sequentially, chain them in a single call.
  - Do NOT prefix commands with `cd` or `Set-Location`.
  - For git commands:
    - Prefer to create a new commit rather than amending an existing commit.
    - Before running destructive operations, consider whether there is a safer alternative.
    - Never skip hooks (--no-verify) or bypass signing unless the user has explicitly asked for it.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "command": {
      "type": "string",
      "description": "The PowerShell command to execute"
    },
    "timeout": {
      "type": "number",
      "description": "Optional timeout in milliseconds (max 600000)"
    },
    "description": {
      "type": "string",
      "description": "Clear, concise description of what this command does in active voice."
    },
    "run_in_background": {
      "type": "boolean",
      "description": "Set to true to run this command in the background."
    },
    "dangerouslyDisableSandbox": {
      "type": "boolean",
      "description": "Set this to true to dangerously override sandbox mode and run commands without sandboxing."
    }
  },
  "required": ["command"],
  "additionalProperties": false
}
```

---

## 35. CronCreate

**Tool Name:** `CronCreate`
**Source:** `src/tools/ScheduleCronTool/CronCreateTool.ts`

> Only available when `AGENT_TRIGGERS` feature flag is enabled.

### Full Description

```
Schedule a prompt to be enqueued at a future time. Use for both recurring schedules and one-shot reminders.

Uses standard 5-field cron in the user's local timezone: minute hour day-of-month month day-of-week. "0 9 * * *" means 9am local — no timezone conversion needed.

## One-shot tasks (recurring: false)

For "remind me at X" or "at <time>, do Y" requests — fire once then auto-delete.
Pin minute/hour/day-of-month/month to specific values:
  "remind me at 2:30pm today to check the deploy" → cron: "30 14 <today_dom> <today_month> *", recurring: false
  "tomorrow morning, run the smoke test" → cron: "57 8 <tomorrow_dom> <tomorrow_month> *", recurring: false

## Recurring jobs (recurring: true, the default)

For "every N minutes" / "every hour" / "weekdays at 9am" requests:
  "*/5 * * * *" (every 5 min), "0 * * * *" (hourly), "0 9 * * 1-5" (weekdays at 9am local)

## Avoid the :00 and :30 minute marks when the task allows it

Every user who asks for "9am" gets `0 9`, and every user who asks for "hourly" gets `0 *` — which means requests from across the planet land on the API at the same instant. When the user's request is approximate, pick a minute that is NOT 0 or 30:
  "every morning around 9" → "57 8 * * *" or "3 9 * * *" (not "0 9 * * *")
  "hourly" → "7 * * * *" (not "0 * * * *")
  "in an hour or so, remind me to..." → pick whatever minute you land on, don't round

Only use minute 0 or 30 when the user names that exact time and clearly means it ("at 9:00 sharp", "at half past", coordinating with a meeting). When in doubt, nudge a few minutes early or late — the user will not notice, and the fleet will.

## Durability

By default (durable: false) the job lives only in this Claude session — nothing is written to disk, and the job is gone when Claude exits. Pass durable: true to write to .claude/scheduled_tasks.json so the job survives restarts. Only use durable: true when the user explicitly asks for the task to persist ("keep doing this every day", "set this up permanently"). Most "remind me in 5 minutes" / "check back in an hour" requests should stay session-only.

## Runtime behavior

Jobs only fire while the REPL is idle (not mid-query). Durable jobs persist to .claude/scheduled_tasks.json and survive session restarts — on next launch they resume automatically. One-shot durable tasks that were missed while the REPL was closed are surfaced for catch-up. Session-only jobs die with the process. The scheduler adds a small deterministic jitter on top of whatever you pick: recurring tasks fire up to 10% of their period late (max 15 min); one-shot tasks landing on :00 or :30 fire up to 90 s early. Picking an off-minute is still the bigger lever.

Recurring tasks auto-expire after 7 days — they fire one final time, then are deleted. This bounds session lifetime. Tell the user about the 7-day limit when scheduling recurring jobs.

Returns a job ID you can pass to CronDelete.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "cron": {
      "type": "string",
      "description": "Standard 5-field cron expression in local time: \"M H DoM Mon DoW\""
    },
    "prompt": {
      "type": "string",
      "description": "The prompt to enqueue at each fire time."
    },
    "recurring": {
      "type": "boolean",
      "description": "true = fire on every cron match until deleted or auto-expired after 7 days. false = fire once at the next match, then auto-delete. Use false for \"remind me at X\" one-shot requests with pinned minute/hour/dom/month."
    },
    "durable": {
      "type": "boolean",
      "description": "true = persist to .claude/scheduled_tasks.json and survive restarts. false (default) = in-memory only, dies when this Claude session ends. Use true only when the user asks for the task to persist."
    }
  },
  "required": ["cron", "prompt"],
  "additionalProperties": false
}
```

---

## 36. CronDelete

**Tool Name:** `CronDelete`
**Source:** `src/tools/ScheduleCronTool/CronDeleteTool.ts`

> Only available when `AGENT_TRIGGERS` feature flag is enabled.

### Full Description

```
Cancel a cron job previously scheduled with CronCreate. Removes it from .claude/scheduled_tasks.json (durable jobs) or the in-memory session store (session-only jobs).
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "id": {
      "type": "string",
      "description": "Job ID returned by CronCreate."
    }
  },
  "required": ["id"],
  "additionalProperties": false
}
```

---

## 37. CronList

**Tool Name:** `CronList`
**Source:** `src/tools/ScheduleCronTool/CronListTool.ts`

> Only available when `AGENT_TRIGGERS` feature flag is enabled.

### Full Description

```
List all cron jobs scheduled via CronCreate, both durable (.claude/scheduled_tasks.json) and session-only.
```

### input_schema

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

---

## 38. RemoteTrigger

**Tool Name:** `RemoteTrigger`
**Source:** `src/tools/RemoteTriggerTool/`

> Only available when `AGENT_TRIGGERS_REMOTE` feature flag is enabled.

### Full Description

```
Call the claude.ai remote-trigger API. Use this instead of curl — the OAuth token is added automatically in-process and never exposed.

Actions:
- list: GET /v1/code/triggers
- get: GET /v1/code/triggers/{trigger_id}
- create: POST /v1/code/triggers (requires body)
- update: POST /v1/code/triggers/{trigger_id} (requires body, partial update)
- run: POST /v1/code/triggers/{trigger_id}/run

The response is the raw JSON from the API.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["list", "get", "create", "update", "run"],
      "description": "The action to perform"
    },
    "trigger_id": {
      "type": "string",
      "description": "The trigger ID (required for get, update, run actions)"
    },
    "body": {
      "type": "object",
      "additionalProperties": {},
      "description": "The request body (required for create and update actions)"
    }
  },
  "required": ["action"],
  "additionalProperties": false
}
```

---

## 39. Sleep

**Tool Name:** `Sleep`
**Source:** `src/tools/SleepTool/`

> Only available when `PROACTIVE` or `KAIROS` feature flag is enabled.

### Full Description

```
Wait for a specified duration. The user can interrupt the sleep at any time.

Use this when the user tells you to sleep or rest, when you have nothing to do, or when you're waiting for something.

You may receive <tick> prompts — these are periodic check-ins. Look for useful work to do before sleeping.

You can call this concurrently with other tools — it won't interfere with them.

Prefer this over `Bash(sleep ...)` — it doesn't hold a shell process.

Each wake-up costs an API call, but the prompt cache expires after 5 minutes of inactivity — balance accordingly.
```

### input_schema

```json
{
  "type": "object",
  "properties": {
    "duration_ms": {
      "type": "number",
      "description": "Duration to sleep in milliseconds"
    }
  },
  "required": ["duration_ms"]
}
```

> Note: The SleepTool.ts source file is dynamically loaded at build time and not present in the source directory. Schema inferred from tool usage context.

---

## Summary Table

| # | Tool Name | Source Directory | Key Parameters |
|---|-----------|-----------------|----------------|
| 1 | `Bash` | `BashTool/` | `command`, `timeout`, `description`, `run_in_background` |
| 2 | `Read` | `FileReadTool/` | `file_path`, `offset`, `limit`, `pages` |
| 3 | `Edit` | `FileEditTool/` | `file_path`, `old_string`, `new_string`, `replace_all` |
| 4 | `Write` | `FileWriteTool/` | `file_path`, `content` |
| 5 | `Glob` | `GlobTool/` | `pattern`, `path` |
| 6 | `Grep` | `GrepTool/` | `pattern`, `path`, `glob`, `output_mode`, `-i`, `-A`, `-B`, `-C` |
| 7 | `WebFetch` | `WebFetchTool/` | `url`, `prompt` |
| 8 | `WebSearch` | `WebSearchTool/` | `query`, `allowed_domains`, `blocked_domains` |
| 9 | `NotebookEdit` | `NotebookEditTool/` | `notebook_path`, `new_source`, `cell_id`, `edit_mode` |
| 10 | `TodoWrite` | `TodoWriteTool/` | `todos` |
| 11 | `Agent` | `AgentTool/` | `description`, `prompt`, `subagent_type`, `run_in_background`, `name` |
| 12 | `TaskOutput` | `TaskOutputTool/` | `task_id`, `block`, `timeout` |
| 13 | `TaskStop` | `TaskStopTool/` | `task_id` |
| 14 | `AskUserQuestion` | `AskUserQuestionTool/` | `questions` |
| 15 | `Skill` | `SkillTool/` | `skill`, `args` |
| 16 | `EnterPlanMode` | `EnterPlanModeTool/` | _(none)_ |
| 17 | `ExitPlanMode` | `ExitPlanModeTool/` | _(none)_ |
| 18 | `EnterWorktree` | `EnterWorktreeTool/` | `name`, `path` |
| 19 | `ExitWorktree` | `ExitWorktreeTool/` | `action`, `discard_changes` |
| 20 | `SendMessage` | `SendMessageTool/` | `to`, `message`, `summary` |
| 21 | `TaskCreate` | `TaskCreateTool/` | `subject`, `description`, `activeForm`, `metadata` |
| 22 | `TaskGet` | `TaskGetTool/` | `taskId` |
| 23 | `TaskUpdate` | `TaskUpdateTool/` | `taskId`, `status`, `owner`, `addBlocks`, `addBlockedBy` |
| 24 | `TaskList` | `TaskListTool/` | _(none)_ |
| 25 | `TeamCreate` | `TeamCreateTool/` | `team_name`, `description`, `agent_type` |
| 26 | `TeamDelete` | `TeamDeleteTool/` | _(none)_ |
| 27 | `ListMcpResourcesTool` | `ListMcpResourcesTool/` | `server` |
| 28 | `ReadMcpResource` | `ReadMcpResourceTool/` | `server`, `uri` |
| 29 | `ToolSearch` | `ToolSearchTool/` | `query`, `max_results` |
| 30 | `SendUserMessage` | `BriefTool/` | `message`, `attachments`, `status` |
| 31 | `Config` | `ConfigTool/` | `setting`, `value` |
| 32 | `LSP` | `LSPTool/` | `operation`, `filePath`, `line`, `character` |
| 33 | `MCP` (dynamic) | `MCPTool/` | _(passthrough)_ |
| 34 | `PowerShell` | `PowerShellTool/` | `command`, `timeout`, `description` |
| 35 | `CronCreate` | `ScheduleCronTool/` | `cron`, `prompt`, `recurring`, `durable` |
| 36 | `CronDelete` | `ScheduleCronTool/` | `id` |
| 37 | `CronList` | `ScheduleCronTool/` | _(none)_ |
| 38 | `RemoteTrigger` | `RemoteTriggerTool/` | `action`, `trigger_id`, `body` |
| 39 | `Sleep` | `SleepTool/` | `duration_ms` |
