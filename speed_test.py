#!/usr/bin/env python3
"""
Speed test for NameMC Sniper - Test your setup's performance
"""

import asyncio
import aiohttp
import time
import statistics
from datetime import datetime

async def test_minecraft_api_speed(bearer_token: str, num_tests: int = 10):
    """Test speed to Minecraft API"""
    print(f"🚀 Testing Minecraft API speed with {num_tests} requests...")
    
    url = "https://api.minecraftservices.com/minecraft/profile"
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/json'
    }
    
    connector = aiohttp.TCPConnector(
        limit=100,
        limit_per_host=50,
        ttl_dns_cache=300,
        use_dns_cache=True
    )
    
    response_times = []
    
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(num_tests):
            start_time = time.time()
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    await response.text()
                    response_time = (time.time() - start_time) * 1000  # Convert to ms
                    response_times.append(response_time)
                    print(f"  Request {i+1}: {response_time:.0f}ms (Status: {response.status})")
            except Exception as e:
                print(f"  Request {i+1}: FAILED - {e}")
            
            await asyncio.sleep(0.1)  # Small delay between tests
    
    if response_times:
        avg_time = statistics.mean(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        
        print(f"\n📊 Results:")
        print(f"  Average: {avg_time:.0f}ms")
        print(f"  Fastest: {min_time:.0f}ms")
        print(f"  Slowest: {max_time:.0f}ms")
        
        if avg_time < 50:
            print("  🟢 EXCELLENT - Your connection is very fast!")
        elif avg_time < 100:
            print("  🟡 GOOD - Decent speed for sniping")
        else:
            print("  🔴 SLOW - Consider using a VPS or better internet")
    else:
        print("❌ All requests failed!")

async def test_concurrent_requests(bearer_token: str, concurrent: int = 50):
    """Test concurrent request performance"""
    print(f"\n🔥 Testing {concurrent} concurrent requests...")
    
    url = "https://api.minecraftservices.com/minecraft/profile"
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/json'
    }
    
    connector = aiohttp.TCPConnector(
        limit=500,
        limit_per_host=100,
        ttl_dns_cache=300,
        use_dns_cache=True
    )
    
    async def make_request(session, request_id):
        start_time = time.time()
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=2)) as response:
                await response.text()
                response_time = (time.time() - start_time) * 1000
                return {'id': request_id, 'time': response_time, 'status': response.status, 'success': True}
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return {'id': request_id, 'time': response_time, 'error': str(e), 'success': False}
    
    start_time = time.time()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [make_request(session, i) for i in range(concurrent)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    total_time = time.time() - start_time
    
    successful = [r for r in results if isinstance(r, dict) and r.get('success')]
    failed = [r for r in results if isinstance(r, dict) and not r.get('success')]
    
    print(f"📊 Concurrent Test Results:")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Successful: {len(successful)}/{concurrent}")
    print(f"  Failed: {len(failed)}/{concurrent}")
    print(f"  Requests/second: {concurrent/total_time:.1f}")
    
    if successful:
        avg_time = statistics.mean([r['time'] for r in successful])
        print(f"  Average response time: {avg_time:.0f}ms")
        
        if len(successful) == concurrent and avg_time < 100:
            print("  🟢 EXCELLENT - Ready for competitive sniping!")
        elif len(successful) > concurrent * 0.8:
            print("  🟡 GOOD - Should work for most snipes")
        else:
            print("  🔴 POOR - May struggle against fast snipers")

def test_system_clock():
    """Test system clock accuracy"""
    print(f"\n🕐 System Clock Test:")
    print(f"  Current time: {datetime.now()}")
    print(f"  UTC time: {datetime.utcnow()}")
    print("  💡 Tip: Sync with NTP for best accuracy!")

async def main():
    print("⚡ NameMC Sniper Speed Test ⚡")
    print("=" * 40)
    
    bearer_token = input("Enter your bearer token: ").strip()
    
    if not bearer_token:
        print("❌ Bearer token required!")
        return
    
    print("\n🧪 Running speed tests...")
    
    # Test basic API speed
    await test_minecraft_api_speed(bearer_token, 5)
    
    # Test concurrent performance
    await test_concurrent_requests(bearer_token, 25)
    
    # Test system clock
    test_system_clock()
    
    print("\n💡 Optimization Tips:")
    print("  1. Use residential proxies close to Minecraft servers")
    print("  2. Run on a VPS with low latency (US East Coast)")
    print("  3. Use SSD storage and wired internet")
    print("  4. Close unnecessary programs during sniping")
    print("  5. Sync system clock with NTP servers")

if __name__ == "__main__":
    asyncio.run(main())
