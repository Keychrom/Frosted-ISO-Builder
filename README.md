# Frosted ISO Builder

**English** | [日本語](README.ja.md)

[![CI](https://github.com/Keychrom/Frosted-ISO-Builder/actions/workflows/ci.yml/badge.svg)](https://github.com/Keychrom/Frosted-ISO-Builder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Build Debian live ISOs from **a single recipe file**.

It wraps [live-build](https://wiki.debian.org/DebianLive). Using live-build
directly means learning three separate mechanisms — the `config/` tree,
`auto/config`, and three stages of hooks. This tool takes all of that over and
asks you only what you want to build.

```toml
[iso]
name = "mylinux"

[desktop]
environment = "xfce"
```

That is enough to build. It also produces the artifacts you need to *distribute*
an image (checksums, build metadata, GPG signatures), so the whole release
workflow fits in one tool.

The UI is available in English and Japanese. It is detected from `LANG` /
`LC_ALL`, or set explicitly with `--lang en` / `--lang ja`.

---

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Try it in five minutes](#try-it-in-five-minutes)
- [Recipe reference](#recipe-reference)
- [Command reference](#command-reference)
- [Presets](#presets)
- [Desktop environments](#desktop-environments)
- [Distributing an ISO](#distributing-an-iso)
- [How it works](#how-it-works)
- [Persistence](#persistence)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Verification status](#verification-status)
- [License](#license)

---

## Requirements

| | |
| --- | --- |
| OS | Debian 12 (bookworm) or 13 (trixie); derivatives should work |
| Python | 3.11 or newer (standard library only) |
| Privileges | root, for building |
| Disk space | 6 GiB minimum, 20 GiB or more to be comfortable |
| Network | access to an APT mirror |

Building requires root, and live-build creates a chroot, so it may not work
inside a container. Use a real machine or a VM.

## Installation

```sh
git clone https://github.com/Keychrom/Frosted-ISO-Builder
cd Frosted-ISO-Builder

# Install with its dependencies (recommended)
sudo ./install.sh --with-deps

# Or install the tool only
sudo ./install.sh
```

If you skip `--with-deps`, install these first:

```sh
sudo apt install live-build debootstrap xorriso squashfs-tools cpio rsync \
    uuid-runtime mtools dosfstools syslinux-common isolinux \
    grub-efi-amd64-bin grub-pc-bin fakeroot gnupg
```

On arm64, use `grub-efi-arm64-bin` instead of the amd64/x86 GRUB packages.
`./install.sh --with-deps` picks the right ones for the host architecture.

You can also run it without installing:

```sh
python3 bin/frosted --version
```

Uninstall with `sudo ./install.sh --uninstall`.

## Try it in five minutes

```sh
# 1. Check the environment. Tells you what is missing.
frosted doctor

# 2. Create a recipe interactively.
frosted init

# 3. Look at the settings before building (no root needed, takes seconds).
frosted gen mylinux.toml

# 4. Build. This takes tens of minutes.
sudo frosted build mylinux.toml

# 5. Check it boots before writing a USB stick.
frosted test mylinux.toml
```

`init` picks up your machine's timezone, keyboard and locale as defaults, so in
most cases you can just press Enter through it.

Start with [`examples/minimal.toml`](examples/minimal.toml) to confirm the whole
pipeline works. It builds a plain console-only Debian image in about ten minutes.

```sh
sudo frosted build examples/minimal.toml
```

## Recipe reference

Recipes are TOML. Anything you leave out gets a default, so you only write what
you care about.

### `[iso]` — what you are building

| Key | Default | Description |
| --- | --- | --- |
| `name` | (required) | ISO name. Lowercase letters, digits and hyphens |
| `version` | `"1.0"` | Version, used in the output file name |
| `label` | derived from `name` | ISO volume label, up to 32 characters |
| `distribution` | `trixie` | `trixie` (13), `bookworm` (12), `testing`, or `sid` (`forky`/`unstable` aliases also work) |
| `architecture` | `amd64` | `amd64`, `i386` or `arm64` |
| `output` | derived | Output file name. Defaults to `<name>-<version>-<arch>.iso` |
| `publisher` | the tool's name | Publisher recorded in the ISO. **Set this if you distribute** |
| `preparer` | the tool's name | Preparer recorded in the ISO. **Set this if you distribute** |
| `application` | same as `name` | ISO application identifier |

`publisher` and `preparer` are written into the ISO and can be read back with
`isoinfo -d -i image.iso`. They default to this tool's name, so change them to
your own name or project before publishing an image.

`testing` follows Debian Testing (currently `forky`), and `sid` is unstable.
These are development branches: packages move and a build or boot that worked
yesterday can break today. `sid` has no security archive, so
`build.security_mirror` is ignored for it.

### `[system]` — locale and region

| Key | Default | Description |
| --- | --- | --- |
| `hostname` | same as `name` | Hostname |
| `locale` | `en_US.UTF-8` | Locale, e.g. `ja_JP.UTF-8` |
| `timezone` | `UTC` | e.g. `Asia/Tokyo` |
| `keyboard_layout` | `us` | e.g. `jp` |
| `keyboard_variant` | empty | For kana input and similar |
| `keyboard_model` | `pc105` | Usually left alone |
| `utc` | `true` | Treat the hardware clock as UTC |

### `[user]` — the user in the live system

| Key | Default | Description |
| --- | --- | --- |
| `name` | `user` | User name |
| `fullname` | `Live User` | Display name |
| `password` | empty | Empty means no password. A `$6$...` hash also works |
| `root_password` | empty | Password for root |
| `default_groups` | empty | Extra groups to join, e.g. `sudo,dialout` |
| `autologin` | `true` | Log in automatically at boot |
| `sudo` | `true` | Allow passwordless sudo |

### `[desktop]` — desktop environment

| Key | Default | Description |
| --- | --- | --- |
| `environment` | `none` | [`none` / `xfce` / `lxqt` / `mate` / `gnome` / `kde` / `cinnamon`](#desktop-environments) |
| `session_manager` | automatic | X session. Usually left alone |
| `extra_packages` | empty | Extra packages for the desktop environment |
| `wallpaper` | empty | Host image copied into the image and set at login |

```toml
[desktop]
environment = "xfce"
wallpaper = "./assets/wallpaper.jpg"
```

Wallpaper is applied at login on Xfce, GNOME, MATE, Cinnamon and LXQt.
On KDE it is copied into the image but not set automatically. Supported
formats are PNG, JPEG, WebP and SVG.

### `[packages]` — packages

| Key | Description |
| --- | --- |
| `include` | Packages to install |
| `exclude` | Packages to remove explicitly |

`exclude` runs `apt-get remove` after installation. It does not follow
dependencies, so only the packages you name are removed.

### `[ssh]`

| Key | Default | Description |
| --- | --- | --- |
| `enable_server` | `false` | Install openssh-server and enable it at boot |
| `authorized_keys` | empty | Paths to public key files, on the host |
| `permit_root_login` | `false` | Allow SSH login as root |
| `password_authentication` | `false` | Allow password authentication |

If you set neither keys nor a password, you will not be able to log in, and
validation warns you about that combination.

### `[[files.copy]]` / `[[files.write]]` — putting files in the image

```toml
# Copy a file from the host into the image
[[files.copy]]
source = "./assets/motd"     # relative to the recipe
target = "/etc/motd"         # absolute path inside the image
mode = "0644"                # optional
owner = "root:root"             # optional (old name: Keychrom)

# Write content directly into the image
[[files.write]]
path = "/etc/skel/.bashrc"
content = '''
export EDITOR=vim
alias ls='ls --color=auto'
'''
mode = "0644"
```

`content` supports `'''`-quoted multi-line strings, so you can paste a shell
script in without escaping anything.

If `source` in a `files.copy` entry is a directory, its contents are copied.

### `[scripts]` — running scripts

```toml
[scripts]
setup = ["./scripts/install-tools.sh"]     # run inside the chroot while building
firstboot = ["./scripts/first-run.sh"]     # run on first boot
```

`setup` runs as root inside the chroot during the build. Use it to install
packages or adjust settings. If it fails, the build fails.

`firstboot` runs after boot. **Unless you enable persistence, a live system
returns to a clean state on every boot, so in practice this runs every time.**
Enable [`boot.persistence`](#persistence) if you need it to run only once.

### `[boot]`

| Key | Default | Description |
| --- | --- | --- |
| `append` | empty | Extra kernel parameters, e.g. `quiet splash toram` |
| `persistence` | `false` | Enable persistence |
| `failsafe_noautologin` | `true` | Turn off autologin in the failsafe menu entry |

### `[build]` — build settings

| Key | Default | Description |
| --- | --- | --- |
| `workdir` | `"build"` | Where live-build runs |
| `mirror` | `http://deb.debian.org/debian/` | APT mirror. Point this at an internal mirror if you have one |
| `security_mirror` | `http://security.debian.org/...` | Security updates mirror (ignored for `sid`/`unstable`) |
| `archive_areas` | `main contrib non-free-firmware` | Archive areas to enable |
| `compression` | `xz` | Archive compression for tar/netboot/source (`xz`, `gzip`, `bzip2`, `lzip`, `none`) |
| `apt_recommends` | `false` | Also install recommended packages |
| `apt_proxy` | empty | e.g. `http://192.168.1.10:3142`. Makes rebuilds much faster |
| `cache` | `true` | Keep the cache so rebuilds are fast |
| `firmware` | `true` | Include firmware (needed for Wi-Fi and GPUs) |
| `bootloaders` | `syslinux grub-efi` | BIOS and UEFI support |
| `secure_boot` | `auto` | `auto`, `enable` or `disable` |
| `memtest` | `false` | Add a memory test entry |
| `debootstrap_options` | empty | Passed straight through to debootstrap |
| `extra_repositories` | empty | Additional APT repositories (`deb ...` lines) |
| `repository_keys` | empty | GPG keys for those repositories, installed for apt and copied to `/usr/share/keyrings/` |
| `updates` | unset | Enable the updates suite |
| `backports` | unset | Enable backports |
| `proposed_updates` | unset | Enable proposed updates |
| `security` | unset | Enable the security suite (ignored for `sid`/`unstable`) |
| `source` | unset | Also build source images |
| `debconf_frontend` | unset | `dialog`, `editor`, `noninteractive` or `readline` |
| `debconf_priority` | unset | `low`, `medium`, `high` or `critical` |

```toml
[build]
repository_keys = ["./assets/myrepo.gpg"]
extra_repositories = [
  "deb [signed-by=/usr/share/keyrings/myrepo.gpg] https://repo.example.com/debian stable main",
]
```

Key files must be named with letters, digits, `.`, `_` or `-`, and end in
`.gpg`, `.asc` or `.pgp`. They are placed in `config/archives/` so apt can use
them while installing packages, and are also copied with the same file name
into `/usr/share/keyrings/` in the image for `signed-by=` entries.

### `[apt]` — APT behaviour

| Key | Default | Description |
| --- | --- | --- |
| `backend` | unset | `apt`, `apt-get` or `aptitude` |
| `secure` | unset | Verify repository signatures |
| `source_archives` | unset | Include `deb-src` entries |
| `indices` | unset | Keep package indices in the image |
| `options` | empty | One string passed to APT, e.g. `--no-install-recommends` |
| `pipeline` | unset | APT pipeline depth |
| `keyring_packages` | empty | Keyring packages installed for APT |

`[build] apt_recommends` and `[build] apt_proxy` remain the settings for
recommends and the HTTP proxy.

### `[installer]` — Debian installer

| Key | Default | Description |
| --- | --- | --- |
| `type` | `none` | `none`, `cdrom`, `netinst`, `netboot`, `businesscard` or `live` |
| `gui` | unset | Use the graphical installer |
| `distribution` | same as `iso.distribution` | Installer release |
| `preseed` | empty | Host preseed file copied to `config/preseed/frosted.cfg` |

The installer type must be compatible with `[binary] image_type`,
bootloaders and the selected image layout. Try a small image first.

### `[kernel]` — kernel packages

| Key | Default | Description |
| --- | --- | --- |
| `packages` | empty | e.g. `linux-image` |
| `flavours` | empty | e.g. `["amd64"]` or `["686-pae"]` |

### `[binary]` — image layout and compression

| Key | Default | Description |
| --- | --- | --- |
| `image_type` | `iso-hybrid` | `iso`, `iso-hybrid`, `netboot`, `tar` or `hdd` |
| `filesystem` | unset | `fat16`, `fat32`, `ext2`, `ext3`, `ext4` or `ntfs` |
| `checksums` | `sha256` | `md5`, `sha1`, `sha224`, `sha256`, `sha384`, `sha512` or `none` |
| `chroot_filesystem` | unset | `ext2`, `ext3`, `ext4`, `squashfs`, `jffs2` or `none` |
| `squashfs_compression` | `xz` | `gzip`, `lzma`, `lzo`, `lz4`, `xz` or `zstd` |
| `squashfs_compression_level` | unset | mksquashfs compression level |
| `initramfs_compression` | unset | `bzip2`, `gzip` or `lzma` |
| `zsync` | unset | Generate zsync metadata for delta downloads |
| `win32_loader` | unset | Include the legacy win32-loader |

```toml
[binary]
image_type = "iso-hybrid"
squashfs_compression = "zstd"
squashfs_compression_level = 19
checksums = "sha256"
```

`[build] compression` controls archive compression for tar/netboot/source
images; `[binary] squashfs_compression` controls the live filesystem inside
an ISO.

## Command reference

| Command | Description |
| --- | --- |
| `init` | Create a recipe interactively |
| `gen` | Generate the live-build configuration only (**no root needed**) |
| `build` | Build the ISO |
| `validate` | Check the recipe and the environment |
| `show` | Show the recipe and the boot parameters |
| `doctor` | Diagnose the build environment |
| `presets` | List presets, or show one in detail |
| `clean` | Remove build products |
| `shell` | Open a shell in the build chroot |
| `test` | Boot the ISO in QEMU |
| `verify` | Verify the checksum and signature of a distributed ISO |

Common combinations:

```sh
# Skip the questions and start from a preset
frosted init --preset kiosk --name lobby --output lobby.toml

# Generate the settings and read them by hand
frosted gen mylinux.toml
less mylinux.toml.build/auto/config

# Just the boot parameters
frosted show mylinux.toml --bootappend

# The exact arguments passed to lb config
frosted show mylinux.toml --lb-args

# Remove everything, cache included
frosted clean mylinux.toml --all
```

## Presets

| Name | Contents |
| --- | --- |
| `minimal` | Plain console-only Debian. For your first build |
| `rescue` | Disk recovery and diagnostic tools, with SSH |
| `desktop` | Xfce with Firefox and LibreOffice |
| `kiosk` | Autologin straight into a full-screen browser |
| `dev` | A full set of build tools, with SSH |

```sh
frosted presets kiosk     # see what it includes
frosted init --preset kiosk
```

## Desktop environments

| Key | Environment | Rough size | Display manager |
| --- | --- | --- | --- |
| `none` | None (console) | ~350 MB | — |
| `xfce` | Xfce | ~1.2 GB | lightdm |
| `lxqt` | LXQt | ~1.1 GB | sddm |
| `mate` | MATE | ~2.0 GB | lightdm |
| `gnome` | GNOME | ~3.0 GB | gdm3 |
| `kde` | KDE Plasma | ~3.2 GB | sddm |
| `cinnamon` | Cinnamon | ~2.2 GB | lightdm |

Autologin is configured per display manager. With `user.autologin = true` you
get an automatic login in every one of them.

## Distributing an ISO

Shipping an image means more than the image itself: whoever receives it needs to
be able to tell that it really came from you, and what is in it. `build` creates
these next to the ISO:

| File | Contents |
| --- | --- |
| `SHA256SUMS` | The conventional combined format |
| `<ISO name>.sha256` | For handing out on its own |
| `<ISO name>.build-info.json` | A record of what went into it and how |
| `<ISO name>.asc` | Detached GPG signature (only with `--sign`) |

```sh
# Build with a signature
sudo frosted build release.toml --sign you@example.com
```

`build-info.json` contains the recipe hash, the installed packages and their
versions, the options that were actually used, and the ISO's hash and size. It
lets you trace an image back to the exact recipe it came from.

Ship those files alongside the ISO. The person receiving it can then check
everything with one command:

```sh
frosted verify mylinux-1.0-amd64.iso
```

`verify` checks the checksum and the signature, and reports the build metadata.
The result is shown clearly. You can of course also use `sha256sum -c
SHA256SUMS` and `gpg --verify` directly.

### Pre-release checklist

- [ ] `[iso] publisher` and `preparer` set to your name or project
- [ ] `[iso] version` bumped
- [ ] no placeholder left in `user.password`
- [ ] `user.autologin` and `user.sudo` are what you intend
- [ ] `ssh.authorized_keys` contains no one else's keys
- [ ] `frosted test` boots on both BIOS and UEFI
- [ ] signed with `--sign`

## How it works

```
recipe (TOML)
    │
    │  frosted gen
    ▼
<work directory>/
├── auto/config                     ← every option for lb config
├── config/package-lists/*.list.chroot
├── config/includes.chroot/         ← files copied into the image
├── config/hooks/live/*.hook.chroot ← run inside the chroot during the build
└── .frosted-manifest.json          ← list of generated files (used for cleanup)
    │
    │  frosted build
    ▼
   ISO + SHA256SUMS + build-info.json (+ .asc)
```

The resulting tree is in the format live-build understands, so you can also
build it without this tool: `cd <work directory> && sudo lb build`.

### What this tool takes off your hands

- **Building the `lb config` command** — nearly sixty options, derived from the recipe
- **Boot parameters** — `hostname=`, `username=`, `locales=`, `keyboard-layouts=`
  and friends, spelled correctly (these are easy to get wrong)
- **Autologin** — a different file for lightdm, sddm and gdm3
- **Per-user setup at boot** — the live user is created at boot time by
  live-config, so passwords and SSH keys cannot be written at build time. A
  systemd unit is installed to handle them once the system comes up
- **Cleanup** — APT caches, logs and machine-id are removed to keep the image small

### Handling live-build version differences

`lb config` option names have shifted between live-build versions (singular
versus plural, as in `--architecture` and `--architectures`). Before generating
anything, this tool reads `lb config --help` and **picks the spelling your
live-build actually accepts**. `frosted doctor` shows what it found.

That resolution is verified against a real live-build in CI
(`tests/test_lb_integration.py`).

## Persistence

To keep changes on the USB stick, enable it in the recipe:

```toml
[boot]
persistence = true
```

**That alone is not enough.** The stick needs to be prepared as well.

1. Create a partition labelled `persistence` on the USB stick
2. Put a `persistence.conf` at its root

```sh
# Example: /dev/sdb2 is the second partition of the stick
sudo mkfs.ext4 -L persistence /dev/sdb2
sudo mkdir -p /mnt/persist
sudo mount /dev/sdb2 /mnt/persist
echo "/ union" | sudo tee /mnt/persist/persistence.conf
sudo umount /mnt/persist
```

`/ union` means the whole root is saved. You can narrow it, for example to
`/home union`.

## Troubleshooting

### Run `frosted doctor` first

It lists what is missing and how to fix it. Start there.

### The build fails partway through

The full build log is kept in `build.log` in the work directory. It contains the
raw `lb build` output, which usually tells you what happened.

```sh
less <work directory>/build.log
```

### It complains about an invalid option

That is a live-build version difference.

```sh
frosted doctor <recipe>
```

The `lb options` line warns about any setting that will not take effect.

### The second build behaves oddly

live-build can carry over settings from a previous run. Regenerate just the
configuration:

```sh
frosted gen <recipe>      # regenerate the settings
sudo frosted build <recipe>
```

If that does not help, clear the cache as well:

```sh
frosted clean <recipe> --all
```

### It boots but does not log in automatically

Check that the display manager is the one you expected. After a build,
`0200-autologin.hook.chroot` in the output of `frosted gen` shows which file it
tries to write.

On a running system, press Ctrl-Alt-F2 at the login screen to reach a console
and investigate with the user or root password:

```sh
systemctl status frosted-boot-setup
journalctl -u frosted-boot-setup
```

### Writing the USB stick

```sh
sudo dd if=mylinux-1.0-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

**Always double-check that `/dev/sdX` is really your device. The wrong one will
erase everything on it.** Use `lsblk` to confirm before running it.

If you want several ISOs on one stick, [Ventoy](https://www.ventoy.net/) is a
good option.

## Contributing

There are no runtime dependencies. Python 3.11 or newer is all you need.

```sh
git clone https://github.com/Keychrom/Frosted-ISO-Builder
cd Frosted-ISO-Builder

# Tests (standard library unittest only)
python3 -m unittest discover -s tests -t . -v

# Run without installing
python3 bin/frosted --help
```

### Layout

| Path | Role |
| --- | --- |
| `frosted/recipe.py` | The recipe model and validation. The single source of truth |
| `frosted/catalog.py` | Desktop environments and presets. Adding one means touching only this file |
| `frosted/backend/livebuild.py` | Recipe to live-build tree. The core of the tool |
| `frosted/preflight.py` | Pre-build environment checks |
| `frosted/release.py` | Checksums, build metadata and signing |
| `frosted/wizard.py` | The interactive wizard |
| `frosted/i18n.py`, `i18n_en.py` | UI translation. Japanese source strings are the keys |
| `frosted/cli.py` | The command line |

### Things to be careful about

- **Always write generated files with LF endings.** CRLF makes shell scripts
  fail on Linux with `bad header: /bin/sh^M` (see `newline="\n"` in `_write_file`).
- **Never drop `noauto` from `auto/config`.** Without it live-build recurses.
- **Do not generate `auto/build` or `auto/clean`.** live-build calls `auto/`
  scripts automatically, so calling `lb build` from inside one risks recursion.
- **If you add a recipe setting, test that it reaches the output.**
  `RecipeKnobsReachTheOutputTest` exists for exactly that.
- **Do not hardcode `lb config` option names.** Add a candidate to
  `OPTION_ALIASES` and the right spelling is selected at runtime.
- **Add UI text to the catalog.** `tests/test_i18n.py` runs the CLI in English
  and fails if any Japanese is left in the output.

## Verification status

Being straight with you.

**Verified (the automated test suite plus CI)**

- Reading, writing and validating recipes, including rejecting bad input and
  round-tripping TOML
- The contents of the generated live-build tree
- The syntax of every generated shell script, parsed with `sh -n`
- Execution of `auto/config` against a stub `lb`, checking that arguments and
  their quoting survive intact
- That generated files use LF endings
- Checksum and build metadata generation, and detection of corruption
- Tree generation for every preset and every desktop environment
- **That a real live-build accepts the generated configuration** (the CI
  `live-build` job feeds it to `lb config`)
- That the English UI contains no leftover Japanese

**Not verified**

- **A real ISO build has never been run.** `sudo frosted build` has not yet been
  executed on a Debian machine.
- Booting a built ISO
- Autologin, SSH key deployment and password setting on real hardware. The
  boot-time systemd unit has only been checked as far as it being installed.

Do your first build with [`examples/minimal.toml`](examples/minimal.toml). Once
that works, the rest is adding packages and a desktop environment.

If something goes wrong, `build.log` and the output of `frosted doctor` will
usually tell you why.

## License

[MIT](LICENSE)
