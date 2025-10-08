"""
espicoW.py - WiFi Library for RP2040 with ESP8285
Complete WiFi library for RP2040 boards with onboard ESP8285 chip
Supports: Station mode, AP mode, TCP/UDP connections, HTTP requests
"""

from machine import UART, Pin
import time

class ESPicoW:
    """WiFi library for RP2040 with ESP8285 using AT commands"""
    
    # WiFi modes
    MODE_STATION = 1
    MODE_AP = 2
    MODE_BOTH = 3
    
    # Connection types
    TYPE_TCP = "TCP"
    TYPE_UDP = "UDP"
    TYPE_SSL = "SSL"
    
    def __init__(self, uart_id=0, tx_pin=0, rx_pin=1, baudrate=115200, debug=False):
        """
        Initialize ESP8285 communication
        
        Args:
            uart_id: UART peripheral (0 or 1)
            tx_pin: TX pin number
            rx_pin: RX pin number
            baudrate: Communication speed (default 115200)
            debug: Enable debug output
        """
        self.uart = UART(uart_id, baudrate=baudrate, tx=Pin(tx_pin), rx=Pin(rx_pin))
        self.debug = debug
        self.timeout = 5000  # Default timeout in ms
        self.connections = {}
        
    def _send_cmd(self, cmd, timeout=None, wait_for="OK"):
        """Send AT command and wait for response"""
        if timeout is None:
            timeout = self.timeout
            
        if self.debug:
            print(f"[TX] {cmd}")
            
        self.uart.write(cmd + "\r\n")
        start = time.ticks_ms()
        response = b""
        
        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            if self.uart.any():
                chunk = self.uart.read()
                if chunk:
                    response += chunk
                
                try:
                    resp_str = response.decode('utf-8', 'ignore')
                    if wait_for in resp_str or "ERROR" in resp_str or "FAIL" in resp_str:
                        if self.debug:
                            print(f"[RX] {resp_str}")
                        return resp_str
                except:
                    # If decode fails, continue collecting data
                    pass
                    
            time.sleep_ms(10)
        
        # Final decode attempt
        try:
            resp_str = response.decode('utf-8', 'ignore')
        except:
            resp_str = str(response)
            
        if self.debug:
            print(f"[RX] Timeout: {resp_str}")
        return resp_str
    
    def reset(self):
        """Reset ESP8285 module"""
        resp = self._send_cmd("AT+RST", timeout=3000, wait_for="ready")
        time.sleep(2)
        # Clear any remaining data in buffer
        while self.uart.any():
            self.uart.read()
        time.sleep_ms(500)
        return self.test()
    
    def test(self):
        """Test AT command interface"""
        resp = self._send_cmd("AT", timeout=1000)
        return "OK" in resp
    
    def get_version(self):
        """Get firmware version"""
        resp = self._send_cmd("AT+GMR")
        return resp
    
    def set_mode(self, mode):
        """
        Set WiFi mode
        
        Args:
            mode: MODE_STATION, MODE_AP, or MODE_BOTH
        """
        resp = self._send_cmd(f"AT+CWMODE={mode}")
        return "OK" in resp
    
    def connect(self, ssid, password, timeout=15000):
        """
        Connect to WiFi network (Station mode)
        
        Args:
            ssid: Network SSID
            password: Network password
            timeout: Connection timeout in ms
        """
        # Set station mode
        self.set_mode(self.MODE_STATION)
        time.sleep_ms(100)
        
        # Connect to AP
        cmd = f'AT+CWJAP="{ssid}","{password}"'
        resp = self._send_cmd(cmd, timeout=timeout, wait_for="WIFI CONNECTED")
        
        if "WIFI CONNECTED" in resp or "OK" in resp:
            time.sleep(1)
            return True
        return False
    
    def disconnect(self):
        """Disconnect from WiFi network"""
        resp = self._send_cmd("AT+CWQAP")
        return "OK" in resp
    
    def is_connected(self):
        """Check if connected to WiFi"""
        resp = self._send_cmd("AT+CWJAP?", timeout=2000)
        return "No AP" not in resp and "ERROR" not in resp
    
    def get_ip(self):
        """Get IP address information"""
        resp = self._send_cmd("AT+CIFSR", timeout=2000)
        
        # Parse IP addresses manually
        sta_ip = None
        ap_ip = None
        
        lines = resp.split('\n')
        for line in lines:
            # Handle both CIFSR and CISFR (typo in some firmware)
            if 'STAIP' in line or 'STIP' in line:
                # Extract IP between quotes
                try:
                    if '"' in line:
                        start = line.index('"') + 1
                        end = line.index('"', start)
                        sta_ip = line[start:end]
                except:
                    pass
            elif 'APIP' in line:
                try:
                    if '"' in line:
                        start = line.index('"') + 1
                        end = line.index('"', start)
                        ap_ip = line[start:end]
                except:
                    pass
        
        return {
            'station': sta_ip,
            'ap': ap_ip
        }
    
    def scan(self):
        """Scan for available WiFi networks"""
        resp = self._send_cmd("AT+CWLAP", timeout=10000)
        
        # Parse network list manually (MicroPython's re is limited)
        networks = []
        lines = resp.split('\n')
        
        for line in lines:
            if '+CWLAP:' in line:
                try:
                    # Extract values between parentheses
                    start = line.index('(') + 1
                    end = line.rindex(')')
                    data = line[start:end]
                    
                    # Split by comma, handling quoted strings
                    parts = []
                    current = ""
                    in_quotes = False
                    
                    for char in data:
                        if char == '"':
                            in_quotes = not in_quotes
                        elif char == ',' and not in_quotes:
                            parts.append(current)
                            current = ""
                        else:
                            current += char
                    parts.append(current)
                    
                    if len(parts) >= 5:
                        networks.append({
                            'encryption': int(parts[0]),
                            'ssid': parts[1].strip('"'),
                            'rssi': int(parts[2]),
                            'mac': parts[3].strip('"'),
                            'channel': int(parts[4])
                        })
                except:
                    continue
                    
        return networks
    
    def create_ap(self, ssid, password, channel=1, encryption=3):
        """
        Create Access Point
        
        Args:
            ssid: AP SSID
            password: AP password (min 8 chars)
            channel: WiFi channel (1-13)
            encryption: 0=Open, 2=WPA_PSK, 3=WPA2_PSK, 4=WPA_WPA2_PSK
        """
        self.set_mode(self.MODE_AP)
        time.sleep_ms(100)
        
        cmd = f'AT+CWSAP="{ssid}","{password}",{channel},{encryption}'
        resp = self._send_cmd(cmd, timeout=3000)
        return "OK" in resp
    
    def set_multiple_connections(self, enable=True):
        """Enable/disable multiple connections"""
        mode = 1 if enable else 0
        resp = self._send_cmd(f"AT+CIPMUX={mode}")
        return "OK" in resp
    
    def start_connection(self, link_id, conn_type, remote_ip, remote_port, local_port=0):
        """
        Start TCP/UDP connection
        
        Args:
            link_id: Connection ID (0-4)
            conn_type: TYPE_TCP, TYPE_UDP, or TYPE_SSL
            remote_ip: Remote host IP or domain
            remote_port: Remote port
            local_port: Local port (UDP only)
        """
        if conn_type == self.TYPE_UDP and local_port > 0:
            cmd = f'AT+CIPSTART={link_id},"{conn_type}","{remote_ip}",{remote_port},{local_port}'
        else:
            cmd = f'AT+CIPSTART={link_id},"{conn_type}","{remote_ip}",{remote_port}'
            
        resp = self._send_cmd(cmd, timeout=10000)
        
        if "OK" in resp or "ALREADY CONNECTED" in resp:
            self.connections[link_id] = {
                'type': conn_type,
                'ip': remote_ip,
                'port': remote_port
            }
            return True
        return False
    
    def send(self, link_id, data):
        """
        Send data through connection
        
        Args:
            link_id: Connection ID
            data: Data to send (string or bytes)
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
            
        length = len(data)
        
        # Send length command
        cmd = f"AT+CIPSEND={link_id},{length}"
        resp = self._send_cmd(cmd, timeout=1000, wait_for=">")
        
        if ">" not in resp:
            return False
            
        # Send actual data
        self.uart.write(data)
        start = time.ticks_ms()
        response = b""
        
        while time.ticks_diff(time.ticks_ms(), start) < 5000:
            if self.uart.any():
                response += self.uart.read()
                resp_str = response.decode('utf-8', 'ignore')
                if "SEND OK" in resp_str:
                    return True
                if "SEND FAIL" in resp_str or "ERROR" in resp_str:
                    return False
            time.sleep_ms(10)
            
        return False
    
    def receive(self, timeout=5000):
        """
        Receive data from connections
        
        Returns:
            List of tuples (link_id, data)
        """
        start = time.ticks_ms()
        response = b""
        received = []
        
        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            if self.uart.any():
                response += self.uart.read()
                
                # Parse +IPD messages manually
                try:
                    resp_str = response.decode('utf-8', 'ignore')
                    
                    # Find all +IPD messages
                    idx = 0
                    while True:
                        ipd_pos = resp_str.find('+IPD,', idx)
                        if ipd_pos == -1:
                            break
                        
                        # Parse: +IPD,link_id,length:data
                        try:
                            comma1 = resp_str.index(',', ipd_pos)
                            comma2 = resp_str.index(',', comma1 + 1)
                            colon = resp_str.index(':', comma2)
                            
                            link_id = int(resp_str[comma1+1:comma2])
                            length = int(resp_str[comma2+1:colon])
                            data_start = colon + 1
                            data = resp_str[data_start:data_start+length]
                            
                            received.append((link_id, data))
                            idx = data_start + length
                        except:
                            break
                            
                except:
                    pass
                    
                if received:
                    return received
                    
            time.sleep_ms(10)
            
        return received
    
    def close(self, link_id):
        """Close connection"""
        resp = self._send_cmd(f"AT+CIPCLOSE={link_id}")
        if link_id in self.connections:
            del self.connections[link_id]
        return "OK" in resp
    
    def close_all(self):
        """Close all connections"""
        for link_id in list(self.connections.keys()):
            self.close(link_id)
    
    def http_get(self, url, timeout=10000):
        """
        Perform HTTP GET request
        
        Args:
            url: Full URL to fetch
            
        Returns:
            Response string or None
        """
        # Parse URL
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            return None  # HTTPS not supported directly
            
        parts = url.split('/', 1)
        host = parts[0]
        path = '/' + parts[1] if len(parts) > 1 else '/'
        
        # Enable single connection mode
        self.set_multiple_connections(False)
        time.sleep_ms(100)
        
        # Connect
        cmd = f'AT+CIPSTART="TCP","{host}",80'
        resp = self._send_cmd(cmd, timeout=10000)
        
        if "OK" not in resp and "ALREADY CONNECTED" not in resp:
            return None
            
        # Build HTTP request
        request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        length = len(request)
        
        # Send request
        cmd = f"AT+CIPSEND={length}"
        resp = self._send_cmd(cmd, timeout=1000, wait_for=">")
        
        if ">" not in resp:
            return None
            
        self.uart.write(request)
        
        # Read response
        start = time.ticks_ms()
        response = b""
        
        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            if self.uart.any():
                response += self.uart.read()
                
            # Check for connection closed
            resp_str = response.decode('utf-8', 'ignore')
            if "CLOSED" in resp_str:
                break
                
            time.sleep_ms(10)
            
        # Parse HTTP response
        resp_str = response.decode('utf-8', 'ignore')
        if '\r\n\r\n' in resp_str:
            return resp_str.split('\r\n\r\n', 1)[1]
        return resp_str
    
    def ping(self, host):
        """Ping a host"""
        resp = self._send_cmd(f'AT+PING="{host}"', timeout=5000)
        
        # Parse ping time manually
        # Look for +<number> pattern
        if '+' in resp:
            try:
                lines = resp.split('\n')
                for line in lines:
                    if line.strip().startswith('+'):
                        # Extract number after +
                        num_str = line.strip()[1:].split()[0]
                        return int(num_str)
            except:
                pass
        return None
    
    def get_connection_status(self):
        """Get status of all connections"""
        resp = self._send_cmd("AT+CIPSTATUS")
        
        statuses = []
        lines = resp.split('\n')
        
        for line in lines:
            if '+CIPSTATUS:' in line:
                try:
                    # Parse: +CIPSTATUS:link_id,"type","remote_ip",remote_port,local_port,tetype
                    start = line.index(':') + 1
                    parts = []
                    current = ""
                    in_quotes = False
                    
                    for char in line[start:]:
                        if char == '"':
                            in_quotes = not in_quotes
                        elif char == ',' and not in_quotes:
                            parts.append(current)
                            current = ""
                        else:
                            current += char
                    parts.append(current)
                    
                    if len(parts) >= 6:
                        statuses.append({
                            'link_id': int(parts[0]),
                            'type': parts[1].strip('"'),
                            'remote_ip': parts[2].strip('"'),
                            'remote_port': int(parts[3]),
                            'local_port': int(parts[4]),
                            'tetype': int(parts[5])
                        })
                except:
                    continue
            
        return statuses
    
    def set_sleep_mode(self, mode):
        """
        Set sleep mode
        
        Args:
            mode: 0=disable, 1=light sleep, 2=modem sleep
        """
        resp = self._send_cmd(f"AT+SLEEP={mode}")
        return "OK" in resp
    
    def enable_dhcp(self, mode, enable=True):
        """
        Enable/disable DHCP
        
        Args:
            mode: 0=softAP, 1=station, 2=both
            enable: True to enable, False to disable
        """
        en = 1 if enable else 0
        resp = self._send_cmd(f"AT+CWDHCP={mode},{en}")
        return "OK" in resp
