"""Play TTS audio on N1 device via SSH — uses ssh_tool for connection reuse."""
from __future__ import annotations

import asyncio
import logging
import os

from app.services.ssh_tool import get_ssh_tool, SSHConnectionError, SSHAuthError

logger = logging.getLogger(__name__)

N1_AUDIO_DIR = "/tmp/phone_tts"


async def play_on_device(device_ip: str, local_audio_path: str) -> None:
    ssh = get_ssh_tool()
    remote_path = f"{N1_AUDIO_DIR}/{os.path.basename(local_audio_path)}"
    is_mp3 = local_audio_path.endswith(".mp3")

    try:
        conn = await ssh._get_connection(device_ip)

        # 合并setup命令为一次SSH调用：mkdir + pulseaudio + 检测输出
        setup_script = (
            f"mkdir -p {N1_AUDIO_DIR} && "
            "(pgrep -x pulseaudio > /dev/null 2>&1 || "
            "(pulseaudio --start 2>/dev/null || pulseaudio -D --fail=quiet 2>/dev/null)) && "
            "sleep 0.3 && "
            "pactl list sinks short 2>/dev/null | grep bluez | head -1 | awk '{print $2}'"
        )
        r_setup = await conn.run(setup_script, check=False, timeout=8)
        sink_name = (r_setup.stdout or "").strip() if r_setup.exit_status == 0 else ""

        # SCP传音频文件
        import asyncssh
        await asyncssh.scp(local_audio_path, (conn, remote_path), timeout=10)

        # 设置蓝牙_sink + 播放
        if sink_name:
            await conn.run(
                f"pactl set-default-sink {sink_name} && pactl set-sink-volume @DEFAULT_SINK@ 75%",
                check=False, timeout=3,
            )

        if is_mp3:
            cmd = f"mpg123 -o pulse -q '{remote_path}' 2>/dev/null || ffplay -nodisp -autoexit -loglevel quiet '{remote_path}'"
        else:
            cmd = f"paplay '{remote_path}' 2>/dev/null || aplay -q '{remote_path}'"

        result = await conn.run(cmd, check=False, timeout=30)
        if result.exit_status == 0:
            logger.info("N1 audio played on %s", device_ip)
        else:
            stderr = result.stderr.strip() if result.stderr else ""
            logger.warning("N1 player exit=%d stderr=%s", result.exit_status, stderr[:200])

        await conn.run(f"rm -f '{remote_path}'", check=False)
    except SSHAuthError as e:
        logger.error("N1 SSH auth failed to %s: %s", device_ip, e)
    except SSHConnectionError as e:
        logger.warning("N1 SSH connection issue to %s: %s", device_ip, e)
    except Exception as e:
        logger.error("N1 play_on_device error (%s): %s", device_ip, e)
