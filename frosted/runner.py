"""外部コマンドの実行。

ライブビルドは数十分かかるので、進捗が流れていくのが見えることと、
あとから原因を追えるようにログが残ることが大事。ここでは
「画面に流しつつファイルにも書く」を 1 か所にまとめている。
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from .errors import BuildError


def which(name: str) -> str | None:
    return shutil.which(name)


def is_root() -> bool:
    """root 権限で動いているか。

    geteuid が無い環境 (Windows) では False を返す。
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return False
    return geteuid() == 0


def format_command(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def privileged(cmd: Sequence[str]) -> list[str]:
    """必要なら sudo を前置する。

    live-build は root で動かす必要がある。すでに root なら何もしない。
    """
    if is_root():
        return list(cmd)
    sudo = which("sudo")
    if sudo is None:
        raise BuildError(
            "root 権限が必要ですが sudo が見つかりません。",
            hint="root でログインし直すか、sudo をインストールしてください。",
        )
    return [sudo, "-E", *cmd]


def run_capture(
    cmd: Sequence[str], cwd: Path | None = None, timeout: int = 60
) -> tuple[int, str]:
    """出力をまとめて受け取る。プリフライトのような短い確認用。"""
    try:
        proc = subprocess.run(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError as exc:
        return 126, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def run_streaming(
    cmd: Sequence[str],
    cwd: Path | None = None,
    log_path: Path | None = None,
    env: dict[str, str] | None = None,
    echo: bool = True,
) -> int:
    """コマンドを実行し、出力を画面とログの両方に流す。

    Ctrl-C を受けたら子プロセスにも SIGINT を送ってから中断する。
    ビルド途中で投げ出すと live-build のマウントが残ることがあるため、
    子プロセスにきちんと後片付けをさせるのが狙い。
    """
    child_env = dict(os.environ)
    if env:
        child_env.update(env)
    # live-build の出力はパイプだと色を出さないので、素直にそのまま流す
    child_env.setdefault("LC_ALL", child_env.get("LC_ALL", "C.UTF-8"))

    if echo:
        print(f"    $ {format_command(cmd)}", flush=True)

    log_file = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("w", encoding="utf-8", errors="replace")
        log_file.write(f"$ {format_command(cmd)}\n\n")
        log_file.flush()

    try:
        process = subprocess.Popen(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            env=child_env,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        if log_file:
            log_file.close()
        raise BuildError(
            f"コマンドが見つかりません: {cmd[0]}",
            hint="live-build 一式がインストールされているか確認してください。"
            " `frosted doctor` で診断できます。",
        ) from exc
    except OSError as exc:
        if log_file:
            log_file.close()
        raise BuildError(f"コマンドを実行できません: {exc}") from exc

    try:
        assert process.stdout is not None
        for line in process.stdout:
            if echo:
                sys.stdout.write(line)
                sys.stdout.flush()
            if log_file:
                log_file.write(line)
        process.stdout.close()
        return_code = process.wait()
    except KeyboardInterrupt:
        _interrupt_child(process)
        raise
    finally:
        if log_file:
            log_file.flush()
            log_file.close()

    return return_code


def _interrupt_child(process: subprocess.Popen[str]) -> None:
    """子プロセス (とその子孫) に SIGINT を送って片付ける。"""
    if process.poll() is not None:
        return
    sigint = getattr(signal, "SIGINT", None)
    if sigint is None:
        process.terminate()
        return
    killpg = getattr(os, "killpg", None)
    getpgid = getattr(os, "getpgid", None)
    try:
        if killpg is not None and getpgid is not None:
            killpg(getpgid(process.pid), sigint)
        else:
            process.send_signal(sigint)
    except (OSError, ProcessLookupError):
        try:
            process.terminate()
        except OSError:
            return
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()


def tail_file(path: Path, lines: int = 30) -> str:
    """ログの末尾だけを拾う。エラー表示に添えるのに使う。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    collected = text.splitlines()[-lines:]
    return "\n".join(collected)
