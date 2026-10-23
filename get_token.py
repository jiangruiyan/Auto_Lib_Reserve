import os
import sys

from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "token.txt")
LIB = "https://libroom.nankai.edu.cn"
WAIT_SECONDS = 300


class Fatal(Exception):
    pass


def main():
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
            browser = p.chromium.launch(channel="chrome", headless=False)
        except Exception as e:
            raise Fatal(f"无法启动 Chrome，请确认已安装谷歌浏览器。\n详细信息：{e}")

        page = browser.new_context().new_page()
        page.on("response", on_response)
        try:
            page.goto(LIB, timeout=30000)
        except Exception as e:
            browser.close()
            raise Fatal(f"打开网站失败，请确认连接了校园网。\n详细信息：{e}")

        print("请在弹出的 Chrome 窗口里输入学号和密码登录（最多等待 5 分钟）...")
        for _ in range(WAIT_SECONDS):
            if "token" in result:
                break
            try:
                page.wait_for_timeout(1000)
            except Exception:
                break  # 用户手动关闭了窗口
        try:
            browser.close()
        except Exception:
            pass

    if "token" not in result:
        raise Fatal("没有获取到 token（超时或窗口被提前关闭），请重新运行。")

    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(result["token"])
    print("\n成功！token 已保存，有效期 2 小时。现在可以运行“预定房间”了。")


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