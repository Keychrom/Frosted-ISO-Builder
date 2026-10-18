# Feature overview and usage

**English** | [日本語](FEATURES.ja.md)

Frosted ISO Builder builds Debian Live ISOs from a single TOML recipe.
This document is a task-oriented map of what the tool can do and how to use it.
For every key and its default, see the recipe reference in
[README.md](README.md).

- [Five-minute tour](#five-minute-tour)
- [Feature map](#feature-map)
- [ISO basics](#iso-basics)
- [Locale, language and user](#locale-language-and-user)
- [Desktop environments](#desktop-environments)
- [Packages](#packages)
- [Custom repositories and APT](#custom-repositories-and-apt)
- [Boot and persistence](#boot-and-persistence)
- [Image layout and compression](#image-layout-and-compression)
- [Debian installer](#debian-installer)
- [Files, scripts and SSH](#files-scripts-and-ssh)
- [Build environment](#build-environment)
- [Distribution and verification](#distribution-and-verification)
- [Presets](#presets)
- [Command cheat sheet](#command-cheat-sheet)
- [Example recipes](#example-recipes)
- [Not configurable yet, and caveats](#not-configurable-yet-and-caveats)

---

## Five-minute tour

```sh
git clone https://github.com/Keychrom/Frosted-ISO-Builder
cd Frosted-ISO-Builder
sudo ./install.sh --with-deps

# Create a minimal recipe interactively
frosted init --preset minimal --name mylinux

# Check the recipe and the host
frosted doctor mylinux.toml
frosted validate mylinux.toml

# Build it, then boot it in QEMU
sudo frosted build mylinux.toml
frosted test mylinux.toml
```

You can also skip the wizard and start from a minimal TOML file:

```toml
version = 1

[iso]
name = "mylinux"
```

That is enough to build. Add settings as you need them. To generate the
live-build configuration without building (no root needed), run
`frosted gen mylinux.toml`. To drive live-build directly, run
`sudo lb build` in the generated `build/` directory; its `auto/config` is
used automatically.

## Feature map

| Area | What you can do | Main settings |
| --- | --- | --- |
| ISO basics | Name, version, label, base release, architecture, output name | `[iso]` |
| Locale and system | Hostname, locale, timezone, keyboard | `[system]` |
| User | Username, display name, password, sudo, autologin | `[user]` |
| Desktop | Seven environments, wallpaper, extra packages | `[desktop]` |
| Packages | Add, remove, bundle local `.deb`, choose the kernel | `[packages]`, `[kernel]` |
| Repositories | Custom mirrors, GPG keys, APT pinning | `[build]`, `[apt]` |
| Boot | Kernel parameters, persistence, bootloaders, Secure Boot | `[boot]`, `[build]` |
| Image | Image type, filesystem, compression, checksums, swap | `[binary]` |
| Installer | Bundle the Debian installer and a preseed file | `[installer]` |
| Files | Copy host files or write content directly | `[[files.copy]]`, `[[files.write]]` |
| Scripts | Build-time and first-boot hooks | `[scripts]` |
| SSH | Server, authorized keys, root login | `[ssh]` |
| Build | Work directory, cache, mirror, debconf | `[build]` |
| Distribution | SHA256, build metadata, GPG signatures, verification | `build`, `verify` |
| Reproducibility | Presets, interactive wizard, `show` inspection | `init`, `presets` |

## ISO basics

```toml
[iso]
name = "mycompany-live"       # required; lowercase letters, digits and hyphens
version = "2026.10"
label = "MYCOMPANY_LIVE"      # generated from name if omitted
distribution = "trixie"       # bookworm / testing / sid also work
architecture = "amd64"        # amd64 / i386 / arm64
publisher = "Example Inc."
preparer = "Example Inc."
application = "MyCompany Live"
```

| Key | Description |
| --- | --- |
| `name` | ISO name. Used to generate the label (the wizard also uses it as the default hostname) |
| `version` | Version included in the output file name |
| `label` | ISO volume label (up to 32 characters) |
| `distribution` | `trixie`, `bookworm`, `testing`, `forky`, `sid` or `unstable` |
| `architecture` | `amd64`, `i386` or `arm64` |
| `output` | Output file name. Defaults to `<name>-<version>-<arch>.iso` |
| `publisher` / `preparer` | Recorded in the ISO. Always set these for distribution |
| `application` | ISO application identifier. Defaults to `name` |

`testing` and `sid` are development releases. `sid` has no security archive,
so `[build] security_mirror` is ignored there.

## Locale, language and user

```toml
[system]
hostname = "mylinux"
locale = "ja_JP.UTF-8"
timezone = "Asia/Tokyo"
keyboard_layout = "jp"
keyboard_variant = ""
keyboard_model = ""
utc = true

[user]
name = "live"
fullname = "Live User"
password = "live"              # plain text; values starting with $ are hashes
root_password = ""
default_groups = "sudo,dialout"
autologin = true
sudo = true
```

| Section | Main keys |
| --- | --- |
| `[system]` | `hostname`, `locale`, `timezone`, `keyboard_layout`, `keyboard_variant`, `keyboard_model`, `utc` |
| `[user]` | `name`, `fullname`, `password`, `root_password`, `default_groups`, `autologin`, `sudo` |

Locale, timezone, keyboard, username, hostname and the desktop session are
passed to live-config at boot. `fullname` is applied by a post-boot setup
step, not on the kernel command line.

If you disable autologin, set a password. Validation warns when neither a
password nor an SSH key is available.

## Desktop environments

```toml
[desktop]
environment = "xfce"                       # none / xfce / lxqt / mate / gnome / kde / cinnamon
session_manager = ""                       # usually automatic
extra_packages = ["fcitx5", "fcitx5-mozc"] # added regardless of the desktop
wallpaper = "./assets/wallpaper.png"       # PNG, JPEG, WebP or SVG
```

| `environment` | Character |
| --- | --- |
| `none` | CUI only. Rescue or server use |
| `xfce` | Light and stable. The usual Live USB choice |
| `lxqt` | Even lighter than Xfce |
| `mate` | Traditional desktop |
| `gnome` | Full-featured; 2 GB of RAM or more recommended |
| `kde` | Full-featured and polished; heavy |
| `cinnamon` | Familiar, Windows-like workflow |

Xfce, GNOME, MATE, Cinnamon and LXQt apply the wallpaper automatically at
login. KDE does not support automatic wallpaper setup; the image is only
copied into the ISO.

The wizard adds fonts and input methods for Japanese, Korean and Chinese to
`[packages] include` when you choose a language. If you write the recipe by
hand, add the packages yourself. `extra_packages` also works with
`environment = "none"`.

## Packages

```toml
[packages]
include = ["vim", "curl", "git"]
exclude = ["nano"]
local = [
  "./debs/myapp_1.2.0_amd64.deb",
  "./debs/myapp-data_1.2.0_all.deb",
]

[kernel]
packages = "linux-image"     # live-build's default if omitted
flavours = ["amd64"]
```

| Key | Description |
| --- | --- |
| `include` | Extra packages to install |
| `exclude` | Packages to remove explicitly after installation |
| `local` | Local `.deb` files. Installed with dependencies via `config/packages.chroot/` |
| `[kernel] packages` / `flavours` | Kernel package and flavours |

`exclude` does not follow dependencies; only the named packages are removed.

Local `.deb` files must keep the names dpkg produces, ending in `_all.deb`
or `_<architecture>.deb`. live-build does not pick up any other name, so
validation rejects them. Architecture-specific files must match
`[iso] architecture`.

## Custom repositories and APT

```toml
[build]
mirror = "http://deb.debian.org/debian/"
security_mirror = "http://security.debian.org/debian-security/"
archive_areas = ["main", "contrib", "non-free-firmware"]
extra_repositories = [
  "deb [signed-by=/usr/share/keyrings/myrepo.gpg] https://repo.example.com/debian trixie main",
]
repository_keys = ["./assets/myrepo.gpg"]
repositories_in_image = true
updates = true
backports = false

[apt]
backend = "apt"
options = "--no-install-recommends"
indices = false
preferences = '''
Package: *
Pin: release a=trixie
Pin-Priority: 100
'''
```

| Setting | Description |
| --- | --- |
| `[build] mirror` | Debian mirror used as the base |
| `security_mirror` | Security mirror. Ignored for `sid`/`unstable` |
| `archive_areas` | `main`, `contrib`, `non-free`, `non-free-firmware` |
| `extra_repositories` | Extra repositories, as raw `deb ...` lines |
| `repository_keys` | GPG keys, installed for apt and under `/usr/share/keyrings/` |
| `repositories_in_image` | `false` means build-only; `true` keeps them in the image |
| `[apt] backend` | `apt`, `apt-get` or `aptitude` |
| `[apt] preferences` | APT pinning, written to `/etc/apt/preferences.d/frosted.pref` |
| `[build] updates` etc. | updates, backports, proposed-updates, security, source |

Extra repositories are used only while packages are being installed by
default, and are removed from the finished image's `sources.list.d`. Set
`repositories_in_image = true` if the live system should also be able to use
that mirror with `apt`.

If you use `signed-by=`, list the key in `repository_keys`; it stays in
`/usr/share/keyrings/`.

## Boot and persistence

```toml
[boot]
append = "quiet splash"
install_append = "quiet splash"
persistence = true
failsafe_noautologin = true

[build]
bootloaders = ["syslinux", "grub-efi"]
secure_boot = "auto"
memtest = false
```

| Key | Description |
| --- | --- |
| `[boot] append` | Extra kernel parameters for the live system |
| `[boot] install_append` | Kernel parameters for the installed system |
| `[boot] persistence` | Enable persistence |
| `[boot] failsafe_noautologin` | Disable autologin in the failsafe entry |
| `[build] bootloaders` | `syslinux`, `grub-efi`, `grub-pc` or `grub-legacy` |
| `[build] secure_boot` | `auto`, `enable` or `disable` |
| `[build] memtest` | Add a memtest86+ entry |

Locale, keyboard, username and similar settings are added to the boot
parameters automatically. Use `append` for things such as `toram` or `quiet`
that should go straight to live-boot.

On arm64, `syslinux`, `grub-pc` and `grub-legacy` are not available; only
`grub-efi` is used.

Persistence also requires a partition labelled `persistence` on the USB
stick with a `persistence.conf` at its root. The image only carries the boot
option.

## Image layout and compression

```toml
[binary]
image_type = "iso-hybrid"          # iso / iso-hybrid / netboot / tar / hdd
filesystem = ""                     # hdd: fat32, ext4, ...
checksums = "sha256"
chroot_filesystem = "squashfs"
squashfs_compression = "zstd"
squashfs_compression_level = 19
initramfs_compression = "gzip"
zsync = true
win32_loader = false
swap_file_path = "/swapfile"
swap_file_size = 1024
```

| Key | Description |
| --- | --- |
| `image_type` | Normally `iso-hybrid`; boots on BIOS/UEFI and can be written to USB |
| `filesystem` | Filesystem for hdd images |
| `checksums` | `md5`, `sha1`, `sha256`, `sha512`, `none`, etc. |
| `chroot_filesystem` | Live filesystem format. Normally `squashfs` |
| `squashfs_compression` | `xz`, `zstd`, `gzip`, `lz4`, etc. |
| `squashfs_compression_level` | mksquashfs compression level |
| `initramfs_compression` | `bzip2`, `gzip` or `lzma` |
| `zsync` | Generate `.zsync` metadata for delta downloads |
| `win32_loader` | Include the legacy win32-loader |
| `swap_file_path` / `swap_file_size` | Create a swap file inside the image |

`[build] compression` controls archive compression for tar/netboot/source
images; `[binary] squashfs_compression` controls the live filesystem inside
the ISO. The swap file is stored inside the image, so it increases both the
ISO size and the space used on the USB stick.

`hdd` and `netboot` are available as live-build image types, but this tool
does not yet expose some related options such as the hdd size. Use
`iso-hybrid` for normal USB images.

## Debian installer

```toml
[installer]
type = "live"                 # none / cdrom / netinst / netboot / businesscard / live
gui = true
distribution = "trixie"
preseed = "./assets/preseed.cfg"

[build]
firmware_binary = true
```

| Key | Description |
| --- | --- |
| `type` | Installer flavour to bundle. Defaults to `none` |
| `gui` | Use the graphical installer |
| `distribution` | Installer release. Defaults to `[iso] distribution` |
| `preseed` | Preseed file, copied to `config/preseed/frosted.cfg` |
| `[build] firmware_binary` | Include firmware in the installer as well |

The installer flavour must match the image type, bootloaders and package
layout. Start with a small image first.

## Files, scripts and SSH

```toml
[[files.copy]]
source = "./assets/motd"
target = "/etc/motd"
mode = "0644"
owner = "root:root"

[[files.write]]
path = "/etc/skel/.bashrc"
content = '''
export EDITOR=vim
alias ls='ls --color=auto'
'''
mode = "0644"

[scripts]
setup = ["./scripts/install-tools.sh"]      # run in the chroot while building
firstboot = ["./scripts/first-run.sh"]      # run on first boot

[ssh]
enable_server = true
authorized_keys = ["./keys/id_ed25519.pub"]
permit_root_login = false
password_authentication = false
```

| Feature | Description |
| --- | --- |
| `files.copy` | Copy a host file or directory to an absolute path in the image |
| `files.write` | Write TOML content directly as a file |
| `scripts.setup` | Run as root inside the chroot during the build; failure fails the build |
| `scripts.firstboot` | Run after boot. Without persistence, effectively every boot |
| `ssh.enable_server` | Install and enable openssh-server |
| `ssh.authorized_keys` | Deploy public keys. Warns if there are no keys and no password |
| `ssh.permit_root_login` | Allow SSH login as root |
| `ssh.password_authentication` | Allow password authentication |

To make `scripts.firstboot` run only once, enable `[boot] persistence = true`
and prepare a persistence partition.

## Build environment

```toml
[build]
workdir = "build"
cache = true
compression = "xz"
apt_recommends = false
apt_proxy = "http://192.168.1.10:3142"
debootstrap_options = ""
initsystem = "systemd"
initramfs = "live-boot"
debconf_frontend = "noninteractive"
debconf_priority = "critical"
```

| Key | Description |
| --- | --- |
| `workdir` | Where live-build runs |
| `cache` | Keep the cache so rebuilds are fast |
| `compression` | Compression for tar/netboot/source archives |
| `apt_recommends` | Install recommended packages |
| `apt_proxy` | HTTP proxy such as apt-cacher-ng |
| `debootstrap_options` | Passed straight to debootstrap |
| `initsystem` | `systemd`, `sysvinit` or `none` |
| `initramfs` | `live-boot` or `none` |
| `debconf_frontend` / `debconf_priority` | debconf behaviour |

Install options:

```sh
sudo ./install.sh --with-deps                    # required build dependencies
sudo ./install.sh --with-deps --with-additional  # also QEMU/OVMF, zsync, apt-cacher-ng
```

`--with-additional` does not install the required dependencies by itself;
normally pass it together with `--with-deps`.

## Distribution and verification

`frosted build` produces these alongside the ISO:

| File | Content |
| --- | --- |
| `<ISO>.sha256` | SHA256 for the ISO alone |
| `SHA256SUMS` | Combined checksums for multiple ISOs |
| `<ISO>.build-info.json` | Recipe, version and build environment |
| `<ISO>.asc` | GPG detached signature when `--sign` is used |

```sh
# Build with a signature
sudo frosted build mylinux.toml --sign you@example.com

# The recipient can verify it like this
frosted verify mylinux-1.0-amd64.iso
frosted verify mylinux-1.0-amd64.iso --sums SHA256SUMS --signature mylinux-1.0-amd64.iso.asc
```

`--no-checksum` skips the checksum files and build metadata. `frosted verify`
never reports success when the checksum does not match or the signature is
missing.

## Presets

```sh
frosted presets            # list
frosted presets kiosk      # detail
frosted init --preset kiosk --name lobby
```

| Preset | Purpose |
| --- | --- |
| `minimal` | CUI only. A good first build |
| `rescue` | Disk recovery and diagnostics. SSH enabled |
| `desktop` | Xfce + Firefox + LibreOffice |
| `kiosk` | Autologin and a full-screen browser. Reception or signage |
| `dev` | Build tools and SSH |

Presets are starting points. Edit the recipe after `frosted init` to add
packages and settings freely.

## Command cheat sheet

| Command | What it does | Common options |
| --- | --- | --- |
| `init` | Create a recipe interactively | `--preset`, `--name`, `--distribution`, `--arch`, `--yes` |
| `gen` | Generate the live-build configuration only (no root) | `--quiet` |
| `build` | Build the ISO | `--sign`, `--no-checksum`, `--output`, `--skip-preflight` |
| `validate` | Check the recipe and host | `--no-network`, `--no-root` |
| `show` | Show the recipe and `lb config` arguments | `--bootappend`, `--lb-args` |
| `doctor` | Diagnose the build environment | `--no-network` |
| `clean` | Remove build products | `--all` |
| `shell` | Open a shell in the build chroot | `--prepare` |
| `test` | Boot the ISO in QEMU | `--uefi`, `--memory`, `--no-kvm` |
| `verify` | Verify checksums and signatures | `--sums`, `--signature` |
| `presets` | List presets or show one | name |

## Example recipes

### Japanese Xfce Live USB

```toml
version = 1

[iso]
name = "ja-live"
version = "1.0"
publisher = "Example"
preparer = "Example"

[system]
hostname = "ja-live"
locale = "ja_JP.UTF-8"
timezone = "Asia/Tokyo"
keyboard_layout = "jp"

[user]
name = "live"
fullname = "Live User"
password = "live"

[desktop]
environment = "xfce"
wallpaper = "./assets/wallpaper.png"
extra_packages = [
  "fonts-noto-cjk",
  "fonts-noto-color-emoji",
  "fonts-vlgothic",
  "fcitx5",
  "fcitx5-mozc",
  "fcitx5-frontend-gtk3",
  "fcitx5-frontend-gtk4",
  "fcitx5-frontend-qt5",
  "fcitx5-frontend-qt6",
  "im-config",
  "manpages-ja",
]

[boot]
persistence = true
```

### Internal package and mirror

```toml
version = 1

[iso]
name = "company-live"
publisher = "Example Inc."

[packages]
include = ["vim", "curl"]
local = ["./debs/company-agent_2.1.0_amd64.deb"]

[build]
repositories_in_image = true
repository_keys = ["./assets/company.gpg"]
extra_repositories = [
  "deb [signed-by=/usr/share/keyrings/company.gpg] https://repo.example.com/debian trixie main",
]

[apt]
preferences = '''
Package: *
Pin: release a=trixie
Pin-Priority: 100
'''
```

### With the Debian installer

```toml
version = 1

[iso]
name = "installer-live"
publisher = "Example"

[installer]
type = "live"
gui = true
preseed = "./assets/preseed.cfg"

[build]
firmware_binary = true
```

## Not configurable yet, and caveats

The tool covers a large part of live-build, but not everything. The main
settings not exposed in the recipe yet:

- source image type (`--source-images`)
- `--distribution-binary` / `--distribution-chroot`
- `--mirror-debian-installer`
- hdd size, label and partition start
- `--cache-indices` / `--cache-packages`
- live-build's `--interactive` / `--debug`
- `--bootstrap-qemu-*` for cross-architecture builds
- dm-verity, ONIE and netboot's net-root options

Other caveats:

- **CI does not build a full ISO.** It verifies that the generated
  configuration is accepted by the real `lb config`. Run the first real
  build on a Debian machine after `frosted doctor` passes.
- Windows and macOS can generate and validate configuration but cannot build
  ISOs.
- `frosted test` targets amd64/i386. Boot arm64 images on real hardware or
  with `qemu-system-aarch64` and AAVMF.
- KDE does not set the wallpaper automatically; the image is copied into the
  ISO.
- `sid`/`unstable` have no security archive.
- Extra repositories are not kept in the image by default; set
  `repositories_in_image = true` to keep them.
- Persistence needs a USB partition and `persistence.conf`.
- The swap file is stored inside the image, which makes the ISO larger.
