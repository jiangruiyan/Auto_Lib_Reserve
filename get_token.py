import os
import sys

from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "token.txt")
LIB = "https://libroom.nankai.edu.cn"
WAIT_SECONDS = 300

# 支持的浏览器：channel 是 Playwright 调用本机已装浏览器所用的通道名
BROWSERS = {
    "chrome": {"channel": "chrome", "name": "Chrome"},
    "edge": {"channel": "msedge", "name": "Edge"},
}


class Fatal(Exception):
    pass


def fetch_token(log_fn=print, browser="chrome"):
    """运行浏览器登录流程，获取并保存 token，返回 token 字符串。

    browser 可选 'chrome'（谷歌浏览器）或 'edge'（Edge 浏览器）。
    """
    spec = BROWSERS.get(browser) or BROWSERS["chrome"]
    channel = spec["channel"]
    name = spec["name"]

    result = {}

    def on_response(resp):
        if "remoteCasLogin" in resp.url and resp.status == 200:
            try:
                d = resp.json()
                if d.get("status"):
                    result["token"] = d["data"]["token"]
            except Exception:
                pass

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel=channel, headless=False)
        except Exception as e:
            raise Fatal(f"无法启动 {name}，请确认已安装 {name} 浏览器。\n详细信息：{e}")

        page = b.new_context().new_page()
        page.on("response", on_response)
        try:
            page.goto(LIB, timeout=30000)
        except Exception as e:
            b.close()
            raise Fatal(f"打开网站失败，请确认连接了校园网。\n详细信息：{e}")

        log_fn(f"请在弹出的 {name} 窗口里输入学号和密码登录（最多等待 5 分钟）...")
        for _ in range(WAIT_SECONDS):
            if "token" in result:
                break
            try:
                page.wait_for_timeout(1000)
            except Exception:
                break  # 用户手动关闭了窗口
        try:
            b.close()
        except Exception:
            pass

    if "token" not in result:
        raise Fatal("没有获取到 token（超时或窗口被提前关闭），请重新运行。")

    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(result["token"])
    log_fn("成功！token 已保存，有效期 2 小时。现在可以预约了。")
    return result["token"]


def main():
    fetch_token()


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
