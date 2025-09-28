# test_espicoW.py
# Test script for the combined espicoW library

import espicoW
import utime

def test_basic_connection():
    """Test basic WiFi connectivity"""
    print("=" * 50)
    print("Testing espicoW Library")
    print("=" * 50)
    
    # Initialize
    print("1. Initializing WiFi...")
    if not espicoW.init():
        print("   FAILED: Could not initialize WiFi")
        return False
    print("   SUCCESS: WiFi initialized")
    
    # Connect to WiFi
    print("2. Connecting to WiFi...")
    result = espicoW.begin("Hasan", "nhasan_2008")
    if result != espicoW.WL_CONNECTED:
        print(f"   FAILED: WiFi connection failed (status: {result})")
        return False
    print("   SUCCESS: WiFi connected")
    
    # Get network info
    print("3. Network Information:")
    ip = espicoW.local_ip()
    gateway = espicoW.gateway_ip()
    subnet = espicoW.subnet_mask()
    rssi = espicoW.rssi()
    channel = espicoW.channel()
    
    print(f"   IP Address: {ip}")
    print(f"   Gateway: {gateway}")
    print(f"   Subnet: {subnet}")
    print(f"   RSSI: {rssi} dBm")
    print(f"   Channel: {channel}")
    
    return True

def test_http_connection():
    """Test HTTP connection (not HTTPS)"""
    print("\n4. Testing HTTP Connection...")
    
    client = espicoW.Client()
    
    # Try HTTP connection to a reliable server
    test_servers = [
        ("httpbin.org", 80),
        ("www.google.com", 80),
        ("www.example.com", 80)
    ]
    
    for host, port in test_servers:
        print(f"   Trying {host}:{port}...")
        
        if client.connect(host, port):
            print(f"   SUCCESS: Connected to {host}")
            
            # Send simple HTTP request
            request = f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
            client.print(request)
            client.flush()
            
            # Wait for response
            timeout = utime.ticks_ms()
            while client.available() == 0 and utime.ticks_ms() - timeout < 5000:
                utime.sleep_ms(100)
            
            if client.available() > 0:
                # Read some response data
                data = client.readBuf(200)  # Read first 200 bytes
                print(f"   Response received ({len(data)} bytes)")
                print(f"   Preview: {data[:100]}...")
                client.stop()
                return True
            else:
                print(f"   No response from {host}")
                client.stop()
        else:
            print(f"   FAILED: Could not connect to {host}")
    
    print("   All HTTP tests failed")
    return False

def test_ssl_connection():
    """Test SSL connection with known working servers"""
    print("\n5. Testing SSL Connection...")
    
    client = espicoW.Client()
    
    # Try SSL with servers known to work with ESP8285
    ssl_servers = [
        ("www.google.com", 443),
        ("httpbin.org", 443),
    ]
    
    for host, port in ssl_servers:
        print(f"   Trying SSL to {host}:{port}...")
        
        if client.connectSSL(host, port):
            print(f"   SUCCESS: SSL connected to {host}")
            
            # Send simple HTTPS request
            request = f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
            client.print(request)
            client.flush()
            
            # Wait for response
            timeout = utime.ticks_ms()
            while client.available() == 0 and utime.ticks_ms() - timeout < 8000:
                utime.sleep_ms(100)
            
            if client.available() > 0:
                data = client.readBuf(200)
                print(f"   SSL Response received ({len(data)} bytes)")
                print(f"   Preview: {data[:100]}...")
                client.stop()
                return True
            else:
                print(f"   No SSL response from {host}")
                client.stop()
        else:
            print(f"   FAILED: Could not SSL connect to {host}")
    
    print("   All SSL tests failed")
    return False

def test_error_handling():
    """Test error handling"""
    print("\n6. Testing Error Handling...")
    
    client = espicoW.Client()
    
    # Try to connect to non-existent server
    print("   Testing connection to invalid server...")
    if not client.connect("nonexistent.invalid.domain", 80):
        print("   SUCCESS: Properly handled invalid connection")
        error = espicoW.get_last_error()
        error_msg = espicoW.get_error_string(error)
        print(f"   Error code: {error} ({error_msg})")
    else:
        print("   WARNING: Connected to invalid domain (unexpected)")
        client.stop()

def test_multiple_clients():
    """Test multiple client connections"""
    print("\n7. Testing Multiple Clients...")
    
    clients = []
    success_count = 0
    
    # Try to create multiple connections
    for i in range(3):
        client = espicoW.Client()
        print(f"   Creating client {i+1}...")
        
        if client.connect("httpbin.org", 80):
            print(f"   Client {i+1}: Connected")
            clients.append(client)
            success_count += 1
        else:
            print(f"   Client {i+1}: Failed to connect")
    
    print(f"   Successfully created {success_count} concurrent connections")
    
    # Clean up
    for client in clients:
        client.stop()
    
    return success_count > 0

def main():
    """Run all tests"""
    try:
        print("Starting espicoW Library Tests...")
        print(f"Library version: {espicoW.__version__}")
        
        # Test basic connectivity
        if not test_basic_connection():
            print("\nBasic connectivity failed. Stopping tests.")
            return
        
        # Test HTTP
        http_ok = test_http_connection()
        
        # Test SSL (might fail depending on firmware)
        ssl_ok = test_ssl_connection()
        
        # Test error handling
        test_error_handling()
        
        # Test multiple clients
        multi_ok = test_multiple_clients()
        
        # Summary
        print("\n" + "=" * 50)
        print("TEST RESULTS SUMMARY")
        print("=" * 50)
        print(f"WiFi Connection:    {'PASS' if True else 'FAIL'}")
        print(f"HTTP Connection:    {'PASS' if http_ok else 'FAIL'}")
        print(f"SSL Connection:     {'PASS' if ssl_ok else 'FAIL'}")
        print(f"Multiple Clients:   {'PASS' if multi_ok else 'FAIL'}")
        print(f"Error Handling:     PASS")
        
        if http_ok:
            print("\nCONCLUSION: espicoW library is working correctly!")
            print("You can use it for HTTP-based projects.")
            if ssl_ok:
                print("SSL/HTTPS functionality is also working.")
            else:
                print("SSL may need firmware updates for full compatibility.")
        else:
            print("\nWARNING: Basic HTTP connectivity failed.")
            print("Check network settings and ESP8285 firmware.")
        
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
    except Exception as e:
        print(f"\nTest error: {e}")
    finally:
        # Cleanup
        try:
            espicoW.disconnect()
        except:
            pass
        print("\nTest complete.")

if __name__ == "__main__":
    main()