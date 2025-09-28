# espicoW.py
# Combined WiFi library for Chinese Pico W boards with ESP8285
# Combines functionality from WiFi2.py and EspAtDrv2.py into a single module
# Version: 1.0.0

from machine import UART
from micropython import const
import utime

# Connection status constants
WL_NO_SHIELD = const(255)
WL_NO_MODULE = WL_NO_SHIELD
WL_IDLE_STATUS = const(0)
WL_CONNECTED = const(1)
WL_CONNECT_FAILED = const(2)
WL_CONNECTION_LOST = const(3)
WL_DISCONNECTED = const(4)
WL_AP_LISTENING = const(5)
WL_AP_CONNECTED = const(6)
WL_AP_FAILED = const(7)

# AT Driver constants
LINKS_COUNT = const(5)
NO_LINK = const(255)

# Error codes
Error_NO_ERROR = const(0)
Error_NOT_INITIALIZED = const(1)
Error_AT_NOT_RESPONDING = const(2)
Error_AT_ERROR = const(3)
Error_NO_AP = const(4)
Error_LINK_ALREADY_CONNECTED = const(5)
Error_LINK_NOT_ACTIVE = const(6)
Error_RECEIVE = const(7)
Error_SEND = const(8)

# WiFi modes
WIFI_SOFT_RESET = const(0)
WIFI_EXTERNAL_RESET = const(2)
WIFI_MODE_STA = const(1)
WIFI_MODE_SAP = const(2)

# Communication parameters
TIMEOUT = const(2000)
TIMEOUT_COUNT = const(10)

# Link flags
LINK_CONNECTED = const(1)
LINK_CLOSING = const(2)
LINK_IS_INCOMING = const(4)

# Logging configuration
LOG_ERROR = const(True)
LOG_INFO = const(True)
LOG_DEBUG = const(False)

class LinkInfo:
    """Information about a network link"""
    def __init__(self):
        self.flags = 0
        self.avail = 0

class Client:
    """WiFi client for TCP/SSL connections"""
    
    def __init__(self):
        self.linkId = NO_LINK
        self.port = 0
        self.assigned = False
        self.rxBuffer = b''
        self.txBuffer = b''

    def connect(self, host: str, port: int) -> bool:
        """Connect using TCP"""
        return self._connect_internal("TCP", host, port)

    def connectSSL(self, host: str, port: int) -> bool:
        """Connect using SSL/TLS"""
        return self._connect_internal("SSL", host, port)

    def _connect_internal(self, protocol: str, host: str, port: int) -> bool:
        """Internal connection method"""
        log_info(f"Attempting {protocol} connection to {host}:{port}")
        
        linkId = _at_connect(protocol, host, port)
        if linkId == NO_LINK:
            log_error(f"Failed to establish {protocol} connection")
            return False

        self.linkId = linkId
        self.port = port
        self.assigned = True
        _client_pool[linkId] = self

        log_info(f'Connected {host}:{port} on linkId {linkId}')
        return True

    def connected(self) -> bool:
        """Check if connection is active"""
        if self.linkId == NO_LINK:
            return False
        if _at_connected(self.linkId) or self.available():
            return True
        
        self._free()
        return False

    def available(self) -> int:
        """Get number of bytes available to read"""
        avail = len(self.rxBuffer)
        if self.linkId == NO_LINK:
            return avail

        if avail == 0:
            avail = _at_available_data(self.linkId)

        if avail == 0:
            self.flush()

        return avail

    def read(self) -> int:
        """Read single byte"""
        if self.linkId == NO_LINK or self.available() == 0:
            return -1

        data = self.readBuf(1)
        return data[0] if len(data) > 0 else -1

    def readBuf(self, size: int) -> bytes:
        """Read buffer of specified size"""
        if size == 0 or self.available() == 0:
            return b''

        if len(self.rxBuffer) == 0:
            self.rxBuffer = _at_recv_data(self.linkId)

        data = self.rxBuffer[:size]
        self.rxBuffer = self.rxBuffer[size:]

        if len(data) < size and self.available() > 0:
            data += self.readBuf(size - len(data))
            
        return data

    def print(self, data: str) -> int:
        """Add data to transmit buffer"""
        if self.linkId == NO_LINK or len(data) == 0:
            return 0

        self.txBuffer += data.encode()
        return len(self.txBuffer)

    def flush(self):
        """Send buffered data"""
        if self.linkId != NO_LINK and self.txBuffer:
            _at_send_data(self.linkId, self.txBuffer)
        self.txBuffer = b''

    def stop(self):
        """Close connection gracefully"""
        self.flush()
        self.abort()

    def abort(self):
        """Abort connection"""
        if self.linkId != NO_LINK:
            _at_close(self.linkId, True)
        self._free()

    def peek(self) -> int:
        """Peek at first byte without consuming"""
        if self.linkId == NO_LINK or self.available() == 0:
            return -1

        if len(self.rxBuffer) == 0:
            self.rxBuffer = _at_recv_data(self.linkId)

        return self.rxBuffer[0] if len(self.rxBuffer) > 0 else -1

    def _free(self):
        """Free client resources"""
        self.linkId = NO_LINK
        self.assigned = False
        self.port = 0
        self.rxBuffer = b''
        self.txBuffer = b''

# Global variables
_esp_uart = None
_link_info = []
_client_pool = []
_last_error_code = Error_NO_ERROR
_buffer = bytearray()
_wifi_mode = 0
_wifi_mode_def = 0
_persistent = False
_last_sync = 0
_state = WL_NO_MODULE

def init(reset_type: int = WIFI_SOFT_RESET) -> bool:
    """Initialize WiFi system"""
    global _esp_uart, _last_error_code, _link_info, _client_pool, _state
    
    log_info("Initializing ESP8285 WiFi system...")
    
    # Configure UART
    _esp_uart = UART(0, 115200, timeout=2000, timeout_char=200)
    _last_error_code = Error_NO_ERROR
    
    # Initialize link tracking
    _link_info = [LinkInfo() for _ in range(LINKS_COUNT)]
    _client_pool = [Client() for _ in range(LINKS_COUNT)]
    
    # Clear UART buffer
    while _esp_uart.any():
        _esp_uart.read(1)
        
    success = _reset(reset_type)
    _state = WL_IDLE_STATUS if success else WL_NO_MODULE
    
    log_info(f"WiFi initialization: {'SUCCESS' if success else 'FAILED'}")
    return success

def begin(ssid: str, password: str, bssid: bytearray = None) -> int:
    """Connect to WiFi network"""
    global _state
    
    log_info(f"Connecting to WiFi: {ssid}")
    
    # Force station mode
    if not _force_station_mode():
        log_error("Failed to set station mode")
        _state = WL_CONNECT_FAILED
        return _state
    
    # Small delay for mode switching
    utime.sleep_ms(1000)
    
    # Attempt connection
    success = _at_join_ap(ssid, password, bssid)
    _state = WL_CONNECTED if success else WL_CONNECT_FAILED
    
    if success:
        log_info(f"Successfully connected to {ssid}")
    else:
        log_error(f"Failed to connect to {ssid}")
        
    return _state

def disconnect(persistent: bool = False) -> int:
    """Disconnect from WiFi"""
    global _state
    
    log_info("Disconnecting from WiFi...")
    if _at_quit_ap(persistent):
        _state = WL_DISCONNECTED
        log_info("Disconnected successfully")
    else:
        log_error("Disconnect failed")
    return _state

def status() -> int:
    """Get current WiFi status"""
    global _state
    
    if _state == WL_NO_MODULE:
        return _state
    
    sta_status = _at_sta_status()
    if sta_status == -1:
        if get_last_error() in (Error_NOT_INITIALIZED, Error_AT_NOT_RESPONDING):
            _state = WL_NO_MODULE
    elif sta_status in (2, 3, 4):
        _state = WL_CONNECTED
    elif sta_status in (0, 1, 5):
        if _state == WL_CONNECT_FAILED:
            pass  # No change
        elif _state == WL_CONNECTED:
            _state = WL_CONNECTION_LOST
        else:
            _state = WL_DISCONNECTED
            
    return _state

def local_ip() -> str:
    """Get local IP address"""
    ip_info = _at_sta_ip_query()
    return ip_info[0] if ip_info and len(ip_info) > 0 else None

def gateway_ip() -> str:
    """Get gateway IP address"""
    ip_info = _at_sta_ip_query()
    return ip_info[1] if ip_info and len(ip_info) > 1 else None

def subnet_mask() -> str:
    """Get subnet mask"""
    ip_info = _at_sta_ip_query()
    return ip_info[2] if ip_info and len(ip_info) > 2 else None

def rssi() -> int:
    """Get signal strength"""
    ap_info = _at_ap_query()
    if ap_info and len(ap_info) > 3:
        try:
            return int(ap_info[3].strip())
        except:
            pass
    return None

def channel() -> int:
    """Get WiFi channel"""
    ap_info = _at_ap_query()
    if ap_info and len(ap_info) > 2:
        try:
            return int(ap_info[2].strip())
        except:
            pass
    return None

def dns_ip(n: int = None):
    """Get DNS server addresses"""
    dns_info = _at_dns_query()
    if not dns_info:
        return None
    if n is None:
        return dns_info
    if 1 <= n <= len(dns_info):
        return dns_info[n-1]
    return None

def get_last_error() -> int:
    """Get last error code"""
    return _last_error_code

def scan_networks() -> list:
    """Scan for available networks"""
    return _at_scan_networks()

# AT command driver functions
def _reset(reset_type: int) -> bool:
    """Reset ESP8285"""
    global _wifi_mode, _wifi_mode_def, _buffer
    
    log_info(f"Performing reset (type {reset_type})")
    
    if reset_type != WIFI_EXTERNAL_RESET:
        _maintain()
        
    if reset_type == WIFI_SOFT_RESET:
        log_info("Soft reset...")
        _send_string("AT+RST")
        _send_command("ready", True, False)
        utime.sleep(2)
    
    log_info("Configuring ESP8285...")
    
    # Test communication
    if not _test_at_communication():
        return False
    
    # Configure ESP
    if not _simple_command("ATE0"):
        log_error("Failed to disable echo")
        return False
        
    if not _simple_command("AT+CIPMUX=1"):
        log_error("Failed to enable multiple connections")
        return False
        
    if not _simple_command("AT+CIPRECVMODE=1"):
        log_error("Failed to set TCP receive mode")
        return False

    # Read WiFi mode
    log_info("Reading WiFi mode...")
    _send_string("AT+CWMODE?")
    if not _send_command("+CWMODE", True, False):
        log_error("Failed to read WiFi mode")
        return False

    try:
        _wifi_mode = _buffer[8] - ord('0')
        if not _read_ok():
            return False
        _wifi_mode_def = _wifi_mode
        log_info(f"Current WiFi mode: {_wifi_mode}")
    except:
        log_error("Error parsing WiFi mode")
        return False
        
    log_info("ESP8285 initialization complete")
    return True

def _test_at_communication() -> bool:
    """Test basic AT communication"""
    log_info("Testing AT communication...")
    
    for i in range(5):
        if _simple_command("AT"):
            log_info("AT communication OK")
            return True
        log_info(f"AT test attempt {i+1} failed")
        utime.sleep_ms(500)
    
    log_error("AT communication failed")
    return False

def _force_station_mode() -> bool:
    """Force ESP into station mode"""
    global _wifi_mode
    
    log_info("Forcing ESP into station mode...")
    
    # Disable AP configurations
    _simple_command("AT+CWSAP_DEF=\"\",\"\",1,0")
    _simple_command("AT+CWSAP_CUR=\"\",\"\",1,0")
    
    # Set station mode
    if _simple_command("AT+CWMODE_CUR=1"):
        _wifi_mode = 1
        log_info("Successfully set to station mode")
        return True
    else:
        log_error("Failed to set station mode")
        return False

def _maintain():
    """Maintain connection and clear errors"""
    global _last_error_code
    _last_error_code = Error_NO_ERROR
    return _read_rx(None, False, False)

def _send_string(cmd: str) -> bool:
    """Send AT command string"""
    try:
        n = _esp_uart.write(cmd)
        log_debug(f"TX: {cmd}")
        return n == len(cmd)
    except:
        return False

def _send_command(expected: str, buffer_data: bool, list_item: bool) -> bool:
    """Send complete AT command with newline"""
    global _last_error_code
    
    log_debug("Sending command...")
    
    if not _send_string("\r\n"):
        _last_error_code = Error_AT_NOT_RESPONDING
        return False

    if expected:
        return _read_rx(expected, buffer_data, list_item)
    else:
        return _read_ok()

def _simple_command(cmd: str) -> bool:
    """Send simple AT command and wait for OK"""
    _maintain()
    if not _send_string(cmd):
        return False

    log_debug("Sending simple command...")
    if not _send_string("\r\n"):
        return False

    return _read_ok()

def _read_rx(expected: str, buffer_data: bool, list_item: bool) -> bool:
    """Read AT response"""
    global _buffer, _last_error_code, _link_info
    
    timeout = 0
    unlink_bug = False
    ignored_count = 0

    while True:
        avail = _esp_uart.any()
        if not expected and avail == 0:
            return True

        _buffer = bytearray()
        b = _esp_uart.read(1)
        
        if b is None:
            if timeout == TIMEOUT_COUNT:
                log_error("AT firmware not responding")
                _last_error_code = Error_AT_NOT_RESPONDING
                return False

            # Try to wake ESP
            _send_string("AT")
            _send_string("\r\n")
            timeout += 1
            utime.sleep_ms(100)
            continue

        _buffer.extend(b)

        if _buffer[0] == ord('>'):
            # CIPSEND prompt
            _esp_uart.read(1)  # Clear space
            timeout = 0
        else:
            b = _esp_uart.read(1)
            if b is None:
                continue
            timeout = 0
            _buffer.extend(b)

            if _buffer.startswith(b'\r\n'):
                continue
            terminator = b'\n'
            
            if _buffer[0] == ord('+'):
                if _buffer[1] == ord('C') and not buffer_data:
                    terminator = b':'
                elif _buffer[1] == ord('I'):
                    _buffer.extend(_esp_uart.read(4))
                    
            while True:
                b = _esp_uart.read(1)
                if b is None or b == terminator:
                    break
                _buffer.extend(b)
                
            while _buffer and _buffer[-1] == 13:
                _buffer = _buffer[:-1]

        log_debug(f"RX: {_buffer}")

        if expected and _buffer.startswith(expected.encode()):
            log_debug("Response matched")
            return True
        
        # Handle various AT responses
        if _handle_at_response():
            continue
        elif _buffer.startswith(b"ERROR") or _buffer == b'FAIL':
            if unlink_bug:
                log_debug("UNLINK handled as OK")
                return True
            if expected is None or expected == "":
                log_debug("Ignored late ERROR")
            else:
                log_error(f'Expected {expected} got {_buffer.decode()}')
                _last_error_code = Error_AT_ERROR
                return False
        elif _buffer == b'No AP':
            log_error(f'Expected {expected} got {_buffer.decode()}')
            _last_error_code = Error_NO_AP
            return False
        elif _buffer == b'UNLINK':
            unlink_bug = True
            log_debug("UNLINK processed")
        elif list_item and _buffer == b'OK':
            log_debug("End of list")
            return False
        else:
            ignored_count += 1
            if ignored_count > 100:
                log_error("Too much garbage on RX")
                _last_error_code = Error_AT_NOT_RESPONDING
                return False
            log_debug("Response ignored")
            
    return False

def _handle_at_response() -> bool:
    """Handle specific AT responses"""
    global _buffer, _link_info
    
    if _buffer.startswith(b"+IPD,"):
        try:
            link_id = _buffer[5] - ord('0')
            comma_pos = _buffer.find(b',', 7)
            if comma_pos > 0:
                rec_len = int(_buffer[7:comma_pos])
            else:
                rec_len = int(_buffer[7:])

            if 0 <= link_id < LINKS_COUNT and rec_len > 0:
                _link_info[link_id].avail = rec_len
                log_debug("Processed IPD")
                return True
        except:
            pass
    elif len(_buffer) > 1 and _buffer[1:].startswith(b",CONNECT"):
        try:
            link_id = _buffer[0] - ord('0')
            if 0 <= link_id < LINKS_COUNT:
                link = _link_info[link_id]
                if (link.avail == 0 and
                    (not (link.flags & LINK_CONNECTED) or (link.flags & LINK_CLOSING))):
                    link.flags = LINK_CONNECTED | LINK_IS_INCOMING
                    log_debug("Processed CONNECT")
                    return True
        except:
            pass
    elif len(_buffer) > 1 and (_buffer[1:].startswith(b",CLOSED") or
                               _buffer[1:].startswith(b",CONNECT FAIL")):
        try:
            link_id = _buffer[0] - ord('0')
            if 0 <= link_id < LINKS_COUNT:
                _link_info[link_id].flags = 0
                log_debug(f"Processed CLOSED for link {link_id}")
                return True
        except:
            pass
    
    return False

def _read_ok() -> bool:
    """Read OK response"""
    return _read_rx("OK", True, False)

# AT command implementations
def _at_sta_status() -> int:
    """Get station status"""
    global _wifi_mode_def, _last_error_code, _buffer
    
    _maintain()
    log_debug("Getting WiFi status...")

    if _wifi_mode_def == 0:
        log_error("AT firmware not initialized")
        _last_error_code = Error_NOT_INITIALIZED
        return -1

    if not _send_string("AT+CIPSTATUS"):
        _last_error_code = Error_AT_NOT_RESPONDING
        return -1

    if not _send_command("STATUS", True, False):
        return -1

    try:
        status = _buffer[7] - ord('0')
        return status if _read_ok() else -1
    except:
        return -1

def _at_join_ap(ssid: str, password: str, bssid: bytearray) -> bool:
    """Join access point"""
    global _wifi_mode, _persistent
    
    _maintain()
    log_info(f'Joining AP {ssid}')

    # Build command
    cmd = f'AT+CWJAP_CUR="{ssid}"'
    if password and len(password) > 0:
        cmd += f',"{password}"'
    if bssid:
        hx = ':'.join(['%02X' % b for b in bssid])
        cmd += f',"{hx}"'

    log_info(f"Sending: {cmd}")
    _send_string(cmd)
    
    # Extended timeout for connection
    original_timeout = globals().get('TIMEOUT', 2000)
    globals()['TIMEOUT'] = 10000
    
    try:
        result = _send_command("OK", True, False)
        if result:
            log_info("Join succeeded")
            utime.sleep_ms(2000)  # Allow connection to establish
        else:
            log_error("Join failed")
    finally:
        globals()['TIMEOUT'] = original_timeout

    return result

def _at_quit_ap(save: bool) -> bool:
    """Quit access point"""
    log_info("Quitting AP")

    # Clear configurations
    if not _simple_command("AT+CIPDNS_CUR=0"):
        return False
    if not _simple_command("AT+CWDHCP_CUR=1,1"):
        return False

    return _simple_command("AT+CWQAP")

def _at_connect(protocol: str, host: str, port: int) -> int:
    """Connect to remote host"""
    _maintain()

    link_id = _free_link_id()
    if link_id == NO_LINK:
        return NO_LINK

    log_info(f'Starting {protocol} to {host}:{port} on link {link_id}')

    link = _link_info[link_id]
    if link.flags & LINK_CONNECTED:
        log_error(f'Link {link_id} already connected')
        _last_error_code = Error_LINK_ALREADY_CONNECTED
        return NO_LINK

    cmd = f'AT+CIPSTART={link_id},"{protocol}","{host}",{port}'
    if not _send_string(cmd):
        link.flags = 0
        return NO_LINK

    if not _send_command("OK", True, False):
        link.flags = 0
        return NO_LINK

    link.flags = LINK_CONNECTED
    return link_id

def _free_link_id() -> int:
    """Find free link ID"""
    _maintain()
    
    for link_id in range(LINKS_COUNT-1, -1, -1):
        link = _link_info[link_id]
        if not (link.flags & (LINK_CONNECTED | LINK_CLOSING)) and link.avail == 0:
            log_debug(f'Free link ID: {link_id}')
            return link_id
    
    return NO_LINK

def _at_connected(link_id: int) -> bool:
    """Check if link is connected"""
    _maintain()
    link = _link_info[link_id]
    return (link.flags & LINK_CONNECTED) and not (link.flags & LINK_CLOSING)

def _at_available_data(link_id: int) -> int:
    """Get available data for link"""
    _maintain()
    return _link_info[link_id].avail

def _at_recv_data(link_id: int, buff_size: int = 1000) -> bytes:
    """Receive data from link"""
    global _last_error_code, _buffer
    
    _maintain()
    log_debug(f'Receiving data on link {link_id}')

    if _link_info[link_id].avail == 0:
        if not (_link_info[link_id].flags & LINK_CONNECTED):
            log_error("Link not active")
            _last_error_code = Error_LINK_NOT_ACTIVE
        return b''

    _send_string(f'AT+CIPRECVDATA={link_id},{buff_size}')

    if not _send_command("+CIPRECVDATA", False, False):
        log_error(f'Error receiving on link {link_id}')
        _link_info[link_id].avail = 0
        _last_error_code = Error_RECEIVE
        return b''

    try:
        exp_len = int(_buffer[13:])
        data = _esp_uart.read(exp_len)

        if len(data) != exp_len:
            log_error(f'Receive timeout on link {link_id}')
            _link_info[link_id].avail = 0
            _last_error_code = Error_RECEIVE
            return b''

        if exp_len > _link_info[link_id].avail:
            _link_info[link_id].avail = 0
        else:
            _link_info[link_id].avail -= exp_len

        _read_ok()
        log_debug(f'Received {exp_len} bytes on link {link_id}')
        return data
        
    except Exception as e:
        log_error(f'Error parsing receive data: {e}')
        _link_info[link_id].avail = 0
        _last_error_code = Error_RECEIVE
        return b''

def _at_send_data(link_id: int, data: bytes) -> int:
    """Send data on link"""
    global _last_error_code, _buffer
    
    _maintain()
    log_debug(f'Sending {len(data)} bytes on link {link_id}')

    if len(data) == 0:
        return 0
    
    if not (_link_info[link_id].flags & LINK_CONNECTED):
        log_error("Link not connected")
        _last_error_code = Error_LINK_NOT_ACTIVE
        return 0

    _send_string(f'AT+CIPSEND={link_id},{len(data)}')

    if not _send_command(">", True, False):
        return 0

    if _esp_uart.write(data) != len(data):
        return 0

    if not _read_rx("Recv ", True, False):
        return 0

    try:
        space_pos = _buffer.find(b' ', 5)
        if space_pos > 0:
            recv_len = int(_buffer[5:space_pos])
            
            if _read_rx("SEND ", True, False) and _buffer[5:7] == b'OK':
                log_debug(f'Sent {recv_len} bytes on link {link_id}')
                return recv_len

        log_error("Failed to send data")
        _last_error_code = Error_SEND
        return 0
        
    except Exception as e:
        log_error(f'Error parsing send response: {e}')
        _last_error_code = Error_SEND
        return 0

def _at_close(link_id: int, abort: bool) -> bool:
    """Close link"""
    _maintain()
    log_info(f'Closing link {link_id}')

    link = _link_info[link_id]
    link.avail = 0

    if not (link.flags & LINK_CONNECTED):
        log_info("Link already closed")
        return True

    link.flags |= LINK_CLOSING

    if abort:
        _send_string(f'AT+CIPCLOSEMODE={link_id},1')
        _send_command("OK", True, False)

    _send_string(f'AT+CIPCLOSE={link_id}')
    return _send_command("OK", True, False)

def _at_sta_ip_query() -> list:
    """Query station IP information"""
    global _buffer
    
    _maintain()
    result = []

    _send_string("AT+CIPSTA?")
    if not _send_command("+CIPSTA", True, False):
        log_error("Failed to get IP info")
        return None
        
    try:
        # Parse IP address
        ip_line = _buffer.decode()
        log_debug(f"IP line: {ip_line}")
        
        if '+CIPSTA:ip:' in ip_line:
            ip_start = ip_line.find('"') + 1
            ip_end = ip_line.find('"', ip_start)
            if ip_start > 0 and ip_end > ip_start:
                result.append(ip_line[ip_start:ip_end])
        
        # Read gateway
        if _read_rx("+CIPSTA", True, False):
            gw_line = _buffer.decode()
            if '+CIPSTA:gateway:' in gw_line:
                gw_start = gw_line.find('"') + 1
                gw_end = gw_line.find('"', gw_start)
                if gw_start > 0 and gw_end > gw_start:
                    result.append(gw_line[gw_start:gw_end])
            
            # Read netmask
            if _read_rx("+CIPSTA", True, False):
                nm_line = _buffer.decode()
                if '+CIPSTA:netmask:' in nm_line:
                    nm_start = nm_line.find('"') + 1
                    nm_end = nm_line.find('"', nm_start)
                    if nm_start > 0 and nm_end > nm_start:
                        result.append(nm_line[nm_start:nm_end])
        
        _read_ok()
        log_info(f"IP info retrieved: {result}")
        return result
        
    except Exception as e:
        log_error(f"Error parsing IP info: {e}")
        _read_ok()
        return None

def _at_ap_query() -> list:
    """Query connected access point information"""
    global _wifi_mode, _buffer
    
    _maintain()
    if _wifi_mode != WIFI_MODE_STA and _wifi_mode != (WIFI_MODE_STA | WIFI_MODE_SAP):
        log_error("STA mode not active")
        return None

    _send_string("AT+CWJAP?")
    if _send_command("+CWJAP", True, False):
        try:
            line = _buffer.decode()
            log_debug(f"AP query response: {line}")
            
            if '+CWJAP:' in line:
                # Parse: +CWJAP:"SSID","BSSID",channel,rssi
                parts = []
                in_quote = False
                current = ""
                
                for char in line[7:]:  # Skip '+CWJAP:'
                    if char == '"':
                        if in_quote:
                            parts.append(current)
                            current = ""
                        in_quote = not in_quote
                    elif char == ',' and not in_quote:
                        if current:
                            parts.append(current)
                            current = ""
                    else:
                        current += char
                
                if current:
                    parts.append(current)
                
                log_info(f"AP info: {parts}")
                return parts
            return None
        except Exception as e:
            log_error(f"Error parsing AP query: {e}")
            return None
    return None

def _at_dns_query() -> list:
    """Query DNS server information"""
    global _buffer
    
    _maintain()
    result = []

    _send_string("AT+CIPDNS_CUR?")
    if not _send_command("+CIPDNS_CUR", True, False):
        return None
        
    try:
        parts = _buffer.decode().split(':')
        if len(parts) >= 2:
            result.append(parts[1].strip())
            
        if _read_rx("+CIPDNS_CUR", True, False):
            parts = _buffer.decode().split(':')
            if len(parts) >= 2:
                result.append(parts[1].strip())
        
        _read_ok()
        return result
    except Exception as e:
        log_error(f"Error parsing DNS info: {e}")
        return None

def _at_scan_networks() -> list:
    """Scan for available networks"""
    _maintain()
    
    # Make sure we're in station mode
    if _wifi_mode != WIFI_MODE_STA:
        if not _force_station_mode():
            log_error("Cannot scan - not in station mode")
            return []
    
    log_info("Scanning for networks...")
    _send_string("AT+CWLAP")
    networks = []
    
    while _read_rx("+CWLAP", True, True):
        try:
            net_info = _buffer.decode()
            networks.append(net_info)
            log_info(f"Found network: {net_info}")
        except:
            break
    
    _read_ok()
    log_info(f"Scan complete. Found {len(networks)} networks")
    return networks

# Logging functions
def log_info(msg: str = None, prefix: bool = True):
    """Log info message"""
    if LOG_INFO:
        if msg is None or prefix:
            print("[espicoW-i] ", end="")
        if msg is not None:
            print(msg, end="" if not prefix else "\n")

def log_error(msg: str = None, prefix: bool = True):
    """Log error message"""
    if LOG_ERROR:
        if msg is None or prefix:
            print("[espicoW-e] ", end="")
        if msg is not None:
            print(msg, end="" if not prefix else "\n")

def log_debug(msg: str = None, prefix: bool = True):
    """Log debug message"""
    if LOG_DEBUG:
        if msg is None or prefix:
            print("[espicoW-d] ", end="")
        if msg is not None:
            print(msg, end="" if not prefix else "\n")

# TCP Server functionality (for web interface)
class SimpleServer:
    """Simple TCP server for web interface"""
    
    def __init__(self, port: int = 80):
        self.port = port
        self.clients = []
        self.server_client = None
        
    def start(self):
        """Start server (simplified implementation)"""
        log_info(f"Starting server on port {self.port}")
        # In a full implementation, this would create a listening socket
        # For now, we'll use a simplified approach
        return True
        
    def accept(self):
        """Accept incoming connection (returns None if no connection)"""
        # This would normally check for incoming connections
        # For this implementation, we'll return None (no connection)
        return None
        
    def stop(self):
        """Stop server"""
        log_info("Stopping server")
        # Close any active connections
        for client in self.clients:
            try:
                client.stop()
            except:
                pass
        self.clients.clear()

# Utility functions for backward compatibility
def Client():
    """Create a new WiFi client"""
    return Client()

def setPersistent(persistent: bool) -> bool:
    """Set connection persistence"""
    global _persistent
    _persistent = persistent
    return True

# Module initialization check
def is_initialized() -> bool:
    """Check if WiFi system is initialized"""
    return _esp_uart is not None

# Network utilities
def ping(host: str, timeout: int = 5000) -> bool:
    """Ping a host (simplified implementation)"""
    log_info(f"Pinging {host}...")
    # Create temporary client to test connectivity
    client = Client()
    try:
        # Try to connect to port 80 (HTTP) as connectivity test
        if client.connect(host, 80):
            client.stop()
            log_info(f"Ping to {host}: SUCCESS")
            return True
        else:
            log_info(f"Ping to {host}: FAILED")
            return False
    except:
        log_info(f"Ping to {host}: ERROR")
        return False
    finally:
        client.stop()

def get_mac_address() -> str:
    """Get MAC address (placeholder)"""
    # This would require additional AT commands to implement
    log_info("MAC address query not implemented")
    return "00:00:00:00:00:00"

# Configuration functions
def set_hostname(hostname: str) -> bool:
    """Set device hostname"""
    log_info(f"Setting hostname to: {hostname}")
    return _simple_command(f'AT+CWHOSTNAME="{hostname}"')

def get_hostname() -> str:
    """Get device hostname"""
    _send_string("AT+CWHOSTNAME?")
    if _send_command("+CWHOSTNAME", True, False):
        try:
            line = _buffer.decode()
            if '+CWHOSTNAME:' in line:
                start = line.find('"') + 1
                end = line.find('"', start)
                if start > 0 and end > start:
                    return line[start:end]
        except:
            pass
    return "Unknown"

# Power management
def set_sleep_mode(mode: int) -> bool:
    """Set WiFi sleep mode (0=none, 1=light, 2=modem)"""
    log_info(f"Setting sleep mode: {mode}")
    return _simple_command(f"AT+CWSLEEP={mode}")

def get_sleep_mode() -> int:
    """Get current sleep mode"""
    _send_string("AT+CWSLEEP?")
    if _send_command("+CWSLEEP", True, False):
        try:
            mode = _buffer[9] - ord('0')  # '+CWSLEEP:'
            return mode
        except:
            pass
    return -1

# Advanced configuration
def set_country(country_code: str) -> bool:
    """Set WiFi country code"""
    log_info(f"Setting country code: {country_code}")
    return _simple_command(f'AT+CWCOUNTRY_CUR="{country_code}",1,13')

# Error handling utilities
def get_error_string(error_code: int) -> str:
    """Get human-readable error string"""
    error_strings = {
        Error_NO_ERROR: "No error",
        Error_NOT_INITIALIZED: "WiFi not initialized",
        Error_AT_NOT_RESPONDING: "ESP8285 not responding",
        Error_AT_ERROR: "AT command error",
        Error_NO_AP: "Access point not found",
        Error_LINK_ALREADY_CONNECTED: "Link already connected",
        Error_LINK_NOT_ACTIVE: "Link not active",
        Error_RECEIVE: "Receive error",
        Error_SEND: "Send error"
    }
    return error_strings.get(error_code, f"Unknown error ({error_code})")

# Module metadata
__version__ = "1.0.0"
__author__ = "Combined WiFi2 and EspAtDrv2 libraries"
__description__ = "WiFi library for Chinese Pico W boards with ESP8285"