"""
test_espicoW.py - Comprehensive test suite for ESPicoW library
Tests all major functionality of the WiFi library
"""

from espicoW import ESPicoW
import time

# Configuration - CHANGE THESE TO MATCH YOUR SETUP
WIFI_SSID = "Hasan"
WIFI_PASSWORD = "nhasan_2008"
UART_ID = 0
TX_PIN = 0
RX_PIN = 1

# Test configuration
TEST_TCP_HOST = "example.com"
TEST_TCP_PORT = 80
TEST_PING_HOST = "8.8.8.8"

class TestResult:
    """Track test results"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add(self, name, passed, message=""):
        self.tests.append({
            'name': name,
            'passed': passed,
            'message': message
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
    
    def print_summary(self):
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        for test in self.tests:
            status = "✓ PASS" if test['passed'] else "✗ FAIL"
            msg = f" - {test['message']}" if test['message'] else ""
            print(f"{status}: {test['name']}{msg}")
        
        print("=" * 70)
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0
        print(f"Results: {self.passed}/{total} passed ({percentage:.1f}%)")
        print("=" * 70)

def print_test_header(title):
    """Print formatted test section header"""
    print("\n" + "-" * 70)
    print(f"TEST: {title}")
    print("-" * 70)

def test_basic_communication(wifi, results):
    """Test 1: Basic AT command communication"""
    print_test_header("Basic Communication")
    
    # Test AT command
    print("Testing AT command response...")
    if wifi.test():
        print("  ✓ AT command successful")
        results.add("AT Command", True)
    else:
        print("  ✗ AT command failed")
        results.add("AT Command", False, "No response from ESP8285")
        return False
    
    # Test firmware version
    print("Getting firmware version...")
    version = wifi.get_version()
    if version and "OK" in version:
        print(f"  ✓ Firmware version retrieved")
        # Extract version info
        for line in version.split('\n'):
            if 'SDK' in line or 'AT' in line:
                print(f"    {line.strip()}")
        results.add("Get Version", True)
    else:
        print("  ✗ Failed to get version")
        results.add("Get Version", False)
    
    # Test reset
    print("Testing module reset...")
    if wifi.reset():
        print("  ✓ Reset successful")
        results.add("Module Reset", True)
    else:
        print("  ✗ Reset failed")
        results.add("Module Reset", False)
    
    return True

def test_wifi_modes(wifi, results):
    """Test 2: WiFi mode setting"""
    print_test_header("WiFi Modes")
    
    modes = [
        (wifi.MODE_STATION, "Station"),
        (wifi.MODE_AP, "Access Point"),
        (wifi.MODE_BOTH, "Station + AP")
    ]
    
    for mode, name in modes:
        print(f"Setting mode to {name}...")
        if wifi.set_mode(mode):
            print(f"  ✓ {name} mode set successfully")
            results.add(f"Set {name} Mode", True)
        else:
            print(f"  ✗ Failed to set {name} mode")
            results.add(f"Set {name} Mode", False)
        time.sleep_ms(500)

def test_network_scan(wifi, results):
    """Test 3: Network scanning"""
    print_test_header("Network Scanning")
    
    print("Scanning for WiFi networks...")
    networks = wifi.scan()
    
    if networks and len(networks) > 0:
        print(f"  ✓ Found {len(networks)} networks")
        results.add("Network Scan", True, f"Found {len(networks)} networks")
        
        # Display top 5 networks
        print("\n  Top networks by signal strength:")
        networks.sort(key=lambda x: x['rssi'], reverse=True)
        
        enc_types = {0: "Open", 1: "WEP", 2: "WPA", 3: "WPA2", 4: "WPA/2"}
        for i, net in enumerate(networks[:5], 1):
            enc = enc_types.get(net['encryption'], "?")
            print(f"    {i}. {net['ssid']:<25} {net['rssi']:>4} dBm  Ch:{net['channel']:>2}  {enc}")
        
        # Check if our target SSID is visible
        target_found = any(net['ssid'] == WIFI_SSID for net in networks)
        if target_found:
            print(f"\n  ✓ Target network '{WIFI_SSID}' is visible")
            results.add("Target Network Visible", True)
        else:
            print(f"\n  ⚠ Warning: Target network '{WIFI_SSID}' not found in scan")
            results.add("Target Network Visible", False, "Not in scan results")
    else:
        print("  ✗ No networks found")
        results.add("Network Scan", False, "No networks detected")

def test_wifi_connection(wifi, results):
    """Test 4: WiFi connection"""
    print_test_header("WiFi Connection")
    
    # Ensure station mode
    wifi.set_mode(wifi.MODE_STATION)
    time.sleep_ms(500)
    
    print(f"Connecting to '{WIFI_SSID}'...")
    start_time = time.ticks_ms()
    
    if wifi.connect(WIFI_SSID, WIFI_PASSWORD, timeout=20000):
        elapsed = time.ticks_diff(time.ticks_ms(), start_time) / 1000
        print(f"  ✓ Connected successfully in {elapsed:.1f}s")
        results.add("WiFi Connection", True, f"{elapsed:.1f}s")
        
        # Get IP address
        print("Getting IP address...")
        ip_info = wifi.get_ip()
        
        if ip_info['station']:
            print(f"  ✓ IP Address: {ip_info['station']}")
            results.add("Get IP Address", True, ip_info['station'])
        else:
            print("  ✗ Failed to get IP address")
            results.add("Get IP Address", False)
        
        # Check connection status
        print("Verifying connection status...")
        if wifi.is_connected():
            print("  ✓ Connection status verified")
            results.add("Connection Status Check", True)
        else:
            print("  ✗ Connection status check failed")
            results.add("Connection Status Check", False)
        
        return True
    else:
        print("  ✗ Connection failed")
        results.add("WiFi Connection", False, "Timeout or auth error")
        return False

def test_ping(wifi, results):
    """Test 5: Ping functionality"""
    print_test_header("Ping Test")
    
    hosts = [
        ("8.8.8.8", "Google DNS"),
        ("1.1.1.1", "Cloudflare DNS")
    ]
    
    for host, name in hosts:
        print(f"Pinging {name} ({host})...")
        response_time = wifi.ping(host)
        
        if response_time:
            print(f"  ✓ Response time: {response_time} ms")
            results.add(f"Ping {name}", True, f"{response_time}ms")
        else:
            print(f"  ✗ Ping failed or timeout")
            results.add(f"Ping {name}", False, "No response")
        
        time.sleep(1)

def test_http_get(wifi, results):
    """Test 6: HTTP GET requests"""
    print_test_header("HTTP GET Requests")
    
    test_urls = [
        ("http://example.com", "Example.com"),
        ("http://httpbin.org/ip", "HTTPBin IP Check")
    ]
    
    for url, name in test_urls:
        print(f"Fetching {name}...")
        print(f"  URL: {url}")
        
        start_time = time.ticks_ms()
        response = wifi.http_get(url, timeout=15000)
        elapsed = time.ticks_diff(time.ticks_ms(), start_time) / 1000
        
        if response and len(response) > 0:
            print(f"  ✓ Request successful in {elapsed:.1f}s")
            print(f"    Response size: {len(response)} bytes")
            
            # Show preview
            preview = response[:100].replace('\n', ' ').replace('\r', '')
            print(f"    Preview: {preview}...")
            
            results.add(f"HTTP GET {name}", True, f"{len(response)} bytes in {elapsed:.1f}s")
        else:
            print(f"  ✗ Request failed")
            results.add(f"HTTP GET {name}", False, "No response or error")
        
        time.sleep(1)

def test_tcp_connection(wifi, results):
    """Test 7: TCP connection"""
    print_test_header("TCP Connection")
    
    # Enable multiple connections
    print("Enabling multiple connections...")
    if wifi.set_multiple_connections(True):
        print("  ✓ Multiple connections enabled")
        results.add("Enable Multiple Connections", True)
    else:
        print("  ✗ Failed to enable multiple connections")
        results.add("Enable Multiple Connections", False)
        return
    
    time.sleep_ms(500)
    
    # Test TCP connection
    print(f"Connecting to {TEST_TCP_HOST}:{TEST_TCP_PORT}...")
    
    if wifi.start_connection(0, wifi.TYPE_TCP, TEST_TCP_HOST, TEST_TCP_PORT):
        print("  ✓ TCP connection established (Link ID: 0)")
        results.add("TCP Connection Start", True)
        
        # Send HTTP request
        print("Sending HTTP request...")
        request = f"GET / HTTP/1.1\r\nHost: {TEST_TCP_HOST}\r\nConnection: close\r\n\r\n"
        
        if wifi.send(0, request):
            print("  ✓ Data sent successfully")
            results.add("TCP Send Data", True)
            
            # Receive response
            print("Receiving response...")
            start_time = time.ticks_ms()
            response = ""
            
            while time.ticks_diff(time.ticks_ms(), start_time) < 10000:
                data = wifi.receive(timeout=1000)
                if data:
                    for link_id, content in data:
                        response += content
                
                if "CLOSED" in response or len(response) > 1000:
                    break
            
            if len(response) > 0:
                print(f"  ✓ Received {len(response)} bytes")
                results.add("TCP Receive Data", True, f"{len(response)} bytes")
            else:
                print("  ✗ No data received")
                results.add("TCP Receive Data", False)
        else:
            print("  ✗ Failed to send data")
            results.add("TCP Send Data", False)
        
        # Close connection
        print("Closing connection...")
        if wifi.close(0):
            print("  ✓ Connection closed")
            results.add("TCP Close Connection", True)
        else:
            print("  ✗ Failed to close connection")
            results.add("TCP Close Connection", False)
    else:
        print("  ✗ Failed to establish TCP connection")
        results.add("TCP Connection Start", False)

def test_connection_management(wifi, results):
    """Test 8: Connection management"""
    print_test_header("Connection Management")
    
    # Get connection status
    print("Getting connection status...")
    connections = wifi.get_connection_status()
    
    print(f"  Active connections: {len(connections)}")
    results.add("Get Connection Status", True, f"{len(connections)} connections")
    
    if connections:
        for conn in connections:
            print(f"    Link {conn['link_id']}: {conn['type']} to {conn['remote_ip']}:{conn['remote_port']}")

def test_dhcp(wifi, results):
    """Test 9: DHCP settings"""
    print_test_header("DHCP Configuration")
    
    # Test DHCP enable/disable
    print("Testing DHCP enable...")
    if wifi.enable_dhcp(1, True):  # Station mode DHCP
        print("  ✓ DHCP enabled for station mode")
        results.add("Enable DHCP", True)
    else:
        print("  ✗ Failed to enable DHCP")
        results.add("Enable DHCP", False)

def test_disconnect(wifi, results):
    """Test 10: Disconnection"""
    print_test_header("WiFi Disconnection")
    
    print("Disconnecting from WiFi...")
    if wifi.disconnect():
        print("  ✓ Disconnected successfully")
        results.add("WiFi Disconnect", True)
        
        time.sleep(1)
        
        # Verify disconnection
        if not wifi.is_connected():
            print("  ✓ Disconnection verified")
            results.add("Verify Disconnection", True)
        else:
            print("  ✗ Still showing as connected")
            results.add("Verify Disconnection", False)
    else:
        print("  ✗ Disconnect command failed")
        results.add("WiFi Disconnect", False)

def run_all_tests():
    """Run complete test suite"""
    print("\n" + "=" * 70)
    print("ESPicoW Library - Complete Test Suite")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  SSID: {WIFI_SSID}")
    print(f"  UART: {UART_ID}, TX:{TX_PIN}, RX:{RX_PIN}")
    print("=" * 70)
    
    # Initialize WiFi
    print("\nInitializing WiFi module...")
    wifi = ESPicoW(uart_id=UART_ID, tx_pin=TX_PIN, rx_pin=RX_PIN, debug=False)
    
    # Create results tracker
    results = TestResult()
    
    # Run all tests
    try:
        # Test 1: Basic communication
        if not test_basic_communication(wifi, results):
            print("\n⚠ Critical failure: Cannot communicate with ESP8285")
            print("Please check wiring and configuration")
            results.print_summary()
            return
        
        # Test 2: WiFi modes
        test_wifi_modes(wifi, results)
        
        # Test 3: Network scan
        test_network_scan(wifi, results)
        
        # Test 4: WiFi connection
        connected = test_wifi_connection(wifi, results)
        
        if connected:
            # Test 5: Ping
            test_ping(wifi, results)
            
            # Test 6: HTTP GET
            test_http_get(wifi, results)
            
            # Test 7: TCP connection
            test_tcp_connection(wifi, results)
            
            # Test 8: Connection management
            test_connection_management(wifi, results)
            
            # Test 9: DHCP
            test_dhcp(wifi, results)
            
            # Test 10: Disconnect
            test_disconnect(wifi, results)
        else:
            print("\n⚠ Skipping network-dependent tests due to connection failure")
        
    except KeyboardInterrupt:
        print("\n\n⚠ Tests interrupted by user")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import sys
        sys.print_exception(e)
    finally:
        # Cleanup
        print("\nCleaning up...")
        try:
            wifi.close_all()
        except:
            pass
    
    # Print results
    results.print_summary()
    
    print("\nTest suite completed!")
    print("Check results above for any failures.")

# Run tests when executed directly
if __name__ == "__main__":
    run_all_tests()
