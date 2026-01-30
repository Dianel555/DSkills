"""Prompt templates and constants for ACE-Tool CLI."""

USER_AGENT = "augment.cli/0.12.0/mcp"
DEFAULT_MODEL = "claude-sonnet-4-5"

# Default models for third-party APIs
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_OPENAI_MODEL = "gpt-5.2-codex"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"

ENHANCE_PROMPT_TEMPLATE = """⚠️ NO TOOLS ALLOWED ⚠️

Here is an instruction that I'd like to give you, but it needs to be improved. Rewrite and enhance this instruction to make it clearer, more specific, less ambiguous, and correct any mistakes. Do not use any tools: reply immediately with your answer, even if you're not sure. Consider the context of our conversation history when enhancing the prompt. If there is code in triple backticks (```) consider whether it is a code sample and should remain unchanged.Reply with the following format:

### BEGIN RESPONSE ###
Here is an enhanced version of the original instruction that is more specific and clear:
<augment-enhanced-prompt>enhanced prompt goes here</augment-enhanced-prompt>

### END RESPONSE ###

Here is my original instruction:

{original_prompt}"""

ITERATIVE_ENHANCE_TEMPLATE = """⚠️ NO TOOLS ALLOWED ⚠️

You are performing an ITERATIVE ENHANCEMENT on an already-enhanced prompt. The user has reviewed and possibly edited the previous enhancement. Your task is to further refine and optimize while PRESERVING the user's modifications and intent.

**Context:**
- Original prompt: {original_prompt}
- Previous enhancement: {previous_enhanced}
- Current version (user may have edited): {current_prompt}

**Instructions:**
1. Identify what the user changed from the previous enhancement (their edits reflect their intent)
2. PRESERVE the user's modifications - do not revert their changes
3. Further optimize clarity, specificity, and correctness
4. If the user made no changes, provide alternative improvements or deeper refinement
5. Do not use any tools: reply immediately

Reply with the following format:

### BEGIN RESPONSE ###
<augment-enhanced-prompt>iteratively enhanced prompt goes here</augment-enhanced-prompt>
### END RESPONSE ###"""

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".java", ".go", ".rs", ".cpp", ".c", ".cc", ".h", ".hpp", ".hxx", ".cs",
    ".rb", ".php", ".swift", ".kt", ".kts", ".scala", ".clj", ".cljs",
    ".lua", ".dart", ".m", ".mm", ".pl", ".pm", ".r", ".R", ".jl",
    ".ex", ".exs", ".erl", ".hs", ".zig", ".v", ".nim", ".f90", ".f95",
    ".groovy", ".gradle", ".sol", ".move",
    ".md", ".mdx", ".txt", ".json", ".jsonc", ".json5",
    ".yaml", ".yml", ".toml", ".xml", ".ini", ".conf", ".cfg", ".properties",
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".styl",
    ".vue", ".svelte", ".astro",
    ".ejs", ".hbs", ".pug", ".jade", ".jinja", ".jinja2", ".erb",
    ".sql", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".graphql", ".gql", ".proto", ".prisma",
}

EXCLUDE_PATTERNS = {
    ".venv", "venv", ".env", "env", "node_modules", "vendor",
    ".pnpm", ".yarn", "bower_components",
    ".git", ".svn", ".hg",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".tox", ".ruff_cache",
    "dist", "build", "target", "out", "bin", "obj",
    ".next", ".nuxt", ".output", ".vercel", ".netlify", ".turbo",
    ".parcel-cache", ".cache", ".temp", ".tmp",
    "coverage", ".nyc_output", "htmlcov",
    ".idea", ".vscode", ".vs",
    ".ace-tool",
}
