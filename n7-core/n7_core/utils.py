from datetime import datetime

def print_banner(service_name: str, version: str = "1.0.0"):
    """
    Print the Naga-7 startup banner with comprehensive information.
    
    Args:
        service_name: Name of the service starting up (e.g., "N7-Core", "N7-Sentinel")
        version: Version number of the service (default: "1.0.0")
    """
    banner = r"""
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣤⣴⢶⣾⣞⠒⠶⢤⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⡟⢩⣇⠀⢛⣿⡟⠀⠀⠀⠙⢿⡲⢤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⡒⡳⠒⠚⠙⠒⠂⠀⠀⠰⡄⢹⡄⢟⢷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⢹⡿⠶⣶⣤⡤⠤⠤⠖⢿⠁⣹⣺⡾⠈⢷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⡇⠀⠀⠘⣗⡒⠒⠒⢺⡏⣹⣽⡇⢰⠀⠀⢳⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⠇⠀⠀⡄⢿⣉⠑⠒⢚⣏⣹⠉⡟⡞⢀⡎⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⠀⠀⠀⢧⣾⣮⣉⠒⢺⠋⡟⢺⣷⠛⣟⡼⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⡏⠀⠀⣇⣼⣾⠃⠈⠁⡏⢸⠷⣇⣼⠚⠋⠀⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣿⠀⣠⢀⣟⣡⡏⠀⠀⣸⠁⣿⣟⣩⡄⢀⠀⣸⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣠⠿⣼⢛⡟⠀⠀⢠⠃⢸⣟⡽⣥⠷⡜⣶⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⢹⣶⢯⢯⣉⠒⠶⡞⣠⣿⢯⡴⢧⢼⣿⠏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣷⣾⣸⠻⢤⣈⠉⣻⠉⢠⣇⣾⣷⣿⠟⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⠃⠀⠀⠀⣰⠃⢀⡿⣻⣿⠟⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⠋⠀⠀⠀⢠⠇⢀⣾⠟⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⠃⠀⠀⠀⠀⠀⢀⣾⠏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⡏⠀⠀⠀⠀⠀⢀⣿⠏⢠⡿⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣠⠴⠶⠶⠶⠤⣄⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣿⠀⠀⠀⠀⠀⢀⣾⡏⠀⠀⠻⣝⠷⣄⣀⣀⣀⣤⠶⠛⠁⠀⠀⠀⠀⠀⠀⠈⢻⡙⢶⣄⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⣀⣀⣀⣀⣀⣀⠀⢸⡇⡀⠘⢦⣰⢃⣸⣿⠀⠀⠀⠀⠙⢷⣄⣀⣩⣥⡤⠤⠦⠦⠤⢤⣤⣤⣤⣴⡶⠏⠀⠀⠙⡆⠀⠀⠀⠀⠀
⠀⠀⠀⣠⡴⠞⠛⠉⢀⡠⠆⠀⠉⠙⢻⡇⠙⠢⣄⣿⣁⣼⣿⣤⠤⠤⠶⠛⠛⠉⠁⠀⣀⣀⣠⡤⠤⠤⠴⢶⠤⠴⠦⠤⣤⣀⣀⣴⡇⠀⠀⠀⠀⠀
⠀⢀⡞⠁⠀⠀⠀⢠⡎⠀⠀⠀⠀⠀⢸⡇⠲⣄⡀⠙⣇⣼⣿⠀⠀⠀⠀⣀⣤⠶⠚⠛⠉⠀⠀⠀⠀⠀⠀⠈⠙⠓⢦⡀⠀⠀⠙⠛⠦⣤⡀⠀⠀⠀
⢠⡟⠀⠀⠀⠀⠀⢸⣄⣤⣤⢤⣤⣀⣸⡇⠀⠀⠉⣋⣯⣸⣿⣤⡤⠞⠋⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⡄⠀⠀⠀⠀⠀⠙⢧⡀⠀
⢸⡇⠀⠀⠀⠀⠀⠘⢿⣉⠀⠀⠀⠉⠛⣿⠤⢤⣀⠈⠙⣤⡿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣀⣤⣤⣤⣀⣸⣿⡄⠀⠀⠀⠀⠀⠀⠘⣷⠀
⠸⣧⠀⠀⠀⠀⠀⠀⠀⠙⠛⠒⠒⠚⠛⢻⡆⠠⣄⣉⣉⣹⡼⢻⣧⠀⠀⠀⠀⠀⣀⣠⣤⠶⠟⠛⠋⠉⠀⠀⠀⠀⠀⠀⣹⡇⠀⠀⠀⠀⠀⠀⠀⣹⠀
⠀⠘⢷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣄⠀⠀⠀⠀⠹⣍⠈⠳⣦⣴⡾⠿⠛⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⡼⠋⠀⠀⠀⠀⠀⠀⠀⢰⡿⡀
⠀⠀⠀⠙⠷⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠻⣄⠀⠀⠀⠀⠈⠳⡄⠀⠉⠛⠲⠤⠤⣤⣀⣀⣤⠤⠤⠤⠔⠚⠋⠁⠀⠀⠀⠀⠀⠀⠀⠀⢠⣿⠃⠀
⠀⠀⠀⠀⠀⠈⠙⠛⠶⠤⣤⣤⣤⣤⣤⣤⣴⠶⠿⢧⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⡿⠁⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠳⢦⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣤⣶⠟⠋⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠙⠒⠲⠤⠤⢤⣄⣀⣀⣀⣀⣀⣠⣤⣤⣤⡤⠶⠶⠛⠛⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
"""
    
    current_year = datetime.now().year
    
    # Print the ASCII art
    print(banner)
    
    # Print comprehensive information
    print("=" * 80)
    print(f"  NAGA-7 (N7) - Multi-Level AI Agent Security System")
    print("=" * 80)
    print(f"  Service:        {service_name}")
    print(f"  Version:        {version}")
    print(f"  Started:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 80)
    print(f"  Description:    Autonomous security monitoring and threat response platform")
    print(f"  Components:     N7-Core | N7-Sentinels | N7-Strikers")
    print("-" * 80)
    print(f"  License:        Apache License 2.0")
    print(f"  Copyright:      © {current_year} Naga-7 Project Contributors")
    print(f"  Project:        https://github.com/naga-7/naga-7")
    print(f"  Documentation:  https://docs.naga-7.io")
    print("=" * 80)
    print()
    print("  Licensed under the Apache License, Version 2.0 (the \"License\");")
    print("  you may not use this software except in compliance with the License.")
    print("  You may obtain a copy of the License at:")
    print()
    print("      http://www.apache.org/licenses/LICENSE-2.0")
    print()
    print("  Unless required by applicable law or agreed to in writing, software")
    print("  distributed under the License is distributed on an \"AS IS\" BASIS,")
    print("  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.")
    print("  See the License for the specific language governing permissions and")
    print("  limitations under the License.")
    print("=" * 80)
    print()
