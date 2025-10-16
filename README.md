# NameMC Sniper

<div align="center">

<img width="1536" height="324" alt="assets_task_01k6cfgfnce75rr55xznbme123_1759208092_img_1" src="https://github.com/user-attachments/assets/cf0a9ba6-a318-424b-a163-82f34b9915b0" />

**A professional-grade Minecraft username sniper with advanced features**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[📚 Documentation](https://zwroee.github.io/NameMCSniper-Docs/) • [🚀 Quick Start](https://zwroee.github.io/NameMCSniper-Docs/#quick-start) • [⚙️ Configuration](https://zwroee.github.io/NameMCSniper-Docs/getting-started/configuration/) • [🤝 Support](https://zwroee.github.io/NameMCSniper-Docs/legal/support/)

</div>

## ✨ Features

<table>
<tr>
<td width="50%">

### 🎯 **Core Features**
- **Ultra-Fast Sniping** - 40 concurrent workers with 8ms precision
- **Multi-Token Support** - Mass sniping with multiple accounts
- **Intelligent Rate Limiting** - Per-token backoff strategies
- **Smart Proxy Rotation** - Residential proxy support (user-provided)
- **Rich CLI Interface** - Beautiful terminal with colors & tables

</td>
<td width="50%">

### 🔧 **Advanced Features**
- **Time Synchronization** - NTP-based accurate timing
- **Adaptive Delays** - Dynamic request timing optimization
- **Network Optimization** - Oracle VPS performance tuning
- **Error Recovery** - Graceful failure handling & retries
- **Token Validation** - Test bearer tokens before sniping

</td>
</tr>
</table>

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Valid Minecraft account with bearer token
- (Optional) Discord webhook for notifications

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/NameMcSniper.git
cd NameMcSniper

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create configuration file
python Main.py config-create
```

### First Run

```bash
# Launch the interactive CLI menu (recommended for beginners)
python menu.py

# Or use command line directly
python Main.py test-token  # Test your bearer token
python Main.py snipe-at -u "Username" -w "12/25/2024 • 3∶30∶00 PM"  # Snipe username
```

## ⚙️ Configuration

### Basic Configuration (`config.yaml`)

```yaml
# Sniping Configuration
snipe:
  target_username: "YourDesiredUsername"
  bearer_token: "your_minecraft_bearer_token_here"
  start_sniping_at_seconds: 0
  max_snipe_attempts: 3000
  request_delay_ms: 8
  concurrent_requests: 40

# Discord Notifications
discord:
  enabled: true
  webhook_url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"
  mention_role_id: "123456789012345678"  # Optional
  embed_color: 65280  # Green

# Proxy Configuration (Optional)
proxy:
  enabled: false
  proxies:
    - "http://username:password@proxy1.example.com:8080"
    - "http://proxy2.example.com:3128"
  rotation_enabled: true
  timeout: 10
  max_retries: 3

# Logging
debug_mode: false
log_level: "INFO"
```

### 🔑 Getting Your Bearer Token

<details>
<summary><strong>Method 1: Browser Developer Tools (Recommended)</strong></summary>

1. Open [minecraft.net](https://minecraft.net) and log in
2. Press `F12` to open Developer Tools
3. Go to the **Network** tab
4. Navigate to any Minecraft service page
5. Look for requests with `Authorization: Bearer <token>`
6. Copy the token (long string after "Bearer ")

</details>

<details>
<summary><strong>Method 2: Using Authentication Script</strong></summary>

```python
# Use minecraft-launcher-lib or similar
import minecraft_launcher_lib

# Authenticate and get token
# (Implementation depends on chosen library)
```

</details>

## 🎮 Usage

### Interactive CLI Menu (Recommended)

Launch the beautiful interactive menu interface:

```bash
# Start the interactive CLI menu
python menu.py
```

**Features:**
- 🎨 **Beautiful ASCII Art** - Matrix-style green interface
- 📋 **Organized Categories** - Easy navigation with numbered options
- ⚡ **Real-time Testing** - Test tokens, proxies, and Discord integration
- 🔧 **Configuration Management** - Create, validate, and manage configs
- 📊 **System Information** - View logs, system stats, and performance data
- 🎯 **One-Click Sniping** - Simple username sniping at specific times

**Menu Categories:**
- **[1] Sniper Operations** - Main sniping functionality
- **[11-14] Configuration** - Config creation, validation, and management  
- **[21-24] Tools & Info** - Token testing, proxy testing, logs, system info
- **[31-33] Discord & Notifications** - Webhook setup and testing
- **[41-43] Advanced Options** - Performance tuning, debug mode
- **[51-53] Help & Support** - Documentation, about, GitHub links

### CLI Interface Preview

The interactive menu features a professional Matrix-style interface with:
- **Green ASCII Art Logo** - Eye-catching NameMC Sniper branding
- **Organized Menu Layout** - Clean categorized options in bordered boxes
- **Real-time Information** - Current time display and status updates
- **User-friendly Navigation** - Simple number-based option selection
- **Professional Styling** - Consistent green theme throughout
<img width="1918" height="983" alt="Screenshot 2025-09-30 063615" src="https://github.com/user-attachments/assets/387111dd-6039-46c1-b04c-73687cbb761a" />

### Command Line Interface

For advanced users and automation:

```bash
# Basic sniping
python Main.py snipe -u "Username" -t "your_bearer_token"

# Snipe at specific time (NameMC format)
python Main.py snipe-at -u "Username" -w "12/25/2024 • 3∶30∶00 PM"

# Configuration management
python Main.py config-create          # Create default config
python Main.py config-validate        # Validate current config
python Main.py test-proxies           # Test proxy connections
python Main.py test-token             # Validate bearer token

# Help and information
python Main.py --help                 # Show all commands
python Main.py version                # Show version info
```

### Time Format

The sniper uses NameMC's exact time format:
```
MM/DD/YYYY • H∶MM∶SS AM/PM
```

**Examples:**
- `12/25/2024 • 3∶30∶00 PM`
- `1/1/2025 • 11∶45∶30 AM`

> **Note:** Use the special bullet (•) and colon (∶) characters as shown

## 🌐 Proxy Setup

### Supported Formats
```yaml
proxies:
  - "http://ip:port"                          # No authentication
  - "http://username:password@ip:port"        # With authentication
  - "https://ip:port"                         # HTTPS proxy
  - "socks5://ip:port"                        # SOCKS5 proxy
```

### Proxy Testing
```bash
# Test all configured proxies
python Main.py test-proxies

# View proxy statistics in real-time
python Main.py snipe --verbose
```

## 📢 Discord Integration

### Webhook Setup (Recommended)
1. Go to your Discord server settings
2. Navigate to **Integrations** → **Webhooks**
3. Click **New Webhook**
4. Copy the webhook URL
5. Add it to your `config.yaml`

### Notification Types
- **Countdown Alerts** - 1h, 30m, 5m, 1m, 30s before drop
- **Sniping Started** - When sniping begins
- **Success/Failure** - Final result with statistics
- **Error Alerts** - Configuration or runtime errors

## 📊 Performance Optimization

### Recommended Settings

| Use Case | Concurrent Requests | Request Delay | Proxy Count |
|----------|-------------------|---------------|-------------|
| **Conservative** | 5 | 50ms | 2-3 |
| **Balanced** | 10 | 25ms | 5-10 |
| **Aggressive** | 15 | 10ms | 10+ |

### Network Optimization
- Use a VPS close to Minecraft servers (US East Coast recommended)
- Test proxy latency: `python Main.py test-proxies`
- Monitor logs for rate limiting warnings

## 🔧 Advanced Usage

### Programmatic Usage

```python
import asyncio
from datetime import datetime, timezone
from config import ConfigManager
from sniper import UsernameSniper

async def snipe_username():
    # Load configuration
    config_manager = ConfigManager("config.yaml")
    config = config_manager.load_config()
    
    # Create sniper instance
    sniper = UsernameSniper(config)
    
    # Snipe at specific time
    drop_time = datetime(2024, 12, 25, 15, 30, 0, tzinfo=timezone.utc)
    result = await sniper.snipe_at_time(drop_time, "Username")
    
    print(f"Success: {result.success}")
    print(f"Attempts: {result.attempts}")

# Run the sniper
asyncio.run(snipe_username())
```

### Custom Notifications

```python
from discord_notifier import DiscordNotifier

async def custom_notification():
    notifier = DiscordNotifier(webhook_url="your_webhook_url")
    
    async with notifier:
        await notifier.notify_status_update("Custom message here!")
```

## 🐛 Troubleshooting

<details>
<summary><strong>Common Issues & Solutions</strong></summary>

### Bearer Token Issues
```bash
# Error: "Bearer token is required"
python Main.py test-token  # Validate your token

# Error: "Unauthorized (401)"
# → Token expired, get a new one from minecraft.net
```

### Proxy Issues
```bash
# Error: "No working proxies available"
python Main.py test-proxies  # Check proxy health

# Error: "Proxy connection failed"
# → Verify proxy credentials and format
```

### Discord Issues
```bash
# Error: "Webhook failed with status 404"
# → Check webhook URL is correct and not expired

# Error: "No Discord notifications"
# → Verify webhook URL and internet connection
```

### Rate Limiting
```bash
# Error: "Rate limited (429)"
# → Increase request_delay_ms in config
# → Reduce concurrent_requests
# → Add more working proxies
```

</details>

### Log Analysis
```bash
# View recent logs
tail -f logs/namemc_sniper_*.log

# Search for errors
grep -i error logs/namemc_sniper_*.log

# Monitor sniping attempts
grep -i "claim attempt" logs/namemc_sniper_*.log
```

## 🚀 Performance

### Optimized for Competitive Sniping

| Metric | Value | Description |
|--------|-------|-------------|
| **Concurrent Workers** | 40 | Simultaneous sniping threads |
| **Request Delay** | 8ms | Ultra-fast request timing |
| **Max Attempts** | 3000 | High-volume attempt capability |
| **Proxy Support** | Unlimited | Residential proxy rotation (user-provided) |
| **Rate Limiting** | Per-token | Intelligent backoff strategies |
| **Time Sync** | NTP-based | Sub-second timing accuracy |

### Infrastructure Compatibility

- ✅ **Oracle VPS** - Optimized for 2+ OCPUs
- ✅ **Residential Proxies** - Compatible with premium proxy providers  
- ✅ **Multi-Token** - Scale with multiple Microsoft accounts
- ✅ **Global Timezones** - Automatic timezone detection
- ✅ **Rate Limit Handling** - Smart 429 response management

## 📚 Documentation

For comprehensive documentation, examples, and advanced configuration:

**[📖 Visit our Documentation Website](https://zwroee.github.io/NameMCSniper-Docs/)**

- 🎯 **Sniping Strategies** - Multi-token and proxy optimization
- 🔧 **API Reference** - Complete function and class documentation  
- 📊 **Performance Tuning** - Oracle VPS and rate limiting optimization
- 🤖 **Discord Integration** - Webhook notifications and status updates
- 📈 **Competitive Analysis** - Success rates against different sniper types

## 👥 Contributors

Thanks to these awesome people who've contributed to the project:

- [@zwroee](https://github.com/zwroee) - Project creator & maintainer
- [@zerolight18](https://github.com/zerolight18) - Co-author  
- [@robertsmrek](https://github.com/robertsmrek) - Python 3.13 compatibility fix

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚖️ Legal & Ethical Use

> **Important:** This tool is for educational purposes only.

- ✅ **Comply** with Minecraft's Terms of Service
- ✅ **Respect** API rate limits and usage policies  
- ✅ **Use responsibly** and ethically
- ❌ **Don't** use for commercial username trading
- ❌ **Don't** abuse or spam Minecraft services

## 🆘 Support

### Getting Help

1. **📚 Check Documentation** - [docs website](https://zwroee.github.io/NameMCSniper-Docs/)
2. **🔍 Search Issues** - Look for similar problems
3. **📝 Create Issue** - Provide detailed information
4. **💬 Discord Community** - Join our support server

### Issue Template
When reporting bugs, please include:
- Python version and OS
- Full error message and stack trace
- Configuration file (remove sensitive data)
- Steps to reproduce the issue

---

<div align="center">

**Made with ❤️ for the Minecraft community**

[⭐ Star this repo](https://github.com/zwroee/NameMcSniper) • [🐛 Report Bug](https://github.com/zwroee/NameMcSniper/issues) • [💡 Request Feature](https://github.com/zwroee/NameMcSniper/issues)

</div>
