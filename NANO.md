# Jetson Orin Nano Super setup and maintenance

Upgrade verified September 10, 2026 EDT; USB application launch and shutdown
verified September 11, 2026; apt security update and headless prune completed
September 11, 2026 (see [Headless prune](#headless-prune-september-11-2026)).
This is the Orin Nano Super, serial **<nano-serial>**, not the separate AGX Orin.

## Current system

| Item | Verified value |
| --- | --- |
| Hardware | NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super, P3767-0005 |
| User / hostname | `<user>` / `<nano-hostname>` |
| OS | Ubuntu 24.04.4 LTS |
| NVIDIA release | JetPack **7.2.1**, L4T **39.2.1** |
| Kernel | `6.8.12-1021-tegra` |
| Runtime package | `nvidia-jetpack-runtime 7.2.1-b49` |
| CUDA runtime / TensorRT | `cuda-cudart-13-2 13.2.86-1` / `10.16.2.10-1+cuda13.2` |
| GPU driver | NVIDIA 595.78; `nvidia-smi` detects Orin |
| Python / NumPy / OpenCV | 3.12.3 / 1.26.4 / 4.8.0, with `FaceDetectorYN` |
| Bootloader | Both slots verified running 39.2.1; final current/active slot A, both normal, capsule status 1 |
| Boot target / power | `multi-user.target` / `MAXN_SUPER`, mode 2 |
| Memory / swap | Approximately 7.3 GiB RAM / 32 GiB SSD swapfile |
| Disk | Samsung SSD 990 EVO Plus 2TB NVMe; 79 GiB used after the prune |
| Packages | 1,187 installed; no desktop, snapd, cloud-init, or Docker |
| Access | Passwordless SSH and `sudo -n` verified |

The runtime installation is not the full developer SDK. Old Python virtual
environments, CUDA applications, and containers may need rebuilding for
Ubuntu 24.04 and CUDA 13.2. Preserved files alone do not establish compatibility.

## Connections from the Mac

The verified wired connection is:

```bash
ssh -o HostName=<nano-lan-ip> nano
```

Ethernet negotiated 1 Gbit/s full duplex on `enP8p1s0`, MAC
`4c:bb:47:32:eb:e4`. The Mac reaches this LAN through its own Wi-Fi.
The Nano also connects to **<wifi-ssid>** at `<nano-wifi-ip>` on `wlP1p1s0`:

```bash
ssh -o HostName=<nano-wifi-ip> nano
```

These are observed DHCP addresses, not reservations. Wi-Fi power saving is on.

### USB

The normal Mac SSH alias remains:

```sshconfig
Host nano
    HostName 192.168.55.1
    User <user>
    HostKeyAlias jetson-orin-nano-<nano-serial>
    IdentitiesOnly yes
```

```bash
ssh nano
```

The Mac's **Linux for Tegra** service uses static `192.168.55.100/24` on `en14`.
The Nano's USB bridge is `192.168.55.1/24`. Power the developer kit using its
DC barrel adapter; USB-C provides data. See NVIDIA's
[hardware guide](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/hardware_layout.html).

**USB verified September 11, 2026:** `python3 launch.py --no-browser`
connected through the default `nano` alias, identified the Orin Nano Super,
deployed the application, and started its detector and SSH tunnel. The Mac's
`http://127.0.0.1:8765/api/health` returned `nano-face` on
`<nano-hostname>`, YuNet 2023mar, OpenCV CPU, and OpenCV 4.8.0.
This confirms that USB SSH recovered after the earlier inactive-link state.

The application was then stopped at the user's request. Checks confirmed no
matching Nano server process and no Mac listener on port 8765. To use it
again, run the launcher and click **Start camera** in the browser. This launch
check did not establish a new live-camera benchmark.

Large USB backup transfers stalled before the upgrade; Ethernet remains the
preferred transport for large maintenance transfers.

The generic NVIDIA USB ID `0955:7020` does not distinguish this Nano from the
AGX. The separate HostKeyAlias preserves their separate trust records, but
cannot resolve two devices exposing the same USB subnet simultaneously.
The AGX's `jetson` alias and installation were not modified.

Cloud-init regenerated SSH host keys on first boot. After verifying the Nano's
wired MAC, USB serial, and running board identity, the original host keys were
restored from the verified configuration backup. They survived subsequent
reboots. The original ED25519 fingerprint is:

```text
SHA256:qt9F+IW7ewbW0HS2FJs0ZF2J7jK/XsuMbOHOGYfw+Gs
```

## EVO SSD usage

The EVO is the main system disk, not a separate data card. No microSD was
detected. `/dev/nvme0n1p1` is the ext4 root filesystem; `/home` and `/var`
already use the SSD. The other partitions contain EFI, NVIDIA kernel,
recovery, and alternate boot components. No repartitioning was performed.

After the upgrade, root reports **1.8 TiB total, 121 GiB used, and 1.6 TiB
available**. The 32 GiB `/swapfile` is active with no pages in use at the check.
First boot created a 2 GiB swapfile and a duplicate fstab entry; the original
32 GiB size was restored and only the duplicate entry removed. The prior
fstab is `/etc/fstab.before-nano-swap-repair`.

The unused `noauto` `/ssd` entry references UUID
`cdf497ff-fcc7-4be8-a4fa-acfda74c3d93`, which is absent from detected devices.
It remains unchanged. Save models and datasets under `/home/<user>` to
use the available space without creating another mount.

## Headless operation and jtop

The Nano boots to `multi-user.target`. GDM, GNOME, Xorg, and Docker are no
longer installed (see the prune section). Ollama is not installed in the
new image. Home directories were preserved.

SSH, NetworkManager, NVIDIA compute services, automatic fan control, and USB
device mode remain active. The final service check reports **zero failed
units**. MAXN_SUPER required NVIDIA's `nvpmodel -m 2 --force` reboot to rebuild
the GPU context; the subsequent boot and power service passed.

jtop is installed in `/opt/jetson-stats` with `/usr/local/bin/jtop` pointing to
its executable. The package environment was made readable/traversable after
the image build left root-only directory permissions. Its release table has
the exact `39.2.1` → `7.2.1` mapping; this is backed by the installed OS version.
Both the API and actual terminal dashboard display **JetPack 7.2.1 / L4T
39.2.1**, without `NOT DETECTED`, and provide live telemetry.

jtop starts manually and was left running for inspection:

```bash
sudo systemctl start jtop
jtop
# Stop monitoring when finished:
sudo systemctl stop jtop
```

The runtime-only installation may leave jtop's CUDA toolkit or OpenCV library
summary blank; the actual runtime packages, OpenCV import, and GPU driver
were checked separately. JetPack detection is verified.

Docker Engine and its 33 GiB of preserved containerd data were removed on
September 11, 2026. `nvidia-container` (the NVIDIA container toolkit) remains
installed because `nvidia-jetpack-runtime` depends on it; its
`nvidia-cdi-refresh` path/service units are disabled because they raced the
GPU driver at boot and serve no purpose without a container engine. To use
containers again: `sudo apt install docker-ce` from the Docker repository,
then `sudo systemctl enable --now nvidia-cdi-refresh.path`.

The original headless cleanup archive is preserved in
`/home/<user>/headless-backup.4rYskn/`. Its rollback instructions describe
the old Ubuntu 22.04 installation; do not apply them blindly to the new OS.

## Mac camera face detection

[Nano Face](README.md) captures camera frames in the Mac browser, sends JPEGs
through SSH, runs YuNet on the Nano's CPU, and draws returned boxes and five
landmarks on the matching frame. No identity recognition or recording is used.

```bash
cd ~/GWorkspace/nano-face
python3 launch.py
```

The default launcher uses the verified USB connection through `nano`. The
application architecture and assets remain in
this repository; no face-project assets were added to the former Mac folder.

After the upgrade, all **six face-server tests passed on the Nano**, including
real-face detection, coordinate scaling, blank frames, request boundaries,
and busy-detector rejection. Ten public-image HTTP requests through an SSH
tunnel also passed, from Mac Wi-Fi to Nano Ethernet: median inference
**16.1 ms**, median round trip **33.6 ms**. These are fixture measurements,
not a new live-camera frame-rate benchmark. The earlier live-camera test on
JetPack 6.2.1 reached about 19.7 fps; see README for that historical result.

## Upgrade and backup record

NVIDIA lists [JetPack 7.2.1](https://developer.nvidia.com/embedded/jetpack/downloads)
as the current release. The upgrade used NVIDIA's
[image-based OTA procedure](https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html#updating-jetson-linux-with-image-based-over-the-air-update)
from R36.4.7, followed by a bootloader-only R39 update for the second chain.
It did not mix R39 packages into Ubuntu 22.04 or use `do-release-upgrade`.

1. With explicit user approval, created and verified a full file-level backup
   on the Mac plus separate configuration/EFI backups.
2. Built an isolated headless R39.2.1 image and both OTA payloads in the
   Parallels VM at `/home/parallels/nano-upgrade-r39.2.1/`, targeting only
   `jetson-orin-nano-devkit-super`, P3767-0005, NVMe. Payload SHA-256 checks
   passed after transfers.
3. The first recovery run reached preservation compression. A blank display
   and missing networking were initially mistaken for a stalled boot; that
   diagnosis was premature. Esc opened UEFI, and changing L4T Boot Mode from
   Recovery Partition to ExtLinux restored the original OS.
4. Validated the 401,972-entry preservation tar, compressed it on the running
   OS with `pigz`, and verified its gzip integrity. The resulting archive was
   51,818,673,521 bytes. The full independent Mac backup remained intact.
5. Retried with wired recovery SSH through NVIDIA's custom OTA task hook,
   using the original host keys and existing authorized key, with password
   login disabled. Image and preservation checks passed. The updater
   extracted the new OS and restored saved data.
6. Verbose restore output was throttled by the recovery serial console,
   including timestamp warnings because recovery's clock began in 1970.
   A temporary Python helper used Linux
   [TIOCCONS](https://man7.org/linux/man-pages/man2/TIOCCONS.2const.html) to
   redirect and drain console output while retaining the complete OTA file
   log. Its self-check passed and it restored the console when tar exited.
7. The full update booted slot B at 39.2.1. The bootloader-only payload then
   booted slot A at 39.2.1, proving both chains were updated. Subsequent power,
   service, SSH, jtop, and face tests passed as recorded above.

The 6.4 GiB payload directory `/ota-nano-upgrade-20260910/` was deleted on
September 11, 2026; payloads are rebuildable in the Parallels VM. Successful
recovery logs remain in `/last_ota_update_log/`. NVIDIA cleaned its
temporary `/ota_work` archives after success.

The private Mac backup and validation records are in:

```text
/Users/mraad/GWorkspace/nano-face/.local/jetpack-upgrade-20260910/
```

This mode-0700 directory is Git-ignored and contains credentials/private data.
Do not commit it. `nano-rootfs.tar.gz` is **78,739,572,901 bytes**, SHA-256:

```text
0396541e61f8c79a3429fd2cccf2e880b8638fc45e3d6e21ee03b4dbd01e263f
```

SHA-256, gzip CRC, and tar validation passed: 642,827 entries and
109,817,418,126 logical bytes. This is a file backup excluding swap and virtual
filesystems, not a raw NVMe/firmware clone. Restore with Linux GNU tar and
appropriate ownership, ACL, and xattr handling; consult the private README.

## Headless prune (September 11, 2026)

`apt-get upgrade` applied 271 packages (233 from `noble-security`); no NVIDIA
package changed because the L4T repository is pinned to `r39.2`. Then
`apt-get purge` and a guarded `autoremove --purge` removed 891 packages and
freed about 42 GiB in total:

- Desktop stack: `ubuntu-desktop`, GDM, GNOME Shell and apps, Xorg, Wayland,
  Mutter, LibreOffice, fonts, ibus, CUPS and printer drivers, PipeWire,
  Bluetooth, ModemManager, fwupd, snapd, apport, cloud-init, plymouth, sssd,
  avahi, ubiquity.
- NVIDIA GUI-only packages: `nvidia-l4t-graphics-demos`, `nvidia-l4t-weston`,
  `nvidia-l4t-vulkan-sc-{samples,sdk,dev}`, `nvidia-l4t-jetsonpower-gui-tools`,
  and the `nvidia-l4t-bsp` metapackage that depends on them. Every other
  `nvidia-l4t-*`, CUDA, TensorRT, cuDNN, VPI, and NVIDIA OpenCV package was
  first marked manually installed so `autoremove` cannot touch it.
- Docker Engine, `openvpn`, `iperf3`, `/var/lib/containerd` (33 GiB),
  `/var/lib/docker`, `/ota-nano-upgrade-20260910` (6.4 GiB), apt cache.
- Kept deliberately: NetworkManager, netplan, `wpasupplicant`, OpenSSH,
  `usbutils`, `lsof`, `jq`, `zip`/`unzip`, `grub-common`, `secureboot-db`,
  `python3-{apt,requests,yaml,serial,paramiko,systemd}`, polkit, and all of
  `/home/<user>`.

Post-reboot: `multi-user.target`, `systemctl is-system-running` reports
`running` with zero failed units, 83 enabled units, USB `l4tbr0` at
192.168.55.1, Ethernet and Wi-Fi connected through NetworkManager,
`nvidia-smi` shows Orin with driver 595.78, MAXN_SUPER mode 2, swap active,
jtop present, `/usr/bin/python3` imports OpenCV 4.8.0 with `FaceDetectorYN`
and NumPy 1.26.4. All six face-server tests passed with the re-downloaded
public fixture, and a Mac USB launch returned one face at 0.868 confidence in
16.4 ms inference through the tunnel. Private apt and prune logs are in
`.local/` on the Mac.

## Maintenance checks

```bash
ssh -o HostName=<nano-lan-ip> nano 'head -n 1 /etc/nv_tegra_release; uname -r'
ssh -o HostName=<nano-lan-ip> nano 'sudo -n nvbootctrl dump-slots-info'
ssh -o HostName=<nano-lan-ip> nano 'systemctl --failed --no-pager; free -h; df -h /'
ssh -o HostName=<nano-lan-ip> nano 'sudo -n nvpmodel -q; swapon --show'
```

Assistant-run local shell commands in this Mac workspace require the `rtk`
prefix; the examples above are for an interactive terminal.
