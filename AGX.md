# Jetson AGX Orin setup

Verified September 11, 2026; apt security update and headless prune completed the same day
(see [Headless prune](#headless-prune-september-11-2026)). Serial **<agx-serial>**, hostname `<agx-hostname>`.
This is the separate AGX Orin Developer Kit, not the Orin Nano in [NANO.md](NANO.md).

| Item | Value |
|------|-------|
| OS / L4T | Ubuntu 24.04, JetPack 7 / L4T R39.2.1 (kernel variant oot) |
| Python / NumPy | `/usr/bin/python3` 3.12.3, NumPy 1.26.4 (apt `python3-numpy`) |
| OpenCV | **No NVIDIA `cv2`.** apt `python3-opencv` is 4.6 (too old for YuNet 2023mar). Installed `opencv-python-headless` 4.11.0.86 into `~/.local` |
| Power | `MODE_50W`, 12 cores, 61 GiB RAM, 2 GiB swapfile |
| Disk | 54 GB eMMC root, 10 GB used after the prune; 3.6 TB NVMe at `/data` (models, venvs, HF cache — untouched) |
| Packages | 1,598 installed; no desktop, snapd, cloud-init, or Docker (never had Docker) |
| Boot target | `multi-user.target` |
| SSH | `jetson` → `<user>@<agx-lan-ip>` (Ethernet); `jetson-usb` → `192.168.55.1` with `HostKeyAlias jetson-agx-orin-<agx-serial>` |
| Access | Passwordless SSH and `sudo -n` verified |

## OpenCV install

```bash
ssh jetson-usb 'pip3 install --user --break-system-packages "opencv-python-headless>=4.8,<5" "numpy<2"'
```

`numpy<2` keeps the apt NumPy 1.26.4 (OpenCV 4.12 would pull NumPy 2). Nothing
outside `~/.local` changes. Verify: `python3 -c 'import cv2; print(cv2.__version__, hasattr(cv2, "FaceDetectorYN"))'`.

## USB device mode: NCM interface not bridged

macOS binds the gadget's NCM function (`usb1` on the AGX), but NVIDIA's
`/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode-start.sh` hardcodes
`ifname="usb0"` in both the RNDIS and ECM/NCM blocks, so `usb1` is never added
to `l4tbr0` and the Mac's "Linux for Tegra" port stays `status: inactive`.

Fixed September 11, 2026: in the `if [ ${enable_ecm} -eq 1 ]` block of that
script (line 304), `ifname="usb0"` became
`ifname="$(cat functions/${ecm_ncm}.usb0/ifname)"`. The original is kept next
to it as `nv-l4t-usb-device-mode-start.sh.orig`. Verified by
`systemctl restart nv-l4t-usb-device-mode`: `bridge link` lists `usb0` and
`usb1`, the Mac port goes active, and 192.168.55.1 answers. A JetPack update
of `nvidia-l4t-tools` may overwrite the script; re-apply if the Mac's
"Linux for Tegra" port shows `status: inactive` again. Manual per-boot
fallback:

```bash
ssh jetson 'sudo -n ip link set usb1 master l4tbr0 && sudo -n ip link set usb1 up'
```

## Headless prune (September 11, 2026)

`apt-get upgrade` applied 16 Ubuntu security packages (python3.12 point release
and libraries); no NVIDIA package changed. Then `apt-get purge --autoremove`
removed 455 packages (1.2 GB) and `apt-get clean` dropped 2.2 GB of cached
`.deb` files; root went from 14 GB to 10 GB. Compared to the Nano this image
was already lean: no LibreOffice, no Docker, no snaps, no OTA leftovers.

- Desktop stack: `ubuntu-desktop(-minimal)`, GDM, GNOME Shell and apps, Xorg,
  `ubuntu-session`, ibus, Yaru themes and wallpapers, webkitgtk, orca,
  speech-dispatcher, firefox, `update-manager`, NetworkManager GUI and
  OpenVPN plugins, snapd, fwupd, apport, cloud-init, plymouth, ModemManager,
  bluez, power-profiles-daemon, sssd, avahi, ubiquity.
- NVIDIA GUI-only packages: the same seven as on the Nano
  (`nvidia-l4t-graphics-demos`, `-weston`, `-vulkan-sc-{samples,sdk,dev}`,
  `-jetsonpower-gui-tools`, `nvidia-l4t-bsp`). Every other `nvidia-l4t-*`,
  CUDA 13.2, TensorRT, cuDNN, and VPI package was marked manually installed
  first; 67 remain.
- Kept deliberately: NetworkManager, netplan, `wpasupplicant`, OpenSSH,
  `grub-common`, `secureboot-db`, `/opt/ota_package` (owned by
  `nvidia-l4t-bootloader`), python3-{numpy,pip,apt,requests,yaml,serial,
  paramiko,systemd}, jetson-stats, `/home`, `/data`.
- Side effects: no Bluetooth, no mDNS (`.local` names), no GUI. Wi-Fi remains
  available through NetworkManager.

Post-reboot: `systemctl is-system-running` reports `running` with zero failed
units, 87 enabled units, `nvidia-smi` shows Orin with driver 595.78, `MODE_50W`,
Ethernet at <agx-lan-ip>, USB `l4tbr0` at 192.168.55.1, `/usr/bin/python3` imports OpenCV 4.11.0 with
`FaceDetectorYN` and NumPy 1.26.4, `nvcc` and `jtop` present. All six
face-server tests passed with the re-downloaded public fixture, and a Mac USB
launch returned one face at 13–15 ms inference, 22–38 ms round trip.

## Application

`python3 launch.py --host jetson-usb` deploys into `~/nano-face` and runs the
same server, tests, and browser UI as on the Nano. September 11 results: six of
six tests passed (positive case with OpenCV's `lena.jpg`), inference 12.9–16.0 ms,
USB tunnel round trip 24–28 ms.
