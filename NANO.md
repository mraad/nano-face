# Jetson Orin Nano Super setup and maintenance

Last verified September 10, 2026, including a reboot after headless service cleanup. This is a separate device from the Jetson AGX Orin. Addresses and resource usage are observations, not guarantees.

## Current system

| Item | Verified value |
| --- | --- |
| Hardware | NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super |
| RAM | 8 GB nominal; Linux reports 7.4 GiB |
| Hostname / user | `<nano-hostname>` / `<user>` |
| OS | Ubuntu 22.04.5 LTS, NVIDIA L4T 36.4.7 |
| Kernel | `5.15.148-tegra` |
| Boot target | `multi-user.target` (headless) |
| Power mode | `MAXN_SUPER`, mode 2; unchanged during cleanup |
| System drive | Samsung SSD 990 EVO Plus 2TB NVMe |
| Mac SSH alias | `nano` |
| Nano USB address | `192.168.55.1` |
| Mac USB address | `192.168.55.100`, observed on `en14` |
| USB serial number | `<nano-serial>` |
| USB identity | NVIDIA Linux for Tegra, `0955:7020` |
| USB serial console | `/dev/cu.usbmodem<nano-serial>3` |
| Authentication | Passwordless SSH and passwordless sudo verified |

## Connect from the Mac

Power the Nano through its DC barrel adapter and connect its USB-C data port to the Mac. The USB-C connection provides data, not power for the developer kit. NVIDIA documents the port in its [Orin Nano hardware guide](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/hardware_layout.html).

```bash
ssh nano
```

The Mac's effective SSH configuration is:

```sshconfig
Host nano
    HostName 192.168.55.1
    User <user>
    HostKeyAlias jetson-orin-nano-<nano-serial>
    IdentitiesOnly yes
```

Without the alias:

```bash
ssh -o HostKeyAlias=jetson-orin-nano-<nano-serial> <user>@192.168.55.1
```

The USB device was identified by unplugging only the Nano: serial `<nano-serial>` disappeared and returned when reconnected. The generic `0955:7020` ID alone does not distinguish it from the AGX. SSH subsequently confirmed the Nano Super board model.

The Mac already had a different host key saved for `192.168.55.1`. The Nano's separate `HostKeyAlias` preserves that record. It separates SSH trust records, but does not resolve routing conflicts if two Jetsons expose the same USB subnet; connect one at a time when using this address. The AGX's documented `jetson` alias uses Ethernet instead.

The user enabled passwordless sudo for `<user>`. Verification used `sudo -n -k whoami`, which returned `root` without using cached sudo credentials. No passwords or private keys are stored here.

## EVO SSD usage

The EVO is the Nano's main system drive, not a separate data mount. No microSD card was detected.

| Partition | Purpose |
| --- | --- |
| `/dev/nvme0n1p1` | ext4 root filesystem at `/`; label in partition table: `APP` |
| `/dev/nvme0n1p10` | FAT EFI partition at `/boot/efi` |
| Other NVMe partitions | NVIDIA kernel, device-tree, recovery, alternate-slot, and reserved partitions |

The root filesystem had approximately **136 GiB used (8%) and 1.6 TiB available**. `/home` and `/var` each used about 37 GiB, `/usr` 29 GiB, and `/opt` 1.4 GiB. The active `/swapfile` occupies 32 GiB on the SSD and had no pages in use at the checks.

Files saved under `/home/<user>` already use the SSD; no repartitioning or data migration is required. The suggested `models`, `datasets`, `recordings`, and `results` directories were not created during this work.

`/etc/fstab` also contains a `noauto` entry for `/ssd` referencing UUID `cdf497ff-fcc7-4be8-a4fa-acfda74c3d93`. That UUID was absent from the detected partitions, and `/ssd` was not a separate mount. The actual root UUID is `f03e3796-b4be-44b4-9e7e-ef70474f4cc3`. The unused fstab entry was left unchanged.

## Headless service cleanup

The Nano already used `multi-user.target`. No packages were removed, and no power-mode change was made.

Disabled at boot and verified inactive after reboot:

| Units | Result |
| --- | --- |
| `nvmemwarning.service`, `nvweston.service` | Desktop memory notifications and compositor startup disabled |
| `kerneloops.service`, `lpd.service` | Kernel crash reporter and unused printer spooler stopped |
| `jtop.service` | Optional monitoring starts manually |
| `docker.service`, `docker.socket`, `containerd.service` | Container runtime starts manually; no containers were present |
| `ollama.service` | Model server starts manually |

Masked only in **<user>'s user service manager**: `pulseaudio.service`, `pulseaudio.socket`, `pipewire.service`, `pipewire.socket`, and `pipewire-media-session.service`. These desktop audio services cannot reactivate until unmasked.

SSH, USB device mode and its serial console, NetworkManager/Wi-Fi, DNS, time synchronization, NVIDIA compute services, automatic fan control, package/security maintenance, and SSD TRIM were retained. A broader batch affecting package, account, and device services was rejected by automatic approval review and was never applied; the actual changes above passed review separately.

Observed RAM use was about **508 MiB before cleanup**, **429 MiB before reboot**, and **355 MiB shortly after reboot**. These are snapshots with different cache/uptime conditions, not a controlled benchmark. Post-reboot available RAM was approximately 6.9 GiB, swap usage was zero, and both system and user service managers reported no failed units. USB SSH, passwordless sudo, Wi-Fi, and fan control were verified after reboot.

### Start tools when needed

Run on the Nano:

```bash
sudo systemctl start docker
sudo systemctl start ollama
sudo systemctl start jtop
jtop
```

Start only the tools needed. Starting Docker also starts its socket and containerd. Docker's NVIDIA runtime registration and Ollama's `/api/version` response (0.21.2) were verified before stopping both again; GPU inference was not benchmarked.

To release their resources again:

```bash
sudo systemctl stop docker.service docker.socket containerd.service
sudo systemctl stop ollama.service jtop.service
```

### Rollback

The Nano holds original configuration archives, complete before/after unit-file states, and instructions in:

```text
/home/<user>/headless-backup.4rYskn/
```

Read `README.txt` there before restoring. To restore the original system service boot enablement:

```bash
sudo systemctl enable nvmemwarning nvweston jtop kerneloops lpd docker ollama
sudo systemctl start nvmemwarning jtop kerneloops lpd docker ollama
```

`nvweston` was enabled but inactive before cleanup; the command above restores its startup setting without starting it immediately. Docker's socket and containerd were originally disabled independently and started through Docker's dependencies.

Restore desktop audio as `<user>`:

```bash
systemctl --user unmask pulseaudio.service pulseaudio.socket pipewire.service pipewire.socket pipewire-media-session.service
systemctl --user start pulseaudio.socket pipewire.socket pipewire-media-session.service
```

## Mac camera face detection

[Nano Face](README.md) uses the Mac's browser camera and sends JPEG frames over the USB SSH connection to a YuNet detector on this Nano. The browser renders returned boxes and landmarks on matching frames. Detection runs on the Nano's CPU; the live test reached about 19.7 fps at 640×480 capture, with sampled 13–19 ms inference and 27–43 ms frame round trips.

Start from the Mac:

```bash
python3 /Users/mraad/GWorkspace/nano-face/launch.py
```

Open `http://127.0.0.1:8765` and click **Start camera**. The launcher deploys to `~/nano-face` and starts an on-demand detector through SSH; Ctrl+C stops it and the tunnel. No boot service is installed, no sudo is needed, and the app does not record frames or identify people. See the linked guide for architecture, model provenance, API, testing, and troubleshooting.

## Maintenance checks

```bash
ssh nano 'systemctl get-default; systemctl --failed --no-pager'
ssh nano 'systemctl is-active ssh nv-l4t-usb-device-mode nvfancontrol NetworkManager'
ssh nano 'free -h; df -h /; swapon --show'
ssh nano 'sudo -n nvpmodel -q'
ssh nano 'sudo -n reboot'
```

The last reboot returned to USB SSH in roughly one minute. The commands above are for an interactive terminal; assistant-run local shell commands in this Mac workspace require the `rtk` prefix.
