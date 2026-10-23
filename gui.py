import json
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

import book
import get_token

CONFIG_PATH = book.CONFIG_PATH
TOKEN_PATH = book.TOKEN_PATH


def time_options():
    """生成 08:00 到 23:00 每 5 分钟一个的时间选项。"""
    opts = []
    for total in range(8 * 60, 23 * 60 + 1, 5):
        h, m = divmod(total, 60)
        opts.append(f"{h:02d}:{m:02d}")
    return opts


WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


class App:
    def __init__(self, root):
        self.root = root
        self.msg_queue = queue.Queue()
        self.login_running = False
        self.booking_running = False
        self.time_values = time_options()

        root.title("南开大学津南中心馆单人研读间预约")
        root.geometry("1000x1200")
        root.minsize(720, 760)
        root.resizable(True, True)

        self.configure_styles()
        root.configure(bg=self.C_BG)

        self.build_header()
        self.build_tip_bar()
        self.build_login_frame()
        self.build_config_frame()
        self.build_booking_frame()

        self.refresh_token_status()
        self.load_config_into_ui()
        self.update_tip()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.drain_queue)
        self.root.after(30000, self.periodic_token_refresh)

    # ---------- 样式 ----------
    def configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # 配色
        self.C_BG = "#eef1f6"        # 窗口底色
        self.C_CARD = "#ffffff"      # 卡片底色
        self.C_PRIMARY = "#711a5f"   # 主色
        self.C_PRIMARY_HOVER = "#711a5f"
        self.C_PRIMARY_DISABLED = "#a9bce0"
        self.C_BORDER = "#d7dde8"
        self.C_TEXT = "#232a35"
        self.C_MUTED = "#6b7480"
        self.C_TIP_BG = "#fff3d1"
        self.C_TIP_FG = "#8a6a12"
        self.C_HEADER = "#711a5f"

        # 字体
        self.F_BODY = ("Microsoft YaHei UI", 10)
        self.F_BOLD = ("Microsoft YaHei UI", 10, "bold")
        self.F_TITLE = ("Microsoft YaHei UI", 16, "bold")
        self.F_SUB = ("Microsoft YaHei UI", 9)
        self.F_MONO = ("Consolas", 10)

        style.configure(".", background=self.C_BG, foreground=self.C_TEXT, font=self.F_BODY)
        style.configure("TFrame", background=self.C_BG)

        # 卡片式分区
        style.configure("Card.TLabelframe", background=self.C_CARD, bordercolor=self.C_BORDER,
                        relief="solid", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background=self.C_CARD, foreground=self.C_PRIMARY,
                        font=self.F_BOLD)

        style.configure("Card.TLabel", background=self.C_CARD, foreground=self.C_TEXT, font=self.F_BODY)
        style.configure("Card.Muted.TLabel", background=self.C_CARD, foreground=self.C_MUTED,
                        font=self.F_BODY)
        style.configure("Card.TRadiobutton", background=self.C_CARD, foreground=self.C_TEXT,
                        font=self.F_BODY)

        # 输入框 / 下拉框
        style.configure("TEntry", padding=6, fieldbackground="#ffffff", bordercolor=self.C_BORDER,
                        lightcolor=self.C_BORDER, darkcolor=self.C_BORDER)
        style.configure("TCombobox", padding=4, fieldbackground="#ffffff", bordercolor=self.C_BORDER,
                        lightcolor=self.C_BORDER, darkcolor=self.C_BORDER, arrowsize=14)

        # 普通按钮
        style.configure("TButton", font=self.F_BODY, padding=(14, 6), background="#e6eaf1",
                        foreground=self.C_TEXT, bordercolor=self.C_BORDER)
        style.map("TButton", background=[("active", "#d9dfeb")])

        # 主按钮（强调色）
        style.configure("Accent.TButton", background=self.C_PRIMARY, foreground="#ffffff",
                        font=self.F_BOLD, padding=(20, 8), borderwidth=0, bordercolor=self.C_PRIMARY)
        style.map("Accent.TButton",
                  background=[("active", self.C_PRIMARY_HOVER), ("disabled", self.C_PRIMARY_DISABLED)],
                  foreground=[("disabled", "#eef1fb")])

    # ---------- 界面构建 ----------
    def build_header(self):
        h = tk.Frame(self.root, bg=self.C_HEADER)
        h.pack(fill="x")
        tk.Label(h, text="南开大学津南中心馆 · 单人研读间预约",
                 bg=self.C_HEADER, fg="#ffffff", font=self.F_TITLE, anchor="w").pack(
            anchor="w", padx=20, pady=(14, 0))
        tk.Label(h, text="每晚 22:00 开放次日预约 · 请先登录，再配置时段，最后发起预约",
                 bg=self.C_HEADER, fg="#c9d9f5", font=self.F_SUB, anchor="w").pack(
            anchor="w", padx=20, pady=(2, 12))

    def build_tip_bar(self):
        self.tip_var = tk.StringVar()
        self.tip_label = tk.Label(
            self.root, textvariable=self.tip_var, bg=self.C_TIP_BG, fg=self.C_TIP_FG,
            font=self.F_BODY, justify="left", anchor="w", padx=14, pady=8,
        )
        self.tip_label.pack(fill="x", padx=16, pady=(12, 0))
        self.tip_label.bind("<Configure>", self._on_tip_resize)

    def _on_tip_resize(self, event):
        # 减去标签的左右内边距，避免换行宽度超过可视区、右边被裁切
        if event.width > 1:
            self.tip_label.configure(wraplength=max(50, event.width - 32))

    def build_login_frame(self):
        f = ttk.LabelFrame(self.root, text="① 登录（获取 token）", padding=14,
                           style="Card.TLabelframe")
        f.pack(fill="x", padx=16, pady=(12, 8))

        self.login_btn_chrome = ttk.Button(f, text="登录（Chrome）", style="Accent.TButton",
                                           command=lambda: self.on_login("chrome"))
        self.login_btn_chrome.pack(side="left")

        self.login_btn_edge = ttk.Button(f, text="登录（Edge）", style="Accent.TButton",
                                         command=lambda: self.on_login("edge"))
        self.login_btn_edge.pack(side="left", padx=(8, 0))

        self.login_buttons = [self.login_btn_chrome, self.login_btn_edge]

        self.token_status_var = tk.StringVar(value="...")
        ttk.Label(f, textvariable=self.token_status_var, style="Card.Muted.TLabel").pack(
            side="left", padx=14)

    def build_config_frame(self):
        f = ttk.LabelFrame(self.root, text="② 配置（房间与时段）", padding=14,
                           style="Card.TLabelframe")
        f.pack(fill="x", padx=16, pady=8)
        f.columnconfigure(1, weight=1, uniform="half")
        f.columnconfigure(3, weight=1, uniform="half")

        ttk.Label(f, text="房间名：", style="Card.TLabel").grid(row=0, column=0, sticky="e", pady=6)
        self.room_name_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.room_name_var).grid(row=0, column=1, sticky="we", padx=(8, 28))

        ttk.Label(f, text="房间号：", style="Card.TLabel").grid(row=1, column=0, sticky="e", pady=6)
        self.room_id_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.room_id_var).grid(row=1, column=1, sticky="we", padx=(8, 28))

        ttk.Label(f, text="开始时间：", style="Card.TLabel").grid(row=0, column=2, sticky="e", pady=6)
        self.begin_var = tk.StringVar()
        self.begin_combo = ttk.Combobox(f, textvariable=self.begin_var, values=self.time_values,
                                        state="readonly", width=9)
        self.begin_combo.grid(row=0, column=3, sticky="w", padx=(8, 0))

        ttk.Label(f, text="结束时间：", style="Card.TLabel").grid(row=1, column=2, sticky="e", pady=6)
        self.end_var = tk.StringVar()
        self.end_combo = ttk.Combobox(f, textvariable=self.end_var, values=self.time_values,
                                      state="readonly", width=9)
        self.end_combo.grid(row=1, column=3, sticky="w", padx=(8, 0))

        ttk.Button(f, text="确定（保存配置）", command=self.on_save_config,
                   style="Accent.TButton").grid(row=2, column=0, columnspan=4, pady=(14, 2))

    def build_booking_frame(self):
        f = ttk.LabelFrame(self.root, text="③ 预约", padding=14, style="Card.TLabelframe")
        f.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        self.mode_var = tk.StringVar(value="tomorrow")
        ttk.Radiobutton(f, text="明天（今晚 22:00 准时预约）", variable=self.mode_var,
                        value="tomorrow", style="Card.TRadiobutton").pack(anchor="w")
        ttk.Radiobutton(f, text="今天（立即预约）", variable=self.mode_var,
                        value="today", style="Card.TRadiobutton").pack(anchor="w")

        self.booking_btn = ttk.Button(f, text="开始预约", command=self.on_book,
                                      style="Accent.TButton")
        self.booking_btn.pack(anchor="w", pady=8)

        self.log_text = scrolledtext.ScrolledText(
            f, height=44, state="disabled", font=self.F_MONO,
            background="#f7f9fc", foreground="#26303c", insertbackground="#26303c",
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=self.C_BORDER, highlightcolor=self.C_BORDER,
            padx=8, pady=6,
        )
        self.log_text.pack(fill="both", expand=True)

    # ---------- 辅助 ----------
    def append_log(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {text}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def refresh_token_status(self):
        try:
            token, exp = book.load_token()
        except Exception:
            self.token_status_var.set("未登录（还没有有效的 token）")
            return
        if exp < time.time():
            self.token_status_var.set("token 已过期，请重新登录")
        else:
            self.token_status_var.set(f"token 有效，剩余约 {int(exp - time.time()) // 60} 分钟")

    def load_config_into_ui(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                cfg = json.load(f)
        except Exception:
            return
        self.room_name_var.set(cfg.get("room_name", ""))
        self.room_id_var.set(str(cfg.get("room_id", "")))
        begin = str(cfg.get("begin", ""))
        end = str(cfg.get("end", ""))
        if begin in self.time_values:
            self.begin_var.set(begin)
        if end in self.time_values:
            self.end_var.set(end)

    def update_tip(self):
        now = datetime.now()
        wd = WEEKDAYS[now.weekday()]
        self.tip_var.set(
            f"温馨提示：现在是 {now.year} 年 {now.month} 月 {now.day} 日 {now.strftime('%H:%M')} {wd}。\n"
            f"周六图书馆闭馆时间通常为 17:00，其余时间闭馆时间通常为 23:00，请确保开始时间和结束时间位于开馆时间内，防止预约失败。"
        )

    def periodic_token_refresh(self):
        self.update_tip()
        if not self.login_running:
            self.refresh_token_status()
        self.root.after(30000, self.periodic_token_refresh)

    # ---------- 事件 ----------
    def on_login(self, browser="chrome"):
        if self.login_running:
            return
        self.login_running = True
        for btn in self.login_buttons:
            btn.config(state="disabled")
        name = "Edge" if browser == "edge" else "Chrome"
        self.append_log(f"开始获取 token（{name}），请在弹出的浏览器窗口中手动登录 ...")

        def worker():
            try:
                get_token.fetch_token(log_fn=lambda m: self.msg_queue.put(("log", m)),
                                      browser=browser)
                self.msg_queue.put(("login_ok", None))
            except Exception as e:
                self.msg_queue.put(("log", f"[错误] {e}"))
            finally:
                self.msg_queue.put(("login_done", None))

        threading.Thread(target=worker, daemon=True).start()

    def on_save_config(self):
        room_name = self.room_name_var.get().strip()
        room_id = self.room_id_var.get().strip()
        begin = self.begin_var.get()
        end = self.end_var.get()

        if not room_id:
            messagebox.showwarning("提示", "房间号(room_id)不能为空。")
            return
        if not begin or not end:
            messagebox.showwarning("提示", "请选择开始时间和结束时间。")
            return
        if begin >= end:
            messagebox.showwarning("提示", "开始时间必须早于结束时间。")
            return

        try:
            with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

        cfg["room_name"] = room_name
        cfg["room_id"] = room_id
        cfg["begin"] = begin
        cfg["end"] = end

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        self.append_log("配置已保存：")
        self.append_log(f"  房间名 = {room_name}")
        self.append_log(f"  房间号 = {room_id}")
        self.append_log(f"  时段 = {begin} - {end}")
        messagebox.showinfo("提示", "配置已保存。")

    def on_book(self):
        if self.booking_running:
            return
        mode = self.mode_var.get()
        self.booking_running = True
        self.booking_btn.config(state="disabled")
        self.append_log(f"开始预约：{'明天（等待 22:00）' if mode == 'tomorrow' else '今天（立即）'}")

        def worker():
            try:
                book.book_room(mode, log_fn=lambda m: self.msg_queue.put(("log", m)))
            except book.Fatal as e:
                self.msg_queue.put(("log", f"[错误] {e}"))
            except Exception as e:
                self.msg_queue.put(("log", f"[未预期的错误] {type(e).__name__}: {e}"))
            finally:
                self.msg_queue.put(("booking_done", None))

        threading.Thread(target=worker, daemon=True).start()

    def drain_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.append_log(str(payload))
                elif kind == "login_ok":
                    self.append_log("token 已保存。")
                    self.refresh_token_status()
                elif kind == "login_done":
                    self.login_running = False
                    for btn in self.login_buttons:
                        btn.config(state="normal")
                    self.refresh_token_status()
                elif kind == "booking_done":
                    self.booking_running = False
                    self.booking_btn.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self.drain_queue)

    def on_close(self):
        if self.login_running or self.booking_running:
            if not messagebox.askokcancel("退出", "仍有任务在运行（登录或预约），确定要退出吗？"):
                return
        self.root.destroy()


def enable_dpi_awareness():
    """Windows 高分屏下开启 DPI 感知，避免 tkinter 界面被位图拉伸而字体模糊。"""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
