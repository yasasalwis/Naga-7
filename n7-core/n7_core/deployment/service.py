import asyncio
import base64
import hashlib
import ipaddress
import logging
from datetime import datetime
from uuid import UUID

import asyncssh
from icmplib import async_ping
from sqlalchemy import select

from ..config_sync.service import ConfigSyncService
from ..database.session import async_session_maker
from ..models.infra_node import InfraNode
from ..service_manager.base_service import BaseService
from ..config import settings

logger = logging.getLogger("n7-core.deployment")


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte URL-safe base64 Fernet key from the application secret."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _arp_lookup(ip: str) -> str | None:
    """
    Look up the MAC address for a given IP from the OS ARP cache.
    Works only for hosts on the same local subnet (populated after a ping).
    Returns None if not found or the platform is unsupported.
    """
    import subprocess
    import re
    import platform
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(["arp", "-a", ip], text=True, timeout=3)
            # Windows arp output: "  192.168.1.1   aa-bb-cc-dd-ee-ff  dynamic"
            match = re.search(r"([\da-fA-F]{2}[-:]){5}[\da-fA-F]{2}", out)
        else:
            out = subprocess.check_output(["arp", "-n", ip], text=True, timeout=3)
            # Linux/macOS output: "? (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] ..."
            match = re.search(r"([\da-fA-F]{2}:){5}[\da-fA-F]{2}", out)
        return match.group(0).upper() if match else None
    except Exception:
        return None


class DeploymentService(BaseService):
    """
    Deployment Service.
    Responsibility: Discover infrastructure nodes and remotely deploy Sentinel/Striker agents.
    Supports SSH (Linux/macOS) and WinRM (Windows) deployment methods.
    """

    def __init__(self):
        super().__init__("DeploymentService")
        from cryptography.fernet import Fernet
        self._fernet = Fernet(_derive_fernet_key(settings.SECRET_KEY))
        self._config_sync = ConfigSyncService()

    async def start(self):
        logger.info("DeploymentService started.")

    async def stop(self):
        logger.info("DeploymentService stopped.")

    # ------------------------------------------------------------------ #
    #  Credential encryption helpers                                       #
    # ------------------------------------------------------------------ #

    def encrypt_credential(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt_credential(self, enc: str) -> str:
        return self._fernet.decrypt(enc.encode()).decode()

    # ------------------------------------------------------------------ #
    #  Network Discovery                                                   #
    # ------------------------------------------------------------------ #

    async def scan_network_ping(self, cidr: str, timeout: int = 30) -> list[dict]:
        """
        ICMP ping sweep using icmplib. Returns list of reachable hosts.
        MAC addresses are resolved via ARP table (available for local-subnet hosts only).
        """
        hosts = [str(ip) for ip in ipaddress.IPv4Network(cidr, strict=False).hosts()]
        # Batch to avoid opening too many sockets at once
        batch_size = 50
        reachable = []
        for i in range(0, len(hosts), batch_size):
            batch = hosts[i:i + batch_size]
            tasks = [async_ping(ip, count=1, timeout=1, privileged=False) for ip in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for ip, result in zip(batch, results):
                if isinstance(result, Exception):
                    continue
                if result.is_alive:
                    reachable.append({
                        "ip_address": ip,
                        "hostname": None,
                        "mac_address": _arp_lookup(ip),
                    })
        return reachable

    async def scan_network_nmap(self, cidr: str, timeout: int = 30) -> list[dict]:
        """
        nmap host discovery scan (-sn). Runs in thread pool.
        Uses -sn (ping scan) which includes ARP requests on local subnets,
        so MAC addresses are available in the scan results.
        """
        def _run_nmap():
            import nmap
            nm = nmap.PortScanner()
            nm.scan(hosts=cidr, arguments=f"-sn --host-timeout {timeout}s")
            found = []
            for host in nm.all_hosts():
                if nm[host].state() == "up":
                    hostname = nm[host].hostname() or None
                    # nmap stores MAC under nm[host]['addresses']['mac']
                    mac = nm[host].get("addresses", {}).get("mac") or None
                    found.append({
                        "ip_address": host,
                        "hostname": hostname,
                        "mac_address": mac,
                    })
            return found

        return await asyncio.to_thread(_run_nmap)

    async def persist_discovered_nodes(self, hosts: list[dict], method: str) -> list[InfraNode]:
        """
        Upsert discovered hosts into infra_nodes.
        Updates last_seen for existing entries; inserts new ones.
        """
        nodes = []
        async with async_session_maker() as session:
            for host in hosts:
                result = await session.execute(
                    select(InfraNode).where(InfraNode.ip_address == host["ip_address"])
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.last_seen = datetime.utcnow()
                    existing.status = "reachable"
                    # Update MAC if we now have one and didn't before
                    if host.get("mac_address") and not existing.mac_address:
                        existing.mac_address = host["mac_address"]
                    nodes.append(existing)
                else:
                    node = InfraNode(
                        ip_address=host["ip_address"],
                        hostname=host.get("hostname"),
                        mac_address=host.get("mac_address"),
                        status="reachable",
                        discovery_method=method,
                    )
                    session.add(node)
                    nodes.append(node)
            await session.commit()
            for n in nodes:
                await session.refresh(n)
        return nodes

    # ------------------------------------------------------------------ #
    #  Deployment Orchestration                                            #
    # ------------------------------------------------------------------ #

    async def deploy_agent(
        self,
        node_id: str,
        agent_type: str,
        agent_subtype: str,
        zone: str,
        core_api_url: str,
        nats_url: str,
        ssh_username: str | None = None,
        ssh_password: str | None = None,
        ssh_key_path: str | None = None,
    ) -> None:
        """
        Background coroutine: deploys the agent to the remote node.
        Updates InfraNode.deployment_status throughout execution.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(InfraNode).where(InfraNode.id == UUID(node_id))
            )
            node = result.scalar_one_or_none()
            if not node:
                logger.error(f"deploy_agent: node {node_id} not found")
                return

            node.deployment_status = "in_progress"
            node.error_message = None
            await session.commit()

            try:
                # Resolve credentials: call-time args take priority over stored
                username = ssh_username or node.ssh_username
                password = ssh_password or (
                    self.decrypt_credential(node.ssh_password_enc)
                    if node.ssh_password_enc else None
                )
                key_path = ssh_key_path or node.ssh_key_path

                if node.os_type == "windows":
                    await self._deploy_via_winrm(
                        node, agent_type, agent_subtype, zone,
                        core_api_url, nats_url, username, password
                    )
                else:
                    await self._deploy_via_ssh(
                        node, agent_type, agent_subtype, zone,
                        core_api_url, nats_url, username, password, key_path
                    )

                node.deployment_status = "success"
                node.deployed_agent_type = agent_type
                node.status = "deployed"

                # Provision centralized config in DB so the agent can pull it on startup
                if node.deployed_agent_id:
                    try:
                        from uuid import UUID as _UUID
                        capabilities = (
                            ["system_probe", "file_integrity"] if agent_type == "sentinel"
                            else ["kill_process", "block_ip", "isolate_host", "unisolate_host"]
                        )
                        await self._config_sync.provision_agent_config(
                            agent_id=_UUID(node.deployed_agent_id),
                            nats_url=nats_url,
                            core_api_url=core_api_url,
                            zone=zone,
                            capabilities=capabilities,
                        )
                    except Exception as cfg_err:
                        logger.warning(
                            f"Config provisioning failed for {node.ip_address}: {cfg_err} "
                            "(agent will use bootstrap .env until config is provisioned manually)"
                        )

            except Exception as e:
                logger.error(f"Deployment failed for {node.ip_address}: {e}")
                node.deployment_status = "failed"
                node.error_message = str(e)

            await session.commit()

    # ------------------------------------------------------------------ #
    #  SSH Deployment (Linux / macOS)                                      #
    # ------------------------------------------------------------------ #

    async def _deploy_via_ssh(
        self, node, agent_type, agent_subtype, zone,
        core_api_url, nats_url, username, password, key_path
    ):
        """Connect via asyncssh and install the agent as a systemd service."""
        if not username:
            raise ValueError("SSH username is required for deployment.")
        if not password and not key_path:
            raise ValueError("Either SSH password or key path is required.")

        repo_package = "n7-sentinels" if agent_type == "sentinel" else "n7-strikers"
        module_name = "n7_sentinels" if agent_type == "sentinel" else "n7_strikers"
        install_dir = f"/opt/n7/{agent_type}"
        service_name = f"n7-{agent_type}"

        # Minimal bootstrap .env — only what the agent needs to call /api/v1/agents/{id}/config.
        # All other config (NATS_URL, zone, thresholds, etc.) is pulled from Core DB on startup.
        env_contents = (
            f"CORE_API_URL={core_api_url}\n"
            f"AGENT_TYPE={agent_type}\n"
            f"AGENT_SUBTYPE={agent_subtype}\n"
        )

        systemd_unit = f"""[Unit]
Description=N7 {agent_type.capitalize()} Agent
After=network.target

[Service]
Type=simple
WorkingDirectory={install_dir}
ExecStart={install_dir}/venv/bin/python -m {module_name}
EnvironmentFile={install_dir}/.env
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

        connect_kwargs = {
            "host": node.ip_address,
            "port": node.ssh_port,
            "username": username,
            "known_hosts": None,
        }
        if key_path:
            connect_kwargs["client_keys"] = [key_path]
        else:
            connect_kwargs["password"] = password

        commands = [
            "python3 -m ensurepip --upgrade 2>/dev/null || true",
            "python3 -m pip install --quiet virtualenv",
            f"mkdir -p {install_dir}",
            f"python3 -m venv {install_dir}/venv",
            f"{install_dir}/venv/bin/pip install --quiet {repo_package}",
        ]

        async with asyncssh.connect(**connect_kwargs) as conn:
            for cmd in commands:
                result = await conn.run(cmd, check=False)
                if result.exit_status != 0:
                    raise RuntimeError(
                        f"Command failed (exit {result.exit_status}): {cmd!r}\n"
                        f"stderr: {result.stderr}"
                    )

            # Write .env file
            async with conn.start_sftp_client() as sftp:
                async with sftp.open(f"{install_dir}/.env", "w") as f:
                    await f.write(env_contents)

            # Write systemd unit and enable the service
            unit_path = f"/etc/systemd/system/{service_name}.service"
            result = await conn.run(
                f"echo {asyncssh.quote(systemd_unit)} | sudo tee {unit_path} > /dev/null",
                check=False
            )
            if result.exit_status != 0:
                raise RuntimeError(f"Failed to write systemd unit: {result.stderr}")

            for cmd in [
                "sudo systemctl daemon-reload",
                f"sudo systemctl enable --now {service_name}",
            ]:
                result = await conn.run(cmd, check=False)
                if result.exit_status != 0:
                    raise RuntimeError(
                        f"Command failed (exit {result.exit_status}): {cmd!r}\n"
                        f"stderr: {result.stderr}"
                    )

        logger.info(f"SSH deployment of {agent_type} to {node.ip_address} completed.")

    # ------------------------------------------------------------------ #
    #  WinRM Deployment (Windows)                                          #
    # ------------------------------------------------------------------ #

    async def _deploy_via_winrm(
        self, node, agent_type, agent_subtype, zone,
        core_api_url, nats_url, username, password
    ):
        """Connect via WinRM and install the agent as a Windows service using NSSM."""
        if not username or not password:
            raise ValueError("SSH username and password are required for WinRM deployment.")

        repo_package = "n7-sentinels" if agent_type == "sentinel" else "n7-strikers"
        module_name = "n7_sentinels" if agent_type == "sentinel" else "n7_strikers"
        install_dir = f"C:\\N7\\{agent_type}"
        service_name = f"n7-{agent_type}"

        ps_commands = [
            f'New-Item -ItemType Directory -Force -Path "{install_dir}"',
            f'python -m venv "{install_dir}\\venv"',
            f'& "{install_dir}\\venv\\Scripts\\pip" install --quiet {repo_package}',
            # Minimal bootstrap .env — agent pulls full config from Core DB on startup
            (
                f'Set-Content -Path "{install_dir}\\.env" -Value '
                f'"CORE_API_URL={core_api_url}`n'
                f'AGENT_TYPE={agent_type}`n'
                f'AGENT_SUBTYPE={agent_subtype}`n"'
            ),
            f'nssm install {service_name} "{install_dir}\\venv\\Scripts\\python" "-m {module_name}"',
            f'nssm set {service_name} AppDirectory "{install_dir}"',
            f'nssm set {service_name} AppEnvironmentExtra "@{install_dir}\\.env"',
            f'nssm start {service_name}',
        ]

        def _run():
            import winrm
            session = winrm.Session(
                f"http://{node.ip_address}:{node.winrm_port}/wsman",
                auth=(username, password),
                transport="ntlm",
            )
            for ps_cmd in ps_commands:
                result = session.run_ps(ps_cmd)
                if result.status_code != 0:
                    raise RuntimeError(
                        f"WinRM command failed ({result.status_code}): {ps_cmd!r}\n"
                        f"stderr: {result.std_err.decode()}"
                    )

        await asyncio.to_thread(_run)
        logger.info(f"WinRM deployment of {agent_type} to {node.ip_address} completed.")
