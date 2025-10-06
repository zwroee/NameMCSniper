#!/usr/bin/env python3
"""
Token collection helper for multi-account sniping
"""

import json
import yaml
from pathlib import Path

def collect_tokens():
    """Interactive token collection"""
    print("🔑 Multi-Token Setup for NameMC Sniper")
    print("=" * 50)
    print()
    print("To compete against multi-account snipers, you need multiple Microsoft accounts.")
    print("Each account needs a bearer token from Minecraft services.")
    print()
    print("How to get bearer tokens:")
    print("1. Go to https://login.microsoftonline.com/")
    print("2. Log into each Microsoft account")
    print("3. Get the bearer token from Minecraft API calls")
    print("4. Enter them below")
    print()
    
    tokens = []
    
    while True:
        token = input(f"Enter bearer token #{len(tokens) + 1} (or 'done' to finish): ").strip()
        
        if token.lower() == 'done':
            break
            
        if not token:
            print("❌ Empty token, skipping...")
            continue
            
        if len(token) < 50:
            print("⚠️ Token seems too short, are you sure it's correct? (y/n)")
            confirm = input().strip().lower()
            if confirm != 'y':
                continue
        
        tokens.append(token)
        print(f"✅ Added token #{len(tokens)}")
    
    if not tokens:
        print("❌ No tokens collected!")
        return
    
    print(f"\n🎯 Collected {len(tokens)} tokens!")
    
    # Update config.yaml
    config_path = Path("config.yaml")
    
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        print("❌ config.yaml not found! Create one first.")
        return
    
    # Update the bearer_tokens list
    if 'snipe' not in config:
        config['snipe'] = {}
    
    config['snipe']['bearer_tokens'] = tokens
    
    # Keep the first token as the primary bearer_token for compatibility
    config['snipe']['bearer_token'] = tokens[0]
    
    # Save updated config
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, indent=2)
    
    print(f"✅ Updated config.yaml with {len(tokens)} tokens!")
    print("\n🚀 Your sniper can now use multiple accounts simultaneously!")
    print(f"💪 You can now compete against multi-account snipers!")

def show_current_tokens():
    """Show currently configured tokens"""
    config_path = Path("config.yaml")
    
    if not config_path.exists():
        print("❌ config.yaml not found!")
        return
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    tokens = config.get('snipe', {}).get('bearer_tokens', [])
    
    if not tokens:
        print("❌ No tokens configured!")
        return
    
    print(f"🔑 Currently configured tokens: {len(tokens)}")
    for i, token in enumerate(tokens, 1):
        print(f"  {i}. ...{token[-12:]}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        show_current_tokens()
    else:
        collect_tokens()
