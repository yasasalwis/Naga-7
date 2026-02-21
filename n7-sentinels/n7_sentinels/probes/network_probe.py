import asyncio
import logging
import threading
from typing import AsyncIterator, Dict, Any

from ..agent_id import get_agent_id

from scapy.all import sniff, IP, TCP
from scapy.layers.http import HTTPRequest

logger = logging.getLogger("n7-sentinel.probes.network")


class NetworkProbe:
    """
    Network Probe.
    Responsibility: Monitor network traffic for suspicious patterns.
    """

    def __init__(self):
        self.probe_type = "network_monitor"
        self._running = False
        self._stop_event = threading.Event()
        self._queue = asyncio.Queue()

    async def initialize(self, config: dict) -> None:
        logger.info("Initializing NetworkProbe...")
        # Config could specify interface, filter, etc.
        self.interface = config.get("interface", None)  # None = default

    def _packet_callback(self, packet):
        if not self._running:
            return

        try:
            if IP in packet:
                src_ip = packet[IP].src
                dst_ip = packet[IP].dst
                proto = packet[IP].proto

                event_data = {
                    "event_class": "network_connection",
                    "raw_data": {
                        "source_ip": src_ip,
                        "destination_ip": dst_ip,
                        "protocol": str(proto),
                        "length": len(packet)
                    }
                }

                # Check for syn scan (TCP SYN flag)
                if TCP in packet and packet[TCP].flags == 'S':
                    event_data['raw_data']['flags'] = 'SYN'
                    event_data['event_class'] = 'port_scan_attempt'  # Simplified classification

                # Put into async queue (this runs in thread, so check safety)
                # asyncio.run_coroutine_threadsafe(self._queue.put(event_data), self._loop)
                # For simplicity in this structure, we might need a safer bridge.
                # Let's simple use a thread-safe list or just loop integration.

                # Using a naive way might block or fail. 
                # Better approach for scapy async is using AsyncSniffer coupled with queue.
                pass

        except Exception as e:
            logger.error(f"Error parsing packet: {e}")

    async def observe(self) -> AsyncIterator[Dict[str, Any]]:
        self._running = True
        logger.info("NetworkProbe started observing.")

        # Scapy sniff is blocking, so run in a separate thread
        loop = asyncio.get_event_loop()

        # Simplified: We will use a non-blocking sniff with timeout in a loop or similar.
        # But AsyncSniffer is better.
        try:
            from scapy.all import AsyncSniffer
        except ImportError:
            logger.error("AsyncSniffer not available")
            return

        def process_packet(pkt):
            if IP in pkt:
                data = {
                    "event_class": "network",
                    "raw_data": {
                        "src": pkt[IP].src,
                        "dst": pkt[IP].dst,
                        "len": len(pkt)
                    },
                    "sentinel_id": get_agent_id()
                }
                # We need to yield this. But we can't yield from callback.
                # We push to queue.
                asyncio.run_coroutine_threadsafe(self._queue.put(data), loop)

        sniffer = AsyncSniffer(prn=process_packet, store=False, filter="ip")
        sniffer.start()

        try:
            while self._running:
                # Get from queue
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    continue
        finally:
            sniffer.stop()

    async def shutdown(self) -> None:
        self._running = False
        logger.info("NetworkProbe shutdown.")
