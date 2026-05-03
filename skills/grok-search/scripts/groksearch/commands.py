import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

from .config import config
from .formatting import merge_search_results
from .provider import GrokSearchProvider
from .tavily import _call_tavily_extract, _call_tavily_map, _call_tavily_search, _tavily_unavailable_reason


async def cmd_web_search(args):
    try:
        provider = GrokSearchProvider(config.grok_api_url, config.grok_api_key, config.grok_model)
        extra_sources = getattr(args, "extra_sources", 0) or 0

        if args.raw:
            grok_result = await provider.search(args.query, args.platform, args.min_results, args.max_results)
            print(grok_result)
            return

        if extra_sources > 0 and _tavily_unavailable_reason() is None:
            grok_task = provider.search(args.query, args.platform, args.min_results, args.max_results)
            tavily_task = _call_tavily_search(args.query, extra_sources)
            grok_result, tavily_results = await asyncio.gather(grok_task, tavily_task)
        else:
            grok_result = await provider.search(args.query, args.platform, args.min_results, args.max_results)
            tavily_results = None

        merged = merge_search_results(grok_result, tavily_results)
        print(json.dumps(merged, ensure_ascii=False, indent=2))
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(json.dumps({"error": f"API error: {e.response.status_code}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


async def cmd_web_fetch(args):
    via = getattr(args, "via", "grok")
    try:
        if via == "tavily":
            reason = _tavily_unavailable_reason()
            if reason:
                print(json.dumps({"error": reason}, ensure_ascii=False), file=sys.stderr)
                sys.exit(1)
            result = await _call_tavily_extract(args.url)
            if result is None:
                print(json.dumps({"error": "Tavily extract failed or returned empty content"}, ensure_ascii=False), file=sys.stderr)
                sys.exit(1)
        else:
            provider = GrokSearchProvider(config.grok_api_url, config.grok_api_key, config.grok_model)
            result = await provider.fetch(args.url)

        if args.out:
            Path(args.out).write_text(result, encoding="utf-8")
            print(f"Content saved to {args.out}")
        else:
            print(result)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"API error: {e.response.status_code}", file=sys.stderr)
        sys.exit(1)


async def cmd_web_map(args):
    result = await _call_tavily_map(
        args.url,
        args.instructions,
        args.max_depth,
        args.max_breadth,
        args.limit,
        args.timeout,
    )
    print(result)


async def cmd_get_config_info(args):
    config_info = config.get_config_info()

    if not args.no_test:
        test_result = {"status": "Not tested", "message": "", "response_time_ms": 0}
        try:
            api_url = config.grok_api_url
            api_key = config.grok_api_key
            models_url = f"{api_url}/models"

            start_time = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    models_url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )
                response_time = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    test_result["status"] = "✅ Connection Successful"
                    test_result["response_time_ms"] = round(response_time, 2)
                    try:
                        models_data = response.json()
                        if "data" in models_data:
                            model_count = len(models_data["data"])
                            test_result["message"] = f"Retrieved {model_count} models"
                            test_result["available_models"] = [
                                m.get("id") for m in models_data["data"] if isinstance(m, dict)
                            ]
                    except Exception:
                        pass
                else:
                    test_result["status"] = "⚠️ Connection Issue"
                    test_result["message"] = f"HTTP {response.status_code}"

        except httpx.TimeoutException:
            test_result["status"] = "❌ Connection Timeout"
            test_result["message"] = "Request timed out (10s)"
        except Exception as e:
            test_result["status"] = "❌ Connection Failed"
            test_result["message"] = str(e)

        config_info["connection_test"] = test_result

    print(json.dumps(config_info, ensure_ascii=False, indent=2))


async def cmd_switch_model(args):
    try:
        previous = config.set_model(args.model)
        result = {
            "status": "✅ Success",
            "previous_model": previous,
            "current_model": args.model,
            "config_file": str(config.config_file),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"status": "❌ Failed", "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


async def cmd_toggle_builtin_tools(args):
    if args.root:
        root = Path(args.root)
        if not root.exists():
            print(json.dumps({"error": f"Specified root does not exist: {args.root}"}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    else:
        root = Path.cwd()
        while root != root.parent and not (root / ".git").exists():
            root = root.parent
        if not (root / ".git").exists():
            print(
                json.dumps(
                    {
                        "error": "No .git directory found. Use --root to specify project root.",
                        "hint": "Run this command from within a git repository or specify --root PATH",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            sys.exit(1)

    settings_path = root / ".claude" / "settings.json"
    tools = ["WebFetch", "WebSearch"]

    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {"permissions": {"deny": []}}

    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    blocked = all(t in deny for t in tools)

    action = args.action.lower()
    if action in ["on", "enable"]:
        for t in tools:
            if t not in deny:
                deny.append(t)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        msg = "Built-in tools disabled"
        blocked = True
    elif action in ["off", "disable"]:
        deny[:] = [t for t in deny if t not in tools]
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        msg = "Built-in tools enabled"
        blocked = False
    else:
        msg = f"Built-in tools currently {'disabled' if blocked else 'enabled'}"

    print(
        json.dumps(
            {"blocked": blocked, "deny_list": deny, "file": str(settings_path), "message": msg},
            ensure_ascii=False,
            indent=2,
        )
    )
