import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests

BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "token.txt")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

BASE = "https://libroom.nankai.edu.cn/spa/static/api/book"
OPEN_HOUR = 22          # 每天 22:00 开放明天
RETRY_INTERVAL = 0.5    # 秒
MAX_FAILS = 10          # 连续失败多少次后退出
TIMEOUT = 5


class Fatal(Exception):
    pass


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}", flush=True)


def to_minutes(hhmm):
    try:
        h, m = hhmm.strip().split(":")
        h, m = int(h), int(m)
        if not (0 <= h <= 24 and 0 <= m < 60):
            raise ValueError
        return h * 60 + m
    except ValueError:
        raise Fatal(f"config.json 中的时间格式不对：{hhmm!r}，应写成 09:00 这种形式")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise Fatal("找不到 config.json，请确认它和本程序在同一个文件夹里。")
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        raise Fatal(f"config.json 格式有误（检查引号、逗号）：{e}")
    for k in ("room_id", "use_type", "begin", "end"):
        if not cfg.get(k):
            raise Fatal(f"config.json 缺少 {k}")
    cfg["room_id"] = str(cfg["room_id"])
    cfg["use_type"] = str(cfg["use_type"])
    cfg["begin_min"] = to_minutes(cfg["begin"])
    cfg["end_min"] = to_minutes(cfg["end"])
    if cfg["begin_min"] >= cfg["end_min"]:
        raise Fatal("config.json 中开始时间必须早于结束时间")
    return cfg


def load_token():
    if not os.path.exists(TOKEN_PATH):
        raise Fatal("找不到 token.txt，请先运行 login.exe 或者 get_token.py 并登录。")
    with open(TOKEN_PATH, encoding="utf-8") as f:
        token = f.read().strip()
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
    except Exception:
        raise Fatal("token.txt 内容不正确，请重新运行 login.exe 或者 get_token.py。")
    return token, exp

def confirm_enter():
    print("欢迎使用津南中心馆单人研读间预约系统。")
    print("是否开始使用？")
    print("  1. 是")
    print("  2. 否")
    while True:
        s = input("请输入 1 或 2：").strip()
        if s == "1":
            print()
            return True
        if s == "2":
            return False
        print("输入有误，请重新输入。")

def choose_date():
    print("请选择预定日期：")
    print("  1. 明天（等到 22:00 准点抢约，直接回车默认选这个）")
    print("  2. 今天（立即预定）")
    while True:
        s = input("请输入 1 或 2：").strip()
        if s in ("", "1"):
            return "tomorrow"
        if s == "2":
            return "today"
        print("输入有误，请重新输入。")


def main():
    if not confirm_enter():
        print("已退出。")
        return

    cfg = load_config()
    token, exp = load_token()
    mode = choose_date()

    now = datetime.now()
    target = now.replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)
    need_wait = mode == "tomorrow" and now < target
    on_date = (now + timedelta(days=1 if mode == "tomorrow" else 0)).strftime("%Y-%m-%d")

    # token 检查
    if exp < time.time():
        raise Fatal("token 已过期（有效期仅 2 小时），请重新运行 login.exe 或者 get_token.py 并登录。")
    if need_wait and exp < target.timestamp() + 60:
        raise Fatal("token 会在 22:00 之前过期，请在 21:30 之后重新运行“获取token”。")
    log(f"token 剩余有效时间：{int(exp - time.time()) // 60} 分钟")

    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Authorization": token,
        "Content-Type": "application/json",
        "Origin": "https://libroom.nankai.edu.cn",
        "Referer": "https://libroom.nankai.edu.cn/spa-v/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    })

    # 预检：验证 token 和房间
    try:
        r = session.post(
            f"{BASE}/getRoomDtoByRoomIdAndDate",
            json={"roomId": cfg["room_id"], "selectDate": now.strftime("%Y-%m-%d"), "seatNo": ""},
            timeout=TIMEOUT,
        )
        d = r.json()
    except Exception as e:
        raise Fatal(f"无法连接图书馆系统，请确认已连接校园网：{e}")
    if not d.get("status"):
        raise Fatal(f"预检失败（token 可能无效，或房间号有误）：{d.get('message')}")
    log(f"预检通过，房间：{d['data'].get('name')}")
    log(f"目标：{on_date}  {cfg['begin']} - {cfg['end']}")

    # 等待 22:00
    if need_wait:
        log("等待至 22:00:00，请保持电脑不休眠、不要关闭本窗口 ...")
        while True:
            remaining = target.timestamp() - time.time()
            if remaining <= 0:
                break
            time.sleep(min(remaining - 1, 30) if remaining > 1 else 0.001)

    body = {
        "begin": cfg["begin_min"], "end": cfg["end_min"], "onDate": on_date,
        "roomId": cfg["room_id"], "useType": cfg["use_type"],
        "participants": "", "filePath": "", "source": "WEB",
        "seatNo": 0, "teamId": 0, "theme": "", "extraField": {},
        "batchUserDto": {"classCodes": "", "depCodes": "", "usernames": ""},
    }
    log("开始预定 ...")

    fails = 0
    last_msg = ""
    while fails < MAX_FAILS:
        try:
            r = session.post(f"{BASE}/saveReservation", json=body, timeout=TIMEOUT)
            d = r.json()
        except requests.RequestException as e:
            fails += 1
            last_msg = f"网络异常：{e}"
            log(f"第 {fails}/{MAX_FAILS} 次失败：{last_msg}")
            time.sleep(RETRY_INTERVAL)
            continue
        except ValueError:
            fails += 1
            last_msg = f"服务器返回内容异常：HTTP {r.status_code}"
            log(f"第 {fails}/{MAX_FAILS} 次失败：{last_msg}")
            time.sleep(RETRY_INTERVAL)
            continue

        msg = str(d.get("message", ""))
        if d.get("status"):
            log(f"预定成功！{msg}")
            print("\n提示：如果不需要这个预约，请及时到网站手动取消，以免影响信用分。")
            return

        fails += 1
        last_msg = f"{msg}（code={d.get('code')}）"
        log(f"第 {fails}/{MAX_FAILS} 次失败：{last_msg}")
        time.sleep(RETRY_INTERVAL)

    raise Fatal(f"连续 {MAX_FAILS} 次失败，已停止。最后一次原因：{last_msg}\n"
                "若中途出现过网络异常，请到网站确认是否其实已经预定成功。")


def run():
    try:
        main()
    except Fatal as e:
        print(f"\n[错误] {e}")
    except KeyboardInterrupt:
        print("\n已手动终止")
    except Exception as e:
        print(f"\n[未预期的错误] {type(e).__name__}: {e}")
    input("\n按回车键退出...")


if __name__ == "__main__":
    run()