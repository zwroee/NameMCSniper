#!/usr/bin/env python3
"""
NameMC Sniper - Interactive CLI Menu
Beautiful ASCII art menu interface similar to RedTiger style
"""

import os
import sys
import time
import asyncio
from pathlib import Path
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.align import Align

from config import ConfigManager
from sniper import UsernameSniper
from proxy_manager import ProxyManager
from discord_notifier import DiscordNotifier
from logger import setup_logging

console = Console()

class NameMCSniperCLI:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = None
        self.running = True
        
    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_ascii_logo(self):
        """Print the NameMC Sniper ASCII logo"""
        logo = """
[bold green]
███╗   ██╗ █████╗ ███╗   ███╗███████╗███╗   ███╗ ██████╗
████╗  ██║██╔══██╗████╗ ████║██╔════╝████╗ ████║██╔════╝
██╔██╗ ██║███████║██╔████╔██║█████╗  ██╔████╔██║██║     
██║╚██╗██║██╔══██║██║╚██╔╝██║██╔══╝  ██║╚██╔╝██║██║     
██║ ╚████║██║  ██║██║ ╚═╝ ██║███████╗██║ ╚═╝ ██║╚██████╗
╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝

███████╗███╗   ██╗██╗██████╗ ███████╗██████╗ 
██╔════╝████╗  ██║██║██╔══██╗██╔════╝██╔══██╗
███████╗██╔██╗ ██║██║██████╔╝█████╗  ██████╔╝
╚════██║██║╚██╗██║██║██╔═══╝ ██╔══╝  ██╔══██╗
███████║██║ ╚████║██║██║     ███████╗██║  ██║
╚══════╝╚═╝  ╚═══╝╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝
[/bold green]

[green]                    github.com/zwroee/NameMcSniper[/green]
"""
        console.print(Align.center(logo))
    
    def print_menu_header(self):
        """Print the menu header with categories"""
        header = """
[bold cyan]┌─────────────────────────────────────────────────────────────────────────────────────────────┐[/bold cyan]
[bold cyan]│[/bold cyan] [bold white]I[/bold white] [cyan]Info[/cyan]                    [bold cyan]│[/bold cyan] [bold white]S[/bold white] [cyan]Snipe[/cyan]                   [bold cyan]│[/bold cyan] [bold white]C[/bold white] [cyan]Config[/cyan]                [bold cyan]│[/bold cyan]
[bold cyan]└─────────────────────────────────────────────────────────────────────────────────────────────┘[/bold cyan]
"""
        console.print(Align.center(header))
    
    def print_menu_options(self):
        """Print the main menu options"""
        options = """
[bold green]┌─[/bold green] [bold yellow]Sniper Operations[/bold yellow] [bold green]─────────┐[/bold green] [bold green]┌─[/bold green] [bold yellow]Configuration[/bold yellow] [bold green]──────────┐[/bold green] [bold green]┌─[/bold green] [bold yellow]Tools & Info[/bold yellow] [bold green]────────────┐[/bold green]
[bold green]│[/bold green] [bold white][1][/bold white] Snipe at Time            [bold green]│[/bold green] [bold green]│[/bold green] [bold white][11][/bold white] Create Config          [bold green]│[/bold green] [bold green]│[/bold green] [bold white][21][/bold white] Test Bearer Token      [bold green]│[/bold green]
[bold green]│[/bold green]                              [bold green]│[/bold green] [bold green]│[/bold green] [bold white][12][/bold white] Edit Config            [bold green]│[/bold green] [bold green]│[/bold green] [bold white][22][/bold white] Test Proxies           [bold green]│[/bold green]
[bold green]│[/bold green]                              [bold green]│[/bold green] [bold green]│[/bold green] [bold white][13][/bold white] Validate Config        [bold green]│[/bold green] [bold green]│[/bold green] [bold white][23][/bold white] View Logs              [bold green]│[/bold green]
[bold green]│[/bold green]                              [bold green]│[/bold green] [bold green]│[/bold green] [bold white][14][/bold white] Reset Config           [bold green]│[/bold green] [bold green]│[/bold green] [bold white][24][/bold white] System Info            [bold green]│[/bold green]
[bold green]└─────────────────────────────┘[/bold green] [bold green]└───────────────────────────┘[/bold green] [bold green]└───────────────────────────┘[/bold green]

[bold green]┌─[/bold green] [bold yellow]Discord & Notifications[/bold yellow] [bold green]───┐[/bold green] [bold green]┌─[/bold green] [bold yellow]Advanced Options[/bold yellow] [bold green]────────┐[/bold green] [bold green]┌─[/bold green] [bold yellow]Help & Support[/bold yellow] [bold green]─────────┐[/bold green]
[bold green]│[/bold green] [bold white][31][/bold white] Setup Discord Webhook   [bold green]│[/bold green] [bold green]│[/bold green] [bold white][41][/bold white] Performance Tuning     [bold green]│[/bold green] [bold green]│[/bold green] [bold white][51][/bold white] Show Help              [bold green]│[/bold green]
[bold green]│[/bold green] [bold white][32][/bold white] Test Discord             [bold green]│[/bold green] [bold green]│[/bold green] [bold white][42][/bold white] Proxy Manager          [bold green]│[/bold green] [bold green]│[/bold green] [bold white][52][/bold white] About                  [bold green]│[/bold green]
[bold green]│[/bold green] [bold white][33][/bold white] Notification Settings   [bold green]│[/bold green] [bold green]│[/bold green] [bold white][43][/bold white] Debug Mode             [bold green]│[/bold green] [bold green]│[/bold green] [bold white][53][/bold white] GitHub Repository      [bold green]│[/bold green]
[bold green]└─────────────────────────────┘[/bold green] [bold green]└───────────────────────────┘[/bold green] [bold green]└───────────────────────────┘[/bold green]

[bold red]                                    [99] Exit Program[/bold red]
"""
        console.print(Align.center(options))
    
    def print_footer(self):
        """Print the footer with navigation info"""
        footer = f"""
[bold green]┌─────────────────────────────────────────────────────────────────────────────────────────────┐[/bold green]
[bold green]│[/bold green] [dim]Enter option number and press Enter. Type 'back' to return to main menu.[/dim]              [bold green]│[/bold green]
[bold green]│[/bold green] [dim]Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]                                                    [bold green]│[/bold green]
[bold green]└─────────────────────────────────────────────────────────────────────────────────────────────┘[/bold green]
"""
        console.print(Align.center(footer))
    
    def show_main_menu(self):
        """Display the main menu"""
        self.clear_screen()
        self.print_ascii_logo()
        console.print()
        self.print_menu_header()
        console.print()
        self.print_menu_options()
        console.print()
        self.print_footer()
    
    def get_user_input(self, prompt="Enter option"):
        """Get user input with styled prompt"""
        return console.input(f"\n[bold green]┌─[/bold green] [bold white]{prompt}[/bold white] [bold green]─>[/bold green] ")
    
    def show_loading(self, message="Loading..."):
        """Show a loading animation"""
        with console.status(f"[bold green]{message}"):
            time.sleep(1)
    
    def show_success(self, message):
        """Show success message"""
        console.print(f"\n[bold green]✅ {message}[/bold green]")
        time.sleep(2)
    
    def show_error(self, message):
        """Show error message"""
        console.print(f"\n[bold red]❌ {message}[/bold red]")
        time.sleep(2)
    
    def show_info(self, title, content):
        """Show information panel"""
        panel = Panel(content, title=f"[bold green]{title}[/bold green]", border_style="green")
        console.print(panel)
        console.input("\n[dim]Press Enter to continue...[/dim]")
    
    # Menu option handlers
    def create_config(self):
        """Create new configuration file"""
        self.clear_screen()
        console.print("[bold yellow]📝 Create Configuration[/bold yellow]\n")
        
        if Path("config.yaml").exists():
            overwrite = self.get_user_input("Config exists. Overwrite? (y/N)")
            if overwrite.lower() != 'y':
                return
        
        try:
            self.config_manager.create_default_config()
            self.show_success("Configuration file created successfully!")
            console.print("\n[green]Next steps:[/green]")
            console.print("1. Edit config.yaml with your settings")
            console.print("2. Add your bearer token")
            console.print("3. Configure Discord webhook (optional)")
            console.input("\n[dim]Press Enter to continue...[/dim]")
        except Exception as e:
            self.show_error(f"Failed to create config: {e}")
    
    def validate_config(self):
        """Validate configuration file"""
        self.clear_screen()
        console.print("[bold yellow]✅ Validate Configuration[/bold yellow]\n")
        
        try:
            self.config = self.config_manager.load_config()
            errors = self.config_manager.validate_config()
            
            if errors:
                error_text = "\n".join([f"• {error}" for error in errors])
                self.show_info("Configuration Errors Found", f"[red]{error_text}[/red]")
            else:
                info = f"""[green]✅ Configuration is valid![/green]

[green]Current Settings:[/green]
• Target Username: [bold]{self.config.snipe.target_username or 'Not set'}[/bold]
• Bearer Token: [bold]{'Set' if self.config.snipe.bearer_token else 'Not set'}[/bold]
• Proxy Enabled: [bold]{'Yes' if self.config.proxy.enabled else 'No'}[/bold]
• Discord Enabled: [bold]{'Yes' if self.config.discord.enabled else 'No'}[/bold]
• Concurrent Requests: [bold]{self.config.snipe.concurrent_requests}[/bold]
• Request Delay: [bold]{self.config.snipe.request_delay_ms}ms[/bold]"""
                self.show_info("Configuration Valid", info)
        except Exception as e:
            self.show_error(f"Config validation failed: {e}")
    
    async def snipe_at_time(self):
        """Snipe at specific time option"""
        self.clear_screen()
        console.print("[bold yellow]⏰ Snipe at Specific Time[/bold yellow]\n")
        
        username = self.get_user_input("Enter username to snipe")
        if not username:
            self.show_error("Username is required!")
            return
        
        console.print("\n[cyan]Enter drop time in NameMC format:[/cyan]")
        console.print("[dim]Example: 12/25/2024 • 3∶30∶00 PM[/dim]")
        drop_window = self.get_user_input("Drop window")
        
        if not drop_window:
            self.show_error("Drop window is required!")
            return
        
        # Validate format
        if '•' not in drop_window or '∶' not in drop_window:
            self.show_error("Invalid format! Use exact NameMC format with • and ∶")
            return
        
        try:
            # Parse time (simplified version)
            from datetime import datetime, timezone, timedelta
            import time as time_module
            
            clean_window = drop_window.replace('•', '').replace('∶', ':').strip()
            parsed_time = datetime.strptime(clean_window, '%m/%d/%Y %I:%M:%S %p')
            
            # Convert to UTC (simplified)
            local_offset_seconds = -time_module.timezone if time_module.daylight == 0 else -time_module.altzone
            local_offset = timedelta(seconds=local_offset_seconds)
            local_tz = timezone(local_offset)
            parsed_time = parsed_time.replace(tzinfo=local_tz)
            parsed_time = parsed_time.astimezone(timezone.utc)
            
            # Check if time is in future
            now = datetime.now(timezone.utc)
            if parsed_time <= now:
                self.show_error("Drop time must be in the future!")
                return
            
            time_until = (parsed_time - now).total_seconds()
            console.print(f"\n[green]✅ Drop time parsed successfully![/green]")
            console.print(f"[cyan]Time until drop: {time_until/3600:.2f} hours ({time_until:.0f} seconds)[/cyan]")
            
            confirm = self.get_user_input("Start sniper? (y/N)")
            if confirm.lower() != 'y':
                return
            
            # Load config and start sniper
            self.config = self.config_manager.load_config()
            self.config.snipe.target_username = username
            
            sniper = UsernameSniper(self.config)
            result = await sniper.snipe_at_time(parsed_time, username)
            
            if result.success:
                self.show_success(f"Successfully claimed {username}!")
            else:
                self.show_error(f"Failed to claim {username}. Attempts: {result.attempts}")
                
        except Exception as e:
            self.show_error(f"Error: {e}")
    
    async def test_proxies(self):
        """Test proxy connections"""
        self.clear_screen()
        console.print("[bold yellow]🌐 Test Proxies[/bold yellow]\n")
        
        try:
            self.config = self.config_manager.load_config()
            
            if not self.config.proxy.enabled or not self.config.proxy.proxies:
                self.show_error("No proxies configured! Enable proxies in config.yaml")
                return
            
            console.print(f"[green]Testing {len(self.config.proxy.proxies)} proxies...[/green]")
            console.print("[yellow]⚠️  This may take a while with many proxies. Press Ctrl+C to cancel.[/yellow]\n")
            
            try:
                proxy_manager = ProxyManager(
                    proxy_list=self.config.proxy.proxies,
                    rotation_enabled=self.config.proxy.rotation_enabled,
                    timeout=min(self.config.proxy.timeout, 5)  # Cap timeout at 5 seconds for faster testing
                )
                
                with console.status("[bold green]Testing proxies..."):
                    # Add timeout to prevent infinite hanging
                    await asyncio.wait_for(proxy_manager.test_all_proxies(), timeout=300)  # 5 minute max
                
                stats = proxy_manager.get_proxy_stats()
                
                info = f"""[green]Proxy Test Results:[/green]

• Total Proxies: [bold]{stats['total_proxies']}[/bold]
• Working Proxies: [bold green]{stats['working_proxies']}[/bold green]
• Failed Proxies: [bold red]{stats['bad_proxies']}[/bold red]
• Success Rate: [bold]{(stats['working_proxies']/stats['total_proxies']*100):.1f}%[/bold]
• Average Response Time: [bold]{stats['average_response_time']:.2f}s[/bold]

[yellow]Recommendation:[/yellow]
{'✅ Good proxy setup!' if stats['working_proxies'] > 0 else '❌ No working proxies - check your proxy list'}

[dim]Note: Only working proxies will be used during sniping[/dim]"""
                
                self.show_info("Proxy Test Results", info)
                
            except asyncio.TimeoutError:
                self.show_error("Proxy testing timed out after 5 minutes. Try with fewer proxies.")
            except KeyboardInterrupt:
                self.show_error("Proxy testing cancelled by user.")
            
        except Exception as e:
            self.show_error(f"Proxy test failed: {e}")
    
    def view_logs(self):
        """View recent logs"""
        self.clear_screen()
        console.print("[bold yellow]📋 View Logs[/bold yellow]\n")
        
        logs_dir = Path("logs")
        if not logs_dir.exists():
            self.show_error("No logs directory found. Run a snipe operation first.")
            return
        
        log_files = list(logs_dir.glob("*.log"))
        if not log_files:
            self.show_error("No log files found.")
            return
        
        # Get most recent log file
        latest_log = max(log_files, key=lambda f: f.stat().st_mtime)
        
        try:
            with open(latest_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Show last 50 lines
            recent_lines = lines[-50:] if len(lines) > 50 else lines
            log_content = ''.join(recent_lines)
            
            info = f"""[cyan]Latest Log File:[/cyan] [bold]{latest_log.name}[/bold]
[cyan]Size:[/cyan] [bold]{latest_log.stat().st_size} bytes[/bold]
[cyan]Modified:[/cyan] [bold]{datetime.fromtimestamp(latest_log.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}[/bold]

[dim]--- Last 50 lines ---[/dim]
{log_content}"""
            
            self.show_info("Log Viewer", info)
            
        except Exception as e:
            self.show_error(f"Failed to read log file: {e}")
    
    def system_info(self):
        """Show system information"""
        self.clear_screen()
        console.print("[bold yellow]💻 System Information[/bold yellow]\n")
        
        import platform
        import psutil
        
        try:
            info = f"""[cyan]System Information:[/cyan]

[yellow]Operating System:[/yellow]
• OS: [bold]{platform.system()} {platform.release()}[/bold]
• Architecture: [bold]{platform.machine()}[/bold]
• Python Version: [bold]{platform.python_version()}[/bold]

[yellow]Hardware:[/yellow]
• CPU Cores: [bold]{psutil.cpu_count()}[/bold]
• Memory: [bold]{psutil.virtual_memory().total // (1024**3)} GB[/bold]
• Available Memory: [bold]{psutil.virtual_memory().available // (1024**3)} GB[/bold]

[yellow]Network:[/yellow]
• Network Interfaces: [bold]{len(psutil.net_if_addrs())}[/bold]

[yellow]NameMC Sniper:[/yellow]
• Config File: [bold]{'✅ Found' if Path('config.yaml').exists() else '❌ Missing'}[/bold]
• Logs Directory: [bold]{'✅ Found' if Path('logs').exists() else '❌ Missing'}[/bold]
• Virtual Environment: [bold]{'✅ Active' if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) else '❌ Not detected'}[/bold]"""
            
            self.show_info("System Information", info)
            
        except Exception as e:
            self.show_error(f"Failed to get system info: {e}")
    
    async def setup_discord_webhook(self):
        """Setup Discord webhook"""
        self.clear_screen()
        console.print("[bold yellow]🔗 Setup Discord Webhook[/bold yellow]\n")
        
        console.print("[cyan]Discord Webhook Setup Guide:[/cyan]")
        console.print("1. Go to your Discord server settings")
        console.print("2. Navigate to Integrations → Webhooks")
        console.print("3. Click 'New Webhook'")
        console.print("4. Copy the webhook URL\n")
        
        webhook_url = self.get_user_input("Enter Discord webhook URL")
        if not webhook_url:
            return
        
        if not webhook_url.startswith("https://discord.com/api/webhooks/"):
            self.show_error("Invalid webhook URL format!")
            return
        
        # Test webhook
        try:
            notifier = DiscordNotifier(webhook_url=webhook_url)
            async with notifier:
                await notifier.notify_status_update("🎉 Discord webhook test successful!")
            
            # Save to config
            try:
                self.config = self.config_manager.load_config()
                self.config.discord.enabled = True
                self.config.discord.webhook_url = webhook_url
                self.config_manager.save_config()
                
                self.show_success("Discord webhook configured successfully!")
            except Exception as e:
                self.show_error(f"Failed to save config: {e}")
                
        except Exception as e:
            self.show_error(f"Webhook test failed: {e}")
    
    async def test_discord(self):
        """Test Discord notifications"""
        self.clear_screen()
        console.print("[bold yellow]📢 Test Discord Notifications[/bold yellow]\n")
        
        try:
            self.config = self.config_manager.load_config()
            
            if not self.config.discord.enabled or not self.config.discord.webhook_url:
                self.show_error("Discord not configured! Use option 31 to setup webhook.")
                return
            
            notifier = DiscordNotifier(
                webhook_url=self.config.discord.webhook_url,
                mention_role_id=self.config.discord.mention_role_id,
                embed_color=self.config.discord.embed_color
            )
            
            with console.status("[bold green]Sending test notifications..."):
                async with notifier:
                    # Send different types of notifications
                    await notifier.notify_status_update("🧪 Testing Discord integration...")
                    await asyncio.sleep(1)
                    
                    await notifier.notify_drop_countdown(
                        username="TestUser",
                        time_remaining="5 minutes",
                        drop_time=datetime.now(timezone.utc)
                    )
                    await asyncio.sleep(1)
                    
                    await notifier.notify_snipe_result(
                        username="TestUser",
                        success=True,
                        attempts=25,
                        response_time=150.5
                    )
            
            self.show_success("Discord test notifications sent successfully!")
            
        except Exception as e:
            self.show_error(f"Discord test failed: {e}")
    
    def performance_tuning(self):
        """Show performance tuning options"""
        self.clear_screen()
        console.print("[bold yellow]⚡ Performance Tuning[/bold yellow]\n")
        
        try:
            self.config = self.config_manager.load_config()
            
            current = f"""[cyan]Current Performance Settings:[/cyan]

• Concurrent Requests: [bold]{self.config.snipe.concurrent_requests}[/bold]
• Request Delay: [bold]{self.config.snipe.request_delay_ms}ms[/bold]
• Max Attempts: [bold]{self.config.snipe.max_snipe_attempts}[/bold]
• Start Sniping: [bold]{self.config.snipe.start_sniping_at_seconds}s before drop[/bold]

[yellow]Recommended Settings:[/yellow]

[bold green]Conservative (Stable):[/bold green]
• Concurrent Requests: 5
• Request Delay: 50ms
• Good for: Avoiding rate limits

[bold yellow]Balanced (Recommended):[/bold yellow]
• Concurrent Requests: 10
• Request Delay: 25ms
• Good for: Most situations

[bold red]Aggressive (Risky):[/bold red]
• Concurrent Requests: 15
• Request Delay: 10ms
• Good for: Maximum speed (may get rate limited)

[dim]Edit config.yaml to change these settings[/dim]"""
            
            self.show_info("Performance Tuning Guide", current)
            
        except Exception as e:
            self.show_error(f"Failed to load config: {e}")
    
    def debug_mode(self):
        """Toggle debug mode"""
        self.clear_screen()
        console.print("[bold yellow]🐛 Debug Mode[/bold yellow]\n")
        
        try:
            self.config = self.config_manager.load_config()
            
            current_debug = self.config.debug_mode
            current_log_level = self.config.log_level
            
            info = f"""[cyan]Current Debug Settings:[/cyan]

• Debug Mode: [bold]{'✅ Enabled' if current_debug else '❌ Disabled'}[/bold]
• Log Level: [bold]{current_log_level}[/bold]

[yellow]Debug Mode Features:[/yellow]
• Detailed request/response logging
• Proxy connection details
• Timing information
• Error stack traces

[yellow]Log Levels:[/yellow]
• DEBUG: Most verbose (all details)
• INFO: General information
• WARNING: Important warnings only
• ERROR: Errors only

[dim]Edit config.yaml to change debug_mode and log_level[/dim]"""
            
            self.show_info("Debug Mode Settings", info)
            
        except Exception as e:
            self.show_error(f"Failed to load config: {e}")
    
    async def test_bearer_token(self):
        """Test bearer token"""
        self.clear_screen()
        console.print("[bold yellow]🔑 Bearer Token Test[/bold yellow]\n")
        
        try:
            self.config = self.config_manager.load_config()
            if not self.config.snipe.bearer_token or self.config.snipe.bearer_token == "your_minecraft_bearer_token_here":
                self.show_error("Bearer token not configured!")
                return
            
            import aiohttp
            url = "https://api.minecraftservices.com/minecraft/profile"
            headers = {
                'Authorization': f'Bearer {self.config.snipe.bearer_token}',
                'User-Agent': 'MinecraftSniper/1.0'
            }
            
            try:
                with console.status("[bold green]Testing bearer token..."):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=headers) as response:
                            if response.status == 200:
                                profile_data = await response.json()
                                current_name = profile_data.get('name', 'Unknown')
                                uuid = profile_data.get('id', 'Unknown')
                                
                                info = f"""[green]✅ Bearer token is valid![/green]

[green]Account Information:[/green]
• Username: [bold]{current_name}[/bold]
• UUID: [bold]{uuid}[/bold]
• Token Status: [bold green]Active[/bold green]
"""
                                self.show_info("Token Test Results", info)
                            elif response.status == 401:
                                self.show_error("Bearer token is invalid or expired")
                            else:
                                response_text = await response.text()
                                self.show_error(f"Token validation failed: HTTP {response.status} - {response_text}")
            except Exception as e:
                self.show_error(f"Token test error: {e}")
            
        except Exception as e:
            self.show_error(f"Config error: {e}")
    
    def show_help(self):
        """Show help information"""
        help_text = """[bold cyan]NameMC Sniper Help[/bold cyan]

[yellow]Quick Start:[/yellow]
1. Use option [bold]11[/bold] to create configuration
2. Use option [bold]21[/bold] to test your bearer token
3. Use option [bold]2[/bold] to snipe at specific time

[yellow]Key Features:[/yellow]
• [bold]High-Speed Sniping[/bold] - 10 concurrent workers
• [bold]Proxy Support[/bold] - Rotate through multiple proxies
• [bold]Discord Notifications[/bold] - Real-time updates
• [bold]Precise Timing[/bold] - Starts 0.1s before drop

[yellow]Time Format:[/yellow]
Use NameMC's exact format: [bold]MM/DD/YYYY • H∶MM∶SS AM/PM[/bold]
Example: [bold]12/25/2024 • 3∶30∶00 PM[/bold]

[yellow]Support:[/yellow]
• GitHub: [bold]github.com/zwroee/NameMcSniper[/bold]
• Check logs in the [bold]logs/[/bold] directory for debugging
"""
        self.show_info("Help & Documentation", help_text)
    
    def show_about(self):
        """Show about information"""
        about_text = f"""[bold cyan]NameMC Sniper v2.0.0[/bold cyan]

[yellow]Authors:[/yellow]
• [bold]zwroe[/bold] - github.com/zwroee
• [bold]light[/bold] - github.com/ZeroLight18

[yellow]Description:[/yellow]
Professional-grade Minecraft username sniper with advanced features including high-speed concurrent sniping, proxy rotation, Discord notifications, and precise timing control.

[yellow]Features:[/yellow]
• Async architecture for maximum performance
• Bearer token authentication
• Smart proxy management with health checking
• Rich CLI interface with beautiful menus
• Comprehensive logging and error handling

[yellow]Legal Notice:[/yellow]
This tool is for educational purposes only. Please comply with Minecraft's Terms of Service and use responsibly.

[dim]Built with Python • Created through collaborative development[/dim]
"""
        self.show_info("About NameMC Sniper", about_text)
    
    async def run(self):
        """Main CLI loop"""
        while self.running:
            self.show_main_menu()
            
            try:
                choice = self.get_user_input().strip()
                
                if choice == "99":
                    console.print("\n[bold red]👋 Thanks for using NameMC Sniper![/bold red]")
                    break
                elif choice == "1":
                    await self.snipe_at_time()
                elif choice == "11":
                    self.create_config()
                elif choice == "12":
                    console.print("\n[yellow]💡 Tip: Edit config.yaml with your preferred text editor[/yellow]")
                    console.input("\n[dim]Press Enter to continue...[/dim]")
                elif choice == "13":
                    self.validate_config()
                elif choice == "14":
                    confirm = self.get_user_input("Reset config to defaults? (y/N)")
                    if confirm.lower() == 'y':
                        self.create_config()
                elif choice == "21":
                    await self.test_bearer_token()
                elif choice == "22":
                    await self.test_proxies()
                elif choice == "23":
                    self.view_logs()
                elif choice == "24":
                    self.system_info()
                elif choice == "31":
                    await self.setup_discord_webhook()
                elif choice == "32":
                    await self.test_discord()
                elif choice == "33":
                    console.print("\n[yellow]💡 Tip: Edit notification intervals in config.yaml[/yellow]")
                    console.input("\n[dim]Press Enter to continue...[/dim]")
                elif choice == "41":
                    self.performance_tuning()
                elif choice == "42":
                    console.print("\n[yellow]💡 Tip: Use option 22 to test and manage proxies[/yellow]")
                    console.input("\n[dim]Press Enter to continue...[/dim]")
                elif choice == "43":
                    self.debug_mode()
                elif choice == "51":
                    self.show_help()
                elif choice == "52":
                    self.show_about()
                elif choice == "53":
                    import webbrowser
                    webbrowser.open("https://github.com/zwroee/NameMcSniper")
                    self.show_success("Opened GitHub repository in browser!")
                elif choice == "back" or choice == "":
                    continue
                else:
                    self.show_error(f"Invalid option: {choice}")
                    
            except KeyboardInterrupt:
                console.print("\n\n[bold red]👋 Goodbye![/bold red]")
                break
            except Exception as e:
                self.show_error(f"Unexpected error: {e}")

def main():
    """Main entry point"""
    try:
        cli = NameMCSniperCLI()
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
