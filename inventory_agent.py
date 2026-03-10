import platform
import socket
import subprocess
import requests
import getpass
import json
import re
import os

# ── Detect OS ─────────────────────────────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"

def run(cmd):
    try:
        return subprocess.getoutput(cmd)
    except:
        return ""

# ══════════════════════════════════════════════════════════════════════════════
# WINDOWS HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def parse_wmic_single(output):
    lines = [l.strip() for l in output.split("\n") if l.strip()]
    values = lines[1:]
    return " ".join(values).strip()

def parse_wmic_list(output):
    lines = [l.strip() for l in output.split("\n") if l.strip()]
    return lines[1:]

def bytes_to_gb(raw_output):
    lines = [l.strip() for l in raw_output.split("\n") if l.strip()]
    for line in lines[1:]:
        try:
            gb = round(int(line.strip()) / (1024 ** 3), 1)
            return f"{gb} GB"
        except ValueError:
            continue
    return raw_output

def get_software_list_windows():
    ps_cmd = (
        'powershell -NoProfile -Command "'
        '$paths = @('
        "  'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "  'HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "  'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'"
        '); '
        '$apps = Get-ItemProperty $paths -ErrorAction SilentlyContinue '
        '| Where-Object { $_.DisplayName } '
        '| Select-Object DisplayName, DisplayVersion, Publisher '
        '| Sort-Object DisplayName; '
        'ConvertTo-Json -InputObject @($apps)"'
    )
    raw = run(ps_cmd)
    try:
        apps = json.loads(raw)
        result = []
        for app in apps:
            name      = (app.get("DisplayName")    or "").strip()
            version   = (app.get("DisplayVersion") or "").strip()
            publisher = (app.get("Publisher")      or "").strip()
            if name:
                entry = name
                if version:
                    entry += f" (v{version})"
                if publisher:
                    entry += f" - {publisher}"
                result.append(entry)
        return result
    except Exception:
        raw_wmic = run("wmic product get name,version")
        return parse_wmic_list(raw_wmic)

def get_disk_info_windows():
    raw = run("wmic logicaldisk get Caption,Size,FreeSpace,FileSystem")
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    disks = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 1:
            disk = {"drive": parts[0]}
            if len(parts) >= 2:
                try:
                    disk["free_gb"] = round(int(parts[1]) / (1024 ** 3), 1)
                except:
                    pass
            if len(parts) >= 3:
                try:
                    disk["total_gb"] = round(int(parts[2]) / (1024 ** 3), 1)
                except:
                    pass
            if len(parts) >= 4:
                disk["filesystem"] = parts[3]
            disks.append(disk)
    return disks

def get_monitor_device_ids_windows():
    raw = run('wmic path Win32_PnPEntity where "PNPClass=\'Monitor\'" get DeviceID,Name')
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    devices = []
    for line in lines[1:]:
        parts = line.rsplit(None, 1)
        if len(parts) == 2:
            device_id, name = parts[0].strip(), parts[1].strip()
            devices.append({"name": name, "device_id": device_id})
        elif parts:
            devices.append({"name": parts[0].strip(), "device_id": ""})
    return devices

def get_keyboard_device_ids_windows():
    raw = run('wmic path Win32_PnPEntity where "PNPClass=\'Keyboard\'" get DeviceID,Name')
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    devices = []
    for line in lines[1:]:
        parts = line.rsplit(None, 1)
        if len(parts) == 2:
            device_id, name = parts[0].strip(), parts[1].strip()
            devices.append({"name": name, "device_id": device_id})
        elif parts:
            devices.append({"name": parts[0].strip(), "device_id": ""})
    return devices

def get_mouse_device_ids_windows():
    raw = run('wmic path Win32_PnPEntity where "PNPClass=\'Mouse\'" get DeviceID,Name')
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    devices = []
    for line in lines[1:]:
        parts = line.rsplit(None, 1)
        if len(parts) == 2:
            device_id, name = parts[0].strip(), parts[1].strip()
            devices.append({"name": name, "device_id": device_id})
        elif parts:
            devices.append({"name": parts[0].strip(), "device_id": ""})
    return devices

def get_network_info_windows():
    raw = run("wmic nic where NetEnabled=true get Name,MACAddress")
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    adapters = []
    for line in lines[1:]:
        parts = line.rsplit(None, 1)
        if len(parts) == 2:
            name, mac = parts[0].strip(), parts[1].strip()
            if len(mac) == 17 and mac.count(":") == 5:
                adapters.append({"name": name, "mac": mac})
            else:
                adapters.append({"name": line, "mac": ""})
        elif parts:
            adapters.append({"name": parts[0], "mac": ""})
    return adapters

# ══════════════════════════════════════════════════════════════════════════════
# LINUX HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_software_list_linux():
    result = []

    # Try dpkg (Debian/Ubuntu)
    raw = run("dpkg-query -W -f='${PackageName} (v${Version}) - ${Maintainer}\n' 2>/dev/null")
    if raw:
        result = [l.strip() for l in raw.split("\n") if l.strip()]
        return result

    # Try rpm (CentOS/RHEL/Fedora)
    raw = run("rpm -qa --queryformat '%{NAME} (v%{VERSION}) - %{VENDOR}\n' 2>/dev/null")
    if raw:
        result = [l.strip() for l in raw.split("\n") if l.strip()]
        return result

    return result

def get_disk_info_linux():
    raw = run("df -BGB --output=target,size,avail,fstype -x tmpfs -x devtmpfs 2>/dev/null")
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    disks = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 3:
            try:
                disks.append({
                    "drive":      parts[0],
                    "total_gb":   float(parts[1].replace("G", "")),
                    "free_gb":    float(parts[2].replace("G", "")),
                    "filesystem": parts[3] if len(parts) >= 4 else "",
                })
            except:
                pass
    return disks

def get_network_info_linux():
    adapters = []
    raw = run("ip -o link show")
    for line in raw.split("\n"):
        if not line.strip() or "lo" in line:
            continue
        # Extract interface name
        match_name = re.search(r'\d+:\s+(\S+):', line)
        match_mac  = re.search(r'link/ether\s+([0-9a-f:]{17})', line)
        if match_name:
            name = match_name.group(1)
            mac  = match_mac.group(1) if match_mac else ""
            adapters.append({"name": name, "mac": mac})
    return adapters

def get_monitor_device_ids_linux():
    devices = []
    raw = run("xrandr --query 2>/dev/null | grep ' connected'")
    edid_raw = run("find /sys/class/drm -name 'edid' 2>/dev/null")
    for line in raw.split("\n"):
        if not line.strip():
            continue
        name = line.split()[0]
        # Try to get EDID-based ID from sysfs
        device_id = ""
        for edid_path in edid_raw.split("\n"):
            if name in edid_path:
                device_id = edid_path.replace("/edid", "").strip()
                break
        if not device_id:
            # Fallback: use sysfs connector path
            sysfs = run(f"find /sys/class/drm -name '*{name}*' 2>/dev/null | head -1").strip()
            device_id = sysfs if sysfs else name
        devices.append({"name": name, "device_id": device_id})
    return devices if devices else [{"name": "Unknown Monitor", "device_id": ""}]

def get_keyboard_device_ids_linux():
    devices = []
    raw = run("cat /proc/bus/input/devices")
    current = {}
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("N: Name="):
            current["name"] = line.split("=", 1)[1].strip('"')
        elif line.startswith("S: Sysfs="):
            current["device_id"] = line.split("=", 1)[1].strip()
        elif line == "" and current:
            name = current.get("name", "")
            if "keyboard" in name.lower() or "kbd" in name.lower():
                devices.append({
                    "name": name,
                    "device_id": current.get("device_id", "")
                })
            current = {}
    if not devices:
        raw_xi = run("xinput list --name-only 2>/dev/null | grep -i keyboard")
        for n in raw_xi.split("\n"):
            if n.strip():
                devices.append({"name": n.strip(), "device_id": ""})
    return devices if devices else [{"name": "Unknown Keyboard", "device_id": ""}]

def get_mouse_device_ids_linux():
    devices = []
    raw = run("cat /proc/bus/input/devices")
    current = {}
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("N: Name="):
            current["name"] = line.split("=", 1)[1].strip('"')
        elif line.startswith("S: Sysfs="):
            current["device_id"] = line.split("=", 1)[1].strip()
        elif line == "" and current:
            name = current.get("name", "")
            if "mouse" in name.lower() or "pointer" in name.lower():
                devices.append({
                    "name": name,
                    "device_id": current.get("device_id", "")
                })
            current = {}
    if not devices:
        raw_xi = run("xinput list --name-only 2>/dev/null | grep -i mouse")
        for n in raw_xi.split("\n"):
            if n.strip():
                devices.append({"name": n.strip(), "device_id": ""})
    return devices if devices else [{"name": "Unknown Mouse", "device_id": ""}]

def get_cpu_linux():
    raw = run("cat /proc/cpuinfo")
    for line in raw.split("\n"):
        if "model name" in line.lower():
            return line.split(":")[1].strip()
    return run("lscpu | grep 'Model name' | awk -F: '{print $2}'").strip()

def get_ram_linux():
    raw = run("grep MemTotal /proc/meminfo")
    try:
        kb = int(raw.split()[1])
        gb = round(kb / (1024 ** 2), 1)
        return f"{gb} GB"
    except:
        return raw

def get_gpu_linux():
    raw = run("lspci | grep -i 'vga\\|3d\\|display'")
    return [l.strip() for l in raw.split("\n") if l.strip()]

def get_monitor_linux():
    raw = run("xrandr --query 2>/dev/null | grep ' connected'")
    if raw:
        return [l.split()[0] for l in raw.split("\n") if l.strip()]
    return ["Unknown Monitor"]

def get_mouse_linux():
    raw = run("xinput list --name-only 2>/dev/null | grep -i mouse")
    if raw:
        return [l.strip() for l in raw.split("\n") if l.strip()]
    return [run("cat /proc/bus/input/devices | grep -A5 'mouse' | grep Name | head -1").strip()]

def get_keyboard_linux():
    raw = run("xinput list --name-only 2>/dev/null | grep -i keyboard")
    if raw:
        return [l.strip() for l in raw.split("\n") if l.strip()]
    return ["Unknown Keyboard"]

def get_bios_linux():
    return run("sudo dmidecode -s bios-version 2>/dev/null").strip() or \
           run("cat /sys/class/dmi/id/bios_version 2>/dev/null").strip()

def get_motherboard_linux():
    vendor  = run("cat /sys/class/dmi/id/board_vendor 2>/dev/null").strip()
    product = run("cat /sys/class/dmi/id/board_name 2>/dev/null").strip()
    return f"{vendor} {product}".strip()

def get_usb_linux():
    raw = run("lsusb")
    devices = []
    for line in raw.split("\n"):
        if line.strip():
            # Extract device name after ID xxxx:xxxx
            match = re.search(r'ID\s+\w+:\w+\s+(.*)', line)
            if match:
                name = match.group(1).strip()
                if name and "Hub" not in name and "root hub" not in name.lower():
                    devices.append(name)
    return devices

# ══════════════════════════════════════════════════════════════════════════════
# COLLECT INFO — pick Windows or Linux path
# ══════════════════════════════════════════════════════════════════════════════

device_name = socket.gethostname()
user        = getpass.getuser()
os_info     = platform.system() + " " + platform.release()

try:
    ip = socket.gethostbyname(device_name)
except:
    ip = run("hostname -I 2>/dev/null").split()[0] if IS_LINUX else ""

if IS_WINDOWS:
    cpu         = parse_wmic_single(run("wmic cpu get name"))
    ram         = bytes_to_gb(run("wmic computersystem get totalphysicalmemory"))
    bios        = parse_wmic_single(run("wmic bios get serialnumber"))
    motherboard = parse_wmic_single(run("wmic baseboard get manufacturer,product"))
    gpu         = parse_wmic_list(run("wmic path win32_VideoController get name"))
    monitor     = get_monitor_device_ids_windows()
    mouse       = get_mouse_device_ids_windows()
    keyboard    = get_keyboard_device_ids_windows()
    usb_raw     = parse_wmic_list(run("wmic path Win32_PnPEntity where \"PNPClass='USB'\" get Name"))
    usb_devices = [
        u for u in usb_raw
        if u and "Root Hub" not in u and "Composite" not in u and "Generic USB Hub" not in u
    ]
    disk        = get_disk_info_windows()
    network     = get_network_info_windows()
    software    = get_software_list_windows()

elif IS_LINUX:
    cpu         = get_cpu_linux()
    ram         = get_ram_linux()
    bios        = get_bios_linux()
    motherboard = get_motherboard_linux()
    gpu         = get_gpu_linux()
    monitor     = get_monitor_device_ids_linux()
    mouse       = get_mouse_device_ids_linux()
    keyboard    = get_keyboard_device_ids_linux()
    usb_devices = get_usb_linux()
    disk        = get_disk_info_linux()
    network     = get_network_info_linux()
    software    = get_software_list_linux()

else:
    # Unsupported OS fallback
    cpu = ram = bios = motherboard = os_info
    gpu = monitor = mouse = keyboard = usb_devices = []
    disk = network = software = []

# ── Build payload ──────────────────────────────────────────────────────────────

data = {
    "api_key":     "mpulse123",
    "device_name": device_name,
    "user":        user,
    "os":          os_info,
    "ip":          ip,
    "cpu":         cpu,
    "ram":         ram,
    "bios":        bios,
    "motherboard": motherboard,
    "gpu":         gpu,
    "monitor":     monitor,
    "mouse":       mouse,
    "keyboard":    keyboard,
    "usb":         usb_devices,
    "disk":        disk,
    "network":     network,
    "software":    software,
}

# ── Send to server ─────────────────────────────────────────────────────────────

url = "http://192.168.0.137/mpulse/index.php/inventory/save"

try:
    response = requests.post(url, json=data, timeout=15)
    if response.status_code == 200:
        print("Inventory sent successfully")
        print(f"Server response: {response.text}")
    else:
        print(f"Server returned status {response.status_code}: {response.text}")
except requests.exceptions.ConnectionError:
    print(f"ERROR: Could not connect to server at {url}")
except requests.exceptions.Timeout:
    print("ERROR: Request timed out")
except Exception as e:
    print(f"ERROR: {e}")
