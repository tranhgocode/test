"""
Modbus TCP Server Standalone Application
Chạy server để mô phỏng PLC/Slave với SHT20 Sensor và EZi-STEP Drive
Usage: python -m slave.server_main
"""
import sys
import time
import signal
from .modbus_tcp_server import ModbusTCPServer, ServerSimulator
from .logger_handler import logger
from .config import DEFAULT_TCP_PORT


class ServerApplication:
    """Ứng dụng Server standalone"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_TCP_PORT):
        self.host = host
        self.port = port
        self.server = None
        self.simulator = None
        self.running = False
    
    def start(self):
        """Khởi động server"""
        logger.info("=" * 60, "APP")
        logger.info("MODBUS TCP SERVER APPLICATION", "APP")
        logger.info("=" * 60, "APP")
        
        # Start server
        self.server = ModbusTCPServer(self.host, self.port)
        
        if not self.server.start():
            logger.error("Failed to start server", "APP")
            return False
        
        # Start simulator (optional)
        self.simulator = ServerSimulator(self.server)
        self.simulator.start()
        
        self.running = True
        logger.info(f"Server running on {self.host}:{self.port}", "APP")
        logger.info("Press Ctrl+C to stop", "APP")
        
        return True
    
    def stop(self):
        """Dừng server"""
        logger.info("Stopping server...", "APP")
        
        if self.simulator:
            self.simulator.stop()
        
        if self.server:
            self.server.stop()
        
        self.running = False
        logger.info("Server stopped", "APP")
    
    def run(self):
        """Main loop"""
        if not self.start():
            return
        
        try:
            while self.running:
                time.sleep(1)
                
                # Display stats every 10 seconds
                if int(time.time()) % 10 == 0:
                    stats = self.server.get_stats()
                    logger.info(
                        f"Stats: Requests={stats['request_count']}, "
                        f"Responses={stats['response_count']}, "
                        f"Errors={stats['error_count']}",
                        "APP"
                    )
        
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received", "APP")
        
        finally:
            self.stop()


def signal_handler(sig, frame):
    """Handle Ctrl+C"""
    print("\nShutting down...")
    sys.exit(0)


def main():
    """Entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Modbus TCP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_TCP_PORT, help=f"Port (default: {DEFAULT_TCP_PORT})")
    parser.add_argument("--no-sim", action="store_true", help="Disable data simulator")
    
    args = parser.parse_args()
    
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start application
    app = ServerApplication(args.host, args.port)
    
    if args.no_sim and app.server:
        app.simulator = None
    
    app.run()


if __name__ == "__main__":
    main()