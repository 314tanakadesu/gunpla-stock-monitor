"""PC-only monitor window: run while the PC is awake, no extra packages."""
import argparse
import json
import queue
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from monitor import PRODUCT, URL, parse_amazon, notification_due

BASE = Path(__file__).resolve().parent
STATE = BASE / '.pc-monitor-state.json'
STATUS = BASE / 'pc-status.json'
INTERVAL_MS = 300_000


def check_local():
    """Use the Windows HTTP client that was verified on this PC."""
    bundled = Path(sys.executable).parent.parent / 'native' / 'powershell' / 'pwsh.exe'
    shell = str(bundled) if bundled.is_file() else (shutil.which('pwsh') or shutil.which('powershell'))
    if not shell:
        return dict(status='確認失敗', detail='Windows PowerShellが見つかりません', eligible=False)
    command = "$ErrorActionPreference='Stop'; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.amazon.co.jp/dp/B0H32PBNFR' -OutFile $env:GUNPLA_PAGE_PATH -TimeoutSec 30 -Headers @{'User-Agent'='Mozilla/5.0';'Accept-Language'='ja-JP,ja;q=0.9'}"
    import os
    with tempfile.TemporaryDirectory(prefix='gunpla-') as directory:
        page = Path(directory) / 'page.html'
        env = dict(os.environ, GUNPLA_PAGE_PATH=str(page))
        try:
            response = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', command],
                                      env=env, capture_output=True, timeout=40,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            if response.returncode != 0 or not page.is_file():
                return dict(status='確認失敗', detail='Windowsの通信処理に失敗しました。次回再確認します', eligible=False)
            return parse_amazon(page.read_text(encoding='utf-8', errors='replace'))
        except (OSError, subprocess.TimeoutExpired):
            return dict(status='確認失敗', detail='通信が完了しませんでした。次回再確認します', eligible=False)


class App:
    def __init__(self, root, fetch=check_local, persist=True):
        self.root, self.fetch = root, fetch
        self.persist = persist
        self.inbox = queue.Queue()
        self.busy = False
        self.timer = None
        self.closed = False
        self.alert = None
        self.root.title('ガンプラ在庫モニター')
        self.root.geometry('760x550')
        self.root.minsize(660, 500)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=PRODUCT, font=('Yu Gothic UI', 17, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='販売元を問わず、送料込み3,190円以下。予約も対象。').pack(anchor='w', pady=(8, 16))
        self.status = tk.StringVar(value='確認を開始しています…')
        ttk.Label(frame, textvariable=self.status, font=('Yu Gothic UI', 15, 'bold')).pack(anchor='w')
        self.detail = tk.StringVar()
        ttk.Label(frame, textvariable=self.detail, wraplength=690).pack(anchor='w', pady=10)
        self.values = {}
        grid = ttk.Frame(frame)
        grid.pack(fill='x')
        for row, (label, key) in enumerate([('商品価格', 'price'), ('送料', 'shipping'), ('合計', 'total'),
                                          ('販売元', 'seller'), ('購入・予約状況', 'availability'),
                                          ('確認日時（日本時間）', 'checked_at')]):
            ttk.Label(grid, text=label, width=24).grid(row=row, column=0, sticky='nw', pady=5)
            self.values[key] = tk.StringVar(value='未確認')
            ttk.Label(grid, textvariable=self.values[key], wraplength=450).grid(row=row, column=1, sticky='w')
        self.next_check = tk.StringVar(value='5分間隔で自動確認')
        ttk.Label(frame, textvariable=self.next_check).pack(anchor='w', pady=12)
        buttons = ttk.Frame(frame)
        buttons.pack(anchor='w')
        self.button = ttk.Button(buttons, text='今すぐ確認', command=self.start)
        self.button.pack(side='left')
        ttk.Button(buttons, text='Amazonで確認', command=lambda: webbrowser.open(URL)).pack(side='left', padx=12)
        ttk.Label(frame, text='条件に合う新規入荷は音と通知ウィンドウでお知らせします。\nこのウィンドウを閉じると監視終了。最小化中は継続します。\nPCの電源オフ・スリープ中は確認できません。他の出品一覧は対象外です。',
                  wraplength=690).pack(anchor='w', pady=(18, 0))
        try:
            self.previous = json.loads(STATE.read_text(encoding='utf-8'))
            if not isinstance(self.previous, dict):
                self.previous = {}
        except (OSError, ValueError):
            self.previous = {}
        self.root.after(100, self.poll)
        self.start()

    def start(self):
        if self.busy or self.closed:
            return
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.busy = True
        self.button.configure(state='disabled')
        self.next_check.set('Amazonを確認しています…')
        def worker():
            try:
                result = self.fetch()
            except Exception as error:
                result = dict(status='確認失敗', detail=f'処理エラー: {type(error).__name__}', eligible=False)
            self.inbox.put(result)
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        if self.closed:
            return
        try:
            result = self.inbox.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.button.configure(state='normal')
            result['checked_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
            self.status.set(result['status'])
            self.detail.set(result['detail'])
            for key, variable in self.values.items():
                value = result.get(key)
                variable.set(f'{value:,}円' if key in {'price', 'shipping', 'total'} and value is not None else str(value or '未確認'))
            due, state = notification_due(result, self.previous)
            try:
                if self.persist:
                    STATUS.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                    STATE.write_text(json.dumps(state), encoding='utf-8')
                self.previous = state
            except OSError:
                self.detail.set(result['detail'] + '（履歴保存に失敗。重複通知の可能性があります）')
            if due:
                self.show_alert(result)
            self.next_check.set('次の確認：5分後（PC起動中・スリープ解除中）')
            self.timer = self.root.after(INTERVAL_MS, self.start)
        self.root.after(100, self.poll)

    def show_alert(self, result):
        if self.alert and self.alert.winfo_exists():
            self.alert.destroy()
        try:
            import winsound
            winsound.PlaySound('SystemExclamation', winsound.SND_ALIAS | winsound.SND_ASYNC)
        except (ImportError, RuntimeError):
            self.root.bell()
        self.alert = tk.Toplevel(self.root)
        self.alert.title('入荷通知：ガンダムヴァサーゴ')
        self.alert.attributes('-topmost', True)
        frame = ttk.Frame(self.alert, padding=24)
        frame.pack()
        ttk.Label(frame, text='条件に合う入荷を確認しました', font=('Yu Gothic UI', 16, 'bold')).pack()
        ttk.Label(frame, text=f"送料込み {result['total']:,}円\n販売元：{result['seller']}\n購入前にAmazonで最終条件を確認してください。", wraplength=480).pack(pady=16)
        ttk.Button(frame, text='Amazonで確認', command=lambda: webbrowser.open(URL)).pack()
        ttk.Button(frame, text='閉じる', command=self.alert.destroy).pack(pady=(12, 0))

    def close(self):
        self.closed = True
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke', action='store_true', help='UIのオフライン検証。通知なし')
    args = parser.parse_args()
    # Prevent duplicate windows and competing notification state writes.
    lock = socket.socket()
    try:
        lock.bind(('127.0.0.1', 49173))
    except OSError:
        print('在庫モニターは既に起動しています（または専用ポートが使用中です）。')
        return
    root = tk.Tk()
    if args.smoke:
        app = App(root, fetch=lambda: dict(status='判定不能', detail='UI検証', eligible=False), persist=False)
        root.after(600, app.close)
    else:
        App(root)
    root.mainloop()
    lock.close()


if __name__ == '__main__':
    main()
