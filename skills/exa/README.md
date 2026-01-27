# Exa Search CLI

Standalone CLI for Exa semantic search API. Provides 9 tools for web search, content extraction, and AI-powered research.

## Installation

```bash
pip install httpx tenacity
```

## Configuration

Set `EXA_API_KEY` via environment variable or `.env` file:

```bash
export EXA_API_KEY=your-api-key-here
```

Or copy `.env.example` to `.env` in the scripts directory.

## Usage

```bash
cd scripts

# Semantic search
python exa_cli.py web_search_exa --query "TypeScript design patterns"

# Advanced search with filters
python exa_cli.py web_search_advanced_exa --query "machine learning" --include-domains arxiv.org --text

# Code context
python exa_cli.py get_code_context_exa --query "React hooks examples"

# Company research
python exa_cli.py company_research_exa --company "Anthropic"

# URL content extraction
python exa_cli.py crawling_exa --url "https://example.com" --text

# AI research task
python exa_cli.py deep_researcher_start --instructions "Analyze LLM impact on coding"
python exa_cli.py deep_researcher_check --task-id "<taskId>"

# Check configuration
python exa_cli.py get_config_info
```

## Available Commands

| Command | Description |
|---------|-------------|
| `web_search_exa` | Semantic web search |
| `web_search_advanced_exa` | Search with domain/date filters |
| `deep_search_exa` | Deep search with query expansion |
| `company_research_exa` | Company information lookup |
| `linkedin_search_exa` | LinkedIn profile search |
| `crawling_exa` | Extract content from URL |
| `get_code_context_exa` | Code documentation lookup |
| `deep_researcher_start` | Start AI research task |
| `deep_researcher_check` | Check research task status |
| `get_config_info` | Show configuration |

## Global Options

- `--api-url`: Override EXA_API_URL
- `--api-key`: Override EXA_API_KEY
- `--debug`: Enable debug output
