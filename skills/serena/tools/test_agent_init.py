#!/usr/bin/env python3
"""Diagnostic script to test SerenaAgent initialization."""

import sys
from pathlib import Path

def main():
    try:
        from serena.agent import SerenaAgent, SerenaConfig
        print("✓ serena imports successful")

        # Test 1: Default config
        print("\nTest 1: SerenaConfig()")
        config = SerenaConfig()
        print(f"✓ Config created: {type(config)}")

        # Test 2: Agent initialization
        print("\nTest 2: SerenaAgent")
        tools_dir = Path(__file__).parent
        project_path = tools_dir.parent.parent.parent  # DSkills root
        agent = SerenaAgent(project=str(project_path), serena_config=config)
        print(f"✓ Agent created: {type(agent)}")

        # Test 3: Check _active_tools
        print("\nTest 3: _active_tools attribute")
        if hasattr(agent, '_active_tools'):
            tools = agent._active_tools
            print(f"✓ _active_tools exists")
            print(f"  Type: {type(tools)}")
            print(f"  Length: {len(tools)}")

            tools_list = list(tools)
            print(f"  Converted to list: {len(tools_list)} items")

            if tools_list:
                print("  Sample tools:")
                for tool in tools_list[:5]:
                    name = getattr(tool, 'name', 'NO_NAME')
                    print(f"    - {name}")
        else:
            print("✗ _active_tools not found")
            print(f"  Available: {[a for a in dir(agent) if not a.startswith('__')]}")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
